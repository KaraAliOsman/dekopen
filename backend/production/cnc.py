"""CNC workspace: org-declared machines and tools, per-member program
generation, machine-neutral validation, and program staleness.

Authority model: machines and tools are org-declared manufacturing
authority (write through ``documentary_backend`` after API role checks).
Every create/update of that authority is recorded in
``cnc_authority_events`` (append-only) — a verdict is only honest when the
authority it checked against is auditable. Programs are generated
artifacts — immutable rows that flip CURRENT → SUPERSEDED when a replan
changes their input fingerprint, so an operator never runs stale output
without the flag being visible.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from uuid import UUID

from django.db import transaction

from dekopen_engine.cutting import CutBar
from dekopen_engine.operations import (
    ClampZone,
    CoordinateSystem,
    MachineProfile,
    MemberFace,
    NeutralOpsPostProcessor,
    OperationKind,
    PostProcessor,
    Tool,
    ToolKind,
    member_meta_map,
    member_program,
    operations_from_plan,
    validate_operations,
)
from documents.repository import (
    DocumentaryError,
    documentary_backend,
    one,
    rows,
    write,
)
from documents.renderers import (
    _cut_key,
    _cut_member_map,
    _piece_labels,
)
from production.service import (
    _declared_intent_gaps,
    _decoded,
    _operations_fact_units,
    _ops_source_fingerprint,
    _raw_fact_units,
)


_TOOL_KINDS = {kind.value for kind in ToolKind}
_OP_KINDS = {kind.value for kind in OperationKind}
_FACES = {face.value for face in MemberFace}
_COORDS = {coord.value for coord in CoordinateSystem}
# Declared machine families — org authority names WHAT the machine is, the
# engine never guesses a type from the name.
_MACHINE_TYPES = {
    "MACHINING_CENTER",
    "ROUTER",
    "SAW_DRILL_LINE",
    "COPY_ROUTER",
    "OTHER",
}

_MACHINE_SELECT = """
    SELECT id, code, name, manufacturer, model, controller_family,
           coordinate_systems, supported_kinds, supported_faces,
           max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
           postprocessor_id, postprocessor_version, units, encoding, active,
           machine_type, axes_count, travel_x_mm, travel_y_mm, travel_z_mm
    FROM public.cnc_machines
"""


def _dec(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DocumentaryError("cnc_numeric_invalid")


def _string_list(value: object, *, allowed: set[str], code: str) -> list[str] | None:
    """NULL = unrestricted; otherwise validate against the enum set."""
    if value is None:
        return None
    if not isinstance(value, list) or any(
        not isinstance(item, str) or item not in allowed for item in value
    ):
        raise DocumentaryError(code)
    return value


def _public_tool(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "code": row["code"],
        "name": row["name"],
        "kind": row["kind"],
        "diameter_mm": row["diameter_mm"],
        "working_length_mm": row["working_length_mm"],
        "max_depth_mm": row["max_depth_mm"],
        "compatible_kinds": row.get("compatible_kinds"),
        "active": row["active"],
    }


def _jsonb_value(value: object) -> object:
    # rows() returns jsonb columns as raw text; decode before domain use.
    return json.loads(value) if isinstance(value, str) else value


def _jsonb_list(value: object) -> list[object]:
    decoded = _jsonb_value(value)
    return decoded if isinstance(decoded, list) else []


def _public_machine(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "code": row["code"],
        "name": row["name"],
        "manufacturer": row["manufacturer"],
        "model": row["model"],
        "controller_family": row["controller_family"],
        "coordinate_systems": row["coordinate_systems"],
        "supported_kinds": row["supported_kinds"],
        "supported_faces": row["supported_faces"],
        "max_member_length_mm": row["max_member_length_mm"],
        "safe_margin_mm": row["safe_margin_mm"],
        "clamp_zones": _jsonb_value(row["clamp_zones"]),
        "tool_ids": [str(tool_id) for tool_id in row["tool_ids"]],
        "postprocessor_id": row["postprocessor_id"],
        "postprocessor_version": row["postprocessor_version"],
        "units": row["units"],
        "encoding": row["encoding"],
        "active": row["active"],
        "machine_type": row.get("machine_type") or "MACHINING_CENTER",
        "axes_count": row.get("axes_count"),
        "travel_x_mm": row.get("travel_x_mm"),
        "travel_y_mm": row.get("travel_y_mm"),
        "travel_z_mm": row.get("travel_z_mm"),
    }


def _record_authority_event(
    *,
    org_id: UUID,
    entity: str,
    entity_id: object,
    entity_code: str,
    action: str,
    actor_id: UUID,
    before: dict[str, object] | None,
    after: dict[str, object],
) -> None:
    """Append one row to the authority audit trail. ``changed`` carries the
    field-level diff ({field: {from, to}}) — on create every declared field
    is a ``from: null`` entry. Runs inside the caller's
    ``documentary_backend`` transaction so the change and its record commit
    together or not at all."""
    changed: dict[str, object] = {}
    keys = set(after) | set(before or {})
    for key in sorted(keys):
        if key == "id":
            continue
        old = (before or {}).get(key)
        new = after.get(key)
        if old != new:
            changed[key] = {"from": old, "to": new}
    rows(
        """
        INSERT INTO public.cnc_authority_events
            (org_id, entity, entity_id, entity_code, action, actor_id, changed)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id
        """,
        [
            str(org_id),
            entity,
            str(entity_id),
            entity_code,
            action,
            str(actor_id),
            json.dumps(changed, default=str),
        ],
    )


def _authority_action(
    before: dict[str, object] | None, after: dict[str, object]
) -> str:
    if before is None:
        return "created"
    if before.get("active") is True and after.get("active") is False:
        return "deactivated"
    if before.get("active") is False and after.get("active") is True:
        return "reactivated"
    return "updated"


def list_authority_events(
    *, org_id: UUID, limit: int = 60
) -> list[dict[str, object]]:
    """Recent machine/tool authority changes for the workspace audit view —
    newest first, actor shown as id (the UI resolves names when it can)."""
    return [
        {
            "id": str(row["id"]),
            "entity": row["entity"],
            "entity_id": str(row["entity_id"]),
            "entity_code": row["entity_code"],
            "action": row["action"],
            "actor_id": str(row["actor_id"]) if row["actor_id"] else None,
            "changed": _jsonb_value(row["changed"]),
            "created_at": row["created_at"],
        }
        for row in rows(
            """
            SELECT id, entity, entity_id, entity_code, action, actor_id,
                   changed, created_at
            FROM public.cnc_authority_events
            WHERE org_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            [str(org_id), limit],
        )
    ]


def list_tools(*, org_id: UUID) -> list[dict[str, object]]:
    return [
        _public_tool(row)
        for row in rows(
            """
            SELECT id, code, name, kind, diameter_mm, working_length_mm,
                   max_depth_mm, compatible_kinds, active
            FROM public.cnc_tools WHERE org_id = %s ORDER BY code
            """,
            [str(org_id)],
        )
    ]


