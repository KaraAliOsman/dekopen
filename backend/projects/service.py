"""Tenant-scoped project inputs; technical outputs belong exclusively to engine."""

from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import re
from uuid import uuid4

from django.db import connection
from psycopg import sql

from authentication.errors import contract_error
from dekopen_engine.documentary_canonical import same_documentary_value
from dekopen_engine.models import EngineResult
from dekopen_engine.snapshot import calculation_response, calculation_hash, result_payload
from documents.repository import documentary_backend
from engine_api.adapter import (
    calculate_from_api,
    evaluate_assembly_from_api,
    elevation_envelope,
    parse_product_model,
    UnsupportedEngineContract,
)
from engine_api.repository import SystemParamsRepository, SystemNotFound, UnsupportedCatalogContract
from pricing.repository import audit_reason, commercial_backend, json_text, one, rows
from pricing.service import decoded
from projects.clients import linkable_client
from projects.measurement import (
    measurement_fields_for_save,
    resolve_position_measurement,
)
from projects.serializers import PositionWriteSerializer
from projects.typology import derive_typology

METADATA = (
    "name",
    "client_name",
    "client_rut",
    "client_email",
    "client_phone",
    "client_giro",
    "client_comuna",
    "client_address",
    "delivery_address",
    "notes_commercial",
    "notes_internal",
)
PROJECT_COLUMNS = (
    "id",
    "code",
    *METADATA,
    "status",
    "current_revision",
    "total_price_net",
    "total_price_tax",
    "total_price_gross",
    "client_id",
    # P18 — declaraciones térmicas del proyecto (OGUC 4.1.10).
    "thermal_zone",
    "thermal_use",
    "thermal_wall_areas",
    "updated_at",
)
POSITION_COLUMNS = (
    "id",
    "project_id",
    "org_id",
    "position_index",
    "location_tag",
    "quantity",
    "typology",
    "system_id",
    "width_mm",
    "height_mm",
    "color_interior",
    "color_exterior",
    "parametric_tree",
    "bom_snapshot",
    # cost_net is a commercial authority column — the shot-08 column grant
    # excludes it from every member read; sale price stays readable.
    "price_net",
    "discount_pct",
    "rough_opening_input",
    "mounting_rule_id",
    "fabrication_lock",
    "measurement_state",
    "measurement_confirmed_at",
    "measurement_confirmed_by",
    # P18 — orientación del paramento donde se instala (N/OP/S/OGT/ROOF).
    "thermal_orientation",
    "updated_at",
)


def missing():
    raise contract_error(404, "project_not_found", "El proyecto o vano no está disponible.")


def project_row(org_id, project_id, *, lock=False):
    values = rows(
        f"SELECT {','.join(PROJECT_COLUMNS)} FROM public.projects "
        "WHERE id=%s AND org_id=%s" + (" FOR UPDATE" if lock else ""),
        [project_id, org_id],
    )
    if not values:
        missing()
    return values[0]


def _pricing_authority(org_id, project_id, revision):
    with commercial_backend():
        values = rows(
            "SELECT id, request->>'currency' AS currency FROM public.pricing_operations "
            "WHERE org_id=%s AND project_id=%s "
            "AND state='APPLIED' AND COALESCE(revision_code,'REV-A')=%s "
            "AND ((SELECT pricing_reset_at FROM public.projects WHERE id=%s) IS NULL "
            "OR approved_at > (SELECT pricing_reset_at FROM public.projects WHERE id=%s)) "
            "ORDER BY approved_at DESC,id DESC LIMIT 1",
            [org_id, project_id, revision, project_id, project_id],
        )
    return values[0] if values else None


def _priced(org_id, project_id, revision):
    return _pricing_authority(org_id, project_id, revision) is not None


def editable(org_id, project_id):
    project = project_row(org_id, project_id, lock=True)
    sealed = rows(
        "SELECT id FROM public.project_versions WHERE org_id=%s AND project_id=%s "
        "AND revision_code=%s",
        [org_id, project_id, project["current_revision"]],
    )
    if project["status"] != "DRAFT" or sealed:
        raise contract_error(409, "revision_required", "Esta revisión está cerrada para edición.")
    if _priced(org_id, project_id, project["current_revision"]):
        raise contract_error(
            409,
            "commercial_revision_required",
            "El proyecto tiene precios aplicados y requiere una revisión.",
        )
    return project


