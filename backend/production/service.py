"""Production orchestration: release sealed versions to workshop orders.

A work order is an ``orders`` row with ``order_type='WORKSHOP_OT'`` — the
substrate the schema already reserves for the shop floor (free-form status,
org-scoped access). Its ``payload_json`` carries the per-position cut list
straight from the sealed version snapshot, so nothing is re-entered between
the commercial and the workshop departments. Routing lives in
``production_steps``; every transition appends to ``production_step_events``
so the floor has a paperless trail."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from time import perf_counter
import hashlib
import json
from uuid import UUID

from django.db import transaction
import segno

from dekopen_engine.cutting import CutBar, optimize_cut, pieces_from_result
from dekopen_engine.manufacturing import ManufacturingFactsV1
from dekopen_engine.models import EngineResult
from dekopen_engine.nesting import NestPiece, SheetRule, nest_rects
from dekopen_engine.operations import (
    NeutralOpsPostProcessor,
    operations_from_plan,
    ops_document,
)
from documents.repository import (
    DocumentaryError,
    decoded,
    documentary_backend,
    one,
    rows,
)
from documents.renderers import (
    _cut_key,
    _cut_member_map,
    _infill_code_map,
    _infill_key,
    _piece_labels,
)
from engine_api.cutting_repository import CuttingRepository
from inventory import remnants as remnants_service
from inventory import production_stock
from production.confirmations import confirmation_summary
from production.dxf import dxf_files
from production.dispatch_notes import issue_dispatch_note
from projects import sii_envio
from projects.service import project_row


_STEP_CODE_FOR_CENTER = {
    "CUT": "CUT",
    "PROFILE_CUT": "PROFILE_CUT",
    "REINFORCEMENT_CUT": "REINFORCEMENT_CUT",
    "MACHINING": "MACHINING",
    "WELDING": "WELD",
    "CLEANING": "CLEAN",
    "CRIMPING": "CRIMP",
    "SASH_ASSEMBLY": "SASH_ASSEMBLE",
    "ASSEMBLY": "ASSEMBLE",
    "HARDWARE": "HARDWARE",
    "GLAZING": "GLAZE",
    "QC": "QC",
    "PACK": "PACK",
}

# Station code (as stored on production_steps.code) → work_centers.kind.
_CENTER_KIND_FOR_STATION = {station: kind for kind, station in _STEP_CODE_FOR_CENTER.items()}

_DEFAULT_CENTERS = [
    ("CUT_SAW", "Sierra de corte", "CUT", 10),
    ("MACHINING_CELL", "Centro de mecanizado", "MACHINING", 15),
    ("WELDER", "Soldadora", "WELDING", 20),
    ("CLEANING_STATION", "Limpiadora de esquinas", "CLEANING", 25),
    ("CRIMPING_MACHINE", "Prensadora de esquinas", "CRIMPING", 26),
    ("ASSEMBLY_BENCH", "Banco de armado", "ASSEMBLY", 30),
    ("SASH_ASSEMBLY_BENCH", "Banco de armado de hojas", "SASH_ASSEMBLY", 31),
    ("HARDWARE_BENCH", "Banco de herrajes", "HARDWARE", 32),
    ("GLAZING_BENCH", "Banco de vidriado", "GLAZING", 40),
    ("QC_STATION", "Puesto de control", "QC", 50),
    ("PACK_STATION", "Puesto de embalaje", "PACK", 60),
]

_STEP_LABELS = {
    "CUT": "Corte de perfiles",
    "PROFILE_CUT": "Corte de perfiles",
    "REINFORCEMENT_CUT": "Corte de refuerzos",
    "MACHINING": "Mecanizado",
    "WELD": "Soldadura",
    "CLEAN": "Limpieza de esquinas",
    "CRIMP": "Prensado de esquinas",
    "SASH_ASSEMBLE": "Armado de hojas",
    "ASSEMBLE": "Armado y herrajes",
    "HARDWARE": "Montaje de herrajes",
    "GLAZE": "Vidriado y paneles",
    "QC": "Control de calidad",
    "PACK": "Embalaje",
}

# §10: which stock kinds a routing step physically consumes — bars and
# sheets drop at the saw, kits and fittings land at assembly, panels at
# glazing. Reservations stay open until their step completes.
_STEP_CONSUMED_KINDS = {
    "CUT": {"BAR", "SHEET"},
    "ASSEMBLE": {"HARDWARE_KIT", "FITTING"},
    "HARDWARE": {"HARDWARE_KIT", "FITTING"},
    "GLAZE": {"PANEL"},
}

# Stations that physically work the sealed plan without consuming stock:
# they must never START or COMPLETE against a missing/invalidated plan —
# a machining cell running a dead program produces scrap, not just bad
# bookkeeping. Stock settlement itself still lives in _STEP_CONSUMED_KINDS.
_PLAN_REQUIRED_STATIONS = {"MACHINING", "PROFILE_CUT", "REINFORCEMENT_CUT"}

# Steps where execution evidence is per-operation: COMPLETE must declare
# every member machining op routed to the station (review: a machining
# step completing with zero ops recorded is a status flip, not work).
_OPS_EVIDENCE_STATIONS = {"MACHINING", "PROFILE_CUT", "REINFORCEMENT_CUT"}

# The QC step is the check on everyone else's work — the operator who ran
# the saw must not be the signature that verifies it (producer/verifier
# separation).
_QC_STEP_ACTORS = {"OWNER", "WORKSHOP_MANAGER"}

# Glass and panel infills always carry a CUT_TO_SIZE purchase authority —
# pieces no workshop sheet hosts are supplied finished, not short. Only an
# unnesting reason outside the purchased-supply set may block completion.
_PURCHASED_UNNESTED_REASONS = frozenset({
    "shaped_glass_outline",
    "no_declared_sheet",
    "piece_larger_than_usable_sheet",
})

_EVENTS = {
    "START": "STEP_STARTED",
    "COMPLETE": "STEP_COMPLETED",
    "BLOCK": "STEP_BLOCKED",
    "UNBLOCK": "STEP_UNBLOCKED",
    "NOTE": "NOTE",
    "QC_CHECK": "QC_CHECK",
}

_TRANSITIONS = {
    "START": ("IN_PROGRESS", {"PENDING", "READY"}),
    "COMPLETE": ("DONE", {"IN_PROGRESS"}),
    "BLOCK": ("BLOCKED", {"PENDING", "READY", "IN_PROGRESS"}),
    "UNBLOCK": ("READY", {"BLOCKED"}),
    "NOTE": (None, {"PENDING", "READY", "IN_PROGRESS", "DONE", "BLOCKED"}),
    # §13: recording one measured check on the QC step is not a status
    # change — the step still completes via COMPLETE/QC_FAILED.
    "QC_CHECK": (None, {"READY", "IN_PROGRESS", "BLOCKED"}),
}


def _member_ops_for_station(
    *, org_id: UUID, order: dict[str, object], station: str
) -> dict[str, str]:
    """operation_id → human label (``M-07 · HANDLE_PREP``) for the member
    machining ops the frozen routing assigns to ``station`` — the same
    sealed derivation the operator card and ops export read. Empty when the
    order has no derivable plan (the plan gates then refuse first)."""
    from production import trace as production_trace

    payload = _decoded(order.get("payload_json"))
    optimization = payload.get("optimization")
    if not isinstance(optimization, dict) or not optimization.get("bars"):
        return {}
    if not order.get("project_version_id"):
        return {}
    version_row = one(
        """
        SELECT snapshot_json::text AS snapshot_json
        FROM public.project_versions WHERE id = %s AND org_id = %s
        """,
        [str(order["project_version_id"]), str(org_id)],
        "work_order_missing_version",
    )
    version_snapshot = _decoded(version_row["snapshot_json"])
    ops_doc = production_trace._trace_operations(
        payload=payload,
        optimization=optimization,
        version_snapshot=version_snapshot,
    )
    try:
        labels = _piece_labels(version_snapshot)
    except DocumentaryError:
        labels = {}
    member_labels = {
        **(labels.get("member") or {}),
        **(labels.get("reinforcement") or {}),
    }
    expected: dict[str, str] = {}
    for op in ops_doc.get("items", []):
        if op.get("host_kind") != "MEMBER" or op.get("station") != station:
            continue
        code = member_labels.get(str(op.get("host"))) or str(
            op.get("host") or op["operation_id"]
        )
        expected[str(op["operation_id"])] = f"{code} · {op.get('kind')}"
    return expected


def _ensure_work_centers(
    org_id: UUID,
) -> tuple[dict[str, dict[str, object]], set[str]]:
    """(active-by-kind, inactive-kinds). A kind the org deliberately
    deactivated is never silently re-seeded: its steps land unassigned and the
    work order carries an explicit work_center_inactive blocker."""
    query = (
        "SELECT id, code, kind, active FROM public.work_centers "
        "WHERE org_id = %s ORDER BY display_order"
    )
    existing = rows(query, [str(org_id)])
    present_kinds = {str(center["kind"]) for center in existing}
    missing = [center for center in _DEFAULT_CENTERS if center[2] not in present_kinds]
    if missing:
        with transaction.atomic(), documentary_backend():
            for code, name, kind, order in missing:
                rows(
                    """
                    INSERT INTO public.work_centers(org_id, code, name, kind, display_order)
                    VALUES (%s, %s, %s, %s, %s) ON CONFLICT (org_id, code) DO NOTHING
                    RETURNING id
                    """,
                    [str(org_id), code, name, kind, order],
                )
            existing = rows(query, [str(org_id)])
    # First ACTIVE center of each kind wins (display_order ascending) — a
    # custom station the org ordered first keeps step assignment over any
    # default seeded later of the same kind.
    by_kind: dict[str, dict[str, object]] = {}
    for center in existing:
        if center.get("active"):
            by_kind.setdefault(str(center["kind"]), center)
    inactive_kinds = present_kinds - {str(kind) for kind in by_kind}
    return by_kind, inactive_kinds


def _cut_roles(engine_result: dict[str, object]) -> set[str]:
    return {
        str(cut.get("role") or "")
        for cut in (engine_result.get("profile_cuts") or [])
        if isinstance(cut, dict)
    }


def _is_frameless(engine_result: dict[str, object]) -> bool:
    """The pane is the product: channel runs/fittings serve a frameless
    spec. Such a position must never inherit weld/crimp from whatever
    material its associated system declares."""
    if "CHANNEL" in _cut_roles(engine_result):
        return True
    if engine_result.get("fittings") and "FRAME" not in _cut_roles(engine_result):
        return True
    return any(
        isinstance(piece, dict) and bool(piece.get("exposed_edges"))
        for piece in (engine_result.get("glasses") or [])
    )


_FRAMED_CUT_ROLES = {
    "FRAME", "SASH", "MULLION_V", "MULLION_H", "COUPLER", "THRESHOLD", "INVERSOR",
}


def _has_framed_work(engine_result: dict[str, object]) -> bool:
    """A framed unit inside the same position — the joining steps must
    survive even when a frameless pane shares the work order."""
    return bool(_cut_roles(engine_result) & _FRAMED_CUT_ROLES)


def _merge_frameless(
    base: dict[str, object],
    frameless: dict[str, object],
) -> dict[str, object]:
    """Mixed assembly: the declared/material profile keeps its joining
    authority; the frameless template contributes the stations and op
    mappings only the pane can produce (a pane is never machined)."""
    merged = dict(base)
    merged_stations = [dict(s) for s in (merged.get("stations") or []) if isinstance(s, dict)]
    by_code = {str(s["code"]): s for s in merged_stations}
    for station in (frameless.get("stations") or []):
        if not isinstance(station, dict):
            continue
        code = str(station.get("code") or "")
        if not code:
            continue
        if code in by_code:
            if station.get("when") == "required":
                by_code[code]["when"] = "required"
            continue
        # Frameless-only stations slot before the QC/PACK tail.
        insert_at = next(
            (i for i, s in enumerate(merged_stations) if str(s.get("code")) in ("QC", "PACK")),
            len(merged_stations),
        )
        merged_stations.insert(insert_at, dict(station))
        by_code[code] = merged_stations[insert_at]
    merged["stations"] = merged_stations
    frameless_ops = set(frameless.get("optional_operations") or [])
    merged_map = dict(base.get("operation_station_map") or {})
    for op, station in (frameless.get("operation_station_map") or {}).items():
        if str(op) in frameless_ops or op not in merged_map:
            merged_map[op] = station
    merged["operation_station_map"] = merged_map
    merged["optional_operations"] = sorted(
        set(base.get("optional_operations") or []) | frameless_ops
    )
    return merged


def _load_profile_for(
    org_id: UUID,
    *,
    code: str | None = None,
    profile_id: str | None = None,
    material: str | None = None,
    product_kind: str | None = None,
) -> tuple[dict[str, object] | None, str | None]:
    """Resolve the declared process authority. Org rows override the global
    seeds; resolution order is explicit binding → product kind → material.
    Returns (row, resolved_via)."""
    where = "org_id IS NULL OR org_id = %s"
    params: list[object] = [str(org_id)]
    clause = ""
    if profile_id:
        clause = " AND id = %s"
        params.append(profile_id)
    elif code:
        clause = " AND code = %s"
        params.append(code)
    elif product_kind:
        clause = " AND product_kind = %s"
        params.append(product_kind)
    elif material:
        clause = " AND material = %s AND product_kind = 'STANDARD'"
        params.append(material)
    else:
        return None, None
    record = rows(
        f"""
        SELECT * FROM public.manufacturing_process_profiles
        WHERE ({where}){clause}
        ORDER BY (org_id IS NOT NULL) DESC, version DESC
        LIMIT 1
        """,
        params,
    )
    if not record:
        return None, None
    row = dict(record[0])
    # jsonb columns arrive undecoded in some paths — normalize before the
    # routing template consumes them.
    for field in ("stations", "operation_station_map", "optional_operations",
                  "machine_neutral_machining", "provenance"):
        value = row.get(field)
        if isinstance(value, str):
            try:
                row[field] = json.loads(value)
            except (TypeError, ValueError):
                row[field] = [] if field != "operation_station_map" else {}
    via = (
        "system_declared"
        if profile_id
        else ("product_kind" if product_kind else ("material_default" if material else "code"))
    )
    return row, via


def _resolve_process_profile(
    org_id: UUID,
    engine_result: dict[str, object],
    system_facts: dict[str, object] | None,
) -> tuple[dict[str, object] | None, str | None]:
    """sealed product → declared authority. A pure frameless position wins
    over material always; a system-bound profile wins over the material
    default; a MIXED framed+frameless assembly resolves the declared profile
    and merges the frameless stations/mappings the pane needs — the framed
    module never loses its joining steps to its sibling's pane."""
    facts = system_facts or {}
    if _is_frameless(engine_result) and not _has_framed_work(engine_result):
        row, via = _load_profile_for(org_id, product_kind="FRAMELESS")
        if row:
            return row, via
    bound = facts.get("process_profile_id")
    row: dict[str, object] | None = None
    via: str | None = None
    if bound:
        row, via = _load_profile_for(org_id, profile_id=str(bound))
    if row is None:
        material = str(facts.get("material") or "").upper() or None
        if material:
            row, via = _load_profile_for(org_id, material=material)
    if row is None:
        row, via = _load_profile_for(org_id, code="GENERIC_LEGACY")
        via = "generic_fallback" if row else via
    if row is not None and _is_frameless(engine_result) and _has_framed_work(engine_result):
        frameless, _ = _load_profile_for(org_id, product_kind="FRAMELESS")
        if frameless is not None:
            return _merge_frameless(row, frameless), f"{via}_mixed"
    return row, via


def _station_has_work(
    code: str,
    engine_result: dict[str, object],
    *,
    end_milling_overlap_mm: object = None,
    has_handles: bool = False,
    handle_station: str = "MACHINING",
) -> bool:
    """'auto' stations land only when the sealed result carries work."""
    cuts = engine_result.get("profile_cuts") or []
    roles = _cut_roles(engine_result)
    # A handle op exists wherever the profile sends HANDLE_PREP — frameless
    # and mixed profiles route it to HARDWARE, never assume the mill.
    if has_handles and code == handle_station:
        return True
    if code == "CUT":
        return bool(cuts or engine_result.get("reinforcements"))
    if code == "MACHINING":
        # Every member op the sealed facts can emit lands here: END_MACHINING
        # (overlap authority) and HANDLE_PREP when the profile maps it so.
        # Omitting the station while an op maps to it would leave work unrouted.
        try:
            return end_milling_overlap_mm is not None and Decimal(
                str(end_milling_overlap_mm)
            ) > 0
        except ArithmeticError:
            return False
    if code == "SASH_ASSEMBLE":
        return "SASH" in roles
    if code == "HARDWARE":
        return bool(engine_result.get("hardware_items") or engine_result.get("fittings"))
    if code == "GLAZE":
        return bool(engine_result.get("glasses") or engine_result.get("panels"))
    return True