def create_tool(*, org_id: UUID, actor_id: UUID, data: dict[str, object]) -> dict[str, object]:
    code = str(data.get("code") or "").strip()
    name = str(data.get("name") or "").strip()
    kind = str(data.get("kind") or "")
    if not code or not name or kind not in _TOOL_KINDS:
        raise DocumentaryError("cnc_tool_invalid")
    compatible = _string_list(
        data.get("compatible_kinds"), allowed=_OP_KINDS, code="cnc_tool_kind_invalid"
    )
    with documentary_backend(), transaction.atomic():
        created = one(
            """
            INSERT INTO public.cnc_tools
                (org_id, code, name, kind, diameter_mm, working_length_mm,
                 max_depth_mm, compatible_kinds)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, code, name, kind, diameter_mm, working_length_mm,
                      max_depth_mm, compatible_kinds, active
            """,
            [
                str(org_id),
                code,
                name,
                kind,
                _dec(data.get("diameter_mm")),
                _dec(data.get("working_length_mm")),
                _dec(data.get("max_depth_mm")),
                compatible,
            ],
            "cnc_tool_invalid",
        )
        public = _public_tool(created)
        _record_authority_event(
            org_id=org_id,
            entity="tool",
            entity_id=created["id"],
            entity_code=str(created["code"]),
            action="created",
            actor_id=actor_id,
            before=None,
            after=public,
        )
    return public


def update_tool(
    *, org_id: UUID, tool_id: UUID, actor_id: UUID, data: dict[str, object]
) -> dict[str, object]:
    current = one(
        """
        SELECT id, code, name, kind, diameter_mm, working_length_mm,
               max_depth_mm, compatible_kinds, active
        FROM public.cnc_tools WHERE id = %s AND org_id = %s
        """,
        [str(tool_id), str(org_id)],
        "cnc_tool_not_found",
    )
    merged = {**_public_tool(current), **data}
    kind = str(merged["kind"])
    if kind not in _TOOL_KINDS:
        raise DocumentaryError("cnc_tool_invalid")
    compatible = _string_list(
        merged.get("compatible_kinds"), allowed=_OP_KINDS, code="cnc_tool_kind_invalid"
    )
    with documentary_backend(), transaction.atomic():
        updated = one(
            """
            UPDATE public.cnc_tools SET
                code = %s, name = %s, kind = %s, diameter_mm = %s,
                working_length_mm = %s, max_depth_mm = %s,
                compatible_kinds = %s, active = %s
            WHERE id = %s AND org_id = %s
            RETURNING id, code, name, kind, diameter_mm, working_length_mm,
                      max_depth_mm, compatible_kinds, active
            """,
            [
                str(merged["code"]).strip(),
                str(merged["name"]).strip(),
                kind,
                _dec(merged.get("diameter_mm")),
                _dec(merged.get("working_length_mm")),
                _dec(merged.get("max_depth_mm")),
                compatible,
                bool(merged["active"]),
                str(tool_id),
                str(org_id),
            ],
            "cnc_tool_not_found",
        )
        public = _public_tool(updated)
        _record_authority_event(
            org_id=org_id,
            entity="tool",
            entity_id=tool_id,
            entity_code=str(updated["code"]),
            action=_authority_action(_public_tool(current), public),
            actor_id=actor_id,
            before=_public_tool(current),
            after=public,
        )
    return public


def list_machines(*, org_id: UUID) -> list[dict[str, object]]:
    return [
        _public_machine(row)
        for row in rows(
            _MACHINE_SELECT
            + " WHERE org_id = %s ORDER BY code",
            [str(org_id)],
        )
    ]


def _clamp_zones(value: object) -> list[dict[str, object]]:
    value = _jsonb_value(value)
    if value is None:
        return []
    if not isinstance(value, list):
        raise DocumentaryError("cnc_clamp_zones_invalid")
    zones: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise DocumentaryError("cnc_clamp_zones_invalid")
        start = _dec(item.get("start_mm"))
        end = _dec(item.get("end_mm"))
        if start is None or end is None or end <= start:
            raise DocumentaryError("cnc_clamp_zones_invalid")
        zones.append(
            {
                "start_mm": str(start),
                "end_mm": str(end),
                "label": str(item.get("label") or "")[:120],
            }
        )
    return zones


def _tool_ids(value: object, *, org_id: UUID) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DocumentaryError("cnc_tool_ids_invalid")
    ids = [str(item) for item in value]
    if not ids:
        return []
    # Every magazine entry must resolve to an org tool — a phantom tool id
    # would make validation report the wrong blocker.
    found = rows(
        """
        SELECT id::text FROM public.cnc_tools
        WHERE org_id = %s AND id = ANY(%s::uuid[])
        """,
        [str(org_id), ids],
    )
    if {row["id"] for row in found} != set(ids):
        raise DocumentaryError("cnc_tool_not_in_org")
    return ids


def _machine_type(value: object) -> str:
    machine_type = str(value or "MACHINING_CENTER")
    if machine_type not in _MACHINE_TYPES:
        raise DocumentaryError("cnc_machine_type_invalid")
    return machine_type