def editable_measurement_target(org_id, project_id):
    """D07 measurement confirmation runs on an open draft revision — same
    DRAFT + unsealed gate as `editable`, but the applied-pricing check is
    absent: confirming a measure never changes the priced content, so a
    priced draft can still be confirmed before emission."""
    project = project_row(org_id, project_id, lock=True)
    sealed = rows(
        "SELECT id FROM public.project_versions WHERE org_id=%s AND project_id=%s "
        "AND revision_code=%s",
        [org_id, project_id, project["current_revision"]],
    )
    if project["status"] != "DRAFT" or sealed:
        raise contract_error(409, "revision_required", "Esta revisión está cerrada para edición.")
    return project


def unchanged(row, expected):
    if row["updated_at"] != expected:
        raise contract_error(
            409, "stale_edit", "Otra persona guardó cambios. Recarga antes de reemplazarlos."
        )


def _canonical_design(design):
    """D05 canonical request preimage: ``color_exterior`` rides the design
    only when it differs from ``color`` — an explicit duplicate would hash
    differently from the stored legacy contract for the same design."""
    design = dict(design)
    exterior = design.get("color_exterior")
    if exterior is None or str(exterior) == str(design.get("color")):
        design.pop("color_exterior", None)
    return design


def position_public(row):
    design = {
        "system_id": row["system_id"],
        "nominal_width_mm": str(row["width_mm"]),
        "nominal_height_mm": str(row["height_mm"]),
        "color": row["color_interior"],
        "parametric_tree": decoded(row["parametric_tree"]),
    }
    if str(row["color_exterior"]) != str(row["color_interior"]):
        design["color_exterior"] = row["color_exterior"]
    stored = decoded(row["bom_snapshot"])
    try:
        payload = {key: value for key, value in stored.items() if key != "calculation_hash"}
        result = EngineResult.model_validate_json(json_text(payload))
        # Re-validation of a pre-upgrade BOM must hash the persisted field
        # presence: optional fields the model gained later stay absent.
        safe = result_payload(result, exclude_unset=True)
        expected = calculation_hash({**design, "system_id": str(design["system_id"])}, safe)
        # SHOT-08 stored EngineResult before calculation_hash was part of this
        # persistence boundary. Preserve that exact result; do not recalculate.
        if "calculation_hash" in stored and stored["calculation_hash"] != expected:
            raise ValueError("Stored calculation identity mismatch")
    except (KeyError, TypeError, ValueError) as error:
        raise contract_error(
            409,
            "stored_calculation_invalid",
            "El cálculo guardado requiere revisión antes de continuar.",
        ) from error
    return {
        **{
            key: row[key]
            for key in (
                "id",
                "project_id",
                "position_index",
                "location_tag",
                "quantity",
                "typology",
                "updated_at",
            )
        },
        "measurement": resolve_position_measurement(row.get("org_id"), row),
        # Posiciones almacenadas antes de la columna térmica se decodifican
        # sin orientación — el panel las reporta con causa, nunca inventadas.
        "thermal_orientation": row.get("thermal_orientation"),
        # The pricing authority writes these on apply — the workspace shows
        # each vano's live net alongside its total, no re-derivation. The
        # cost side stays inside pricing operations (member-denied column).
        "price_net": str(row["price_net"]),
        "discount_pct": str(row["discount_pct"]),
        "design": design,
        "bom": {**safe, "calculation_hash": expected},
    }


def positions(org_id, project_id):
    return [
        position_public(row)
        for row in rows(
            f"SELECT {','.join(POSITION_COLUMNS)} FROM public.project_positions "
            "WHERE org_id=%s AND project_id=%s ORDER BY position_index",
            [org_id, project_id],
        )
    ]


def project_versions(org_id, project_id):
    # snapshot_json is role-denied (rbac_repair): the sealed money fields must
    # be read through the documentary backend, like _latest_version does.
    with documentary_backend():
        return rows(
            "SELECT id,revision_code,authority_version,bom_hash,snapshot_sha256,"
            "production_allowed,documentary_complete,emitted_at,"
            # Sealed money lets a successor revision's pricing decision compare
            # against what the customer was actually quoted (live totals are
            # zeroed by start_successor, so the snapshot is the only baseline).
            "snapshot_json->>'total_price_net' AS sealed_price_net,"
            "snapshot_json->>'total_price_tax' AS sealed_price_tax,"
            "snapshot_json->>'total_price_gross' AS sealed_price_gross,"
            "snapshot_json->>'currency' AS sealed_currency "
            "FROM public.project_versions WHERE project_id=%s AND org_id=%s "
            "ORDER BY emitted_at,id",
            [project_id, org_id],
        )


_UNSET = object()