def _routing(
    engine_result: dict[str, object],
    *,
    profile: dict[str, object] | None,
    end_milling_overlap_mm: object = None,
    has_handles: bool = False,
) -> list[str]:
    """The ladder is the declared profile's station template pruned by the
    sealed result: required stations are process-inherent and always land;
    auto stations land only with matching sealed work. Where no authority
    resolved, the honest generic path (CUT/ASSEMBLE/GLAZE/QC/PACK) stands."""
    stations = ((profile or {}).get("stations") or []) if profile else []
    if not stations:
        stations = [
            {"code": "CUT", "when": "auto"},
            {"code": "ASSEMBLE", "when": "auto"},
            {"code": "GLAZE", "when": "auto"},
            {"code": "QC", "when": "required"},
            {"code": "PACK", "when": "required"},
        ]
    handle_station = str(
        ((profile or {}).get("operation_station_map") or {}).get("HANDLE_PREP")
        or "MACHINING"
    )
    routing: list[str] = []
    for station in stations:
        if not isinstance(station, dict):
            continue
        code = str(station.get("code") or "")
        if not code:
            continue
        if str(station.get("when") or "auto") == "required" or _station_has_work(
            code,
            engine_result,
            end_milling_overlap_mm=end_milling_overlap_mm,
            has_handles=has_handles,
            handle_station=handle_station,
        ):
            routing.append(code)
    return routing


def _process_authority(
    profile: dict[str, object] | None,
    resolved_via: str | None,
) -> dict[str, object]:
    """The routing authority frozen into the work order's evidence — every
    order names the profile and version it was routed under."""
    if not profile:
        return {"code": "GENERIC_LEGACY", "version": 0, "resolved_via": "fallback"}
    return {
        "profile_id": str(profile.get("id") or ""),
        "code": str(profile.get("code") or ""),
        "version": profile.get("version"),
        "resolved_via": resolved_via,
        "joining_method": profile.get("joining_method"),
        "operation_station_map": profile.get("operation_station_map") or {},
    }


def _work_order_payload(
    position: dict[str, object], *, polishing: list | None = None,
    color: str | None = None,
    process: dict[str, object] | None = None,
    org_id: UUID | None = None,
    system_facts: dict[str, object] | None = None,
    has_handles: bool = False,
) -> dict[str, object]:
    engine = position.get("engine_result") or {}
    profile: dict[str, object] | None = None
    resolved_via: str | None = None
    facts: dict[str, object] = system_facts or {}
    if process is not None:
        # Sealed process facts: the profile/inputs frozen with the version.
        profile = process.get("profile") if isinstance(process.get("profile"), dict) else None
        resolved_via = process.get("resolved_via")
        facts = process.get("system") if isinstance(process.get("system"), dict) else {}
    elif org_id is not None:
        profile, resolved_via = _resolve_process_profile(org_id, engine, system_facts)
    return {
        "schema": "production_wo_v1",
        "position_id": str(position.get("position_id") or ""),
        "system_id": str(position.get("system_id") or ""),
        "quantity": position.get("quantity", 1),
        "color": color,
        "materials": {
            key: engine.get(key) or []
            for key in (
                "profile_cuts", "reinforcements", "glasses", "panels",
                "fittings", "hardware_items",
            )
        },
        "glass_polishing": list(polishing or []),
        "routing": _routing(
            engine,
            profile=profile,
            end_milling_overlap_mm=facts.get("end_milling_overlap_mm"),
            has_handles=has_handles,
        ),
        "process_authority": _process_authority(profile, resolved_via),
    }


_FROZEN_PROFILE_FIELDS = (
    "id", "code", "version", "joining_method", "corner_process",
    "cleaning_process", "stations", "operation_station_map",
    "sash_assembly_required", "hardware_station", "glazing", "qc",
    "packaging", "optional_operations", "machine_neutral_machining",
)


def _frozen_profile(profile: dict[str, object] | None) -> dict[str, object] | None:
    if not profile:
        return None
    return {field: profile.get(field) for field in _FROZEN_PROFILE_FIELDS}


def process_facts_snapshot(
    *,
    org_id: UUID,
    engine_result: dict[str, object],
    system_facts: dict[str, object] | None,
) -> dict[str, object]:
    """The process authority frozen into a sealed position — the resolved
    profile content AND its routing inputs. Release reads this verbatim so a
    later catalog/profile edit can never re-route sealed evidence."""
    profile, via = _resolve_process_profile(org_id, engine_result, system_facts)
    return {
        "system": dict(system_facts or {}),
        "profile": _frozen_profile(profile),
        "resolved_via": via,
    }


def _public_step(step: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(step["id"]),
        "sequence": step["sequence"],
        "code": step["code"],
        "label": step["label"],
        "status": step["status"],
        "work_center_id": str(step["work_center_id"]) if step.get("work_center_id") else None,
        "work_center_code": step.get("work_center_code"),
        "work_center_name": step.get("work_center_name"),
        "started_at": step["started_at"],
        "finished_at": step["finished_at"],
        "actor_id": str(step["actor_id"]) if step.get("actor_id") else None,
        "note": step.get("note"),
    }


def _order_shortage(payload: dict[str, object] | None) -> int:
    """The order's own shortage — only its reservation ledger counts. Before
    optimization there is no per-order signal; the version-wide prep count
    surfaces separately as ``version_shortage`` so a sibling position's
    shortfall is never dressed up as this order's."""
    reservations = ((payload or {}).get("optimization") or {}).get("stock_reservations")
    if reservations is None:
        return 0
    return sum(
        1
        for entry in reservations
        if str(entry.get("short") or "0") not in ("", "0", "0.00")
    )


def _version_shortage(payload: dict[str, object] | None) -> int:
    prep = (payload or {}).get("prep") or {}
    try:
        return int(prep.get("shortages") or 0)
    except (TypeError, ValueError):
        return 0


def _public_order(order: dict[str, object], *, include_payload: bool = False) -> dict[str, object]:
    payload = order.get("payload_json")
    if isinstance(payload, str):
        payload = json.loads(payload)
    status = str(order["status"])
    next_step = order.get("next_step_code")
    output = {
        "id": str(order["id"]),
        "order_code": order["order_code"],
        "order_type": str(order["order_type"]),
        "status": status,
        "position_id": (payload or {}).get("position_id"),
        "quantity": (payload or {}).get("quantity"),
        "steps_done": order.get("steps_done", 0),
        "steps_total": order.get("steps_total", 0),
        # §8 explicit workflow surfacing — all derived from sealed state.
        "next_step": (
            {"code": str(next_step), "label": _STEP_LABELS.get(str(next_step), str(next_step))}
            if next_step
            else None
        ),
        "dispatch_ready": bool(
            (payload or {}).get("packing")
            and status == "COMPLETED"
            and not order.get("has_dispatch_note")
        ),
        "shortage": _order_shortage(payload),
        "version_shortage": _version_shortage(payload),
        "created_at": order["created_at"],
    }
    if include_payload:
        output["payload"] = payload
        output["project_version_id"] = str(order["project_version_id"]) if order.get("project_version_id") else None
    return output


