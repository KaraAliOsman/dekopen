"""D07 — del vano de obra a la medida de fabricación.

Reads the declared measurement evidence on a position (vano record,
mounting rule, manual fabrication pin) and resolves it through the engine
(`dekopen_engine.rough_opening`): the engine owns every derived number —
per-side clearances, the 3-point minimum, the coherence verdict. This
module only fetches the scoped authorities and serializes the result.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db import connection

from authentication.errors import contract_error
from catalogs.mounting import mounting_rule_public, mounting_rule_row
from dekopen_engine.rough_opening import (
    FabricationLock,
    VanoError,
    VanoInput,
    mounting_rule_from_json,
    resolve_fabrication,
    vano_from_json,
)
from pricing.repository import commercial_backend, one
from pricing.service import decoded


def org_spread_tolerance(org_id) -> Decimal:
    value = one(
        "SELECT vano_spread_tolerance_mm FROM public.tenancy_organizations WHERE id=%s",
        [org_id],
    )["vano_spread_tolerance_mm"]
    return Decimal(str(value))


def resolution_public(resolution) -> dict:
    return {
        "vano_width_mm": (
            None if resolution.vano_width_mm is None else str(resolution.vano_width_mm)
        ),
        "vano_height_mm": (
            None if resolution.vano_height_mm is None else str(resolution.vano_height_mm)
        ),
        "width_spread_mm": str(resolution.width_spread_mm),
        "height_spread_mm": str(resolution.height_spread_mm),
        "fabrication_width_mm": str(resolution.fabrication_width_mm),
        "fabrication_height_mm": str(resolution.fabrication_height_mm),
        "fabrication_source": resolution.fabrication_source,
        "used_width_mm": str(resolution.used_width_mm),
        "used_height_mm": str(resolution.used_height_mm),
        "coherent": resolution.coherent,
        "breakdown": [
            {"side": item.side, "label": item.label, "mm": str(item.mm)}
            for item in resolution.breakdown
        ],
        "warnings": [
            {"code": warning.code, "message": warning.message}
            for warning in resolution.warnings
        ],
    }


def _vano_input(value) -> VanoInput | None:
    raw = decoded(value)
    if raw is None:
        return None
    return vano_from_json(raw)


def _fabrication_lock(value) -> FabricationLock | None:
    raw = decoded(value)
    if raw is None:
        return None
    try:
        return FabricationLock(
            width_mm=Decimal(str(raw["width_mm"])),
            height_mm=Decimal(str(raw["height_mm"])),
        )
    except (KeyError, TypeError, VanoError, ArithmeticError) as error:
        raise contract_error(
            400, "invalid_fabrication_lock", "La fijación de fabricación no es válida."
        ) from error


def _engine_rule(rule_row: dict | None):
    if rule_row is None:
        return None
    try:
        return mounting_rule_from_json(decoded(rule_row["authority"]), code_hint=rule_row["code"])
    except VanoError as error:
        raise contract_error(
            400, "invalid_mounting_rule", "La regla de montaje guardada no es válida."
        ) from error


def resolve_position_measurement(org_id, row: dict) -> dict:
    """The measurement block the API returns for one position: the declared
    record plus the engine resolution against the position's own dims.
    Rows built without the measurement columns (old snapshots, in-memory
    fixtures) read as an empty CLIENT_DECLARED record."""
    vano_raw = decoded(row.get("rough_opening_input"))
    lock_raw = decoded(row.get("fabrication_lock"))
    mounting_rule_id = row.get("mounting_rule_id")
    rule_row = None
    if mounting_rule_id is not None:
        rule_row = mounting_rule_row(org_id, mounting_rule_id, row["system_id"])
    resolution = None
    if vano_raw is not None or lock_raw is not None:
        rule = _engine_rule(rule_row)
        vano = _vano_input(vano_raw)
        if vano is not None and rule is None:
            # Measured opening without a rule cannot resolve; the record stays
            # readable and the surface shows the missing rule instead of 500.
            resolution = None
        else:
            try:
                resolution = resolution_public(
                    resolve_fabrication(
                        vano=vano,
                        rule=rule,
                        lock=_fabrication_lock(lock_raw),
                        position_width_mm=Decimal(str(row["width_mm"])),
                        position_height_mm=Decimal(str(row["height_mm"])),
                        spread_tolerance_mm=org_spread_tolerance(org_id),
                    )
                )
            except VanoError as error:
                raise contract_error(
                    409, "measurement_record_invalid",
                    "El registro del vano no es válido; regraba la medición."
                ) from error
    confirmed_by = row.get("measurement_confirmed_by")
    return {
        "state": row.get("measurement_state") or "CLIENT_DECLARED",
        "confirmed_at": row.get("measurement_confirmed_at"),
        "confirmed_by": None if confirmed_by is None else str(confirmed_by),
        "vano": vano_raw,
        "mounting_rule": None if rule_row is None else mounting_rule_public(rule_row),
        "fabrication_lock": lock_raw,
        "resolution": resolution,
    }


def resolve_measurement_preview(
    org_id,
    *,
    system_id: UUID,
    vano_payload: dict | None,
    mounting_rule_id: UUID | None,
    lock_payload: dict | None,
    position_width_mm: Decimal,
    position_height_mm: Decimal,
) -> dict:
    """Live preview for the editor — nothing persisted."""
    rule_row = None
    if mounting_rule_id is not None:
        rule_row = mounting_rule_row(org_id, mounting_rule_id, system_id)
    elif vano_payload is not None:
        raise contract_error(
            400, "mounting_rule_required", "El vano medido requiere una regla de montaje."
        )
    try:
        resolution = resolve_fabrication(
            vano=None if vano_payload is None else vano_from_json(vano_payload),
            rule=_engine_rule(rule_row),
            lock=(
                None if lock_payload is None else FabricationLock(
                    width_mm=Decimal(str(lock_payload["width_mm"])),
                    height_mm=Decimal(str(lock_payload["height_mm"])),
                )
            ),
            position_width_mm=position_width_mm,
            position_height_mm=position_height_mm,
            spread_tolerance_mm=org_spread_tolerance(org_id),
        )
    except VanoError as error:
        raise contract_error(
            400, "measurement_invalid", str(error)
        ) from error
    return {
        "resolution": resolution_public(resolution),
        "mounting_rule": None if rule_row is None else mounting_rule_public(rule_row),
    }


def _vano_record_payload(payload: dict | None) -> dict | None:
    """Serializer-validated vano → canonical stored record: Decimal mm
    become strings so JSONB round-trips byte-for-byte comparable."""
    if payload is None:
        return None
    record = {
        "width_points_mm": [str(value) for value in payload["width_points_mm"]],
        "height_points_mm": [str(value) for value in payload["height_points_mm"]],
    }
    if payload.get("wall_type"):
        record["wall_type"] = payload["wall_type"]
    if payload.get("square_mm") is not None:
        record["square_mm"] = str(payload["square_mm"])
    if payload.get("plumb_mm") is not None:
        record["plumb_mm"] = str(payload["plumb_mm"])
    if payload.get("notes"):
        record["notes"] = payload["notes"]
    return record


def _lock_record_payload(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    record = {
        "width_mm": str(payload["width_mm"]),
        "height_mm": str(payload["height_mm"]),
    }
    if payload.get("reason"):
        record["reason"] = payload["reason"]
    return record


def measurement_fields_for_save(org_id, *, data, current, system_id):
    """Resolve the `measurement` block of a position save into columns.

    Absent `measurement` keeps the stored record — the save may be a pure
    design edit. A present block replaces vano/rule/lock wholesale; the
    state transitions back to SITE_RECTIFIED when the confirmed evidence
    changes, and to CONFIRMED never happens here (explicit action only).
    """
    measurement = data.get("measurement", None)
    if measurement is None:
        if current is None:
            return {
                "rough_opening_input": None,
                "mounting_rule_id": None,
                "fabrication_lock": None,
                "measurement_state": "CLIENT_DECLARED",
                "measurement_confirmed_at": None,
                "measurement_confirmed_by": None,
            }
        # Design edit that kept the measurement payload out: confirm the
        # record still coheres — a dim change resets a stale CONFIRMED.
        if (
            current["measurement_state"] == "CONFIRMED"
            and (
                current["width_mm"] != data["design"]["nominal_width_mm"]
                or current["height_mm"] != data["design"]["nominal_height_mm"]
            )
        ):
            return {
                "rough_opening_input": current["rough_opening_input"],
                "mounting_rule_id": (
                    None if current["mounting_rule_id"] is None
                    else str(current["mounting_rule_id"])
                ),
                "fabrication_lock": current["fabrication_lock"],
                "measurement_state": "SITE_RECTIFIED",
                "measurement_confirmed_at": None,
                "measurement_confirmed_by": None,
            }
        return {
            "rough_opening_input": current["rough_opening_input"],
            "mounting_rule_id": (
                None if current["mounting_rule_id"] is None
                else str(current["mounting_rule_id"])
            ),
            "fabrication_lock": current["fabrication_lock"],
            "measurement_state": current["measurement_state"],
            "measurement_confirmed_at": current["measurement_confirmed_at"],
            "measurement_confirmed_by": current["measurement_confirmed_by"],
        }

    vano_payload = _vano_record_payload(measurement.get("vano"))
    rule_id = measurement.get("mounting_rule_id")
    lock_payload = _lock_record_payload(measurement.get("fabrication_lock"))

    if vano_payload is not None and rule_id is not None:
        # Vano + rule validation happens through the engine preview: the
        # same code path the editor showed the user before saving. A vano
        # without a rule stays recorded evidence — the estimator can pick
        # the mount later; the resolution just doesn't exist yet.
        resolve_measurement_preview(
            org_id,
            system_id=system_id,
            vano_payload=vano_payload,
            mounting_rule_id=rule_id,
            lock_payload=lock_payload,
            position_width_mm=Decimal(str(data["design"]["nominal_width_mm"])),
            position_height_mm=Decimal(str(data["design"]["nominal_height_mm"])),
        )
    elif lock_payload is not None:
        resolve_measurement_preview(
            org_id,
            system_id=system_id,
            vano_payload=None,
            mounting_rule_id=None,
            lock_payload=lock_payload,
            position_width_mm=Decimal(str(data["design"]["nominal_width_mm"])),
            position_height_mm=Decimal(str(data["design"]["nominal_height_mm"])),
        )

    lock = lock_payload

    changed = current is None or (
        decoded(current["rough_opening_input"]) != vano_payload
        or (None if current["mounting_rule_id"] is None else str(current["mounting_rule_id"]))
        != (None if rule_id is None else str(rule_id))
        or decoded(current["fabrication_lock"]) != lock
        or current["width_mm"] != data["design"]["nominal_width_mm"]
        or current["height_mm"] != data["design"]["nominal_height_mm"]
    )
    if current is not None and not changed:
        state = current["measurement_state"]
        confirmed_at = current["measurement_confirmed_at"]
        confirmed_by = current["measurement_confirmed_by"]
    elif current is not None and current["measurement_state"] == "CONFIRMED":
        # The confirmed evidence moved — the measure needs a new explicit
        # confirmation, the stamp never survives a change.
        state = "SITE_RECTIFIED"
        confirmed_at = None
        confirmed_by = None
    else:
        state = "SITE_RECTIFIED" if vano_payload is not None else "CLIENT_DECLARED"
        confirmed_at = None
        confirmed_by = None
    return {
        "rough_opening_input": vano_payload,
        "mounting_rule_id": None if rule_id is None else str(rule_id),
        "fabrication_lock": lock,
        "measurement_state": state,
        "measurement_confirmed_at": confirmed_at,
        "measurement_confirmed_by": confirmed_by,
    }


def confirm_measurement(org_id, project_id, position_id, actor_id, *, confirmed: bool):
    """Explicit human confirmation that the fabrication measure is the
    production truth. Allowed on an open draft revision — including a priced
    one, since confirmation never changes the priced content — but never on
    a sealed revision."""
    from projects.service import editable_measurement_target, position_row

    editable_measurement_target(org_id, project_id)
    current = position_row(org_id, position_id, lock=True)
    if current["project_id"] != project_id:
        raise contract_error(404, "project_not_found", "El proyecto o vano no está disponible.")
    # El sello de medida escribe posición y proyecto incluso en una
    # revisión ya cotizada — confirmar no mueve el contenido cotizado,
    # pero el guard comercial exige el rol de servicio igual que en
    # save_position para proseguir.
    with commercial_backend(), connection.cursor() as cursor:
        if confirmed:
            cursor.execute(
                "UPDATE public.project_positions SET measurement_state=%s,"
                "measurement_confirmed_at=clock_timestamp(),measurement_confirmed_by=%s,"
                "updated_at=clock_timestamp() WHERE id=%s AND org_id=%s",
                ["CONFIRMED", actor_id, position_id, org_id],
            )
        else:
            cursor.execute(
                "UPDATE public.project_positions SET measurement_state=%s,"
                "measurement_confirmed_at=NULL,measurement_confirmed_by=NULL,"
                "updated_at=clock_timestamp() WHERE id=%s AND org_id=%s",
                ["SITE_RECTIFIED", position_id, org_id],
            )
        cursor.execute(
            "UPDATE public.projects SET updated_at=clock_timestamp() WHERE id=%s AND org_id=%s",
            [project_id, org_id],
        )
        return position_row(org_id, position_id)