def project_public(org_id, row, *, detail=False, authority=_UNSET,
                   position_count=_UNSET):
    if authority is _UNSET:
        authority = _pricing_authority(org_id, row["id"], row["current_revision"])
    value = {
        **row,
        "pricing_current": authority is not None,
        "current_pricing_operation_id": authority["id"] if authority else None,
        # The applied operation's currency — a priced project's money needs it
        # to render honestly; unpriced rows keep the org-default CLP fallback.
        "currency": (authority or {}).get("currency") or "CLP",
    }
    value.pop("pricing_reset_at", None)  # internal gate timestamp, not API state
    value["thermal_wall_areas"] = decoded(value["thermal_wall_areas"])
    for key in METADATA:
        value[key] = value[key] or ""
    for key in ("total_price_net", "total_price_tax", "total_price_gross"):
        value[key] = str(value[key])
    if position_count is _UNSET:
        position_count = rows(
            "SELECT count(id) AS count FROM public.project_positions WHERE project_id=%s AND org_id=%s",
            [row["id"], org_id],
        )[0]["count"]
    value["position_count"] = position_count
    if detail:
        value["positions"] = positions(org_id, row["id"])
        value["versions"] = project_versions(org_id, row["id"])
    return value


def _bulk_pricing_authorities(org_id, project_ids):
    """Latest APPLIED op per (project, revision) in ONE query — the list
    endpoint resolves authority per row in Python instead of N×3 queries."""
    if not project_ids:
        return {}
    with commercial_backend():
        result = rows(
            "SELECT DISTINCT ON (project_id, COALESCE(revision_code,'REV-A')) "
            "project_id, COALESCE(revision_code,'REV-A') AS revision, id, "
            "request->>'currency' AS currency, approved_at "
            "FROM public.pricing_operations "
            "WHERE org_id=%s AND project_id = ANY(%s) AND state='APPLIED' "
            "ORDER BY project_id, COALESCE(revision_code,'REV-A'), "
            "approved_at DESC, id DESC",
            [org_id, project_ids],
        )
    return result


def list_projects(org_id):
    project_rows = rows(
        f"SELECT {','.join(PROJECT_COLUMNS)}, pricing_reset_at "
        "FROM public.projects WHERE org_id=%s ORDER BY updated_at DESC,id "
        "LIMIT 500",
        [org_id],
    )
    if not project_rows:
        return []
    project_ids = [row["id"] for row in project_rows]
    counts = {
        item["project_id"]: item["count"]
        for item in rows(
            "SELECT project_id, count(id) AS count "
            "FROM public.project_positions "
            "WHERE org_id=%s AND project_id = ANY(%s) GROUP BY project_id",
            [org_id, project_ids],
        )
    }
    authorities = {}
    rows_by_id = {row["id"]: row for row in project_rows}
    for candidate in _bulk_pricing_authorities(org_id, project_ids):
        row = rows_by_id[candidate["project_id"]]
        reset_at = row.get("pricing_reset_at")
        if candidate["revision"] != row["current_revision"]:
            continue
        # Mirrors the scalar predicate: a NULL approved_at under a set
        # pricing_reset_at excludes the op exactly like SQL NULL comparison.
        if reset_at is not None and not (
            candidate["approved_at"] is not None
            and candidate["approved_at"] > reset_at
        ):
            continue
        authorities[candidate["project_id"]] = candidate
    return [
        project_public(
            org_id, row,
            authority=authorities.get(row["id"]),
            position_count=counts.get(row["id"], 0),
        )
        for row in project_rows
    ]


def _next_project_code():
    """Sequential human code — opaque (a shared sequence leaks no row count)
    and race-free under the (org_id, code) unique index."""
    value = rows("SELECT nextval('public.project_code_seq') AS seq")[0]["seq"]
    return f"P-{int(value):06d}"


def create_project(org_id, actor_id, data):
    identity = uuid4()
    # The code is an opaque human-readable reference, never an internal DB ID input.
    code = _next_project_code()
    values = {key: data.get(key, "") for key in METADATA}
    client_id = data.get("client_id")
    if client_id:
        linkable_client(org_id, client_id)
    rows(
        "INSERT INTO public.projects(id,org_id,code,created_by," + ",".join(METADATA) + ",client_id) "
        "VALUES(" + ",".join(["%s"] * (5 + len(METADATA))) + ") RETURNING id",
        [identity, org_id, code, actor_id, *values.values(), client_id],
    )
    # D06: the org's service templates seed the new project's selections —
    # a preselection the estimator edits, never a hidden charge.
    rows(
        "INSERT INTO public.project_service_selections"
        " (project_id, org_id, service_article_id)"
        " SELECT %s, %s, t.service_article_id"
        " FROM public.org_service_templates t"
        " JOIN public.service_articles a ON a.id = t.service_article_id"
        " WHERE t.org_id = %s AND a.is_active"
        " ON CONFLICT DO NOTHING RETURNING id",
        [identity, org_id, org_id],
    )
    return project_public(org_id, project_row(org_id, identity), detail=True)