def release_production(*, org_id: UUID, version_id: UUID, actor_id: UUID) -> dict[str, object]:
    """Create one WORKSHOP_OT order per sealed position. Idempotent via the
    orders_workshop_position_uq index: a replay returns the existing orders."""
    with transaction.atomic(), documentary_backend():
        version = one(
            """
            SELECT id, project_id, revision_code, snapshot_json, production_allowed
            FROM public.project_versions WHERE id = %s AND org_id = %s
            """,
            [str(version_id), str(org_id)],
            "version_not_found",
        )
        if not version["production_allowed"]:
            raise DocumentaryError("version_not_releasable")
        # A sealed version stays valid only while it is the newest one —
        # once a later revision froze, releasing the superseded quote would
        # build the wrong product (review WM2).
        # Revision codes are base-26 (REV-Z → REV-AA), so recency sorts by
        # suffix length then lexicographically, never plain text order.
        latest = rows(
            """
            SELECT revision_code::text AS code FROM public.project_versions
            WHERE project_id = %s AND org_id = %s
            ORDER BY length(revision_code) DESC, revision_code DESC LIMIT 1
            """,
            [str(version["project_id"]), str(org_id)],
        )
        if latest and str(latest[0]["code"]) != str(version["revision_code"]):
            raise DocumentaryError("version_superseded")
        snapshot = version["snapshot_json"]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        bom = snapshot.get("bom") or []
        project_code = str(
            (snapshot.get("project") or {}).get("code") or version["project_id"]
        )
        position_systems = {
            str(pos.get("id")): str(pos.get("system_id"))
            for pos in snapshot.get("positions") or []
            if pos.get("id") and pos.get("system_id")
        }
        for position in bom:
            position["system_id"] = position_systems.get(str(position.get("position_id") or ""))
        centers, inactive_kinds = _ensure_work_centers(org_id)
        # The sealed polishing choices live on the snapshot positions — the
        # work order embeds them so the workshop reads edge processing without
        # joining the documentary snapshot.
        # Process authority is frozen per position at seal time. Versions
        # sealed before the authority model exist get the honest legacy
        # fallback — their manufacturing facts are never reinterpreted
        # through a later catalog revision.
        frozen_facts = {
            str(pos.get("id")): pos.get("process_facts")
            for pos in snapshot.get("positions") or []
            if pos.get("id")
        }
        # Declared process authority is a release gate, not advisory: a
        # position resolved to GENERIC_LEGACY means no bound/material process
        # profile exists — the routing would be invented. Re-seal on a
        # catalog with real process authority instead of shipping it.
        unresolved = sorted(
            str(pos.get("code") or pos.get("position_index") or pid)
            for pos in (snapshot.get("positions") or [])
            for pid in (str(pos.get("id")),)
            if not isinstance(pos.get("process_facts"), dict)
            or pos["process_facts"].get("resolved_via") == "generic_fallback"
        )
        if unresolved:
            raise DocumentaryError("production_process_unresolved")
        generic_profile, _ = _load_profile_for(org_id, code="GENERIC_LEGACY")
        polishing_by_position = {
            str(pos.get("id")): pos.get("glass_polishing") or []
            for pos in snapshot.get("positions") or []
            if pos.get("id")
        }
        # The sealed color is what the cut optimizer's stock variants are
        # named after — WHITE only when both faces are WHITE, else FOILED.
        color_by_position = {
            str(pos.get("id")): (
                "WHITE"
                if pos.get("color_interior") == "WHITE"
                and pos.get("color_exterior") == "WHITE"
                else "FOILED"
            )
            for pos in snapshot.get("positions") or []
            if pos.get("id")
        }

        created_ids: list[UUID] = []
        order_ids: list[UUID] = []
        for index, position in enumerate(bom):
            position_id = str(position.get("position_id") or "")
            sealed = frozen_facts.get(position_id)
            process = sealed if isinstance(sealed, dict) else {
                "system": {},
                "profile": generic_profile,
                "resolved_via": "generic_fallback",
            }
            has_handles = bool(
                (next(
                    (p for p in (snapshot.get("positions") or [])
                     if str(p.get("id")) == position_id),
                    {},
                )).get("handle_intents")
            )
            payload = _work_order_payload(
                position,
                polishing=polishing_by_position.get(position_id),
                color=color_by_position.get(position_id),
                process=process,
                org_id=org_id,
                has_handles=has_handles,
            )
            inactive_step_kinds = sorted({
                kind for kind, step_code in _STEP_CODE_FOR_CENTER.items()
                if step_code in payload["routing"] and kind in inactive_kinds
            })
            if inactive_step_kinds:
                payload["blockers"] = [
                    f"work_center_inactive:{kind}" for kind in inactive_step_kinds
                ]
            order_code = f"OT-{project_code}-{version['revision_code']}-{index + 1:02d}"[:50]
            inserted = rows(
                """
                INSERT INTO public.orders(
                    org_id, project_id, order_type, order_code, status,
                    payload_json, project_version_id)
                VALUES (%s, %s, 'WORKSHOP_OT', %s, 'RELEASED', %s::jsonb, %s)
                ON CONFLICT (org_id, project_version_id, (payload_json->>'position_id'))
                WHERE order_type = 'WORKSHOP_OT'
                  AND project_version_id IS NOT NULL
                  AND payload_json ? 'position_id'
                  AND NOT (payload_json ? 'remake_of')
                DO NOTHING
                RETURNING id
                """,
                [
                    str(org_id),
                    str(version["project_id"]),
                    order_code,
                    json.dumps(payload),
                    str(version_id),
                ],
            )
            if inserted:
                order_id = inserted[0]["id"]
                created_ids.append(order_id)
            else:
                order_id = one(
                    """
                    SELECT id FROM public.orders
                    WHERE org_id = %s AND project_version_id = %s
                      AND order_type = 'WORKSHOP_OT'
                      AND payload_json->>'position_id' = %s
                      AND NOT (payload_json ? 'remake_of')
                    """,
                    [str(org_id), str(version_id), payload["position_id"]],
                    "work_order_not_found",
                )["id"]
            order_ids.append(order_id)
            if inserted:
                center_by_step = {
                    step_code: centers.get(center_kind)
                    for center_kind, step_code in _STEP_CODE_FOR_CENTER.items()
                }
                for seq, code in enumerate(payload["routing"], start=1):
                    center = center_by_step.get(code)
                    rows(
                        """
                        INSERT INTO public.production_steps(
                            org_id, order_id, sequence, work_center_id, code, label, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'READY')
                        RETURNING id
                        """,
                        [
                            str(org_id),
                            str(order_id),
                            seq,
                            str(center["id"]) if center else None,
                            code,
                            _STEP_LABELS[code],
                        ],
                    )
                rows(
                    """
                    INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
                    VALUES (%s, %s, 'WO_RELEASED', %s, %s::jsonb)
                    RETURNING id
                    """,
                    [
                        str(org_id),
                        str(order_id),
                        str(actor_id),
                        json.dumps({"order_code": order_code, "position_id": payload["position_id"]}),
                    ],
                )
        # §8: the moment a version becomes work, the workshop should already
        # see the material shortage signal the purchasing coverage computes —
        # not only after someone clicks optimize. One coverage read stamps
        # every released order's prep evidence.
        coverage = production_stock.coverage_for_version(org_id=org_id, version_id=version_id)
        prep_stamp = {
            "schema": "work_order_prep_v1",
            "shortages": int(coverage.get("shortages") or 0),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        for order_id in order_ids:
            rows(
                """
                UPDATE public.orders
                SET payload_json = payload_json || %s::jsonb
                WHERE id = %s AND org_id = %s
                RETURNING id
                """,
                [json.dumps({"prep": prep_stamp}), str(order_id), str(org_id)],
            )
        # §08: released into a known shortage → a purchase task per order,
        # queued inside this tx so the task exists iff the release does.
        if prep_stamp["shortages"] > 0:
            from automations.service import emit

            for order_id in order_ids:
                emit(
                    "automation.purchase_task",
                    org_id=org_id,
                    actor_id=actor_id,
                    idempotency_key=f"auto:buy:{order_id}:forecast",
                    order_id=str(order_id),
                )
        orders = rows(
            """
            SELECT o.id, o.order_code, o.order_type::text, o.status::text, o.payload_json,
                   o.project_version_id, o.created_at,
                   COUNT(s.id) AS steps_total,
                   COUNT(s.id) FILTER (WHERE s.status = 'DONE') AS steps_done,
                   (SELECT s2.code FROM public.production_steps s2
                    WHERE s2.order_id = o.id AND s2.status <> 'DONE'
                    ORDER BY s2.sequence LIMIT 1) AS next_step_code,
                   EXISTS(SELECT 1 FROM public.dispatch_notes dn
                          WHERE dn.org_id = o.org_id AND dn.work_order_id = o.id
                            AND dn.voided_at IS NULL
                         ) AS has_dispatch_note
            FROM public.orders o
            LEFT JOIN public.production_steps s ON s.order_id = o.id
            WHERE o.id = ANY(%s::uuid[])
            GROUP BY o.id ORDER BY o.order_code
            """,
            [[str(order_id) for order_id in order_ids]],
        )
        return {
            "version_id": str(version_id),
            "released": len(order_ids),
            "created": len(created_ids),
            "orders": [_public_order(order) for order in orders],
        }


def list_production_orders(*, org_id: UUID) -> dict[str, object]:
    orders = rows(
        """
        SELECT o.id, o.order_code, o.order_type::text, o.status::text, o.payload_json,
               o.project_version_id, o.created_at,
               COUNT(s.id) AS steps_total,
               COUNT(s.id) FILTER (WHERE s.status = 'DONE') AS steps_done,
               (SELECT s2.code FROM public.production_steps s2
                WHERE s2.order_id = o.id AND s2.status <> 'DONE'
                ORDER BY s2.sequence LIMIT 1) AS next_step_code,
               EXISTS(SELECT 1 FROM public.dispatch_notes dn
                      WHERE dn.org_id = o.org_id AND dn.work_order_id = o.id
                        AND dn.voided_at IS NULL
                     ) AS has_dispatch_note
        FROM public.orders o
        LEFT JOIN public.production_steps s ON s.order_id = o.id
        WHERE o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
        GROUP BY o.id ORDER BY o.created_at DESC
        LIMIT 300
        """,
        [str(org_id)],
    )
    return {"orders": [_public_order(order) for order in orders]}


def production_prep(*, org_id: UUID) -> dict[str, object]:
    """§8 project-approved → production preparation: sealed versions that are
    allowed into production but have no workshop order yet. Deterministic —
    no AI, just the state the release action consumes."""
    with documentary_backend():
        versions = rows(
            """
            SELECT v.id, v.project_id, v.revision_code, v.emitted_at,
                   p.code AS project_code,
                   jsonb_array_length(COALESCE(v.snapshot_json->'bom', '[]'::jsonb))
                       AS positions
            FROM public.project_versions v
            JOIN public.projects p ON p.id = v.project_id AND p.org_id = v.org_id
            WHERE v.org_id = %s AND v.production_allowed
              AND jsonb_array_length(COALESCE(v.snapshot_json->'bom', '[]'::jsonb)) > 0
              AND NOT EXISTS (
                  SELECT 1 FROM public.orders o
                  WHERE o.org_id = v.org_id AND o.project_version_id = v.id
                    AND o.order_type = 'WORKSHOP_OT'
              )
              AND NOT EXISTS (
                  -- Only the newest production-allowed revision per project is
                  -- release-able; older ones are superseded, not waiting work.
                  SELECT 1 FROM public.project_versions v2
                  WHERE v2.org_id = v.org_id AND v2.project_id = v.project_id
                    AND v2.production_allowed
                    AND v2.emitted_at > v.emitted_at
              )
            ORDER BY v.emitted_at DESC NULLS LAST, v.id
            """,
            [str(org_id)],
        )
        return {
            "versions": [
                {
                    "version_id": str(item["id"]),
                    "project_id": str(item["project_id"]),
                    "project_code": item["project_code"],
                    "revision_code": item["revision_code"],
                    "positions": int(item["positions"]),
                }
                for item in versions
            ]
        }


def confirm_installation(
    org_id: str, order_id: str, actor_id: str, note: str | None = None
) -> dict:
    """Mark a dispatched order installed — the physical install is done.

    Idempotent: replaying on an INSTALLED order returns the current state.
    """
    with transaction.atomic(), documentary_backend():
        order = one(
            "SELECT id, order_code, status, payload_json FROM public.orders "
            "WHERE id = %s AND org_id = %s FOR UPDATE",
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if order["status"] == "INSTALLED":
            return get_work_order(org_id=org_id, order_id=order_id)
        if order["status"] != "DISPATCHED":
            raise DocumentaryError("installation_requires_dispatched")
        delivery = rows(
            "SELECT status FROM public.deliveries WHERE order_id = %s AND org_id = %s",
            [str(order_id), str(org_id)],
        )
        if not delivery or str(delivery[0]["status"]) != "DELIVERED":
            raise DocumentaryError("installation_requires_delivered")
        # DELIVERED is only stamped by confirm_delivery, so this should always
        # hold; verify anyway so a hand-edited row can't produce an installed
        # order with no sealed comprobante.
        if not rows(
            "SELECT id FROM public.delivery_confirmations "
            "WHERE order_id = %s AND org_id = %s",
            [str(order_id), str(org_id)],
        ):
            raise DocumentaryError("installation_requires_confirmation")
        rows(
            "UPDATE public.orders SET status = 'INSTALLED', updated_at = %s "
            "WHERE id = %s AND org_id = %s RETURNING id",
            [datetime.now(timezone.utc), str(order_id), str(org_id)],
        )
        rows(
            """INSERT INTO public.production_step_events
                   (org_id, order_id, event, actor_id, payload)
                   VALUES (%s, %s, 'WO_INSTALLED', %s, %s) RETURNING id""",
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps(
                    {
                        "order_code": order["order_code"],
                        "note": (note or "").strip() or None,
                    }
                ),
            ],
        )
    return get_work_order(org_id=org_id, order_id=order_id)


def get_work_order(*, org_id: UUID, order_id: UUID) -> dict[str, object]:
    order = one(
        """
        SELECT o.id, o.order_code, o.order_type::text, o.status::text, o.payload_json,
               o.project_version_id, o.created_at,
               COUNT(s.id) AS steps_total,
               COUNT(s.id) FILTER (WHERE s.status = 'DONE') AS steps_done,
               (SELECT s2.code FROM public.production_steps s2
                WHERE s2.order_id = o.id AND s2.status <> 'DONE'
                ORDER BY s2.sequence LIMIT 1) AS next_step_code,
               EXISTS(SELECT 1 FROM public.dispatch_notes dn
                      WHERE dn.org_id = o.org_id AND dn.work_order_id = o.id
                        AND dn.voided_at IS NULL
                     ) AS has_dispatch_note
        FROM public.orders o
        LEFT JOIN public.production_steps s ON s.order_id = o.id
        WHERE o.id = %s AND o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
        GROUP BY o.id
        """,
        [str(order_id), str(org_id)],
        "work_order_not_found",
    )
    steps = rows(
        """
        SELECT s.id, s.sequence, s.code, s.label, s.status, s.work_center_id,
               w.code AS work_center_code, w.name AS work_center_name, s.started_at, s.finished_at, s.actor_id, s.note
        FROM public.production_steps s
        LEFT JOIN public.work_centers w ON w.id = s.work_center_id
        WHERE s.order_id = %s ORDER BY s.sequence
        """,
        [str(order_id)],
    )
    events = rows(
        """
        SELECT ev.id, ev.step_id, ev.event, ev.actor_id, ev.actor_label,
               ev.payload, ev.created_at, st.code::text AS step_code
        FROM public.production_step_events ev
        LEFT JOIN public.production_steps st ON st.id = ev.step_id
        WHERE ev.order_id = %s AND ev.org_id = %s
        ORDER BY ev.created_at
        """,
        [str(order_id), str(org_id)],
    )
    dispatch_note = rows(
        "SELECT id, note_code, voided_at FROM public.dispatch_notes "
        "WHERE org_id=%s AND work_order_id=%s "
        "ORDER BY created_at DESC",
        [str(org_id), str(order_id)],
    )
    live_note = next((row for row in dispatch_note if row.get("voided_at") is None), None)
    output = _public_order(order, include_payload=True)
    output["dispatch_note_code"] = (
        dispatch_note[0]["note_code"] if dispatch_note else None
    )
    output["dispatch_note_voided"] = bool(dispatch_note) and live_note is None
    if live_note:
        dte = rows(
            "SELECT d.id, d.dte_type, d.folio, d.issued_at "
            "FROM public.project_dtes d "
            "WHERE d.org_id=%s AND d.dispatch_note_id=%s",
            [str(org_id), str(live_note["id"])],
        )
        envios = sii_envio.envios_by_dispatch_note(org_id=org_id)
        output["dispatch_note_dte"] = (
            {
                "dte_type": int(dte[0]["dte_type"]),
                "folio": int(dte[0]["folio"]),
                "issued_at": dte[0]["issued_at"],
                "envio": envios.get(str(live_note["id"])),
            }
            if dte
            else None
        )
    else:
        output["dispatch_note_dte"] = None
    # §10 "what are we making": the sealed position's physical identity —
    # typology/dimensions/finish/location — projected out of the frozen
    # snapshot. Only workshop fields cross; commercial data never leaves
    # the documentary context.
    output["making"] = None
    if order["project_version_id"]:
        position_id = _decoded(order["payload_json"]).get("position_id")
        with documentary_backend():
            snapshot = one(
                """
                SELECT snapshot_json::text FROM public.project_versions
                WHERE id = %s AND org_id = %s
                """,
                [str(order["project_version_id"]), str(org_id)],
                "work_order_not_found",
            )
        sealed_snapshot = _decoded(snapshot.get("snapshot_json"))
        sealed_positions = sealed_snapshot.get("positions") or []
        # The sealed project's delivery address prefills the delivery form —
        # workshop data only; the commercial fields stay out of the payload.
        output["delivery_address"] = (
            sealed_snapshot.get("project") or {}
        ).get("delivery_address")
        sealed = next(
            (
                pos
                for pos in sealed_positions
                if isinstance(pos, dict) and str(pos.get("id")) == str(position_id)
            ),
            None,
        )
        if sealed:
            output["making"] = {
                key: sealed.get(key)
                for key in (
                    "position_index", "code", "typology", "quantity",
                    "width_mm", "height_mm", "color_interior",
                    "color_exterior", "location_tag",
                )
            }
    output["steps"] = [_public_step(step) for step in steps]
    output["events"] = [
        {
            "id": str(event["id"]),
            "step_id": str(event["step_id"]) if event["step_id"] else None,
            "step_code": event.get("step_code"),
            "event": event["event"],
            "actor_id": str(event["actor_id"]) if event["actor_id"] else None,
            "actor_label": event.get("actor_label"),
            # JSONB may surface as a raw string through this cursor — decode so
            # the client reads payload.qc_item / payload.note, not a blob.
            "payload": _decoded(event["payload"]),
            "created_at": event["created_at"],
        }
        for event in events
    ]
    return output


def _refresh_order_status(*, org_id: UUID, order_id: UUID, actor_id: UUID) -> str:
    previous = one(
        """
        SELECT status::text AS status FROM public.orders
        WHERE id = %s AND org_id = %s
        """,
        [str(order_id), str(org_id)],
        "work_order_not_found",
    )
    totals = one(
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE status = 'DONE') AS done,
               COUNT(*) FILTER (WHERE status = 'BLOCKED') AS blocked,
               COUNT(*) FILTER (WHERE status = 'IN_PROGRESS') AS in_progress
        FROM public.production_steps WHERE order_id = %s AND org_id = %s
        """,
        [str(order_id), str(org_id)],
        "production_steps_missing",
    )
    if totals["total"] == 0:
        new_status = "RELEASED"
    elif totals["done"] == totals["total"]:
        new_status = "COMPLETED"
    elif totals["blocked"] > 0:
        new_status = "HOLD"
    elif totals["done"] > 0 or totals["in_progress"] > 0:
        new_status = "IN_PROGRESS"
    else:
        new_status = "RELEASED"
    updated = one(
        """
        UPDATE public.orders SET status = %s::order_status, updated_at = %s
        WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
        RETURNING status::text
        """,
        [new_status, datetime.now(timezone.utc), str(order_id), str(org_id)],
        "work_order_not_found",
    )
    if new_status == "COMPLETED":
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id)
            SELECT %s, %s, 'WO_COMPLETED', %s
            WHERE NOT EXISTS (
                SELECT 1 FROM public.production_step_events
                WHERE order_id = %s AND event = 'WO_COMPLETED')
            RETURNING id
            """,
            [str(org_id), str(order_id), str(actor_id), str(order_id)],
        )
    elif new_status == "HOLD" and str(previous["status"]) != "HOLD":
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id)
            VALUES (%s, %s, 'WO_HOLD', %s)
            RETURNING id
            """,
            [str(org_id), str(order_id), str(actor_id)],
        )
    return str(updated["status"])


def transition_step(
    *,
    org_id: UUID,
    step_id: UUID,
    action: str,
    actor_id: UUID,
    note: str | None,
    qc_result: str | None = None,
    qc_check: dict[str, object] | None = None,
    qc_item: str | None = None,
    actor_role: str | None = None,
    ops_done: list[str] | None = None,
) -> dict[str, object]:
    if action not in _TRANSITIONS:
        raise DocumentaryError("step_action_unknown")
    if qc_item is not None:
        qc_item = str(qc_item).strip()[:50] or None
        if qc_item and qc_result != "FAIL":
            raise DocumentaryError("qc_item_requires_fail")
    if action == "NOTE" and not (note or "").strip():
        raise DocumentaryError("step_note_required")
    if action == "BLOCK" and not (note or "").strip():
        # A blocked step without a reason is a dead end on the floor — the
        # note IS the instruction for whoever unblocks it.
        raise DocumentaryError("step_note_required")
    if action == "QC_CHECK":
        if not qc_check or not str(qc_check.get("check") or "").strip():
            raise DocumentaryError("qc_check_required")
        if qc_check.get("result") not in ("PASS", "FAIL"):
            raise DocumentaryError("qc_check_result_invalid")
        qc_check = {
            "check": str(qc_check["check"]).strip()[:200],
            "expected": str(qc_check.get("expected") or "").strip()[:100],
            "actual": str(qc_check.get("actual") or "").strip()[:100],
            "item_code": str(qc_check.get("item_code") or "").strip()[:50],
            "result": qc_check["result"],
        }
    elif qc_check is not None:
        raise DocumentaryError("step_transition_invalid")
    with transaction.atomic(), documentary_backend():
        step_ref = one(
            """
            SELECT order_id FROM public.production_steps
            WHERE id = %s AND org_id = %s
            """,
            [str(step_id), str(org_id)],
            "production_step_not_found",
        )
        # Lock the parent order before any step mutation so all transitions on
        # this order serialize — the status aggregate then sees prior commits.
        order = one(
            """
            SELECT id, status::text, payload_json, project_version_id
            FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(step_ref["order_id"]), str(org_id)],
            "work_order_not_found",
        )
        step = one(
            """
            SELECT s.id, s.order_id, s.status, s.sequence, s.code, s.label,
                   s.work_center_id, s.started_at, s.finished_at, s.actor_id, s.note,
                   w.code AS work_center_code, w.name AS work_center_name
            FROM public.production_steps s
            LEFT JOIN public.work_centers w ON w.id = s.work_center_id
            WHERE s.id = %s AND s.org_id = %s FOR UPDATE OF s
            """,
            [str(step_id), str(org_id)],
            "production_step_not_found",
        )
        # Producer/verifier separation: the QC *decision* (COMPLETE, pass or
        # fail) belongs to a supervisor — the operator who ran the station
        # must not sign off on their own work. Recording a measurement
        # (QC_CHECK) stays open so it can be logged mid-task.
        if (
            str(step["code"]) == "QC"
            and action == "COMPLETE"
            and actor_role not in _QC_STEP_ACTORS
        ):
            raise DocumentaryError(
                "qc_requires_supervisor",
                detail=(
                    "El control de calidad solo lo firma un encargado "
                    "(propietario o jefe de taller), no el operador que "
                    "ejecutó el trabajo."
                ),
            )
        if str(order["status"]) == "INSTALLED":
            raise DocumentaryError("work_order_installed")
        if str(order["status"]) == "DISPATCHED":
            raise DocumentaryError("work_order_dispatched")
        if str(order["status"]) == "COMPLETED":
            raise DocumentaryError("work_order_completed")
        if qc_result is not None and not (
            action == "COMPLETE" and str(step["code"]) == "QC"
        ):
            raise DocumentaryError("step_transition_invalid")
        if action == "QC_CHECK" and str(step["code"]) != "QC":
            raise DocumentaryError("step_transition_invalid")
        new_status, allowed = _TRANSITIONS[action]
        if action == "COMPLETE" and qc_result == "FAIL":
            new_status = "BLOCKED"
        if str(step["status"]) not in allowed:
            raise DocumentaryError("step_transition_invalid")
        # Routing is sequential: a station may only start once every earlier
        # step finished — otherwise GLAZE could run before CUT and the stepper
        # was decorative rather than a sequence (review WM1).
        if action == "START":
            pending_earlier = one(
                """
                SELECT COUNT(*)::int AS remaining FROM public.production_steps
                WHERE order_id = %s AND org_id = %s AND sequence < %s AND status <> 'DONE'
                """,
                [str(step["order_id"]), str(org_id), step["sequence"]],
                "production_step_not_found",
            )
            if int(pending_earlier["remaining"]) > 0:
                raise DocumentaryError("step_sequence_blocked")
        # A step released while its center was inactive — or copied unassigned
        # into a remake — sits READY/PENDING without a center and must never
        # silently progress. When a center of the required kind has since been
        # activated the step adopts it here and the order's payload blocker
        # clears; otherwise the transition refuses and the blocker stays the
        # shop's to-do. Station assignment surfaces before the cut-plan gate:
        # "no saw bench" is the earlier answer to give.
        if (
            action in ("START", "COMPLETE")
            and str(step["status"]) in ("READY", "PENDING")
            and step.get("work_center_id") is None
        ):
            # step.code is the station code (WELD, GLAZE…); work_centers.kind
            # is the step vocabulary (WELDING, GLAZING…).
            kind = _CENTER_KIND_FOR_STATION.get(str(step["code"]))
            if kind is not None:
                center = rows(
                    """
                    SELECT id, code, name FROM public.work_centers
                    WHERE org_id = %s AND kind = %s AND active ORDER BY code LIMIT 1
                    """,
                    [str(org_id), kind],
                )
                if not center:
                    raise DocumentaryError("work_center_unassigned")
                rows(
                    "UPDATE public.production_steps SET work_center_id = %s WHERE id = %s",
                    [str(center[0]["id"]), str(step_id)],
                )
                step["work_center_id"] = center[0]["id"]
                step["work_center_code"] = center[0]["code"]
                step["work_center_name"] = center[0]["name"]
                rows(
                    """
                    UPDATE public.orders
                    SET payload_json = jsonb_set(
                        payload_json, '{blockers}',
                        COALESCE((
                            SELECT jsonb_agg(b) FROM jsonb_array_elements_text(
                                payload_json->'blockers') b
                            WHERE b <> %s
                        ), '[]'::jsonb))
                    WHERE id = %s
                    """,
                    [f"work_center_inactive:{kind}", str(order["id"])],
                )
        # Starting a station that physically works the sealed plan without
        # a usable cut plan is a trap: COMPLETE then refuses (no plan)
        # while replan refuses (a physical step already in progress) — the
        # order only escapes via block/unblock. You can't start the saw —
        # or the machining cell — without a live plan.
        if action == "START" and (
            str(step["code"]) in _STEP_CONSUMED_KINDS
            or str(step["code"]) in _PLAN_REQUIRED_STATIONS
        ):
            opt = _decoded(order.get("payload_json")).get("optimization") or {}
            if not opt or opt.get("invalidated"):
                raise DocumentaryError(
                    "work_order_plan_missing",
                    detail=(
                        "La orden no tiene un plan de corte vigente: "
                        "optimízala antes de iniciar este paso."
                    ),
                )
        # Completing a member-op station carries per-operation evidence:
        # every machining op routed to this station must be declared — the
        # event records WHICH ops ran, not just that someone pressed done.
        ops_executed: list[str] | None = None
        if (
            action == "COMPLETE"
            and str(step["code"]) in _OPS_EVIDENCE_STATIONS
        ):
            expected = _member_ops_for_station(
                org_id=org_id, order=order, station=str(step["code"])
            )
            if expected:
                declared = {str(item) for item in (ops_done or [])}
                unknown = sorted(declared - set(expected))
                if unknown:
                    raise DocumentaryError(
                        "step_ops_unknown",
                        detail=(
                            "Se declararon operaciones que no pertenecen a "
                            "esta estación: " + ", ".join(unknown)
                        ),
                    )
                missing = [
                    op_id for op_id in sorted(expected) if op_id not in declared
                ]
                if missing:
                    raise DocumentaryError(
                        "step_ops_incomplete",
                        detail=(
                            "Faltan operaciones por declarar en este paso: "
                            + ", ".join(expected[op_id] for op_id in missing)
                        ),
                        extra={"missing_operations": missing},
                    )
                ops_executed = sorted(declared)
        # A plan-only station must still refuse a dead plan at COMPLETE —
        # stock-settling stations take the same check through
        # _STEP_CONSUMED_KINDS below.
        if (
            new_status == "DONE"
            and str(step["code"]) in _PLAN_REQUIRED_STATIONS
        ):
            opt_done = _decoded(order.get("payload_json")).get("optimization") or {}
            if not opt_done:
                raise DocumentaryError(
                    "work_order_plan_missing",
                    detail=(
                        "La orden no tiene un plan de corte: optimízala "
                        "antes de completar este paso."
                    ),
                )
            if opt_done.get("invalidated"):
                raise DocumentaryError(
                    "work_order_plan_stale",
                    detail=(
                        "El plan de corte quedó invalidado: vuelve a "
                        "optimizar la orden antes de completar este paso."
                    ),
                )
        event_name = "QC_FAILED" if (
            action == "COMPLETE" and qc_result == "FAIL"
        ) else _EVENTS[action]
        now = datetime.now(timezone.utc)
        if new_status is not None:
            # UNBLOCK resolves the blocking reason — a stale failure note
            # must not follow the step into re-work (the event log keeps the
            # history); an explicit unblock note still wins.
            clears_block_note = (
                new_status == "READY" and str(step["status"]) == "BLOCKED"
            )
            updates = {
                "status": new_status,
                "updated_at": now,
                "note": (
                    note.strip()
                    if note is not None
                    else (None if clears_block_note else step.get("note"))
                ),
            }
            if new_status == "IN_PROGRESS":
                updates["started_at"] = step.get("started_at") or now
                updates["actor_id"] = actor_id
            elif new_status == "DONE":
                updates["finished_at"] = now
                updates["actor_id"] = actor_id
            elif new_status == "BLOCKED":
                updates["actor_id"] = actor_id
            rows(
                """
                UPDATE public.production_steps
                SET status = %(status)s, updated_at = %(updated_at)s, note = %(note)s,
                    started_at = COALESCE(%(started_at)s, started_at),
                    finished_at = COALESCE(%(finished_at)s, finished_at),
                    actor_id = COALESCE(%(actor_id)s, actor_id)
                WHERE id = %(id)s
                RETURNING id
                """,
                {
                    "status": updates["status"],
                    "updated_at": updates["updated_at"],
                    "note": updates["note"],
                    "started_at": updates.get("started_at"),
                    "finished_at": updates.get("finished_at"),
                    "actor_id": updates.get("actor_id"),
                    "id": str(step_id),
                },
            )
        elif note is not None:
            rows(
                "UPDATE public.production_steps SET note = %s, updated_at = %s WHERE id = %s RETURNING id",
                [note, now, str(step_id)],
            )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, step_id, event, actor_id, payload)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(step["order_id"]),
                str(step_id),
                event_name,
                str(actor_id),
                json.dumps({
                    **({"note": note.strip()} if note else {}),
                    **({"qc_result": qc_result} if qc_result else {}),
                    **({"qc_check": qc_check} if qc_check else {}),
                    **({"qc_item": qc_item} if qc_item else {}),
                    **(
                        {"ops_executed": ops_executed}
                        if ops_executed is not None
                        else {}
                    ),
                }),
            ],
        )
        # §6: completing CUT is where the physical drop goes on the saw —
        # reserved remnants consume and the plan's usable remainders return
        # to stock under this order's provenance, once.
        if new_status == "DONE" and str(step["code"]) == "CUT":
            payload_row = one(
                """
                SELECT payload_json FROM public.orders
                WHERE id = %s AND org_id = %s
                """,
                [str(step["order_id"]), str(org_id)],
                "work_order_not_found",
            )
            optimization = (_decoded(payload_row["payload_json"]).get("optimization") or {})
            plan_remnants = optimization.get("remnants") or {}
            # Every remnant the plan claims must still be RESERVED for this
            # order — an operator can unreserve a drop manually, and another
            # order may then have taken it; completing on the stale plan
            # would settle stock the saw never had.
            planned_ids = {
                str(entry["id"])
                for entry in (plan_remnants.get("consumed") or [])
                if entry.get("id")
            }
            if planned_ids:
                still_reserved = rows(
                    """
                    SELECT id FROM public.inventory_remnants
                    WHERE org_id = %s AND reserved_order_id = %s
                      AND status = 'RESERVED' AND id = ANY(%s::uuid[])
                    """,
                    [str(org_id), str(step["order_id"]), sorted(planned_ids)],
                )
                if {str(r["id"]) for r in still_reserved} != planned_ids:
                    raise DocumentaryError("work_order_remnant_released")
            consumed = remnants_service.consume_order_remnants(
                org_id=org_id, order_id=step["order_id"]
            )
            produced = 0
            # Produced remnants are written only once per order — a CUT
            # resume/complete cycle can never double the ledger.
            already = rows(
                """
                SELECT id FROM public.inventory_remnants
                WHERE org_id = %s AND origin_order_id = %s AND origin = 'PRODUCTION'
                LIMIT 1
                """,
                [str(org_id), str(step["order_id"])],
            )
            if not already and (
                plan_remnants.get("produced_bars")
                or plan_remnants.get("produced_sheets")
            ):
                produced = remnants_service.record_produced_remnants(
                    org_id=org_id, order_id=step["order_id"],
                    produced_bars=plan_remnants.get("produced_bars") or [],
                    produced_sheets=plan_remnants.get("produced_sheets") or [],
                )
            if consumed or produced:
                rows(
                    """
                    INSERT INTO public.production_step_events(org_id, order_id, step_id, event, actor_id, payload)
                    VALUES (%s, %s, %s, 'WO_REMNANTS_SETTLED', %s, %s::jsonb)
                    RETURNING id
                    """,
                    [
                        str(org_id),
                        str(step["order_id"]),
                        str(step_id),
                        str(actor_id),
                        json.dumps({
                            "consumed": consumed,
                            "produced": produced,
                        }),
                    ],
                )
        # §10 consumption: completing a step settles the stock reservations
        # of the kinds that step physically uses — CONSUMPTION movements on
        # the ledger, reservation entries stamped consumed_at in the plan.
        consumed_kinds = _STEP_CONSUMED_KINDS.get(str(step["code"]))
        if new_status == "DONE" and consumed_kinds:
            payload_row = one(
                """
                SELECT payload_json FROM public.orders
                WHERE id = %s AND org_id = %s
                """,
                [str(step["order_id"]), str(org_id)],
                "work_order_not_found",
            )
            payload_full = _decoded(payload_row["payload_json"])
            opt = payload_full.get("optimization") or {}
            if not opt:
                # A material-consuming step needs the optimization record:
                # without it the order would complete with no material
                # accounting whatsoever — not even a partial reservation.
                raise DocumentaryError(
                    "work_order_plan_missing",
                    detail="La orden no tiene un plan de corte: optimízala antes de completar este paso.",
                )
            if opt.get("invalidated"):
                # A released remnant (or any other stock change) voids the
                # claim the layout carried — completing against it would settle
                # reservations for stock the plan can no longer prove exists.
                raise DocumentaryError(
                    "work_order_plan_stale",
                    detail=(
                        "El plan de corte perdió material reservado: "
                        "vuelve a optimizar la orden antes de completar este paso."
                    ),
                )
            reservations = opt.get("stock_reservations") or []
            # A consuming step can only complete when its material is fully
            # accounted for: a short reservation, a piece no stock could
            # host, or a sku with no stock mapping means the physical order
            # is incomplete — refuse instead of settling only the reserved
            # part and letting the order reach completion.
            short_entries = [
                entry for entry in reservations
                if entry.get("kind") in consumed_kinds
                and not entry.get("consumed_at")
                and entry.get("short") not in (None, "", "0", "0.00")
            ]
            unplaced_plan = (
                "BAR" in consumed_kinds
                and bool((opt.get("bars") or {}).get("unplaced"))
            ) or (
                "SHEET" in consumed_kinds
                and any(
                    entry.get("reason") not in _PURCHASED_UNNESTED_REASONS
                    for entry in (opt.get("unnested") or [])
                )
            )
            if short_entries or unplaced_plan or opt.get("unmapped_stock_skus"):
                raise DocumentaryError(
                    "work_order_material_shortage",
                    detail=(
                        "La orden no tiene material suficiente para completar este paso: "
                        "revisa los faltantes de la reserva, las piezas sin ubicar y los "
                        "materiales sin equivalencia de stock en Compras."
                    ),
                    extra={
                        "short_skus": sorted({
                            str(entry.get("sku"))
                            for entry in short_entries
                            if entry.get("sku")
                        }),
                        "unmapped_stock_skus": sorted(
                            opt.get("unmapped_stock_skus") or []
                        ),
                        "unplaced": sorted({
                            kind
                            for kind, blocked in (
                                ("BAR", bool((opt.get("bars") or {}).get("unplaced"))),
                                (
                                    "SHEET",
                                    any(
                                        entry.get("reason")
                                        not in _PURCHASED_UNNESTED_REASONS
                                        for entry in (opt.get("unnested") or [])
                                    ),
                                ),
                            )
                            if blocked and kind in consumed_kinds
                        }),
                    },
                )
            open_entries = [
                entry for entry in reservations
                if entry.get("kind") in consumed_kinds
                and not entry.get("consumed_at")
                and entry.get("reserved") not in (None, "", "0", "0.00")
            ]
            if open_entries:
                settled = production_stock.consume_for_order(
                    org_id=org_id,
                    order_id=step["order_id"],
                    actor_id=actor_id,
                    kinds=consumed_kinds,
                    reservations=reservations,
                )
                opt["stock_reservations"] = settled
                payload_full["optimization"] = opt
                rows(
                    """
                    UPDATE public.orders SET payload_json = %s::jsonb, updated_at = %s
                    WHERE id = %s AND org_id = %s
                    RETURNING id
                    """,
                    [
                        json.dumps(payload_full),
                        datetime.now(timezone.utc),
                        str(step["order_id"]),
                        str(org_id),
                    ],
                )
                rows(
                    """
                    INSERT INTO public.production_step_events(org_id, order_id, step_id, event, actor_id, payload)
                    VALUES (%s, %s, %s, 'WO_STOCK_CONSUMED', %s, %s::jsonb)
                    RETURNING id
                    """,
                    [
                        str(org_id),
                        str(step["order_id"]),
                        str(step_id),
                        str(actor_id),
                        json.dumps({
                            "consumed": [
                                {"sku": e["sku"], "qty": e["reserved"],
                                 "kind": e["kind"]}
                                for e in open_entries
                            ],
                        }),
                    ],
                )
        order_status = _refresh_order_status(
            org_id=org_id, order_id=step["order_id"], actor_id=actor_id
        )
        fresh = one(
            """
            SELECT s.id, s.sequence, s.code, s.label, s.status, s.work_center_id,
                   w.code AS work_center_code, w.name AS work_center_name, s.started_at, s.finished_at, s.actor_id, s.note
            FROM public.production_steps s
            LEFT JOIN public.work_centers w ON w.id = s.work_center_id
            WHERE s.id = %s
            """,
            [str(step_id)],
        )
        # §08: a completed station queues the next-step notice — recomputed
        # when the job runs so a retried task reports the true successor.
        if new_status == "DONE":
            from automations.service import emit

            emit(
                "automation.step_advance",
                org_id=org_id,
                actor_id=actor_id,
                idempotency_key=f"auto:step:{step_id}:done",
                order_id=str(step["order_id"]),
                step_code=str(step["code"]),
            )
        return {"step": _public_step(fresh), "order_status": order_status}