def _axes_count(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        axes = int(str(value))
    except (TypeError, ValueError):
        raise DocumentaryError("cnc_machine_axes_invalid")
    if axes < 2 or axes > 6:
        raise DocumentaryError("cnc_machine_axes_invalid")
    return axes


def create_machine(
    *, org_id: UUID, actor_id: UUID, data: dict[str, object]
) -> dict[str, object]:
    code = str(data.get("code") or "").strip()
    name = str(data.get("name") or "").strip()
    if not code or not name:
        raise DocumentaryError("cnc_machine_invalid")
    supported_kinds = _string_list(
        data.get("supported_kinds"), allowed=_OP_KINDS, code="cnc_machine_kind_invalid"
    )
    supported_faces = _string_list(
        data.get("supported_faces"), allowed=_FACES, code="cnc_machine_face_invalid"
    )
    coordinates = _string_list(
        data.get("coordinate_systems"), allowed=_COORDS, code="cnc_machine_coord_invalid"
    ) or sorted(_COORDS)
    with documentary_backend(), transaction.atomic():
        created = one(
            """
            INSERT INTO public.cnc_machines
                (org_id, code, name, manufacturer, model, controller_family,
                 coordinate_systems, supported_kinds, supported_faces,
                 max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
                 postprocessor_id, postprocessor_version, units, encoding,
                 machine_type, axes_count, travel_x_mm, travel_y_mm, travel_z_mm)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::uuid[], %s, %s, %s, %s,
                    %s, %s, %s, %s, %s)
            RETURNING id, code, name, manufacturer, model, controller_family,
                      coordinate_systems, supported_kinds, supported_faces,
                      max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
                      postprocessor_id, postprocessor_version, units, encoding, active,
                      machine_type, axes_count, travel_x_mm, travel_y_mm, travel_z_mm
            """,
            [
                str(org_id),
                code,
                name,
                str(data.get("manufacturer") or "")[:120],
                str(data.get("model") or "")[:120],
                str(data.get("controller_family") or "NEUTRAL")[:80],
                coordinates,
                supported_kinds,
                supported_faces,
                _dec(data.get("max_member_length_mm")),
                _dec(data.get("safe_margin_mm")),
                json.dumps(_clamp_zones(data.get("clamp_zones"))),
                _tool_ids(data.get("tool_ids"), org_id=org_id),
                str(data.get("postprocessor_id") or "neutral-ops-v1")[:80],
                str(data.get("postprocessor_version") or "1")[:40],
                str(data.get("units") or "mm")[:20],
                str(data.get("encoding") or "utf-8")[:40],
                _machine_type(data.get("machine_type")),
                _axes_count(data.get("axes_count")),
                _dec(data.get("travel_x_mm")),
                _dec(data.get("travel_y_mm")),
                _dec(data.get("travel_z_mm")),
            ],
            "cnc_machine_invalid",
        )
        public = _public_machine(created)
        _record_authority_event(
            org_id=org_id,
            entity="machine",
            entity_id=created["id"],
            entity_code=str(created["code"]),
            action="created",
            actor_id=actor_id,
            before=None,
            after=public,
        )
    return public


def update_machine(
    *, org_id: UUID, machine_id: UUID, actor_id: UUID, data: dict[str, object]
) -> dict[str, object]:
    current = _public_machine(
        one(
            _MACHINE_SELECT + " WHERE id = %s AND org_id = %s",
            [str(machine_id), str(org_id)],
            "cnc_machine_not_found",
        )
    )
    merged = {**current, **data}
    supported_kinds = _string_list(
        merged.get("supported_kinds"), allowed=_OP_KINDS, code="cnc_machine_kind_invalid"
    )
    supported_faces = _string_list(
        merged.get("supported_faces"), allowed=_FACES, code="cnc_machine_face_invalid"
    )
    coordinates = _string_list(
        merged.get("coordinate_systems"),
        allowed=_COORDS,
        code="cnc_machine_coord_invalid",
    )
    with documentary_backend(), transaction.atomic():
        updated = one(
            """
            UPDATE public.cnc_machines SET
                code = %s, name = %s, manufacturer = %s, model = %s,
                controller_family = %s, coordinate_systems = %s,
                supported_kinds = %s, supported_faces = %s,
                max_member_length_mm = %s, safe_margin_mm = %s,
                clamp_zones = %s::jsonb, tool_ids = %s::uuid[],
                postprocessor_id = %s, postprocessor_version = %s,
                units = %s, encoding = %s, active = %s, updated_at = %s,
                machine_type = %s, axes_count = %s,
                travel_x_mm = %s, travel_y_mm = %s, travel_z_mm = %s
            WHERE id = %s AND org_id = %s
            RETURNING id, code, name, manufacturer, model, controller_family,
                      coordinate_systems, supported_kinds, supported_faces,
                      max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
                      postprocessor_id, postprocessor_version, units, encoding, active,
                      machine_type, axes_count, travel_x_mm, travel_y_mm, travel_z_mm
            """,
            [
                str(merged["code"]).strip(),
                str(merged["name"]).strip(),
                str(merged.get("manufacturer") or "")[:120],
                str(merged.get("model") or "")[:120],
                str(merged.get("controller_family") or "NEUTRAL")[:80],
                coordinates,
                supported_kinds,
                supported_faces,
                _dec(merged.get("max_member_length_mm")),
                _dec(merged.get("safe_margin_mm")),
                json.dumps(_clamp_zones(merged.get("clamp_zones"))),
                _tool_ids(merged.get("tool_ids"), org_id=org_id),
                str(merged.get("postprocessor_id") or "neutral-ops-v1")[:80],
                str(merged.get("postprocessor_version") or "1")[:40],
                str(merged.get("units") or "mm")[:20],
                str(merged.get("encoding") or "utf-8")[:40],
                bool(merged.get("active", True)),
                datetime.now(timezone.utc),
                _machine_type(merged.get("machine_type")),
                _axes_count(merged.get("axes_count")),
                _dec(merged.get("travel_x_mm")),
                _dec(merged.get("travel_y_mm")),
                _dec(merged.get("travel_z_mm")),
                str(machine_id),
                str(org_id),
            ],
            "cnc_machine_not_found",
        )
        public = _public_machine(updated)
        _record_authority_event(
            org_id=org_id,
            entity="machine",
            entity_id=machine_id,
            entity_code=str(updated["code"]),
            action=_authority_action(current, public),
            actor_id=actor_id,
            before=current,
            after=public,
        )
    return public


def _machine_profile(
    machine_row: dict[str, object], tools_by_id: dict[str, dict[str, object]]
) -> MachineProfile:
    magazine: list[Tool] = []
    for tool_id in machine_row["tool_ids"] or []:
        tool = tools_by_id.get(str(tool_id))
        if tool is None:
            continue
        magazine.append(
            Tool(
                tool_id=str(tool["code"]),
                kind=ToolKind(str(tool["kind"])),
                name=str(tool["name"]),
                diameter_mm=_dec(tool.get("diameter_mm")),
                working_length_mm=_dec(tool.get("working_length_mm")),
                max_depth_mm=_dec(tool.get("max_depth_mm")),
                compatible_kinds=(
                    [OperationKind(kind) for kind in tool["compatible_kinds"]]
                    if tool.get("compatible_kinds")
                    else None
                ),
            )
        )
    return MachineProfile(
        machine_id=str(machine_row["code"]),
        name=str(machine_row["name"]),
        controller_family=str(machine_row["controller_family"]),
        coordinate_systems=[
            CoordinateSystem(value) for value in machine_row["coordinate_systems"] or []
        ],
        tools=magazine,
        supported_kinds=(
            [OperationKind(kind) for kind in machine_row["supported_kinds"]]
            if machine_row.get("supported_kinds")
            else None
        ),
        supported_faces=(
            [MemberFace(face) for face in machine_row["supported_faces"]]
            if machine_row.get("supported_faces")
            else None
        ),
        max_member_length_mm=_dec(machine_row.get("max_member_length_mm")),
        safe_margin_mm=_dec(machine_row.get("safe_margin_mm")),
        clamp_zones=[
            ClampZone(
                start_mm=Decimal(str(zone["start_mm"])),
                end_mm=Decimal(str(zone["end_mm"])),
                label=str(zone.get("label") or ""),
            )
            for zone in _jsonb_list(machine_row.get("clamp_zones"))
            if isinstance(zone, dict)
        ],
        postprocessor_id=str(machine_row["postprocessor_id"]),
        postprocessor_version=str(machine_row["postprocessor_version"]),
        units=str(machine_row["units"]),
        encoding=str(machine_row["encoding"]),
    )


def _order_ops(*, org_id: UUID, order_id: UUID) -> dict[str, object]:
    """Load the order's sealed plan + facts and derive the canonical ops —
    the same derivation the ops export runs, so readiness and programs can
    never disagree with what the shop already sees."""
    order = one(
        """
        SELECT id, order_code, status::text, payload_json, project_version_id,
               project_id
        FROM public.orders
        WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
        """,
        [str(order_id), str(org_id)],
        "work_order_not_found",
    )
    payload = _decoded(order["payload_json"])
    optimization = payload.get("optimization")
    if not isinstance(optimization, dict) or not optimization:
        raise DocumentaryError("operations_requires_optimization")
    if optimization.get("invalidated"):
        raise DocumentaryError("plan_invalidated")
    with documentary_backend():
        version_row = one(
            """
            SELECT snapshot_json, revision_code, project_id
            FROM public.project_versions WHERE id = %s AND org_id = %s
            """,
            [str(order["project_version_id"]), str(org_id)],
            "work_order_missing_version",
        )
    version_snapshot = _decoded(version_row["snapshot_json"])
    position_id = str(payload.get("position_id") or "") or None
    fact_units = _operations_fact_units(version_snapshot, position_id)
    bars = [
        CutBar.model_validate_json(json.dumps(bar))
        for bar in (optimization.get("bars") or {}).get("workshop_cut_plan") or []
    ]
    ops_issues: list[dict[str, object]] = []
    ops = operations_from_plan(
        bars=bars, fact_units=fact_units, issues=ops_issues
    )
    ops_issues.extend(
        _declared_intent_gaps(
            version_snapshot,
            str(payload.get("position_id") or "") or None,
            {op.kind.value for op in ops},
        )
    )
    labels = _piece_labels(version_snapshot)
    member_labels = {
        str(member_id): code for member_id, code in labels.get("member", {}).items()
    }
    member_labels.update(
        {str(rid): code for rid, code in labels.get("reinforcement", {}).items()}
    )
    cut_map = _cut_member_map(version_snapshot, labels)
    for bar in (optimization.get("bars") or {}).get("workshop_cut_plan") or []:
        if isinstance(bar, dict):
            for cut in bar.get("cuts") or []:
                if isinstance(cut, dict) and cut.get("piece_id"):
                    member_labels.setdefault(
                        str(cut["piece_id"]),
                        str(cut_map.get(_cut_key(cut), "")),
                    )
    member_lengths = {
        member.member_id: member.cut_length_mm
        for unit in fact_units
        for member in unit.members
    }
    manufacturing = _raw_fact_units(version_snapshot, position_id)
    input_fingerprint = _ops_source_fingerprint(optimization, manufacturing)
    project_code = ""
    if order.get("project_id"):
        # project_manual_read excludes floor roles — the operator's CNC
        # file must still carry the project code it was cut for.
        with documentary_backend():
            project = rows(
                "SELECT code FROM public.projects WHERE id = %s AND org_id = %s",
                [str(order["project_id"]), str(org_id)],
            )
        project_code = str(project[0]["code"]) if project else ""
    return {
        "order": order,
        "payload": payload,
        "optimization": optimization,
        "ops": ops,
        "ops_issues": ops_issues,
        "fact_units": fact_units,
        "member_labels": member_labels,
        "member_lengths": member_lengths,
        "input_fingerprint": input_fingerprint,
        "version_snapshot": version_snapshot,
        "position_id": position_id,
        "identity": {
            "order_code": str(order["order_code"]),
            "project_code": project_code,
            "revision_code": str(version_row.get("revision_code") or ""),
            "position_id": position_id or "",
            "plan_seed": str(
                (optimization.get("bars") or {}).get("plan_seed") or ""
            ),
        },
    }


def _tools_by_id(*, org_id: UUID) -> dict[str, dict[str, object]]:
    return {
        str(row["id"]): row
        for row in rows(
            """
            SELECT id::text, code, name, kind, diameter_mm, working_length_mm,
                   max_depth_mm, compatible_kinds, active
            FROM public.cnc_tools WHERE org_id = %s
            """,
            [str(org_id)],
        )
    }


# Postprocessors that actually emit bytes. A machine can declare any
# postprocessor_id — when no renderer implements it, readiness reports
# ``emitter_not_implemented`` and program generation refuses. Lo desconocido
# bloquea: never silently ship neutral ops as another vendor's format.
_POSTPROCESSORS: dict[str, PostProcessor] = {
    "neutral-ops-v1": NeutralOpsPostProcessor(),
}


def _postprocessor(postprocessor_id: object) -> PostProcessor | None:
    return _POSTPROCESSORS.get(str(postprocessor_id or "neutral-ops-v1"))


# Workshop-annotation fields that declare machine work no emitter produces
# yet, mapped to the op kind they would run as. ``has_coupler`` is a boolean.
_ANNOTATION_GAP_SOURCES: tuple[tuple[str, str], ...] = (
    ("bottom_drain_holes_mm", "DRAINAGE"),
    ("closing_points_perimeter_mm", "LOCK_PREP"),
    ("has_coupler", "T_CONNECTOR"),
)
# Hardware machining declarations → the op kind they would run as for
# capability checking. OTHER declarations can't be assessed — their cause
# stays "unassessable" rather than borrowing another kind's answer.
_HW_MACHINING_OP_KIND = {
    "LOCK_PREP": "LOCK_PREP",
    "ESPAG_HOUSING": "LOCK_PREP",
    "HINGE_PREP": "HINGE_PREP",
    "DRAINAGE": "DRAINAGE",
}


def _declared_gaps(bundle: dict[str, object]) -> list[dict[str, object]]:
    """Workshop annotations + hardware machining declarations that no
    emitter turned into ops. Every record names the source it came from and
    the cause it is missing — "sin regla", "sin coordenadas" — never a
    guessed operation."""
    emitted = {op.kind.value for op in bundle["ops"]}
    version_snapshot = bundle["version_snapshot"]
    position_id = bundle["position_id"]
    gaps: list[dict[str, object]] = []
    for position in version_snapshot.get("positions") or []:
        if not isinstance(position, dict):
            continue
        if position_id and str(position.get("id")) != position_id:
            continue
        for item in position.get("workshop_annotations") or []:
            if not isinstance(item, dict):
                continue
            for field, kind in _ANNOTATION_GAP_SOURCES:
                if not item.get(field) or kind in emitted:
                    continue
                gaps.append(
                    {
                        "kind": kind,
                        "op_kind": kind,
                        "cause": "no_rule",
                        "source": f"workshop_annotations.{field}",
                        "declared_value": str(item.get(field)),
                        "bay_id": item.get("bay_id") or position.get("bay_id"),
                        "leaf_id": item.get("leaf_id") or position.get("leaf_id"),
                        "member_id": None,
                        "kit_sku": None,
                    }
                )
        if position.get("handle_intents") and "HANDLE_PREP" not in emitted:
            gaps.append(
                {
                    "kind": "HANDLE_PREP",
                    "op_kind": "HANDLE_PREP",
                    "cause": "no_rule",
                    "source": "handle_intents",
                    "declared_value": str(len(position["handle_intents"])),
                    "bay_id": position.get("bay_id"),
                    "leaf_id": position.get("leaf_id"),
                    "member_id": None,
                    "kit_sku": None,
                }
            )
    for declaration in bundle["payload"].get("hardware_machining") or []:
        if not isinstance(declaration, dict):
            continue
        if str(declaration.get("status") or "") != "DECLARED_NOT_EMITTED":
            continue
        kind = str(declaration.get("kind") or "OTHER")
        op_kind = _HW_MACHINING_OP_KIND.get(kind)
        # DECLARED_NOT_EMITTED always means the declaration shipped without
        # coordinates (u_mm) — that is the reason no emitter ran, not an
        # emitter defect.
        if op_kind in emitted:
            continue
        gaps.append(
            {
                "kind": kind,
                "op_kind": op_kind,
                "cause": "no_coordinates",
                "source": "hardware_machining",
                "declared_value": declaration.get("detail") or "",
                "bay_id": declaration.get("bay_id"),
                "leaf_id": declaration.get("leaf_id"),
                "member_id": declaration.get("member_id"),
                "kit_sku": declaration.get("kit_sku"),
            }
        )
    for index, gap in enumerate(gaps):
        gap["gap_id"] = hashlib.sha256(
            "|".join(
                str(part)
                for part in (
                    bundle["order"]["id"],
                    gap["source"],
                    gap["kind"],
                    gap["member_id"],
                    gap["bay_id"],
                    gap["leaf_id"],
                    index,
                )
            ).encode("utf-8")
        ).hexdigest()[:32]
    return gaps


def _gap_machine_checks(
    gaps: list[dict[str, object]],
    machine_rows: list[dict[str, object]],
    tools_by_id: dict[str, dict[str, object]],
) -> None:
    """Per-machine honest capability on every gap: ``can_run`` only when the
    machine declares the kind AND a magazine tool covers it; otherwise the
    blocker cause is named (``no_tool``/``unsupported_kind``/
    ``unassessable``/``emitter_not_implemented``). Mutates gap dicts."""
    for gap in gaps:
        op_kind = gap.get("op_kind")
        checks: list[dict[str, object]] = []
        for machine in machine_rows:
            machine_id = str(machine["id"])
            if _postprocessor(machine.get("postprocessor_id")) is None:
                checks.append(
                    {
                        "machine_id": machine_id,
                        "machine_code": machine["code"],
                        "can_run": False,
                        "cause": "emitter_not_implemented",
                    }
                )
                continue
            if op_kind is None:
                checks.append(
                    {
                        "machine_id": machine_id,
                        "machine_code": machine["code"],
                        "can_run": False,
                        "cause": "unassessable",
                    }
                )
                continue
            kinds = machine.get("supported_kinds")
            if isinstance(kinds, str):
                kinds = _jsonb_value(kinds)
            if kinds and op_kind not in kinds:
                checks.append(
                    {
                        "machine_id": machine_id,
                        "machine_code": machine["code"],
                        "can_run": False,
                        "cause": "unsupported_kind",
                    }
                )
                continue
            magazine = [
                tools_by_id[str(tool_id)]
                for tool_id in (machine.get("tool_ids") or [])
                if str(tool_id) in tools_by_id
            ]
            has_tool = any(
                not tool.get("compatible_kinds")
                or op_kind in (tool.get("compatible_kinds") or [])
                for tool in magazine
                if tool.get("active") is not False
            )
            checks.append(
                {
                    "machine_id": machine_id,
                    "machine_code": machine["code"],
                    "can_run": has_tool,
                    "cause": "" if has_tool else "no_tool",
                }
            )
        gap["machines"] = checks


def cnc_readiness(
    *, org_id: UUID, order_id: UUID, machine_id: UUID | None = None
) -> dict[str, object]:
    """Per-member machining readiness against the org's real machines:
    every member that carries MEMBER ops gets a verdict + named blockers."""
    bundle = _order_ops(org_id=org_id, order_id=order_id)
    machines = rows(
        _MACHINE_SELECT
        + " WHERE org_id = %s AND active"
        + (" AND id = %s" if machine_id else "")
        + " ORDER BY code",
        [str(org_id)] + ([str(machine_id)] if machine_id else []),
    )
    tools_by_id = _tools_by_id(org_id=org_id)
    member_ops: dict[str, list] = {}
    for op in bundle["ops"]:
        if op.host_kind == "MEMBER":
            member_ops.setdefault(op.host, []).append(op)
    member_ids = sorted(member_ops.keys())
    machine_rows = machines
    machine_profiles = [
        _machine_profile(row, tools_by_id) for row in machine_rows
    ]
    member_meta = member_meta_map(bundle["fact_units"])
    members: list[dict[str, object]] = []
    for member_id in member_ids:
        label = bundle["member_labels"].get(member_id) or member_id[:8]
        meta = member_meta.get(member_id) or {}
        ops = member_ops[member_id]
        op_ids = {op.operation_id for op in ops}
        machine_results: list[dict[str, object]] = []
        for profile, machine_row in zip(machine_profiles, machine_rows):
            # A machine whose postprocessor no renderer implements can never
            # emit a file — every member verdict on it is honestly BLOCK with
            # that named cause, not a downstream validation artifact.
            emitter_missing = (
                _postprocessor(machine_row.get("postprocessor_id")) is None
            )
            validations = [
                item
                for item in validate_operations(
                    ops,
                    profile,
                    member_lengths_mm=bundle["member_lengths"],
                    member_labels=bundle["member_labels"],
                )
                # A member's verdict covers its own ops only — a blocker on
                # M-03 must not render M-07 as BLOCK on this machine.
                if item.operation_id in op_ids
            ]
            blockers = [item for item in validations if item.level == "BLOCK"]
            warnings = [item for item in validations if item.level == "WARN"]
            machine_results.append(
                {
                    "machine_id": str(machine_row["id"]),
                    "machine_code": machine_row["code"],
                    "machine_name": machine_row["name"],
                    "verdict": (
                        "BLOCK"
                        if blockers or emitter_missing
                        else ("WARN" if warnings else "PASS")
                    ),
                    "blockers": [
                        item.model_dump(mode="json") for item in blockers
                    ]
                    + (
                        [
                            {
                                "operation_id": "",
                                "level": "BLOCK",
                                "code": "emitter_not_implemented",
                                "detail": {
                                    "postprocessor_id": str(
                                        machine_row.get("postprocessor_id")
                                        or "neutral-ops-v1"
                                    ),
                                },
                            }
                        ]
                        if emitter_missing
                        else []
                    ),
                    "warnings": [item.model_dump(mode="json") for item in warnings],
                }
            )
        members.append(
            {
                "member_id": member_id,
                "member_label": label,
                "workshop_sku": meta.get("workshop_sku"),
                "role": meta.get("role"),
                "material": meta.get("material"),
                "axis": meta.get("axis"),
                "start": meta.get("start"),
                "end": meta.get("end"),
                "angle_left_deg": meta.get("angle_left_deg"),
                "angle_right_deg": meta.get("angle_right_deg"),
                "leaf_slot": meta.get("leaf_slot"),
                "repetition_index": meta.get("repetition_index"),
                "bay_id": meta.get("bay_id"),
                "leaf_id": meta.get("leaf_id"),
                "position_index": meta.get("position_index"),
                "length_mm": str(bundle["member_lengths"].get(member_id) or ""),
                "operation_count": len(ops),
                "kinds": sorted({op.kind.value for op in ops}),
                "machines": machine_results,
                "operations": [
                    {
                        "operation_id": op.operation_id,
                        "kind": op.kind.value,
                        "u_mm": str(op.u_mm) if op.u_mm is not None else None,
                        "x_mm": str(op.x_mm) if op.x_mm is not None else None,
                        "y_mm": str(op.y_mm) if op.y_mm is not None else None,
                        "face": op.face.value if op.face else None,
                        "reference": op.reference,
                        "depth_mm": str(op.depth_mm) if op.depth_mm is not None else None,
                        "angle_left_deg": str(op.angle_left_deg)
                        if op.angle_left_deg is not None
                        else None,
                        "angle_right_deg": str(op.angle_right_deg)
                        if op.angle_right_deg is not None
                        else None,
                        "tool_id": op.tool_id,
                        "basis": op.basis,
                        "detail": op.detail,
                    }
                    for op in ops
                ],
            }
        )
    gaps = _declared_gaps(bundle)
    _gap_machine_checks(gaps, machine_rows, tools_by_id)
    machines_public = [_public_machine(row) for row in machine_rows]
    for machine_public, machine_row in zip(machines_public, machine_rows):
        machine_public["emitter_implemented"] = (
            _postprocessor(machine_row.get("postprocessor_id")) is not None
        )
    return {
        "order_id": str(order_id),
        "order_code": bundle["order"]["order_code"],
        "plan": {
            "fingerprint": str(bundle["input_fingerprint"]),
            "plan_seed": bundle["identity"]["plan_seed"],
            "position_id": bundle["identity"]["position_id"],
        },
        "members": members,
        "declared_gaps": gaps,
        "issues": bundle["ops_issues"],
        # The op tool_ids a magazine must bind literally — without this list
        # a programmer has to guess that code "drill"/"end_mill" is required.
        "required_tool_ids": sorted(
            {op.tool_id for op in bundle["ops"] if op.tool_id}
        ),
        "machines": machines_public,
        "programs": list_programs(org_id=org_id, order_id=order_id),
    }


def _machine_fingerprint(profile: MachineProfile) -> str:
    """Content hash of the resolved machine profile — tools, limits, clamps,
    postprocessor. A machine-config change stales the programs generated
    against the previous profile, exactly like a plan change does."""
    return hashlib.sha256(
        json.dumps(
            profile.model_dump(mode="json"), sort_keys=True, default=str
        ).encode("utf-8")
    ).hexdigest()


def _program_input(plan_fingerprint: str, machine_fingerprint: str) -> str:
    return f"{plan_fingerprint}+{machine_fingerprint}"


def _expected_program_input(
    *, org_id: UUID, order_id: UUID, machine_id: str | None,
) -> str | None:
    """The fingerprint a CURRENT program for this machine would carry today:
    sealed plan inputs + the machine profile as it exists now. None when the
    plan or the machine can't be resolved (everything then reads stale)."""
    if not machine_id:
        return None
    try:
        bundle = _order_ops(org_id=org_id, order_id=order_id)
        machine_row = rows(
            _MACHINE_SELECT + " WHERE id = %s AND org_id = %s",
            [str(machine_id), str(org_id)],
        )
    except DocumentaryError:
        return None
    if not machine_row:
        return None
    machine_fp = _machine_fingerprint(
        _machine_profile(machine_row[0], _tools_by_id(org_id=org_id))
    )
    return _program_input(str(bundle["input_fingerprint"]), machine_fp)


def _program_no(*, order_code: str, member_label: str, machine_code: str, seq: int) -> str:
    label = "".join(ch for ch in member_label if ch.isalnum())[:12] or "M"
    return f"{order_code}-{label}-{machine_code}-{seq:02d}"


def generate_program(
    *, org_id: UUID, order_id: UUID, machine_id: UUID, member_id: str,
    actor_id: UUID,
) -> dict[str, object]:
    bundle = _order_ops(org_id=org_id, order_id=order_id)
    if str(bundle["order"]["status"]) == "CANCELLED":
        raise DocumentaryError("work_order_cancelled")
    tools_by_id = _tools_by_id(org_id=org_id)
    machine_row = one(
        _MACHINE_SELECT + " WHERE id = %s AND org_id = %s AND active",
        [str(machine_id), str(org_id)],
        "cnc_machine_not_found",
    )
    profile = _machine_profile(machine_row, tools_by_id)
    postprocessor = _postprocessor(machine_row.get("postprocessor_id"))
    if postprocessor is None:
        # The machine declares an emitter nobody implemented — refuse the
        # file instead of silently shipping neutral ops as its format.
        raise DocumentaryError(
            "cnc_emitter_not_implemented",
            detail=(
                f"{machine_row['code']} declara el emisor "
                f"'{machine_row['postprocessor_id']}' y no hay ningún "
                "postprocesador implementado que lo renderice."
            ),
        )
    member_ops = [
        op
        for op in bundle["ops"]
        if op.host_kind == "MEMBER" and op.host == member_id
    ]
    if not member_ops:
        raise DocumentaryError("cnc_member_no_ops")
    validations = validate_operations(
        bundle["ops"],
        profile,
        member_lengths_mm=bundle["member_lengths"],
        member_labels=bundle["member_labels"],
    )
    member_blockers = [
        item
        for item in validations
        if item.level == "BLOCK"
        and item.operation_id in {op.operation_id for op in member_ops}
    ]
    if member_blockers:
        # Physical language: which member, which machine, which blocker.
        label = bundle["member_labels"].get(member_id) or member_id[:8]
        first = member_blockers[0]
        raise DocumentaryError(
            "cnc_program_blocked",
            detail=(
                f"{label} no puede mecanizarse en {machine_row['code']}: "
                f"{first.code} ({', '.join(sorted(first.detail.values()))})."
            ),
            extra={
                "blockers": [item.model_dump(mode="json") for item in member_blockers],
            },
        )
    document = member_program(
        bundle["ops"],
        member_id=member_id,
        member_label=bundle["member_labels"].get(member_id) or member_id[:8],
        machine=profile,
        identity=bundle["identity"],
        validations=validations,
        issues=bundle["ops_issues"],
    )
    # Ship the member's sealed geometry inside the program's ops doc so a
    # vendor adapter holding only the file can resolve the host's datum,
    # axis, length and end angles.
    member_fact = next(
        (
            member
            for unit in bundle["fact_units"]
            for member in unit.members
            if member.member_id == member_id
        ),
        None,
    )
    seq_row = one(
        """
        SELECT COUNT(*) + 1 AS seq FROM public.cnc_programs
        WHERE org_id = %s AND work_order_id = %s AND machine_id = %s AND member_id = %s
        """,
        [str(org_id), str(order_id), str(machine_id), member_id],
        "cnc_program_invalid",
    )
    program_no = _program_no(
        order_code=str(bundle["order"]["order_code"]),
        member_label=str(document["identity"]["member_label"]),
        machine_code=str(machine_row["code"]),
        seq=int(seq_row["seq"]),
    )
    files = postprocessor.render(
        {
            "schema": "dekopen_ops_v1",
            "order_code": bundle["identity"]["order_code"],
            "project_code": bundle["identity"]["project_code"],
            "revision_code": bundle["identity"]["revision_code"],
            "plan_seed": bundle["identity"]["plan_seed"],
            "machine": profile.model_dump(mode="json"),
            "operation_count": document["operation_count"],
            "counts_by_kind": document["counts_by_kind"],
            # The member file must admit the same coverage gap the order
            # document reports — never claim nothing was unemitted.
            "unemitted_kinds": sorted(
                _OP_KINDS - {op.kind.value for op in bundle["ops"]}
            ),
            "declared_intent_gaps": [
                issue["kind"]
                for issue in bundle["ops_issues"]
                if issue.get("code") == "declared_intent_not_emitted"
            ],
            "issues": document["issues"],
            "members": (
                {
                    member_id: {
                        "workshop_sku": member_fact.workshop_sku,
                        "material": member_fact.material.value,
                        "role": member_fact.identity.role.value,
                        "cut_length_mm": str(member_fact.cut_length_mm),
                        "angle_left_deg": str(member_fact.angle_left),
                        "angle_right_deg": str(member_fact.angle_right),
                        "axis": member_fact.axis.value,
                        "start": {
                            "x_mm": str(member_fact.start.x_mm),
                            "y_mm": str(member_fact.start.y_mm),
                        },
                        "end": {
                            "x_mm": str(member_fact.end.x_mm),
                            "y_mm": str(member_fact.end.y_mm),
                        },
                        "sagitta_mm": (
                            str(member_fact.sagitta_mm)
                            if member_fact.sagitta_mm is not None
                            else None
                        ),
                        "bay_id": member_fact.bay_id,
                        "leaf_id": member_fact.leaf_id,
                        "leaf_slot": member_fact.identity.leaf_slot,
                    }
                }
                if member_fact is not None
                else {}
            ),
            "piece_labels": bundle["member_labels"],
            "operations": document["operations"],
        }
    )
    # The stored fingerprint binds plan inputs AND the machine profile — a
    # machine-config change invalidates the program like a plan change does.
    program_input = _program_input(
        str(bundle["input_fingerprint"]), _machine_fingerprint(profile)
    )
    # Export manifest: which files this program ships, byte-identical hashes
    # to verify them against, and who generated it — the operator can check
    # what goes to which machine without opening each file.
    files["manifest.json"] = json.dumps(
        {
            "schema": "dekopen_export_manifest_v1",
            "kind": "cnc_program",
            "program_no": program_no,
            "identity": document["identity"],
            "verdict": document["verdict"],
            "fingerprint": document["fingerprint"],
            "input_fingerprint": program_input,
            "machine": {
                "id": str(machine_row["id"]),
                "code": machine_row["code"],
                "postprocessor_id": profile.postprocessor_id,
                "postprocessor_version": profile.postprocessor_version,
            },
            "files": {
                name: {
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "bytes": len(content.encode("utf-8")),
                }
                for name, content in files.items()
            },
            "operation_count": document["operation_count"],
            "counts_by_kind": document["counts_by_kind"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": str(actor_id),
        },
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"
    with transaction.atomic(), documentary_backend():
        write(
            """
            UPDATE public.cnc_programs SET status = 'SUPERSEDED'
            WHERE org_id = %s AND work_order_id = %s AND machine_id = %s
              AND member_id = %s AND status = 'CURRENT'
            """,
            [str(org_id), str(order_id), str(machine_id), member_id],
        )
        created = one(
            """
            INSERT INTO public.cnc_programs
                (org_id, work_order_id, machine_id, member_id, member_label,
                 program_no, operation_count, verdict, fingerprint,
                 input_fingerprint, identity, files, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            RETURNING id, program_no, verdict, fingerprint, created_at
            """,
            [
                str(org_id),
                str(order_id),
                str(machine_id),
                member_id,
                document["identity"]["member_label"],
                program_no,
                int(document["operation_count"]),
                str(document["verdict"]),
                str(document["fingerprint"]),
                program_input,
                json.dumps(document["identity"]),
                json.dumps(files),
                str(actor_id),
            ],
            "cnc_program_invalid",
        )
        # Point each superseded program at its successor — "Reemplazado"
        # must name what replaced it, not just that it did.
        write(
            """
            UPDATE public.cnc_programs SET superseded_by = %s
            WHERE org_id = %s AND work_order_id = %s AND machine_id = %s
              AND member_id = %s AND status = 'SUPERSEDED'
              AND superseded_by IS NULL
            """,
            [str(created["id"]), str(org_id), str(order_id), str(machine_id),
             member_id],
        )
        rows(
            """
            INSERT INTO public.production_step_events(org_id, order_id, event, actor_id, payload)
            VALUES (%s, %s, 'WO_CNC_PROGRAM', %s, %s::jsonb)
            RETURNING id
            """,
            [
                str(org_id),
                str(order_id),
                str(actor_id),
                json.dumps(
                    {
                        "program_no": created["program_no"],
                        "member_id": member_id,
                        "member_label": document["identity"]["member_label"],
                        "machine_code": machine_row["code"],
                        "operation_count": document["operation_count"],
                        "verdict": document["verdict"],
                    }
                ),
            ],
        )
    return {
        "id": str(created["id"]),
        "program_no": created["program_no"],
        "verdict": document["verdict"],
        "fingerprint": document["fingerprint"],
        "operation_count": document["operation_count"],
        "member_label": document["identity"]["member_label"],
        "machine_code": machine_row["code"],
        "files": files,
        "created_at": created["created_at"],
    }


def list_programs(*, org_id: UUID, order_id: UUID) -> list[dict[str, object]]:
    program_rows = rows(
        """
        SELECT p.id, p.program_no, p.member_id, p.member_label, p.operation_count,
               p.verdict, p.fingerprint, p.input_fingerprint, p.status,
               p.created_at, p.machine_id::text, m.code AS machine_code,
               p.identity::text AS identity_json,
               succ.id::text AS succ_id, succ.program_no AS succ_no
        FROM public.cnc_programs p
        LEFT JOIN public.cnc_machines m ON m.id = p.machine_id
        LEFT JOIN public.cnc_programs succ ON succ.id = p.superseded_by
        WHERE p.org_id = %s AND p.work_order_id = %s
        ORDER BY p.created_at DESC
        """,
        [str(org_id), str(order_id)],
    )
    if not program_rows:
        return []
    # Fresh staleness: a program whose inputs changed since generation is
    # reported stale even if it still reads CURRENT (lazy supersede on
    # read — operators see the truth without a background job). Inputs now
    # include the machine profile, so editing clamps/tools/postprocessor
    # also stales the file.
    try:
        bundle = _order_ops(org_id=org_id, order_id=order_id)
        current_plan_input = str(bundle["input_fingerprint"])
    except DocumentaryError:
        current_plan_input = ""
    tools_by_id = _tools_by_id(org_id=org_id)
    machine_rows = rows(
        _MACHINE_SELECT + " WHERE org_id = %s",
        [str(org_id)],
    )
    expected_by_machine = {
        str(row["id"]): _program_input(
            current_plan_input,
            _machine_fingerprint(_machine_profile(row, tools_by_id)),
        )
        for row in machine_rows
    }
    output: list[dict[str, object]] = []
    for row in program_rows:
        stale = (
            row["input_fingerprint"]
            != expected_by_machine.get(str(row["machine_id"]), "")
            or bool(row["status"] == "SUPERSEDED")
        )
        identity = _decoded(row["identity_json"]) or {}
        output.append(
            {
                "id": str(row["id"]),
                "program_no": row["program_no"],
                "member_id": row["member_id"],
                "member_label": row["member_label"],
                "operation_count": row["operation_count"],
                "verdict": row["verdict"],
                "fingerprint": row["fingerprint"],
                "status": "SUPERSEDED" if stale else "CURRENT",
                "machine_code": row["machine_code"],
                # The plan fingerprint + optimization seed this program was
                # cut from — re-optimization produces a different plan part.
                "input_fingerprint": row["input_fingerprint"],
                "plan_fingerprint": str(row["input_fingerprint"]).split("+")[0],
                "plan_seed": identity.get("plan_seed") or "",
                "superseded_by": (
                    {"id": row["succ_id"], "program_no": row["succ_no"]}
                    if row.get("succ_id")
                    else None
                ),
                "created_at": row["created_at"],
            }
        )
    return output


def program_file(
    *, org_id: UUID, program_id: UUID, filename: str
) -> tuple[str, str] | None:
    program = one(
        """
        SELECT p.program_no, p.files::text, p.input_fingerprint, p.status,
               p.work_order_id::text, p.machine_id::text
        FROM public.cnc_programs p
        WHERE p.id = %s AND p.org_id = %s
        """,
        [str(program_id), str(org_id)],
        "cnc_program_not_found",
    )
    if program["status"] == "SUPERSEDED":
        raise DocumentaryError("cnc_program_superseded")
    expected_input = _expected_program_input(
        org_id=org_id,
        order_id=UUID(str(program["work_order_id"])),
        machine_id=str(program["machine_id"]),
    )
    if expected_input is None or str(program["input_fingerprint"]) != expected_input:
        # The plan moved under the program — flip it so downloads stop
        # pretending this file is current.
        with documentary_backend():
            write(
                """
                UPDATE public.cnc_programs SET status = 'SUPERSEDED'
                WHERE id = %s AND org_id = %s
                """,
                [str(program_id), str(org_id)],
            )
        raise DocumentaryError("cnc_program_superseded")
    files = _decoded(program["files"])
    content = files.get(filename)
    if not isinstance(content, str):
        return None
    return f"{program['program_no']}-{filename}", content


# Operation fields a diff reports — the physical content a person checks
# before sending the new file to the machine.
_COMPARED_OP_FIELDS = (
    "kind",
    "coordinate_system",
    "reference",
    "face",
    "x_mm",
    "y_mm",
    "u_mm",
    "angle_left_deg",
    "angle_right_deg",
    "depth_mm",
    "tool_id",
)


def _program_ops(files: dict[str, object]) -> dict[str, dict[str, object]]:
    """operation_id → op dict parsed from the shipped operations.json —
    the program's own files, never a re-derive (a diff compares what was
    actually generated, not what would generate now)."""
    raw = files.get("operations.json")
    if not isinstance(raw, str):
        return {}
    try:
        document = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    ops = document.get("operations")
    if not isinstance(ops, list):
        return {}
    return {
        str(op.get("operation_id")): op
        for op in ops
        if isinstance(op, dict) and op.get("operation_id")
    }


def program_compare(
    *, org_id: UUID, program_id: UUID, other_id: UUID
) -> dict[str, object]:
    """Field-level diff between two program versions of the same member +
    machine family — what changed before the new file goes to the cell."""
    rows_found = rows(
        """
        SELECT id::text, program_no, member_id, member_label, operation_count,
               verdict, fingerprint, files::text, created_at,
               machine_id::text
        FROM public.cnc_programs
        WHERE org_id = %s AND id IN (%s, %s)
        """,
        [str(org_id), str(program_id), str(other_id)],
    )
    by_id = {row["id"]: row for row in rows_found}
    base = by_id.get(str(program_id))
    other = by_id.get(str(other_id))
    if base is None or other is None:
        raise DocumentaryError("cnc_program_not_found")
    base_ops = _program_ops(_decoded(base["files"]) or {})
    other_ops = _program_ops(_decoded(other["files"]) or {})
    added = sorted(set(other_ops) - set(base_ops))
    removed = sorted(set(base_ops) - set(other_ops))
    changed: list[dict[str, object]] = []
    for operation_id in sorted(set(base_ops) & set(other_ops)):
        before_op = base_ops[operation_id]
        after_op = other_ops[operation_id]
        fields = {
            field: {"from": before_op.get(field), "to": after_op.get(field)}
            for field in _COMPARED_OP_FIELDS
            if before_op.get(field) != after_op.get(field)
        }
        if fields:
            changed.append({"operation_id": operation_id, "fields": fields})
    return {
        "base": _program_card(base),
        "other": _program_card(other),
        "added": [other_ops[operation_id] for operation_id in added],
        "removed": [base_ops[operation_id] for operation_id in removed],
        "changed": changed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": len(base_ops) + len(other_ops) - len(added) - len(removed) - len(changed),
        },
    }


def _program_card(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": row["id"],
        "program_no": row["program_no"],
        "member_id": row["member_id"],
        "member_label": row["member_label"],
        "operation_count": row["operation_count"],
        "verdict": row["verdict"],
        "fingerprint": row["fingerprint"],
        "created_at": row["created_at"],
    }


def cnc_workspace(*, org_id: UUID) -> dict[str, object]:
    """Org-level CNC desk: machines, tools, and every optimized order's
    machining readiness at a glance (what needs CNC / what is blocked)."""
    machine_rows = [
        _public_machine(row)
        | {
            "emitter_implemented": (
                _postprocessor(row.get("postprocessor_id")) is not None
            )
        }
        for row in rows(
            _MACHINE_SELECT + " WHERE org_id = %s ORDER BY code",
            [str(org_id)],
        )
    ]
    orders = rows(
        """
        SELECT id::text, order_code, status::text, payload_json::text
        FROM public.orders
        WHERE org_id = %s AND order_type = 'WORKSHOP_OT'
        ORDER BY created_at DESC
        """,
        [str(org_id)],
    )
    order_rows: list[dict[str, object]] = []
    for order in orders:
        payload = _decoded(order["payload_json"])
        optimization = payload.get("optimization") or {}
        needs_machining = False
        if isinstance(optimization, dict) and not optimization.get("invalidated"):
            # An optimized order carries MEMBER ops when facts declare
            # machining (handles, end-milling) — full derive happens in
            # readiness; the desk lists orders that could need machining.
            needs_machining = bool(optimization.get("bars") or payload.get("materials"))
        program_rows = rows(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'CURRENT') AS current
            FROM public.cnc_programs
            WHERE org_id = %s AND work_order_id = %s
            """,
            [str(org_id), str(order["id"])],
        )
        if needs_machining:
            order_rows.append(
                {
                    "order_id": order["id"],
                    "order_code": order["order_code"],
                    "status": order["status"],
                    "programs_total": int(program_rows[0]["total"]),
                    "programs_current": int(program_rows[0]["current"]),
                }
            )
    return {
        "machines": machine_rows,
        "tools": list_tools(org_id=org_id),
        "orders": order_rows,
        "audit": list_authority_events(org_id=org_id),
    }