def update_project(org_id, project_id, data):
    current = editable(org_id, project_id)
    unchanged(current, data["expected_updated_at"])
    values = {key: data[key] for key in METADATA if key in data}
    for key in ("thermal_zone", "thermal_use"):
        if key in data:
            values[key] = data[key]
    if "thermal_wall_areas" in data:
        # JSONB — el placeholder genérico no castea; Jsonb() adapta el dict.
        from psycopg.types.json import Jsonb

        values["thermal_wall_areas"] = (
            Jsonb(data["thermal_wall_areas"])
            if data["thermal_wall_areas"] is not None
            else None
        )
    if "client_id" in data:
        if data["client_id"]:
            linkable_client(org_id, data["client_id"])
        values["client_id"] = data["client_id"] or None
    if not values:
        return project_public(org_id, current, detail=True)
    query = sql.SQL(
        "UPDATE public.projects SET {},updated_at=clock_timestamp() "
        "WHERE id=%s AND org_id=%s RETURNING id"
    ).format(
        sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(key)) for key in values),
    )
    rows(query, [*values.values(), project_id, org_id])
    return project_public(org_id, project_row(org_id, project_id), detail=True)


def position_row(org_id, position_id, *, lock=False):
    result = rows(
        f"SELECT {','.join(POSITION_COLUMNS)} FROM public.project_positions "
        "WHERE id=%s AND org_id=%s" + (" FOR UPDATE" if lock else ""),
        [position_id, org_id],
    )
    if not result:
        missing()
    return result[0]


def calculate_design(org_id, design):
    design = _canonical_design(design)
    try:
        repository = SystemParamsRepository()
        params = repository.load_visible(design["system_id"], org_id)
        tree = design["parametric_tree"]
        if isinstance(tree, dict) and tree.get("version") == "product-v2":
            model = parse_product_model(tree)
            evaluation = evaluate_assembly_from_api(
                product=model,
                color=design["color"],
                color_exterior=design.get("color_exterior"),
                params=params,
                coupler_articles=repository.load_coupler_articles(
                    design["system_id"], org_id
                ),
            )
            if (
                evaluation.status.value == "INVALID"
                or evaluation.bom is None
                or any(
                    module_eval.result is None
                    for module_eval in evaluation.modules
                )
            ):
                # An INVALID evaluation or a partial BOM can never persist:
                # the sealed evidence would read a broken assembly back as
                # authoritative. A module whose evaluation produced no result
                # (geometry failed) is absent from the aggregated BOM — that
                # is a partial BOM too. Draft persistence only tolerates
                # warnings that leave every module's output whole: unassigned
                # couplers and missing bending authority.
                raise contract_error(
                    400,
                    "manufacturing_incomplete",
                    "El conjunto tiene errores que impiden guardarlo: asigna acopladores y revisa cada módulo.",
                )
            intent_unsupported = {
                "contour_opening_unsupported",
                "contour_panel_unsupported",
                "contour_coupling_unsupported",
            }
            reported_codes = {
                issue.code
                for module_eval in evaluation.modules
                for issue in module_eval.issues
            } | {issue.code for issue in evaluation.issues}
            if reported_codes & intent_unsupported:
                # Draft tolerance covers warnings about authority the workshop
                # lacks (member bending) — never a declared intent the engine
                # cannot build at all. An operable leaf, panel or joint on a
                # contour would otherwise seal a fixed rectangular BOM under
                # the declared shape: the saved product would misdescribe
                # itself.
                raise contract_error(
                    400,
                    "manufacturing_incomplete",
                    "La apertura o el panel declarado no se fabrica aún sobre contornos — cámbialo a fijo o vuelve el módulo rectangular.",
                )
            envelope_width, envelope_height = elevation_envelope(model.assembly)
            if (
                design["nominal_width_mm"] != envelope_width
                or design["nominal_height_mm"] != envelope_height
            ):
                raise contract_error(
                    400,
                    "validation_error",
                    "Request validation failed",
                )
            result = evaluation.bom
        else:
            result = calculate_from_api(
                params=params,
                color_exterior=design.get("color_exterior"),
                **{
                    key: design[key]
                    for key in (
                        "parametric_tree",
                        "nominal_width_mm",
                        "nominal_height_mm",
                        "color",
                    )
                },
            )
    except SystemNotFound as error:
        raise contract_error(
            404, "system_not_found", "La serie no está disponible para este taller."
        ) from error
    except (UnsupportedEngineContract, UnsupportedCatalogContract) as error:
        raise contract_error(
            422,
            "technical_authority_required",
            "Revisa las compatibilidades del catálogo de esta serie.",
        ) from error
    except ValueError as error:
        raise contract_error(
            400,
            "validation_error",
            "El diseño no es válido. Revisa medidas, divisiones y aperturas.",
        ) from error
    return calculation_response({**design, "system_id": str(design["system_id"])}, result)