def create_remake(
    *, org_id: UUID, order_id: UUID, actor_id: UUID, note: str | None = None
) -> dict[str, object]:
    """Remake work order for a unit that failed QC: copies the sealed material
    projection and routing from a HOLD order into a new ``-RM-`` order. The
    unique release index excludes remakes (``remake_of`` in payload)."""
    with transaction.atomic(), documentary_backend():
        source = one(
            """
            SELECT id, order_code, status::text, payload_json, project_id,
                   project_version_id
            FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if str(source["status"]) != "HOLD":
            raise DocumentaryError("remake_requires_hold")
        payload = _decoded(source["payload_json"])
        payload.pop("optimization", None)  # stale plan — re-optimize the remake
        payload.pop("cnc_export", None)
        payload.pop("dxf_export", None)
        payload.pop("operations_export", None)
        payload.pop("packing", None)  # labels carry the source order code
        # The source order's blockers were resolved there — a remake starts
        # clean and re-derives its own (a deactivated center lands below).
        payload.pop("blockers", None)
        payload["remake_of"] = str(source["id"])
        # Carry the QC failure forward: the remake order names WHICH unit
        # failed and why, so the floor doesn't re-derive it from the source
        # order's history (review PM-H3).
        failure_rows = rows(
            """
            SELECT payload FROM public.production_step_events
            WHERE org_id = %s AND order_id = %s
              AND payload->>'qc_result' = 'FAIL'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [str(org_id), str(source["id"])],
        )
        if failure_rows:
            failure_payload = _decoded(failure_rows[0].get("payload"))
            reason = {
                "qc_item": failure_payload.get("qc_item"),
                "note": failure_payload.get("note"),
            }
            if reason["qc_item"] or reason["note"]:
                payload["remake_reason"] = reason
        prior = one(
            """
            SELECT COUNT(*) AS n FROM public.orders
            WHERE org_id = %s AND payload_json->>'remake_of' = %s
            """,
            [str(org_id), str(source["id"])],
            "remake_count_unknown",
        )
        # Truncate the source portion, not the suffix — the -RM-nn counter is
        # what distinguishes remakes under the org-unique order_code. When the
        # source fills the 50-char bound, embed a stable id fragment so two
        # long sources sharing the retained prefix still get distinct codes.
        suffix = f"-RM-{int(prior['n']) + 1:02d}"
        source_code = str(source["order_code"])
        if len(source_code) + len(suffix) <= 50:
            order_code = f"{source_code}{suffix}"
        else:
            marker = str(source["id"]).replace("-", "").upper()
            order_code = f"{source_code[: 50 - len(suffix) - 33]}-{marker}{suffix}"
        remake = one(
            """
            INSERT INTO public.orders(
                org_id, project_id, order_type, order_code, status,
                payload_json, project_version_id)
            VALUES (%s, %s, 'WORKSHOP_OT', %s, 'RELEASED', %s::jsonb, %s)
            RETURNING id, order_code
            """,
            [
                str(org_id),
                str(source["project_id"]),
                order_code,
                json.dumps(payload),
                str(source["project_version_id"]) if source["project_version_id"] else None,
            ],
            "remake_not_created",
        )
        rows(
            """
            INSERT INTO public.production_steps(
                org_id, order_id, sequence, work_center_id, code, label)
            SELECT %s, %s, sequence, work_center_id, code, label
            FROM public.production_steps
            WHERE order_id = %s AND org_id = %s ORDER BY sequence
            RETURNING id
            """,
            [str(org_id), str(remake["id"]), str(source["id"]), str(org_id)],
        )
        # A copied step assignment pointing at a center deactivated since the
        # source order must not silently route to a dead station: null it so
        # the START-time adoption picks a live center (or names the missing
        # kind), and carry the same blocker the release path would write.
        dropped_centers = rows(
            """
            UPDATE public.production_steps s
            SET work_center_id = NULL
            FROM public.work_centers w
            WHERE s.order_id = %s AND s.org_id = %s
              AND s.work_center_id = w.id AND w.active = FALSE
            RETURNING s.code
            """,
            [str(remake["id"]), str(org_id)],
        )
        if dropped_centers:
            inactive_blockers = [
                f"work_center_inactive:{_CENTER_KIND_FOR_STATION[str(row['code'])]}"
                for row in dropped_centers
                if row.get("code") and str(row["code"]) in _CENTER_KIND_FOR_STATION
            ]
            if inactive_blockers:
                payload["blockers"] = inactive_blockers
                rows(
                    """
                    UPDATE public.orders SET payload_json = %s::jsonb
                    WHERE id = %s AND org_id = %s RETURNING id
                    """,
                    [json.dumps(payload), str(remake["id"]), str(org_id)],
                )
        rows(
            """
            INSERT INTO public.production_step_events(
                org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_REMADE', %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(remake["id"]),
                str(actor_id),
                json.dumps({
                    "remake_of": str(source["id"]),
                    "source_order_code": source["order_code"],
                    "note": (note or "").strip() or None,
                    "qc_item": (payload.get("remake_reason") or {}).get("qc_item"),
                }),
            ],
        )
        return get_work_order(org_id=org_id, order_id=UUID(str(remake["id"])))


def list_work_centers(*, org_id: UUID) -> dict[str, object]:
    _ensure_work_centers(org_id)
    return {
        "centers": rows(
            """
            SELECT id, code, name, kind, display_order, active
            FROM public.work_centers WHERE org_id = %s ORDER BY display_order
            """,
            [str(org_id)],
        )
    }


def _reinforcement_angle_map(
    version_snapshot: dict[str, object], position_id: str | None
) -> dict[tuple[str, str, str, str | None, str | None], tuple[str, str] | None]:
    """Authoritative reinforcement end angles from the sealed manufacturing
    facts: fact -> parent member gives (role, bay, leaf); the key joins on
    (workshop_sku, cut_length_mm, role, bay_id, leaf_id). A key reached by
    conflicting facts is marked ambiguous (None) so the export refuses to
    invent an angle."""
    angle_map: dict[
        tuple[str, str, str, str | None, str | None], tuple[str, str] | None
    ] = {}
    for unit in version_snapshot.get("manufacturing") or []:
        if position_id and str(unit.get("position_id")) != position_id:
            continue
        members = {
            str(member.get("member_id")): member
            for member in unit.get("members") or []
        }
        for reinforcement in unit.get("reinforcements") or []:
            parent = members.get(str(reinforcement.get("parent_member_id")))
            if parent is None:
                continue
            key = (
                str(reinforcement.get("workshop_sku")),
                str(reinforcement.get("cut_length_mm")),
                str((parent.get("identity") or {}).get("role")),
                parent.get("bay_id"),
                parent.get("leaf_id"),
            )
            angles = (
                str(reinforcement.get("angle_left")),
                str(reinforcement.get("angle_right")),
            )
            if key in angle_map and angle_map[key] != angles:
                angle_map[key] = None  # ambiguous — must not be guessed
            else:
                angle_map[key] = angles
    return angle_map


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    escaped = text.replace('"', '""')
    return f'"{escaped}"' if any(c in text for c in '",\n') else text


def _cnc_bars_csv(
    optimization: dict[str, object],
    *,
    cut_map: dict[tuple[str, ...], str] | None = None,
) -> str:
    """DEKOPEN-CNC-BARS-V1: one row per cut placement, ordered by bar then
    position inside the bar — deterministic output for the saw operator.
    ``piece_label`` carries the printed shop code (M-xx/R-xx) so the saw
    file reconciles against a labeled stick without a second document."""
    rows_out = [
        "bar_index,stock_sku,stock_length_mm,sequence_in_bar,piece_label,piece_id,"
        "cut_length_mm,angle_left_deg,angle_right_deg,"
        "unit_index,bay_id,leaf_id,source_position_id"
    ]
    bars = (optimization.get("bars") or {}).get("workshop_cut_plan") or []
    for bar in sorted(bars, key=lambda b: int(b.get("bar_index") or 0)):
        for cut in sorted(
            bar.get("cuts") or [],
            key=lambda c: int(c.get("sequence") or 0),
        ):
            if (
                str(cut.get("source_kind") or "") == "REINFORCEMENT"
                and (cut.get("angle_left") is None or cut.get("angle_right") is None)
            ):
                raise DocumentaryError("cnc_incomplete_cut_angles")
            rows_out.append(",".join(_csv_cell(v) for v in (
                bar.get("bar_index"),
                bar.get("commercial_sku"),
                bar.get("stock_length_mm"),
                cut.get("sequence"),
                (cut_map or {}).get(_cut_key(cut), ""),
                cut.get("piece_id"),
                cut.get("length_mm"),
                cut.get("angle_left"),
                cut.get("angle_right"),
                cut.get("unit_index"),
                cut.get("bay_id"),
                cut.get("leaf_id"),
                cut.get("source_position_id"),
            )))
    return "\n".join(rows_out) + "\n"


def _cnc_sheets_csv(optimization: dict[str, object]) -> str:
    """DEKOPEN-CNC-SHEETS-V1: one row per nested placement, ordered by sheet
    then Y then X — deterministic input for a panel saw / glass table."""
    rows_out = [
        "sheet_index,purchasing_sku,sheet_width_mm,sheet_height_mm,"
        "x_mm,y_mm,width_mm,height_mm,rotated,piece_id,unit_index,bay_id,leaf_id"
    ]
    for sheet in sorted(
        optimization.get("sheets") or [], key=lambda s: int(s.get("sheet_index") or 0)
    ):
        for placement in sorted(
            sheet.get("placements") or [],
            key=lambda p: (
                Decimal(str(p.get("y_mm") or 0)), Decimal(str(p.get("x_mm") or 0))
            ),
        ):
            rows_out.append(",".join(_csv_cell(v) for v in (
                sheet.get("sheet_index"),
                sheet.get("purchasing_sku"),
                sheet.get("sheet_width_mm"),
                sheet.get("sheet_height_mm"),
                placement.get("x_mm"),
                placement.get("y_mm"),
                placement.get("width_mm"),
                placement.get("height_mm"),
                placement.get("rotated"),
                placement.get("piece_id"),
                placement.get("unit_index"),
                placement.get("bay_id"),
                placement.get("leaf_id"),
            )))
    return "\n".join(rows_out) + "\n"


# Settlement stamps (consumed_at on stock_reservations), wall-clock data
# (optimized_at, actor_id) and measured runtime are bookkeeping, not plan
# geometry — a file rendered pre-cut must still serve after CUT-DONE marks
# its stock consumed, and re-running an identical plan must fingerprint
# identically. Everything else — layouts, reservations, the invalidated
# flag — stays inside the fingerprint.
_FINGERPRINT_VOLATILE = frozenset({
    "consumed_at", "optimized_at", "actor_id", "runtime_ms",
})


def _fingerprint_clean(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _fingerprint_clean(item)
            for key, item in value.items()
            if key not in _FINGERPRINT_VOLATILE
        }
    if isinstance(value, list):
        return [_fingerprint_clean(item) for item in value]
    return value


def _optimization_fingerprint(optimization: dict[str, object]) -> str:
    canonical = json.dumps(
        _fingerprint_clean(optimization), sort_keys=True, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def export_cnc_files(
    *, org_id: UUID, order_id: UUID, actor_id: UUID
) -> dict[str, object]:
    """Machine handoff: renders the stored optimization plan into deterministic
    CSV cut files (bars + sheets), stores them on the order, and records a
    ``WO_CNC_EXPORTED`` event. Requires a prior optimization run."""
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text, payload_json,
                   project_version_id FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if str(order["status"]) == "INSTALLED":
            raise DocumentaryError("work_order_installed")
        if str(order["status"]) == "DISPATCHED":
            raise DocumentaryError("work_order_dispatched")
        if str(order["status"]) == "COMPLETED":
            raise DocumentaryError("work_order_completed")
        payload = _decoded(order["payload_json"])
        optimization = payload.get("optimization")
        if not isinstance(optimization, dict) or not optimization.get("bars"):
            raise DocumentaryError("cnc_requires_optimization")
        if optimization.get("invalidated"):
            raise DocumentaryError("plan_invalidated")
        # Printed piece codes join the saw rows so a labeled stick finds its
        # program line without a second file.
        cnc_cut_map: dict[tuple[str, ...], str] = {}
        if order.get("project_version_id"):
            version_row = one(
                """
                SELECT snapshot_json::text AS snapshot_json
                FROM public.project_versions WHERE id = %s AND org_id = %s
                """,
                [str(order["project_version_id"]), str(org_id)],
                "work_order_missing_version",
            )
            cnc_snapshot = _decoded(version_row["snapshot_json"])
            try:
                cnc_labels = _piece_labels(cnc_snapshot)
                cnc_cut_map = _cut_member_map(cnc_snapshot, cnc_labels)
            except DocumentaryError:
                cnc_cut_map = {}
        fingerprint = _optimization_fingerprint(optimization)
        header = (
            f"# dekopen order={order['order_code']} plan={fingerprint[:12]}"
            f" emitted={datetime.now(timezone.utc).isoformat()}\n"
        )
        files = {"bars.csv": header + _cnc_bars_csv(optimization, cut_map=cnc_cut_map)}
        if optimization.get("sheets"):
            files["sheets.csv"] = header + _cnc_sheets_csv(optimization)
        export = {
            "schema": "work_order_cnc_export_v2",
            "optimization_fingerprint": fingerprint,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "actor_id": str(actor_id),
            "files": files,
        }
        new_payload = {**payload, "cnc_export": export}
        rows(
            """
            UPDATE public.orders SET payload_json = %s::jsonb, updated_at = %s
            WHERE id = %s AND org_id = %s
            RETURNING id
            """,
            [json.dumps(new_payload), datetime.now(timezone.utc),
             str(order_id), str(org_id)],
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_CNC_EXPORTED', %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps({
                    "order_code": order["order_code"],
                    "files": sorted(files),
                }),
            ],
        )
        return {
            "order_id": str(order_id),
            "order_code": order["order_code"],
            "exported_at": export["exported_at"],
            "files": files,
        }


def cnc_file_content(
    *, org_id: UUID, order_id: UUID, filename: str
) -> tuple[str, str] | None:
    order = one(
        """
        SELECT order_code, payload_json FROM public.orders
        WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
        """,
        [str(order_id), str(org_id)],
        "work_order_not_found",
    )
    payload = _decoded(order["payload_json"])
    export = payload.get("cnc_export") or {}
    optimization = payload.get("optimization")
    # The file exists but its plan moved on — say STALE, not 'not found':
    # a 'no file' answer sends the operator to re-download, a 'stale' answer
    # sends them to re-optimize.
    if isinstance(optimization, dict) and optimization.get("invalidated"):
        raise DocumentaryError(
            "cnc_file_stale",
            detail="El plan de corte quedó invalidado: reoptimiza y re-exporta la orden.",
        )
    fingerprint = (
        _optimization_fingerprint(optimization)
        if isinstance(optimization, dict)
        else ""
    )
    if (
        export.get("optimization_fingerprint")
        and fingerprint != export["optimization_fingerprint"]
    ):
        raise DocumentaryError(
            "cnc_file_stale",
            detail="El archivo corresponde a un plan anterior: reoptimiza y re-exporta la orden.",
        )
    files = export.get("files") or {}
    content = files.get(filename)
    if content is None:
        return None
    fp = str(export.get("optimization_fingerprint") or "")[:8]
    prefix = f"{order['order_code']}-{fp}" if fp else str(order["order_code"])
    return f"{prefix}-{filename}", content


def _ops_source_fingerprint(
    optimization: dict[str, object], manufacturing: list[object]
) -> str:
    return hashlib.sha256(
        json.dumps(
            {"optimization": _fingerprint_clean(optimization),
             "manufacturing": manufacturing},
            sort_keys=True, default=str,
        ).encode("utf-8")
    ).hexdigest()


def _raw_fact_units(
    version_snapshot: dict[str, object], position_id: str | None
) -> list[object]:
    return [
        unit for unit in (version_snapshot.get("manufacturing") or [])
        if not position_id or str(unit.get("position_id")) == position_id
    ]


def _operations_fact_units(
    version_snapshot: dict[str, object], position_id: str | None
) -> list[ManufacturingFactsV1]:
    return [
        ManufacturingFactsV1.model_validate_json(json.dumps(unit))
        for unit in _raw_fact_units(version_snapshot, position_id)
    ]


def export_operations(
    *, org_id: UUID, order_id: UUID, actor_id: UUID
) -> dict[str, object]:
    """§7 machine-neutral operations export: derives the sealed plan's
    manufacturing operations (saw boundaries, member machining with declared
    authority), renders the machine-neutral document, stores it on the order
    and records ``WO_OPS_EXPORTED``. Requires a prior optimization run."""
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text, payload_json,
                   project_version_id FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if str(order["status"]) == "INSTALLED":
            raise DocumentaryError("work_order_installed")
        if str(order["status"]) == "DISPATCHED":
            raise DocumentaryError("work_order_dispatched")
        if str(order["status"]) == "COMPLETED":
            raise DocumentaryError("work_order_completed")
        payload = _decoded(order["payload_json"])
        optimization = payload.get("optimization")
        if not isinstance(optimization, dict) or not optimization.get("bars"):
            raise DocumentaryError("operations_requires_optimization")
        if optimization.get("invalidated"):
            raise DocumentaryError("plan_invalidated")
        version_row = one(
            """
            SELECT snapshot_json FROM public.project_versions
            WHERE id = %s AND org_id = %s
            """,
            [str(order["project_version_id"]), str(org_id)],
            "work_order_missing_version",
        )
        version_snapshot = _decoded(version_row["snapshot_json"])
        fact_units = _operations_fact_units(
            version_snapshot,
            str(payload.get("position_id") or "") or None,
        )
        bars = [
            CutBar.model_validate_json(json.dumps(bar))
            for bar in (optimization.get("bars") or {}).get("workshop_cut_plan") or []
        ]
        ops = operations_from_plan(bars=bars, fact_units=fact_units)
        empty_labels: dict[str, dict[object, str]] = {
            key: {}
            for key in (
                "member", "reinforcement", "infill", "handle",
                "bay", "leaf", "leaf_fact", "position",
            )
        }
        try:
            labels = _piece_labels(version_snapshot)
        except DocumentaryError:
            labels = empty_labels
        cut_map = _cut_member_map(version_snapshot, labels)
        piece_labels = {
            str(mid): code for mid, code in labels["member"].items()
        }
        piece_labels.update(
            {str(rid): code for rid, code in labels["reinforcement"].items()}
        )
        for bar in (optimization.get("bars") or {}).get(
            "workshop_cut_plan"
        ) or []:
            for cut in (bar.get("cuts") or []) if isinstance(bar, dict) else []:
                if isinstance(cut, dict) and cut.get("piece_id"):
                    piece_labels[str(cut["piece_id"])] = cut_map.get(
                        _cut_key(cut), ""
                    )
        from production.trace import station_map_for

        station_map = station_map_for(payload, list({op.kind.value for op in ops}))
        document = ops_document(
            ops,
            order_code=str(order["order_code"]),
            plan_seed=(optimization.get("bars") or {}).get("plan_seed"),
            piece_labels=piece_labels,
        )
        # The routing the frozen authority declares travels inside the
        # document: a cell loading the file knows which station each op
        # belongs to without re-deriving it.
        document["station_map"] = station_map
        for op_row in document["operations"]:
            op_row["station"] = station_map.get(str(op_row["kind"]))
        rendered = NeutralOpsPostProcessor().render(document)
        files = {}
        fp = str(_ops_source_fingerprint(
            optimization,
            _raw_fact_units(
                version_snapshot, str(payload.get("position_id") or "") or None
            ),
        ))
        ops_header = (
            f"# dekopen order={order['order_code']} plan={fp[:12]}"
            f" emitted={datetime.now(timezone.utc).isoformat()}\n"
        )
        for name, content in rendered.items():
            files[name] = (
                ops_header + content if name.endswith(".csv") else content
            )
        manufacturing = _raw_fact_units(
            version_snapshot, str(payload.get("position_id") or "") or None
        )
        export = {
            "schema": "work_order_ops_export_v1",
            "source_fingerprint": _ops_source_fingerprint(
                optimization, manufacturing
            ),
            "machine": document["machine"],
            "operation_count": document["operation_count"],
            "counts_by_kind": document["counts_by_kind"],
            "unemitted_kinds": document["unemitted_kinds"],
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "actor_id": str(actor_id),
            "files": files,
        }
        new_payload = {**payload, "operations_export": export}
        rows(
            """
            UPDATE public.orders SET payload_json = %s::jsonb, updated_at = %s
            WHERE id = %s AND org_id = %s
            RETURNING id
            """,
            [json.dumps(new_payload), datetime.now(timezone.utc),
             str(order_id), str(org_id)],
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_OPS_EXPORTED', %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps({
                    "order_code": order["order_code"],
                    "files": sorted(files),
                    "operation_count": document["operation_count"],
                }),
            ],
        )
        return {
            "order_id": str(order_id),
            "order_code": order["order_code"],
            "exported_at": export["exported_at"],
            "operation_count": document["operation_count"],
            "counts_by_kind": document["counts_by_kind"],
            "files": files,
        }


def operations_file_content(
    *, org_id: UUID, order_id: UUID, filename: str
) -> tuple[str, str] | None:
    order = one(
        """
        SELECT order_code, payload_json, project_version_id FROM public.orders
        WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
        """,
        [str(order_id), str(org_id)],
        "work_order_not_found",
    )
    payload = _decoded(order["payload_json"])
    export = payload.get("operations_export") or {}
    optimization = payload.get("optimization")
    # The frozen snapshot is denied to the authenticated role — resolve it
    # through the documentary authority and keep only what the file needs.
    with documentary_backend():
        version_row = one(
            """
            SELECT snapshot_json FROM public.project_versions
            WHERE id = %s AND org_id = %s
            """,
            [str(order["project_version_id"]), str(org_id)],
            "work_order_missing_version",
        )
    version_snapshot = _decoded(version_row["snapshot_json"])
    manufacturing = _raw_fact_units(
        version_snapshot, str(payload.get("position_id") or "") or None
    )
    if isinstance(optimization, dict) and optimization.get("invalidated"):
        raise DocumentaryError(
            "ops_file_stale",
            detail="El plan de corte quedó invalidado: reoptimiza y re-exporta la orden.",
        )
    if (
        export.get("source_fingerprint")
        and _ops_source_fingerprint(
            optimization if isinstance(optimization, dict) else {},
            manufacturing,
        )
        != export["source_fingerprint"]
    ):
        raise DocumentaryError(
            "ops_file_stale",
            detail="El archivo corresponde a un plan anterior: reoptimiza y re-exporta la orden.",
        )
    files = export.get("files") or {}
    content = files.get(filename)
    if content is None:
        return None
    fp = str(export.get("source_fingerprint") or "")[:8]
    prefix = f"{order['order_code']}-{fp}" if fp else str(order["order_code"])
    return f"{prefix}-{filename}", content


def export_dxf_files(
    *, org_id: UUID, order_id: UUID, actor_id: UUID
) -> dict[str, object]:
    """Machine geometry handoff: renders the stored optimization plan into
    DXF files (one per nested sheet plus a bars layout), stored on the order
    under ``dxf_export`` and recorded as ``WO_DXF_EXPORTED``. Same contract
    as the CSV export — requires optimization, invalidates on a fresh plan."""
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text, payload_json,
                   project_version_id
            FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if str(order["status"]) == "INSTALLED":
            raise DocumentaryError("work_order_installed")
        if str(order["status"]) == "DISPATCHED":
            raise DocumentaryError("work_order_dispatched")
        if str(order["status"]) == "COMPLETED":
            raise DocumentaryError("work_order_completed")
        payload = _decoded(order["payload_json"])
        optimization = payload.get("optimization")
        if not isinstance(optimization, dict) or not (
            optimization.get("bars") or optimization.get("sheets")
        ):
            raise DocumentaryError("dxf_requires_optimization")
        if optimization.get("invalidated"):
            raise DocumentaryError("plan_invalidated")
        # Resolve printed piece codes against the sealed snapshot so machine
        # labels match the packs (M-xx / R-xx / I-xx) instead of hash prefixes.
        version = one(
            "SELECT snapshot_json::text AS snapshot_json "
            "FROM public.project_versions WHERE id=%s AND org_id=%s",
            [str(order["project_version_id"]), str(org_id)],
            "version_not_found",
        )
        snapshot = decoded(version["snapshot_json"])
        if not isinstance(snapshot, dict):
            snapshot = {}
        labels = _piece_labels({
            **snapshot,
            "manufacturing": snapshot.get("manufacturing")
            if isinstance(snapshot.get("manufacturing"), list)
            else [],
            "positions": snapshot.get("positions")
            if isinstance(snapshot.get("positions"), list)
            else [],
        })
        cut_map = _cut_member_map(snapshot, labels)
        infill_map = _infill_code_map(snapshot, labels)
        codes: dict[str, str] = {}
        for bar in (optimization.get("bars") or {}).get("workshop_cut_plan") or []:
            if not isinstance(bar, dict):
                continue
            for cut in bar.get("cuts") or []:
                if isinstance(cut, dict) and cut.get("piece_id"):
                    code = cut_map.get(_cut_key(cut))
                    if code:
                        codes[str(cut["piece_id"])] = code
        for sheet in optimization.get("sheets") or []:
            if not isinstance(sheet, dict):
                continue
            for placement in sheet.get("placements") or []:
                if isinstance(placement, dict) and placement.get("piece_id"):
                    codes[str(placement["piece_id"])] = infill_map.get(
                        _infill_key(placement),
                        str(placement["piece_id"]),
                    )
        files = dxf_files(optimization, codes=codes)
        if not files:
            raise DocumentaryError("dxf_requires_optimization")
        export = {
            "schema": "work_order_dxf_export_v1",
            "optimization_fingerprint": _optimization_fingerprint(optimization),
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "actor_id": str(actor_id),
            "files": files,
        }
        new_payload = {**payload, "dxf_export": export}
        rows(
            """
            UPDATE public.orders SET payload_json = %s::jsonb, updated_at = %s
            WHERE id = %s AND org_id = %s
            RETURNING id
            """,
            [json.dumps(new_payload), datetime.now(timezone.utc),
             str(order_id), str(org_id)],
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_DXF_EXPORTED', %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps({
                    "order_code": order["order_code"],
                    "files": sorted(files),
                }),
            ],
        )
        return {
            "order_id": str(order_id),
            "order_code": order["order_code"],
            "exported_at": export["exported_at"],
            "files": files,
        }


def dxf_file_content(
    *, org_id: UUID, order_id: UUID, filename: str
) -> tuple[str, str] | None:
    order = one(
        """
        SELECT order_code, payload_json FROM public.orders
        WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
        """,
        [str(order_id), str(org_id)],
        "work_order_not_found",
    )
    payload = _decoded(order["payload_json"])
    export = payload.get("dxf_export") or {}
    optimization = payload.get("optimization")
    if isinstance(optimization, dict) and optimization.get("invalidated"):
        raise DocumentaryError(
            "dxf_file_stale",
            detail="El plan de corte quedó invalidado: reoptimiza y re-exporta la orden.",
        )
    if (
        export.get("optimization_fingerprint")
        and _optimization_fingerprint(optimization if isinstance(optimization, dict) else {})
        != export["optimization_fingerprint"]
    ):
        raise DocumentaryError(
            "dxf_file_stale",
            detail="El archivo corresponde a un plan anterior: reoptimiza y re-exporta la orden.",
        )
    files = export.get("files") or {}
    content = files.get(filename)
    if content is None:
        return None
    fp = str(export.get("optimization_fingerprint") or "")[:8]
    prefix = f"{order['order_code']}-{fp}" if fp else str(order["order_code"])
    return f"{prefix}-{filename}", content


def _label_code(order_code: str, unit: int) -> str:
    """Printed label identity — ``<order_code>-U<nn>``. An over-length order
    code is shortened with a stable digest infix so the printed code stays
    unique instead of silently colliding with a different order's prefix."""
    suffix = f"-U{unit:02d}"
    budget = 50 - len(suffix)
    if len(order_code) <= budget:
        return f"{order_code}{suffix}"
    digest = hashlib.sha256(order_code.encode("utf-8")).hexdigest()[:8].upper()
    return f"{order_code[: budget - 9]}-{digest}{suffix}"


def generate_packing_manifest(
    *, org_id: UUID, order_id: UUID, actor_id: UUID
) -> dict[str, object]:
    """Per-unit packing manifest: deterministic label codes
    ``<order_code>-U<nn>`` plus piece counts per material kind, so each
    finished unit gets a scannable label and the pack step has a checklist."""
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text, payload_json FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if str(order["status"]) == "INSTALLED":
            raise DocumentaryError("work_order_installed")
        if str(order["status"]) == "DISPATCHED":
            raise DocumentaryError("work_order_dispatched")
        payload = _decoded(order["payload_json"])
        materials = payload.get("materials") or {}
        quantity = int(payload.get("quantity") or 1)
        kind_counts = {
            "profiles": sum(
                int(item.get("qty") or 1)
                for item in materials.get("profile_cuts") or []
            ),
            "reinforcements": sum(
                int(item.get("qty") or 1)
                for item in materials.get("reinforcements") or []
            ),
            "glasses": len(materials.get("glasses") or []),
            "panels": len(materials.get("panels") or []),
            "hardware": sum(
                int(item.get("qty") or 1)
                for item in materials.get("hardware_items") or []
            ),
            "fittings": sum(
                int(item.get("qty") or 1)
                for item in materials.get("fittings") or []
            ),
        }
        units = [
            {
                "unit_index": unit,
                "label_code": _label_code(str(order["order_code"]), unit),
                "position_id": payload.get("position_id"),
                **kind_counts,
            }
            for unit in range(1, quantity + 1)
        ]
        packing = {
            "schema": "work_order_packing_v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "actor_id": str(actor_id),
            "units": units,
        }
        new_payload = {**payload, "packing": packing}
        rows(
            """
            UPDATE public.orders SET payload_json = %s::jsonb, updated_at = %s
            WHERE id = %s AND org_id = %s
            RETURNING id
            """,
            [json.dumps(new_payload), datetime.now(timezone.utc),
             str(order_id), str(org_id)],
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_PACKED', %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps({
                    "order_code": order["order_code"],
                    "units": len(units),
                }),
            ],
        )
        return {
            "order_id": str(order_id),
            "order_code": order["order_code"],
            "packing": packing,
        }