def _typology(tree):
    try:
        return derive_typology(tree)
    except ValueError as error:
        raise contract_error(
            422,
            "typology_derivation_failed",
            "La apertura o división no permite determinar la tipología comercial.",
        ) from error


def _glass_resolution(bom):
    """D02 structured-glass bookkeeping for ``project_positions``: a
    ``bay:leaf`` → composition map plus the review flag — set when a bay
    declares a spec the parser could not structure (UNKNOWN never seals as
    resolved)."""
    compositions = {}
    pending = False
    for piece in bom.get("glasses") or []:
        key = f"{piece.get('bay_id') or ''}:{piece.get('leaf_id') or ''}"
        composition = piece.get("composition")
        if composition is None:
            compositions[key] = {
                "status": "UNKNOWN",
                "spec": piece.get("glass_spec"),
            }
            if piece.get("glass_spec"):
                pending = True
        else:
            compositions[key] = composition
    return compositions, pending


def save_position(org_id, project_id, data, *, position_id=None):
    editable(org_id, project_id)
    current = None
    if position_id:
        current = position_row(org_id, position_id, lock=True)
        if current["project_id"] != project_id:
            missing()
        unchanged(current, data["expected_updated_at"])
    design = _canonical_design(data["design"])
    with connection.cursor() as cursor:
        cursor.execute("SELECT private.reserve_catalog_authority(%s,%s)",
                       [design["system_id"], org_id])
    bom = calculate_design(org_id, design)
    glass_composition, glass_pending = _glass_resolution(bom)
    measurement = measurement_fields_for_save(
        org_id, data=data, current=current, system_id=design["system_id"]
    )
    values = [
        data["location_tag"],
        data["quantity"],
        _typology(design["parametric_tree"]),
        design["system_id"],
        design["nominal_width_mm"],
        design["nominal_height_mm"],
        design["color"],
        design.get("color_exterior") or design["color"],
        json_text(design["parametric_tree"]),
        json_text(bom),
        json_text(glass_composition),
        glass_pending,
        (
            None if measurement["rough_opening_input"] is None
            else json_text(measurement["rough_opening_input"])
        ),
        measurement["mounting_rule_id"],
        (
            None if measurement["fabrication_lock"] is None
            else json_text(measurement["fabrication_lock"])
        ),
        measurement["measurement_state"],
        measurement["measurement_confirmed_at"],
        measurement["measurement_confirmed_by"],
        # Un PUT sin la clave conserva la orientación — clientes antiguos
        # (qty en línea, mover) no deben borrarla al guardar otra cosa.
        (
            data["thermal_orientation"]
            if "thermal_orientation" in data
            else (current["thermal_orientation"] if current else None)
        ),
    ]
    if current:
        rows(
            "UPDATE public.project_positions SET location_tag=%s,quantity=%s,typology=%s,"
            "system_id=%s,width_mm=%s,height_mm=%s,color_interior=%s,color_exterior=%s,"
            "parametric_tree=%s::jsonb,bom_snapshot=%s::jsonb,"
            "glass_composition=%s::jsonb,glass_review_pending=%s,"
            "rough_opening_input=%s::jsonb,mounting_rule_id=%s,fabrication_lock=%s::jsonb,"
            "measurement_state=%s,measurement_confirmed_at=%s,measurement_confirmed_by=%s,"
            "thermal_orientation=%s,updated_at=clock_timestamp() "
            "WHERE id=%s AND org_id=%s RETURNING id",
            [*values, position_id, org_id],
        )
    else:
        index = rows(
            "SELECT COALESCE(MAX(position_index),0)+1 AS next_index "
            "FROM public.project_positions WHERE project_id=%s AND org_id=%s",
            [project_id, org_id],
        )[0]["next_index"]
        position_id = uuid4()
        rows(
            "INSERT INTO public.project_positions(location_tag,quantity,typology,system_id,"
            "width_mm,height_mm,color_interior,color_exterior,parametric_tree,bom_snapshot,"
            "glass_composition,glass_review_pending,"
            "rough_opening_input,mounting_rule_id,fabrication_lock,"
            "measurement_state,measurement_confirmed_at,measurement_confirmed_by,"
            "thermal_orientation,"
            "id,project_id,org_id,position_index) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,"
            "%s::jsonb,%s,%s::jsonb,"
            "%s,%s,%s,"
            "%s,%s,%s,%s,%s) RETURNING id",
            [*values, position_id, project_id, org_id, index],
        )
    rows(
        "UPDATE public.projects SET updated_at=clock_timestamp() WHERE id=%s AND org_id=%s "
        "RETURNING id",
        [project_id, org_id],
    )
    return position_public(position_row(org_id, position_id))


def delete_position(org_id, position_id, expected):
    original = position_row(org_id, position_id)
    editable(org_id, original["project_id"])
    current = position_row(org_id, position_id, lock=True)
    unchanged(current, expected)
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM public.project_positions WHERE id=%s AND org_id=%s", [position_id, org_id]
        )
        cursor.execute(
            "UPDATE public.projects SET updated_at=clock_timestamp() WHERE id=%s AND org_id=%s",
            [original["project_id"], org_id],
        )


def move_position(org_id, position_id, to_index, expected):
    """Move a position inside its project's print order.

    The (project_id, position_index) unique constraint makes an in-place
    swap impossible, so every sibling first parks at a negative scratch
    index and the final 1..N run is assigned in a second pass — all under
    the same row locks the concurrent save path takes.
    """
    original = position_row(org_id, position_id)
    editable(org_id, original["project_id"])
    current = position_row(org_id, position_id, lock=True)
    unchanged(current, expected)
    project_id = original["project_id"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM public.project_positions "
            "WHERE project_id=%s AND org_id=%s ORDER BY position_index FOR UPDATE",
            [project_id, org_id],
        )
        order = [str(row[0]) for row in cursor.fetchall()]
        order.remove(str(position_id))
        target = max(0, min(int(to_index) - 1, len(order)))
        order.insert(target, str(position_id))
        for scratch, row_id in enumerate(order, start=1):
            cursor.execute(
                "UPDATE public.project_positions SET position_index=%s "
                "WHERE id=%s AND org_id=%s",
                [-scratch, row_id, org_id],
            )
        for index, row_id in enumerate(order, start=1):
            # Only the moved row takes a fresh updated_at — bumping the
            # siblings' timestamp would wrongly invalidate a parallel
            # design edit holding their optimistic lock.
            stamp = ",updated_at=clock_timestamp()" if row_id == str(position_id) else ""
            cursor.execute(
                "UPDATE public.project_positions SET position_index=%s"
                + stamp
                + " WHERE id=%s AND org_id=%s",
                [index, row_id, org_id],
            )
        cursor.execute(
            "UPDATE public.projects SET updated_at=clock_timestamp() WHERE id=%s AND org_id=%s",
            [project_id, org_id],
        )
    return position_public(position_row(org_id, position_id))


def _same_documentary_value(left, right):
    # Scale-free compare: the canonical BOM serializes mm as "16.00" while
    # the frozen snapshot's raw model_dump keeps "16" — the same
    # measurement must not read as binding drift (shared with
    # documents.service's freeze-time check).
    return same_documentary_value(left, right)


def next_revision_code(value):
    match = re.fullmatch(r"REV-([A-Z]+)", value)
    if match is None:
        raise contract_error(409, "revision_sequence_invalid", "La secuencia de revisiones no es válida.")
    number = 0
    for character in match.group(1):
        number = number * 26 + ord(character) - ord("A") + 1
    number += 1
    suffix = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        suffix = chr(ord("A") + remainder) + suffix
    return f"REV-{suffix}"


def _latest_version(org_id, project_id):
    with documentary_backend():
        values = rows(
            "SELECT id,revision_code,authority_version,snapshot_json::text AS snapshot_json,"
            "bom_hash,snapshot_sha256,emitted_at FROM public.project_versions "
            "WHERE project_id=%s AND org_id=%s ORDER BY emitted_at DESC,id DESC LIMIT 1",
            [project_id, org_id],
        )
    return values[0] if values else None