def packing_labels(*, org_id: UUID, order_id: UUID) -> dict[str, object]:
    """Printable unit labels: the stored manifest plus a QR per unit.

    The QR encodes ``DEKOPEN|<order_code>|<label_code>|<piece_count>`` so a
    scanned label identifies the order, the unit, and its checklist even
    without a terminal at hand. Rendered on read — the manifest is already
    sealed, so labels never drift from it."""
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text, payload_json FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        packing = (_decoded(order["payload_json"]) or {}).get("packing")
        if not packing or not packing.get("units"):
            raise DocumentaryError("packing_required")
        labels = []
        for unit in packing["units"]:
            pieces = (
                int(unit.get("profiles") or 0)
                + int(unit.get("reinforcements") or 0)
                + int(unit.get("glasses") or 0)
                + int(unit.get("panels") or 0)
                + int(unit.get("hardware") or 0)
                + int(unit.get("fittings") or 0)
            )
            qr_payload = (
                f"DEKOPEN|{order['order_code']}|{unit['label_code']}|{pieces}"
            )
            labels.append(
                {
                    "unit_index": int(unit["unit_index"]),
                    "label_code": unit["label_code"],
                    "pieces": pieces,
                    "profiles": int(unit.get("profiles") or 0),
                    "reinforcements": int(unit.get("reinforcements") or 0),
                    "glasses": int(unit.get("glasses") or 0),
                    "panels": int(unit.get("panels") or 0),
                    "hardware": int(unit.get("hardware") or 0),
                    "fittings": int(unit.get("fittings") or 0),
                    "qr_payload": qr_payload,
                    "qr_svg": segno.make(qr_payload, error="m").svg_inline(
                        border=2, scale=6
                    ),
                }
            )
        return {
            "order_id": str(order_id),
            "order_code": order["order_code"],
            "status": str(order["status"]),
            "labels": labels,
        }