def _assert_live_matches_version(org_id, project_id, version):
    snapshot = decoded(version["snapshot_json"])
    if not isinstance(snapshot, dict):
        raise contract_error(409, "revision_source_drift", "La revisión emitida no coincide con el proyecto.")
    with commercial_backend():
        live_project = rows(
            "SELECT * FROM public.projects WHERE id=%s AND org_id=%s",
            [project_id, org_id],
        )[0]
        live_positions = rows(
            "SELECT * FROM public.project_positions WHERE project_id=%s AND org_id=%s "
            "ORDER BY position_index",
            [project_id, org_id],
        )
    frozen_project = snapshot.get("project")
    frozen_positions = snapshot.get("positions")
    frozen_bom = snapshot.get("bom")
    pricing = snapshot.get("pricing")
    if not all(
        isinstance(value, (dict, list))
        for value in (frozen_project, frozen_positions, frozen_bom, pricing)
    ):
        raise contract_error(409, "revision_source_drift", "La revisión emitida no coincide con el proyecto.")
    project_fields = (
        "code",
        "name",
        "client_name",
        "client_rut",
        "client_email",
        "client_phone",
        "client_giro",
        "client_comuna",
        "client_address",
        "delivery_address",
        "notes_commercial",
        "total_price_net",
        "total_price_tax",
        "total_price_gross",
    )
    if not _same_documentary_value(
        {key: live_project[key] for key in project_fields},
        {key: frozen_project.get(key) for key in project_fields},
    ):
        raise contract_error(409, "revision_source_drift", "La revisión emitida no coincide con el proyecto.")
    frozen_by_id = {
        str(item.get("id")): item for item in frozen_positions if isinstance(item, dict)
    }
    bom_by_id = {
        str(item.get("position_id")): item.get("engine_result")
        for item in frozen_bom
        if isinstance(item, dict)
    }
    pricing_snapshot = pricing.get("input_snapshot")
    pricing_result = pricing.get("result")
    pricing_request = pricing.get("request")
    if not all(isinstance(value, dict) for value in (pricing_snapshot, pricing_result, pricing_request)):
        raise contract_error(409, "revision_source_drift", "La revisión emitida no coincide con el proyecto.")
    try:
        costs = {
            int(index): Decimal(str(amount)) for index, amount in pricing_snapshot["cost_lines"]
        }
        prices = {int(index): Decimal(str(amount)) for index, amount in pricing_result["lines"]}
        discount = Decimal(str(pricing_request["discount_pct"]))
    except (KeyError, TypeError, ValueError) as error:
        raise contract_error(
            409, "revision_source_drift", "La revisión emitida no coincide con el proyecto."
        ) from error
    indexes = {int(item["position_index"]) for item in live_positions}
    if (
        set(frozen_by_id) != {str(item["id"]) for item in live_positions}
        or set(costs) != indexes
        or set(prices) != indexes
    ):
        raise contract_error(409, "revision_source_drift", "La revisión emitida no coincide con el proyecto.")
    for position in live_positions:
        identity = str(position["id"])
        frozen = frozen_by_id[identity]
        live_input = {
            "id": identity,
            "position_index": position["position_index"],
            "quantity": position["quantity"],
            "typology": position["typology"],
            "system_id": position["system_id"],
            "width_mm": position["width_mm"],
            "height_mm": position["height_mm"],
            "color_interior": position["color_interior"],
            "color_exterior": position["color_exterior"],
            "location_tag": position["location_tag"] or "",
            "parametric_tree": decoded(position["parametric_tree"]),
        }
        frozen_input = {key: frozen.get(key) for key in live_input}
        stored_bom = decoded(position["bom_snapshot"])
        if isinstance(stored_bom, dict):
            stored_bom = {key: value for key, value in stored_bom.items() if key != "calculation_hash"}
        index = int(position["position_index"])
        if (
            not _same_documentary_value(live_input, frozen_input)
            or not _same_documentary_value(stored_bom, bom_by_id.get(identity))
            or Decimal(str(position["cost_net"]))
            != costs[index].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            or Decimal(str(position["price_net"]))
            != prices[index].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            or Decimal(str(position["discount_pct"])) != discount
        ):
            raise contract_error(
                409, "revision_source_drift", "La revisión emitida no coincide con el proyecto."
            )
    if Decimal(str(live_project["total_cost_net"])) != Decimal(
        str(pricing.get("applied_total_cost_net"))
    ):
        raise contract_error(409, "revision_source_drift", "La revisión emitida no coincide con el proyecto.")


def clone_project(org_id, actor_id, project_id, data):
    source = project_row(org_id, project_id, lock=True)
    unchanged(source, data["expected_updated_at"])
    latest = _latest_version(org_id, project_id)
    if source["status"] == "QUOTED":
        if latest is None or latest["revision_code"] != source["current_revision"]:
            raise contract_error(409, "revision_source_drift", "La revisión emitida no coincide con el proyecto.")
        _assert_live_matches_version(org_id, project_id, latest)
    source_positions = positions(org_id, project_id)
    metadata = {key: source[key] or "" for key in METADATA}
    metadata["name"] = data.get("name", "Copia de " + source["name"][:246])
    copied = create_project(org_id, actor_id, metadata)
    for position in source_positions:
        serializer = PositionWriteSerializer(
            data={
                "location_tag": position["location_tag"] or "",
                "quantity": position["quantity"],
                "design": deepcopy(position["design"]),
            }
        )
        serializer.is_valid(raise_exception=True)
        save_position(org_id, copied["id"], serializer.validated_data)
    return project_public(org_id, project_row(org_id, copied["id"]), detail=True)