def dispatch_work_order(
    *, org_id: UUID, order_id: UUID, actor_id: UUID, note: str | None = None
) -> dict[str, object]:
    """Ship the finished order: requires COMPLETED (all routing done); sets
    DISPATCHED and records WO_DISPATCHED. Idempotent — re-dispatching an
    already dispatched order returns its current state."""
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text, payload_json, project_id
            FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if str(order["status"]) == "DISPATCHED":
            return get_work_order(org_id=org_id, order_id=order_id)
        if str(order["status"]) != "COMPLETED":
            raise DocumentaryError("dispatch_requires_completed")
        payload = _decoded(order["payload_json"]) or {}
        if not (payload.get("packing") or {}).get("units"):
            raise DocumentaryError("dispatch_requires_packing_manifest")
        # A guía is the legal shipping document — emitting it with no planned
        # delivery ships a truck to nowhere. Schedule the delivery first, or
        # record the hand-off reason in the note (retiro en taller, ...).
        if not rows(
            "SELECT id FROM public.deliveries WHERE order_id = %s AND org_id = %s",
            [str(order_id), str(org_id)],
        ) and not (note or "").strip():
            raise DocumentaryError("dispatch_requires_delivery")
        rows(
            """
            UPDATE public.orders SET status = 'DISPATCHED', updated_at = %s
            WHERE id = %s AND org_id = %s
            RETURNING id
            """,
            [datetime.now(timezone.utc), str(order_id), str(org_id)],
        )
        note_row = issue_dispatch_note(
            org_id=org_id,
            order=order,
            project=project_row(org_id, order["project_id"]),
            actor_id=actor_id,
            note=(note or "").strip() or None,
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_DISPATCHED', %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps({
                    "order_code": order["order_code"],
                    "note": (note or "").strip() or None,
                    "dispatch_note": note_row["note_code"],
                }),
            ],
        )
        return get_work_order(org_id=org_id, order_id=order_id)