def clone_draft(org_id, actor_id, project_id, data):
    return clone_project(org_id, actor_id, project_id, data)


def reset_draft_pricing(org_id, project_id, expected_operation_id, reason):
    project = project_row(org_id, project_id, lock=True)
    if project["status"] != "DRAFT" or rows(
        "SELECT id FROM public.project_versions WHERE project_id=%s AND org_id=%s AND revision_code=%s",
        [project_id, org_id, project["current_revision"]],
    ):
        raise contract_error(409, "revision_required", "Esta revisión ya fue emitida.")
    current = _pricing_authority(org_id, project_id, project["current_revision"])
    if current is None or str(current["id"]) != str(expected_operation_id):
        raise contract_error(409, "stale_pricing_operation", "Recarga los precios del proyecto.")
    if not reason.strip():
        raise contract_error(400, "audit_reason_required", "Indica el motivo para revisar precios.")
    audit_reason(reason)
    with commercial_backend():
        rows("UPDATE public.project_positions SET cost_net=0,price_net=0,discount_pct=0,"
             "updated_at=clock_timestamp() WHERE project_id=%s AND org_id=%s RETURNING id",
             [project_id, org_id])
        rows("UPDATE public.projects SET pricing_reset_at=clock_timestamp(),total_cost_net=0,"
             "total_price_net=0,total_price_tax=0,total_price_gross=0,updated_at=clock_timestamp() "
             "WHERE id=%s AND org_id=%s RETURNING id", [project_id, org_id])
    return project_public(org_id, project_row(org_id, project_id), detail=True)


def start_successor(org_id, project_id, expected_current_revision=None):
    project = project_row(org_id, project_id, lock=True)
    latest = _latest_version(org_id, project_id)
    if latest is None:
        raise contract_error(409, "successor_requires_emission", "Emite la cotización antes de revisarla.")
    expected = expected_current_revision or latest["revision_code"]
    successor = next_revision_code(expected)
    if project["status"] == "DRAFT" and project["current_revision"] == successor and latest["revision_code"] == expected:
        return {
            **project_public(org_id, project_row(org_id, project_id), detail=True),
            "successor_created": False,
        }
    # QUOTED and APPROVED are both revisable — the client portal can flip a
    # quote to APPROVED and the client may still request changes; the sealed
    # revision stays immutable and the successor simply needs a fresh
    # approval (review WM7). But once live workshop orders exist the product
    # is on the factory floor — revising it would silently change what is
    # being built, so production in flight blocks the successor.
    if project["status"] not in ("QUOTED", "APPROVED") or project["current_revision"] != expected:
        raise contract_error(409, "successor_source_stale", "La revisión actual del proyecto no coincide con la esperada.")
    if project["status"] == "APPROVED":
        live_orders = one(
            """
            SELECT COUNT(*)::int AS live FROM public.orders
            WHERE project_id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
              AND status NOT IN ('COMPLETED', 'DISPATCHED', 'INSTALLED', 'CANCELLED', 'FULFILLED')
            """,
            [project_id, org_id],
            "order_lookup_failed",
        )
        if live_orders["live"] > 0:
            raise contract_error(409, "successor_in_production", "El proyecto tiene órdenes de producción en curso; no se puede revisar.")
    if latest["revision_code"] != project["current_revision"]:
        raise contract_error(409, "revision_source_drift", "La revisión emitida no coincide con el proyecto.")
    _assert_live_matches_version(org_id, project_id, latest)
    if project_versions(org_id, project_id)[-1]["revision_code"] != latest["revision_code"]:
        raise contract_error(409, "revision_sequence_invalid", "La secuencia de revisiones no es válida.")
    audit_reason(f"Open {successor}; invalidate {latest['revision_code']} live commercial authority")
    with commercial_backend():
        updated_positions = rows(
            "UPDATE public.project_positions SET cost_net=0.00,price_net=0.00,discount_pct=0.0000,"
            "updated_at=clock_timestamp() WHERE project_id=%s AND org_id=%s RETURNING id",
            [project_id, org_id],
        )
        updated_projects = rows(
            "UPDATE public.projects SET status='DRAFT',current_revision=%s,total_cost_net=0.00,"
            "total_price_net=0.00,total_price_tax=0.00,total_price_gross=0.00,"
            "updated_at=clock_timestamp() WHERE id=%s AND org_id=%s RETURNING id",
            [successor, project_id, org_id],
        )
    if not updated_positions or len(updated_projects) != 1:
        raise contract_error(403, "successor_permission_denied", "Tu rol no permite crear revisiones.")
    return {
        **project_public(org_id, project_row(org_id, project_id), detail=True),
        "successor_created": True,
    }