def void_dispatch_note(
    *, org_id: UUID, order_id: UUID, actor_id: UUID, reason: str | None = None
) -> dict[str, object]:
    """Void a mis-emitted guía before it becomes fiscal evidence and return
    the order to COMPLETED so it can be re-dispatched. Only while the order
    is still DISPATCHED: a scheduled delivery means a truck was booked
    against this document, and a stamped DTE-52 means the folio can only be
    annulled at the SII — both refuse the void."""
    org_id_s, order_id_s = str(org_id), str(order_id)
    reason_text = (reason or "").strip()
    if not reason_text:
        raise DocumentaryError("dispatch_note_void_reason_required")
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text, payload_json, project_id
            FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [order_id_s, org_id_s],
            "work_order_not_found",
        )
        if str(order["status"]) != "DISPATCHED":
            raise DocumentaryError("dispatch_note_void_requires_dispatched")
        note = one(
            """
            SELECT id, note_code FROM public.dispatch_notes
            WHERE org_id=%s AND work_order_id=%s AND voided_at IS NULL
            """,
            [org_id_s, order_id_s],
            "dispatch_note_not_found",
        )
        if rows(
            "SELECT id FROM public.deliveries WHERE org_id=%s AND order_id=%s",
            [org_id_s, order_id_s],
        ):
            raise DocumentaryError("dispatch_note_void_delivery_exists")
        if rows(
            "SELECT id FROM public.project_dtes "
            "WHERE org_id=%s AND dispatch_note_id=%s",
            [org_id_s, str(note["id"])],
        ):
            raise DocumentaryError("dispatch_note_void_stamped")
        now = datetime.now(timezone.utc)
        one(
            """
            UPDATE public.dispatch_notes
            SET voided_at=%s, voided_by=%s, voided_reason=%s
            WHERE id=%s RETURNING id
            """,
            [now, str(actor_id), reason_text[:500], str(note["id"])],
        )
        rows(
            """
            UPDATE public.orders SET status = 'COMPLETED', updated_at = %s
            WHERE id = %s AND org_id = %s RETURNING id
            """,
            [now, order_id_s, org_id_s],
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_DISPATCH_VOIDED', %s, %s::jsonb)
            RETURNING id
            """,
            [
                org_id_s,
                order_id_s,
                str(actor_id),
                json.dumps({
                    "order_code": order["order_code"],
                    "note_code": note["note_code"],
                    "reason": reason_text[:500],
                }),
            ],
        )
        return get_work_order(org_id=org_id, order_id=order_id)


def create_work_center(
    *, org_id: UUID, code: str, name: str, kind: str, display_order: int
) -> dict[str, object]:
    if kind not in _STEP_CODE_FOR_CENTER:
        raise DocumentaryError("work_center_kind_unknown")
    with transaction.atomic(), documentary_backend():
        center = one(
            """
            INSERT INTO public.work_centers(org_id, code, name, kind, display_order)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (org_id, code) DO UPDATE SET
                name = EXCLUDED.name, kind = EXCLUDED.kind,
                display_order = EXCLUDED.display_order, active = TRUE
            RETURNING id, code, name, kind, display_order, active, (xmax = 0) AS created
            """,
            [str(org_id), code, name, kind, display_order],
        )
    created = bool(center.pop("created"))
    return center, created


def _sheet_rules(org_id: UUID) -> dict[str, list[SheetRule]]:
    """Sheet stock declared by the shop: ``inventory_items.attributes`` carrying
    ``sheet_width_mm``/``sheet_height_mm``. Panels match a rule by sku; glass by
    its substrate — ``glass_sku`` on both sides when the piece resolved a
    catalog article, thickness only when neither side declares one. Two glass
    types sharing net thickness never mix onto the same sheet."""
    items = rows(
        """
        SELECT sku, name, attributes FROM public.inventory_items
        WHERE org_id = %s
          AND attributes ? 'sheet_width_mm'
          AND attributes ? 'sheet_height_mm'
        """,
        [str(org_id)],
    )
    by_sku: dict[str, SheetRule] = {}
    by_thickness: dict[str, SheetRule] = {}
    by_glass: dict[str, SheetRule] = {}
    for item in items:
        attributes = item.get("attributes") or {}
        if isinstance(attributes, str):
            attributes = json.loads(attributes)
        try:
            rule = SheetRule(
                workshop_sku=str(item["sku"]),
                purchasing_sku=str(attributes.get("purchasing_sku") or item["sku"]),
                manufacturer_name=attributes.get("manufacturer_name"),
                supplier_name=attributes.get("supplier_name") or item.get("name"),
                sheet_width_mm=Decimal(str(attributes["sheet_width_mm"])),
                sheet_height_mm=Decimal(str(attributes["sheet_height_mm"])),
                edge_trim_mm=Decimal(str(attributes.get("sheet_edge_trim_mm") or 0)),
            )
        except Exception:
            continue
        by_sku.setdefault(rule.workshop_sku, []).append(rule)
        # A rule that declares its substrate serves only that substrate — it
        # stays out of by_thickness so an undeclared piece can't borrow it.
        glass_sku = attributes.get("glass_sku")
        if glass_sku is not None:
            by_glass.setdefault(str(glass_sku), []).append(rule)
        else:
            thickness = attributes.get("sheet_thickness_mm")
            if thickness is not None:
                by_thickness.setdefault(
                    str(Decimal(str(thickness))), []
                ).append(rule)
    # Deterministic authority order: smallest physical sheet first, sku as the
    # tiebreak, so variants never depend on database row order.
    for group in (by_sku, by_thickness, by_glass):
        for candidates in group.values():
            candidates.sort(
                key=lambda r: (r.sheet_width_mm * r.sheet_height_mm, r.workshop_sku)
            )
    return {
        "by_sku": by_sku,
        "by_thickness": by_thickness,
        "by_glass": by_glass,
    }


def _pick_sheet_rule(
    candidates: list[SheetRule], width_mm: Decimal, height_mm: Decimal
) -> SheetRule | None:
    """Smallest declared sheet that holds the piece (either orientation, since
    sheet pieces allow rotation); falls back to the largest sheet so oversized
    pieces still land honestly under ``unnested``."""
    if not candidates:
        return None
    for rule in candidates:
        usable_w = rule.sheet_width_mm - rule.edge_trim_mm * 2
        usable_h = rule.sheet_height_mm - rule.edge_trim_mm * 2
        if (width_mm <= usable_w and height_mm <= usable_h) or (
            height_mm <= usable_w and width_mm <= usable_h
        ):
            return rule
    return candidates[-1]


def _decoded(payload: object) -> dict[str, object]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload if isinstance(payload, dict) else {}


def _compute_optimization(
    *,
    org_id: UUID,
    result: EngineResult,
    system_id: str,
    color: str,
    quantity: int,
    position_id: str | None,
    version_snapshot: dict[str, object],
    strategy: str,
    cutting_profile_code: str | None = None,
) -> dict[str, object]:
    """Pure plan computation — reads stock/remnant pools, writes nothing:
    no reservations, no events. ``optimize_work_order`` persists the result;
    ``compare_optimization_strategies`` previews the same computation per
    strategy so the choice is evidence, not a guess."""
    started = perf_counter()
    stocks = CuttingRepository()
    authorities = stocks.for_result(result, UUID(str(system_id)), org_id, color)
    profile = stocks.cutting_profile(org_id, cutting_profile_code)
    # §6: on-hand bar drops matching the plan's stock authorities are cut
    # before any purchase; the engine consumes smallest-fitting-first.
    bar_remnants = remnants_service.bar_remnants_for_authorities(
        org_id=org_id,
        authority_ids={s.stock_authority_id for s in authorities.stocks},
    )
    per_unit = pieces_from_result(
        result,
        color=color,
        source_position_id=position_id,
        reinforcement_skus=authorities.reinforcement_skus,
        reinforcement_angles=_reinforcement_angle_map(version_snapshot, position_id),
    )
    # pieces_from_result returns one unit's pieces; unit_index is the
    # physical unit ordinal the workshop reads (u1 = first unit), while
    # identical copies inside a unit are disambiguated inside piece_id.
    pieces = [
        piece.model_copy(update={"unit_index": repetition})
        for repetition in range(1, quantity + 1)
        for piece in per_unit
    ]
    bars = optimize_cut(
        pieces, authorities.stocks, profile,
        remnants=bar_remnants, strategy=strategy,
    ).model_dump(mode="json")
    bar_runtime_ms = int((perf_counter() - started) * 1000)

    rules = _sheet_rules(org_id)
    sheets: list[dict[str, object]] = []
    sheet_purchases: list[dict[str, object]] = []
    unnested: list[dict[str, object]] = []
    sheet_groups: list[tuple[SheetRule, list[NestPiece], str]] = []
    for group_key, entries, kind in (
        ("by_thickness", result.glasses, "GLASS"),
        ("by_sku", result.panels, "PANEL"),
    ):
        for index, entry in enumerate(entries, start=1):
            # Glass substrate identity: the resolved catalog article (or
            # the composition spec when no article authority exists) is
            # the grouping key — never net thickness alone.
            substrate = (
                (entry.article_sku or entry.glass_spec)
                if kind == "GLASS"
                else None
            )
            group = (
                str(substrate)
                if substrate
                else (
                    str(entry.thickness_net_mm)
                    if kind == "GLASS"
                    else entry.sku
                )
            )
            if getattr(entry, "shape", None):
                # Non-rectangular glass cannot be guillotine-nested by a
                # bounding rect — it goes to the shape-cutting cell with
                # its true outline, never silently a rectangle.
                unnested.append({
                    "kind": kind, "group": group,
                    "width_mm": str(entry.width_mm),
                    "height_mm": str(entry.height_mm), "quantity": quantity,
                    "bay_id": entry.bay_id, "leaf_id": entry.leaf_id,
                    "shape": [
                        {"x_mm": str(p.x_mm), "y_mm": str(p.y_mm)}
                        for p in entry.shape
                    ],
                    "reason": "shaped_glass_outline",
                })
                continue
            candidates: list[SheetRule]
            if kind == "GLASS" and substrate:
                # Declared substrate → only rules declaring the same
                # substrate; a same-thickness sheet of another glass type
                # is not a compatible host.
                candidates = rules["by_glass"].get(str(substrate)) or []
            else:
                candidates = rules[group_key].get(group) or []
            rule = _pick_sheet_rule(
                candidates, entry.width_mm, entry.height_mm
            )
            label = f"V-{index:02d}" if kind == "GLASS" else f"PAN-{index:02d}"
            if rule is None:
                unnested.append({
                    "kind": kind, "group": group,
                    "width_mm": str(entry.width_mm),
                    "height_mm": str(entry.height_mm), "quantity": quantity,
                    "bay_id": entry.bay_id, "leaf_id": entry.leaf_id,
                    "reason": "no_declared_sheet",
                })
                continue
            sheet_groups.append((
                rule,
                [
                    NestPiece(
                        piece_id=(
                            label if quantity == 1
                            else f"{label}-{repetition:02d}"
                        ),
                        workshop_sku=rule.workshop_sku,
                        width_mm=entry.width_mm,
                        height_mm=entry.height_mm,
                        source_position_id=position_id,
                        bay_id=entry.bay_id,
                        leaf_id=entry.leaf_id,
                        unit_index=repetition,
                    )
                    for repetition in range(1, quantity + 1)
                ],
                kind,
            ))
    # Group by the full selected rule identity (format + trim + purchasing
    # identity), never just the SKU — pieces picked for different variants
    # of one SKU keep separate layouts and purchase lines.
    merged: dict[tuple, tuple[SheetRule, list[NestPiece], str]] = {}
    for rule, pieces_group, group_kind in sheet_groups:
        key = (
            rule.workshop_sku,
            str(rule.sheet_width_mm),
            str(rule.sheet_height_mm),
            str(rule.edge_trim_mm),
            rule.purchasing_sku,
        )
        merged.setdefault(key, (rule, [], group_kind))[1].extend(pieces_group)
    for rule, group_pieces, group_kind in merged.values():
        outcome = nest_rects(
            group_pieces, rule,
            remnants=remnants_service.sheet_remnants_for_sku(
                org_id=org_id, workshop_sku=rule.workshop_sku
            ),
        )
        for layout in outcome.layouts:
            dumped = layout.model_dump(mode="json")
            # sheet_index restarts per bin — renumber across the whole plan
            # so layouts keep a stable globally-unique identity.
            dumped["sheet_index"] = len(sheets) + 1
            # Remnant identity: the workshop sku this layout nests under
            # (produced_remnants rejoin the pool under the same key).
            dumped["workshop_sku"] = rule.workshop_sku
            sheets.append(dumped)
        for purchase in outcome.purchase_list:
            dumped_purchase = purchase.model_dump(mode="json")
            # The purchase row is bought sheet stock — tag which piece group
            # it serves so stock needs can route it (glass sheets reserve at
            # CUT; panel sheets stay on the PANEL authority path).
            dumped_purchase["group_kind"] = group_kind
            sheet_purchases.append(dumped_purchase)
        for piece in outcome.unplaced:
            unnested.append({
                "kind": "SHEET", "group": rule.workshop_sku,
                "width_mm": str(piece.width_mm), "height_mm": str(piece.height_mm),
                "quantity": 1, "bay_id": piece.bay_id, "leaf_id": piece.leaf_id,
                "reason": "piece_larger_than_usable_sheet",
            })

    # §6 remnant lifecycle: the plan claims what it will cut (RESERVED
    # inside the caller's transaction — never a drop double-booked) and
    # reports what reusable material it will return to the rack.
    consumed_bars = [
        {"id": bar["remnant_id"], "kind": "BAR"}
        for bar in bars.get("workshop_cut_plan") or []
        if bar.get("source") == "REMNANT" and bar.get("remnant_id")
    ]
    consumed_sheets = [
        {"id": sheet["remnant_id"], "kind": "SHEET"}
        for sheet in sheets
        if sheet.get("source") == "REMNANT" and sheet.get("remnant_id")
    ]
    # The plan names each physical drop it claims — the operator matches
    # the printed remnant id to the rack tag without opening the ledger.
    consumed_ids = [entry["id"] for entry in consumed_bars + consumed_sheets]
    if consumed_ids:
        consumed_locations = {
            str(r["id"]): r["rack_location"]
            for r in rows(
                "SELECT id, rack_location FROM public.inventory_remnants"
                " WHERE org_id = %s AND id = ANY(%s::uuid[])",
                [str(org_id), consumed_ids],
            )
        }
        for entry in consumed_bars + consumed_sheets:
            entry["rack_location"] = consumed_locations.get(entry["id"])
    produced_bars = [
        {
            "stock_authority_id": bar["stock_authority_id"],
            "remainder_mm": bar["remainder_mm"],
        }
        for bar in bars.get("workshop_cut_plan") or []
        if bar.get("remainder_reusable") and bar.get("stock_authority_id")
    ]
    produced_sheets = [
        {
            "workshop_sku": sheet["workshop_sku"],
            "width_mm": remnant["width_mm"],
            "height_mm": remnant["height_mm"],
        }
        for sheet in sheets
        for remnant in sheet.get("produced_remnants") or []
    ]
    return {
        "bars": bars,
        "sheets": sheets,
        "sheet_purchases": sheet_purchases,
        "unnested": unnested,
        "consumed_bars": consumed_bars,
        "consumed_sheets": consumed_sheets,
        "produced_bars": produced_bars,
        "produced_sheets": produced_sheets,
        "bar_runtime_ms": bar_runtime_ms,
        "runtime_ms": int((perf_counter() - started) * 1000),
    }


def _optimization_stats(plan: dict[str, object]) -> dict[str, object]:
    """Plan aggregates for the optimize header — derived from the dumped
    plan, never recomputed physics."""
    bars = (plan["bars"].get("workshop_cut_plan") or []) if isinstance(
        plan.get("bars"), dict
    ) else []
    cuts_total = 0
    waste_mm = Decimal("0")
    new_bars = 0
    remnant_bars = 0
    for bar in bars:
        cuts_total += len(bar.get("cuts") or [])
        waste_mm += Decimal(str(bar.get("waste_mm") or "0"))
        if bar.get("source") == "REMNANT":
            remnant_bars += 1
        else:
            new_bars += 1
    sheet_purchases = plan.get("sheet_purchases") or []
    bar_purchases = (plan["bars"].get("purchase_list") or []) if isinstance(
        plan.get("bars"), dict
    ) else []
    return {
        "bars_total": len(bars),
        "bars_new": new_bars,
        "bars_remnant": remnant_bars,
        "cuts_total": cuts_total,
        "waste_mm": str(waste_mm),
        "sheets_total": len(plan.get("sheets") or []),
        "pieces_sheets": sum(
            len(sheet.get("placements") or [])
            for sheet in (plan.get("sheets") or [])
        ),
        "unnested_count": len(plan.get("unnested") or []),
        "purchase_bars": sum(
            int(line.get("qty_bars") or 0) for line in bar_purchases
        ),
        "purchase_sheets": sum(
            int(line.get("qty_sheets") or 0) for line in sheet_purchases
        ),
        "remnants_consumed": len(
            (plan.get("consumed_bars") or []) + (plan.get("consumed_sheets") or [])
        ),
        "remnants_produced": len(
            (plan.get("produced_bars") or []) + (plan.get("produced_sheets") or [])
        ),
        "runtime_ms": plan.get("runtime_ms") or 0,
    }


def _order_optimize_context(
    *, org_id: UUID, order_id: UUID, color: str
) -> tuple[dict[str, object], str, dict[str, object], EngineResult, int]:
    """Shared guards + inputs for optimizing an order — the mutating path and
    the read-only comparison both validate against the same sealed facts."""
    order = one(
        """
        SELECT id, order_code, status::text, payload_json FROM public.orders
        WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
        """,
        [str(order_id), str(org_id)],
        "work_order_not_found",
    )
    if str(order["status"]) == "INSTALLED":
        raise DocumentaryError("work_order_installed")
    if str(order["status"]) == "DISPATCHED":
        raise DocumentaryError("work_order_dispatched")
    if str(order["status"]) == "COMPLETED":
        raise DocumentaryError("work_order_completed")
    payload = _decoded(order["payload_json"])
    position_id = payload.get("position_id")
    system_id = payload.get("system_id")
    sealed_color = str(payload.get("color") or "").strip()
    if sealed_color and not color:
        color = sealed_color
    if not color:
        raise DocumentaryError("optimize_color_required")
    if sealed_color and color != sealed_color:
        raise DocumentaryError("optimize_color_mismatch")
    version_row = one(
        """
        SELECT pv.snapshot_json FROM public.project_versions pv
        JOIN public.orders o ON o.project_version_id = pv.id
        WHERE o.id = %s AND o.org_id = %s
        """,
        [str(order_id), str(org_id)],
        "work_order_missing_system",
    )
    version_snapshot = _decoded(version_row["snapshot_json"])
    if not system_id:
        for pos in version_snapshot.get("positions") or []:
            if str(pos.get("id")) == str(position_id) and pos.get("system_id"):
                system_id = str(pos["system_id"])
                break
        if not system_id:
            raise DocumentaryError("work_order_missing_system")
    quantity = int(payload.get("quantity") or 1)
    materials = payload.get("materials") or {}
    result = EngineResult.model_validate(
        {
            "profile_cuts": materials.get("profile_cuts") or [],
            "reinforcements": materials.get("reinforcements") or [],
            "glasses": materials.get("glasses") or [],
            "panels": materials.get("panels") or [],
            "fittings": materials.get("fittings") or [],
            "hardware_items": materials.get("hardware_items") or [],
            "leaf_weights": materials.get("leaf_weights") or [],
        },
        strict=False,
    )
    return order, color, version_snapshot, result, quantity


def compare_optimization_strategies(
    *,
    org_id: UUID,
    order_id: UUID,
    color: str,
) -> dict[str, object]:
    """§6: preview FAST vs DEEP on the same sealed pieces and live stock —
    read-only, no reservations, no events. AUTO delegates to the engine's own
    pick, so the comparison covers the two explicit policies the operator can
    choose."""
    color = (color or "").strip()
    with documentary_backend():
        order, color, version_snapshot, result, quantity = _order_optimize_context(
            org_id=org_id, order_id=order_id, color=color
        )
        payload = _decoded(order["payload_json"])
        position_id = payload.get("position_id")
        system_id = payload.get("system_id") or next(
            (
                str(pos["system_id"])
                for pos in (version_snapshot.get("positions") or [])
                if str(pos.get("id")) == str(position_id) and pos.get("system_id")
            ),
            None,
        )
        rows_out = []
        for strategy in ("fast", "deep"):
            plan = _compute_optimization(
                org_id=org_id,
                result=result,
                system_id=str(system_id),
                color=color,
                quantity=quantity,
                position_id=str(position_id) if position_id else None,
                version_snapshot=version_snapshot,
                strategy=strategy,
            )
            rows_out.append(
                {"strategy": strategy, **_optimization_stats(plan)}
            )
        return {
            "order_id": str(order_id),
            "order_code": order["order_code"],
            "color": color,
            "strategies": rows_out,
        }


def station_queue(*, org_id: UUID) -> dict[str, object]:
    """Group every live order's open steps by station code: what the saw
    bench, the machining cell and the QC post each have queued right now.

    A step shown as ``is_next`` is its order's first unfinished station —
    the work that can actually start, not the whole backlog."""
    step_rows = rows(
        """
        SELECT s.id::text, s.order_id::text, s.sequence, s.code::text AS code,
               s.label, s.status::text AS status, s.note,
               o.order_code, w.code AS work_center_code, w.name AS work_center_name
        FROM public.production_steps s
        JOIN public.orders o ON o.id = s.order_id AND o.org_id = s.org_id
        LEFT JOIN public.work_centers w ON w.id = s.work_center_id
        WHERE s.org_id = %s
          AND o.status::text IN ('RELEASED', 'IN_PROGRESS', 'HOLD')
        ORDER BY o.order_code, s.sequence
        """,
        [str(org_id)],
    )
    stations: dict[str, dict[str, object]] = {}
    first_open: dict[str, str] = {}
    for row in step_rows:
        order_id = str(row["order_id"])
        if row["status"] != "DONE" and order_id not in first_open:
            first_open[order_id] = str(row["id"])
        station = stations.setdefault(
            str(row["code"]),
            {"code": str(row["code"]), "label": row["label"], "entries": []},
        )
        if row["status"] == "DONE":
            continue
        station["entries"].append({
            "step_id": row["id"],
            "order_id": order_id,
            "order_code": row["order_code"],
            "sequence": row["sequence"],
            "label": row["label"],
            "status": row["status"],
            "note": row["note"],
            "work_center_code": row["work_center_code"],
            "work_center_name": row["work_center_name"],
        })
    for station in stations.values():
        for entry in station["entries"]:
            entry["is_next"] = entry["step_id"] == first_open.get(
                entry["order_id"]
            )
        station["pending"] = sum(
            1 for e in station["entries"] if e["status"] in ("PENDING", "READY")
        )
        station["in_progress"] = sum(
            1 for e in station["entries"] if e["status"] == "IN_PROGRESS"
        )
        station["blocked"] = sum(
            1 for e in station["entries"] if e["status"] == "BLOCKED"
        )
    return {
        "stations": [station for _, station in sorted(stations.items())]
    }


def optimize_work_order(
    *,
    org_id: UUID,
    order_id: UUID,
    actor_id: UUID,
    color: str,
    cutting_profile_code: str | None = None,
    strategy: str = "auto",
) -> dict[str, object]:
    """Bar cutting plan (1D best-fit) + sheet nesting (2D guillotine) for one
    work order. Replaces any previous plan in ``payload_json.optimization`` and
    appends a ``WO_OPTIMIZED`` event. Sealed materials are never mutated."""
    color = (color or "").strip()
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text, payload_json FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if str(order["status"]) == "INSTALLED":
            raise DocumentaryError("work_order_installed")
        if str(order["status"]) == "DISPATCHED":
            raise DocumentaryError("work_order_dispatched")
        if str(order["status"]) == "COMPLETED":
            raise DocumentaryError("work_order_completed")
        # A plan writes fresh reservations for every stock kind, but only a
        # consuming step that completes can settle them — replanning after a
        # step already consumed its material would strand the new holds
        # forever (a DONE step cannot complete again). A step IN_PROGRESS is
        # worse: the floor is physically cutting plan A while plan B would
        # silently steal its stock claims. Both refuse.
        consuming_rows = rows(
            """
            SELECT code::text AS code, status::text AS status
            FROM public.production_steps
            WHERE order_id = %s AND org_id = %s AND status IN ('DONE', 'IN_PROGRESS')
            """,
            [str(order_id), str(org_id)],
        )
        # The replan guard covers every station that physically worked the
        # plan — not only stock-consuming ones: a DONE PROFILE_CUT means
        # real bars were already cut even though no reservation settled here.
        physical_stations = set(_STEP_CONSUMED_KINDS) | _PLAN_REQUIRED_STATIONS
        if any(
            str(row["code"]) in physical_stations and row["status"] == "DONE"
            for row in consuming_rows
        ):
            raise DocumentaryError("work_order_replan_after_consumption")
        if any(
            str(row["code"]) in physical_stations
            for row in consuming_rows
        ):
            raise DocumentaryError("work_order_replan_step_in_progress")
        payload = _decoded(order["payload_json"])
        materials = payload.get("materials") or {}
        position_id = payload.get("position_id")
        system_id = payload.get("system_id")
        sealed_color = str(payload.get("color") or "").strip()
        # The sealed color is the authority: an omitted request color inherits
        # it; a contradicting one is refused — optimizing against a different
        # finish would cut/reserve stock the order never asked for.
        if sealed_color and not color:
            color = sealed_color
        if not color:
            raise DocumentaryError("optimize_color_required")
        if sealed_color and color != sealed_color:
            raise DocumentaryError("optimize_color_mismatch")
        # The frozen version snapshot is the only honest source for both the
        # system mapping and the sealed manufacturing facts (reinforcement cut
        # angles live there, not in the BOM rows).
        version_row = one(
            """
            SELECT pv.snapshot_json FROM public.project_versions pv
            JOIN public.orders o ON o.project_version_id = pv.id
            WHERE o.id = %s AND o.org_id = %s
            """,
            [str(order_id), str(org_id)],
            "work_order_missing_system",
        )
        version_snapshot = _decoded(version_row["snapshot_json"])
        if not system_id:
            # Old orders lack system_id: recover the frozen mapping from the
            # referenced version's immutable snapshot, never the live position.
            for pos in version_snapshot.get("positions") or []:
                if str(pos.get("id")) == str(position_id) and pos.get("system_id"):
                    system_id = str(pos["system_id"])
                    break
            if not system_id:
                raise DocumentaryError("work_order_missing_system")
        quantity = int(payload.get("quantity") or 1)
        # payload was produced by model_dump(mode="json") — Decimals are strings,
        # so validate non-strictly to round them back.
        result = EngineResult.model_validate(
            {
                "profile_cuts": materials.get("profile_cuts") or [],
                "reinforcements": materials.get("reinforcements") or [],
                "glasses": materials.get("glasses") or [],
                "panels": materials.get("panels") or [],
                "fittings": materials.get("fittings") or [],
                "hardware_items": materials.get("hardware_items") or [],
                "leaf_weights": materials.get("leaf_weights") or [],
            },
            strict=False,
        )
        plan = _compute_optimization(
            org_id=org_id,
            result=result,
            system_id=str(system_id),
            color=color,
            quantity=quantity,
            position_id=str(position_id) if position_id else None,
            version_snapshot=version_snapshot,
            strategy=strategy,
            cutting_profile_code=cutting_profile_code,
        )
        bars = plan["bars"]
        sheets = plan["sheets"]
        sheet_purchases = plan["sheet_purchases"]
        unnested = plan["unnested"]
        consumed_bars = plan["consumed_bars"]
        consumed_sheets = plan["consumed_sheets"]
        produced_bars = plan["produced_bars"]
        produced_sheets = plan["produced_sheets"]
        # Re-optimizing replaces the plan: the old reservation releases before
        # the new one claims, atomically — for remnants and for ledger stock
        # alike. Ledger reservations are capped at what is physically
        # available under the item row lock, so two concurrent work orders can
        # never hold the same stock; shortfall is reported, not invented.
        remnants_service.release_reservations(org_id=org_id, order_id=order_id)
        production_stock.release_for_order(
            org_id=org_id, order_id=order_id, actor_id=actor_id
        )
        remnants_service.reserve_remnants(
            org_id=org_id,
            remnant_ids=[r["id"] for r in consumed_bars + consumed_sheets],
            order_id=order_id,
        )
        stock_needs = production_stock.bar_stock_needs(
            org_id=org_id, bars=bars.get("workshop_cut_plan") or []
        )
        unit_needs, unmapped_stock_skus = production_stock.unit_stock_needs(
            org_id=org_id,
            system_id=str(system_id),
            quantity=quantity,
            hardware_items=materials.get("hardware_items") or [],
            fittings=materials.get("fittings") or [],
            panels=materials.get("panels") or [],
            sheet_purchases=sheet_purchases,
        )
        stock_reservations = production_stock.reserve_for_order(
            org_id=org_id,
            order_id=order_id,
            actor_id=actor_id,
            needs=[*stock_needs, *unit_needs],
        )
        optimization = {
            "schema": "work_order_optimization_v1",
            "optimized_at": datetime.now(timezone.utc).isoformat(),
            "actor_id": str(actor_id),
            "color": color,
            "units": quantity,
            "strategy": strategy,
            # Which engine strategy physically produced this plan — the
            # `auto` comparison's `chosen`, or the requested one outright.
            "applied_strategy": (
                str(bars.get("strategy_comparison", {}).get("chosen"))
                if isinstance(bars.get("strategy_comparison"), dict)
                and bars["strategy_comparison"].get("chosen")
                else strategy
            ),
            "bars": bars,
            "sheets": sheets,
            "sheet_purchases": sheet_purchases,
            "unnested": unnested,
            "remnants": {
                "consumed": consumed_bars + consumed_sheets,
                "produced_bars": produced_bars,
                "produced_sheets": produced_sheets,
            },
            # §6 plan summary — aggregates computed from the same dumped plan
            # the UI renders, never a second source of numbers.
            "stats": _optimization_stats(plan),
            # §10 ledger reservations this plan holds — what production
            # claimed from stock, what it is short of, and (once the routing
            # consumes them) when each hold settled.
            "stock_reservations": stock_reservations,
            "unmapped_stock_skus": unmapped_stock_skus,
        }
        # A fresh plan invalidates any machine files rendered from the old one.
        new_payload = {**payload, "optimization": optimization}
        new_payload.pop("cnc_export", None)
        new_payload.pop("dxf_export", None)
        new_payload.pop("operations_export", None)
        rows(
            """
            UPDATE public.orders SET payload_json = %s::jsonb, updated_at = %s
            WHERE id = %s AND org_id = %s
            RETURNING id
            """,
            [json.dumps(new_payload), datetime.now(timezone.utc),
             str(order_id), str(org_id)],
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_OPTIMIZED', %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps({
                    "order_code": order["order_code"],
                    "color": color,
                    "bars": len(bars.get("workshop_cut_plan") or []),
                    "sheets": len(sheets),
                    "unnested": len(unnested),
                    "remnants_consumed": len(consumed_bars + consumed_sheets),
                    "stock_reserved": sum(
                        1 for row in stock_reservations if row["reserved"] != "0"
                    ),
                    "stock_short": sum(
                        1 for row in stock_reservations if row["short"] != "0"
                    ),
                }),
            ],
        )
        # §08: the plan says which claims stock couldn't fill — queue the
        # purchase task inside this tx so the plan and the task commit
        # together (deduped to the order, not per optimize click).
        if any(row["short"] != "0" for row in stock_reservations):
            from automations.service import emit

            emit(
                "automation.purchase_task",
                org_id=org_id,
                actor_id=actor_id,
                idempotency_key=f"auto:buy:{order_id}",
                order_id=str(order_id),
            )
        return {
            "order_id": str(order_id),
            "order_code": order["order_code"],
            "optimization": optimization,
        }


_DELIVERY_WINDOWS = ("AM", "PM", "JORNADA")
# DELIVERED is not a manual transition: it is only reachable through
# confirm_delivery, which seals the signed comprobante de entrega and its
# optional cobro in the same transaction.
_DELIVERY_NEXT = {
    "ON_ROUTE": {"SCHEDULED"},
    "FAILED": {"ON_ROUTE"},
}
_DELIVERY_EVENT = {
    "ON_ROUTE": "WO_DELIVERY_ON_ROUTE",
    "FAILED": "WO_DELIVERY_FAILED",
}


def _public_delivery(
    delivery: dict[str, object], *, confirmation: dict | None = None
) -> dict[str, object]:
    return {
        "id": str(delivery["id"]),
        "order_id": str(delivery["order_id"]),
        "order_code": str(delivery["order_code"]),
        "scheduled_date": str(delivery["scheduled_date"]),
        "time_window": str(delivery["time_window"]),
        "address": str(delivery["address"]),
        "contact_name": delivery["contact_name"],
        "contact_phone": delivery["contact_phone"],
        "installer_name": delivery["installer_name"],
        "notes": delivery["notes"],
        "status": str(delivery["status"]),
        "confirmation": confirmation,
        "scheduled_by": str(delivery["scheduled_by"]) if delivery["scheduled_by"] else None,
        "created_at": delivery["created_at"].isoformat(),
        "updated_at": delivery["updated_at"].isoformat(),
    }


def get_delivery(*, org_id: UUID, order_id: UUID) -> dict[str, object]:
    """Delivery for a valid WORKSHOP_OT — `delivery: null` only when the order
    genuinely exists but was never scheduled; bad ids raise work_order_not_found."""
    with documentary_backend():
        found = rows(
            """
            SELECT d.*, o.order_code FROM public.orders o
            LEFT JOIN public.deliveries d ON d.order_id = o.id
            WHERE o.id = %s AND o.org_id = %s AND o.order_type = 'WORKSHOP_OT'
            """,
            [str(order_id), str(org_id)],
        )
        if not found:
            raise DocumentaryError("work_order_not_found")
    delivery = found[0]
    if not delivery.get("id"):
        return {"delivery": None}
    return {
        "delivery": _public_delivery(
            delivery,
            confirmation=confirmation_summary(
                org_id=org_id, order_id=order_id
            ),
        )
    }


def schedule_delivery(
    *,
    org_id: UUID,
    order_id: UUID,
    actor_id: UUID,
    scheduled_date: str,
    time_window: str | None,
    address: str,
    contact_name: str | None = None,
    contact_phone: str | None = None,
    installer_name: str | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    """Create or update the order's single delivery — rescheduling is an
    upsert so retries and edits stay idempotent on the same row."""
    window = (time_window or "AM").strip().upper()
    if window not in _DELIVERY_WINDOWS:
        raise DocumentaryError("delivery_window_invalid")
    if not (address or "").strip():
        raise DocumentaryError("delivery_address_required")
    try:
        day = date.fromisoformat(str(scheduled_date))
    except (TypeError, ValueError):
        raise DocumentaryError("delivery_date_invalid")
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if str(order["status"]) not in ("COMPLETED", "DISPATCHED"):
            raise DocumentaryError("delivery_requires_completed")
        existing = rows(
            "SELECT * FROM public.deliveries WHERE order_id = %s AND org_id = %s",
            [str(order_id), str(org_id)],
        )
        if existing and str(existing[0]["status"]) == "DELIVERED":
            raise DocumentaryError("delivery_already_delivered")
        if existing and str(existing[0]["status"]) == "ON_ROUTE":
            # A truck already moving can't be silently rewound to scheduled —
            # fail it first, then schedule the fresh attempt.
            raise DocumentaryError("delivery_already_on_route")
        normalized = {
            "scheduled_date": day,
            "time_window": window,
            "address": address.strip(),
            "contact_name": (contact_name or "").strip() or None,
            "contact_phone": (contact_phone or "").strip() or None,
            "installer_name": (installer_name or "").strip() or None,
            "notes": (notes or "").strip() or None,
        }
        if (
            existing
            and str(existing[0]["status"]) == "SCHEDULED"
            and all(existing[0][key] == value for key, value in normalized.items())
        ):
            # Identical schedule replay — one row, no duplicate audit event.
            return get_delivery(org_id=org_id, order_id=order_id)
        delivery = one(
            """
            INSERT INTO public.deliveries(
                org_id, order_id, scheduled_date, time_window, address,
                contact_name, contact_phone, installer_name, notes, scheduled_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (order_id) DO UPDATE SET
                scheduled_date = EXCLUDED.scheduled_date,
                time_window = EXCLUDED.time_window,
                address = EXCLUDED.address,
                contact_name = EXCLUDED.contact_name,
                contact_phone = EXCLUDED.contact_phone,
                installer_name = EXCLUDED.installer_name,
                notes = EXCLUDED.notes,
                scheduled_by = EXCLUDED.scheduled_by,
                status = 'SCHEDULED',
                updated_at = %s
            RETURNING *
            """,
            [
                str(org_id),
                str(order_id),
                str(day),
                window,
                address.strip(),
                (contact_name or "").strip() or None,
                (contact_phone or "").strip() or None,
                (installer_name or "").strip() or None,
                (notes or "").strip() or None,
                str(actor_id),
                datetime.now(timezone.utc),
            ],
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_DELIVERY_SCHEDULED', %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps({
                    "order_code": order["order_code"],
                    "scheduled_date": str(day),
                    "time_window": window,
                    "installer_name": delivery["installer_name"],
                }),
            ],
        )
    return get_delivery(org_id=org_id, order_id=order_id)


def transition_delivery(
    *, org_id: UUID, order_id: UUID, actor_id: UUID, to_status: str
) -> dict[str, object]:
    """Move the delivery forward; guarded by both its own state and the
    order's — a truck can't leave before the order is DISPATCHED."""
    target = str(to_status or "").upper()
    if target not in _DELIVERY_NEXT:
        raise DocumentaryError("delivery_transition_invalid")
    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        if str(order["status"]) == "INSTALLED":
            raise DocumentaryError("order_already_installed")
        delivery = one(
            """
            SELECT * FROM public.deliveries
            WHERE order_id = %s AND org_id = %s FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "delivery_not_found",
        )
        current = str(delivery["status"])
        if current == target:
            return get_delivery(org_id=org_id, order_id=order_id)
        if current not in _DELIVERY_NEXT[target]:
            raise DocumentaryError("delivery_transition_invalid")
        if target == "ON_ROUTE" and str(order["status"]) != "DISPATCHED":
            raise DocumentaryError("delivery_requires_dispatched")
        rows(
            """
            UPDATE public.deliveries SET status = %s, updated_at = %s
            WHERE id = %s AND org_id = %s RETURNING id
            """,
            [target, datetime.now(timezone.utc), str(delivery["id"]), str(org_id)],
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                _DELIVERY_EVENT[target],
                str(actor_id),
                json.dumps({"order_code": order["order_code"]}),
            ],
        )
    return get_delivery(org_id=org_id, order_id=order_id)
