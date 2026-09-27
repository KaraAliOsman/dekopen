"""CNC workspace: org-declared machines and tools, per-member program
generation, machine-neutral validation, and program staleness.

Authority model: machines and tools are org-declared manufacturing
authority (write through ``documentary_backend`` after API role checks).
Programs are generated artifacts — immutable rows that flip
CURRENT → SUPERSEDED when a replan changes their input fingerprint, so an
operator never runs stale output without the flag being visible.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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
    Tool,
    ToolKind,
    member_program,
    operations_from_plan,
    validate_operations,
)
from documents.repository import (
    DocumentaryError,
    documentary_backend,
    one,
    rows,
)
from documents.renderers import (
    _cut_key,
    _cut_member_map,
    _piece_labels,
)
from production.service import (
    _decoded,
    _operations_fact_units,
    _ops_source_fingerprint,
    _raw_fact_units,
)


_TOOL_KINDS = {kind.value for kind in ToolKind}
_OP_KINDS = {kind.value for kind in OperationKind}
_FACES = {face.value for face in MemberFace}
_COORDS = {coord.value for coord in CoordinateSystem}


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
        "clamp_zones": row["clamp_zones"],
        "tool_ids": [str(tool_id) for tool_id in row["tool_ids"]],
        "postprocessor_id": row["postprocessor_id"],
        "postprocessor_version": row["postprocessor_version"],
        "units": row["units"],
        "encoding": row["encoding"],
        "active": row["active"],
    }


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
    with documentary_backend():
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
    return _public_tool(created)


def update_tool(
    *, org_id: UUID, tool_id: UUID, data: dict[str, object]
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
    with documentary_backend():
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
    return _public_tool(updated)


def list_machines(*, org_id: UUID) -> list[dict[str, object]]:
    return [
        _public_machine(row)
        for row in rows(
            """
            SELECT id, code, name, manufacturer, model, controller_family,
                   coordinate_systems, supported_kinds, supported_faces,
                   max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
                   postprocessor_id, postprocessor_version, units, encoding, active
            FROM public.cnc_machines WHERE org_id = %s ORDER BY code
            """,
            [str(org_id)],
        )
    ]


def _clamp_zones(value: object) -> list[dict[str, object]]:
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
    with documentary_backend():
        created = one(
            """
            INSERT INTO public.cnc_machines
                (org_id, code, name, manufacturer, model, controller_family,
                 coordinate_systems, supported_kinds, supported_faces,
                 max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
                 postprocessor_id, postprocessor_version, units, encoding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::uuid[], %s, %s, %s, %s)
            RETURNING id, code, name, manufacturer, model, controller_family,
                      coordinate_systems, supported_kinds, supported_faces,
                      max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
                      postprocessor_id, postprocessor_version, units, encoding, active
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
            ],
            "cnc_machine_invalid",
        )
    return _public_machine(created)


def update_machine(
    *, org_id: UUID, machine_id: UUID, data: dict[str, object]
) -> dict[str, object]:
    current = _public_machine(
        one(
            """
            SELECT id, code, name, manufacturer, model, controller_family,
                   coordinate_systems, supported_kinds, supported_faces,
                   max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
                   postprocessor_id, postprocessor_version, units, encoding, active
            FROM public.cnc_machines WHERE id = %s AND org_id = %s
            """,
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
    with documentary_backend():
        updated = one(
            """
            UPDATE public.cnc_machines SET
                code = %s, name = %s, manufacturer = %s, model = %s,
                controller_family = %s, coordinate_systems = %s,
                supported_kinds = %s, supported_faces = %s,
                max_member_length_mm = %s, safe_margin_mm = %s,
                clamp_zones = %s::jsonb, tool_ids = %s::uuid[],
                postprocessor_id = %s, postprocessor_version = %s,
                units = %s, encoding = %s, active = %s, updated_at = %s
            WHERE id = %s AND org_id = %s
            RETURNING id, code, name, manufacturer, model, controller_family,
                      coordinate_systems, supported_kinds, supported_faces,
                      max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
                      postprocessor_id, postprocessor_version, units, encoding, active
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
                str(machine_id),
                str(org_id),
            ],
            "cnc_machine_not_found",
        )
    return _public_machine(updated)


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
            for zone in (
                machine_row["clamp_zones"]
                if isinstance(machine_row.get("clamp_zones"), list)
                else []
            )
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
    ops = operations_from_plan(bars=bars, fact_units=fact_units)
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
        "fact_units": fact_units,
        "member_labels": member_labels,
        "member_lengths": member_lengths,
        "input_fingerprint": input_fingerprint,
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


def cnc_readiness(
    *, org_id: UUID, order_id: UUID, machine_id: UUID | None = None
) -> dict[str, object]:
    """Per-member machining readiness against the org's real machines:
    every member that carries MEMBER ops gets a verdict + named blockers."""
    bundle = _order_ops(org_id=org_id, order_id=order_id)
    machines = rows(
        """
        SELECT id, code, name, manufacturer, model, controller_family,
               coordinate_systems, supported_kinds, supported_faces,
               max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
               postprocessor_id, postprocessor_version, units, encoding, active
        FROM public.cnc_machines
        WHERE org_id = %s AND active
        """ + (" AND id = %s" if machine_id else "") + " ORDER BY code",
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
    members: list[dict[str, object]] = []
    for member_id in member_ids:
        label = bundle["member_labels"].get(member_id) or member_id[:8]
        ops = member_ops[member_id]
        machine_results: list[dict[str, object]] = []
        for profile, machine_row in zip(machine_profiles, machine_rows):
            validations = validate_operations(
                ops,
                profile,
                member_lengths_mm=bundle["member_lengths"],
                member_labels=bundle["member_labels"],
            )
            blockers = [item for item in validations if item.level == "BLOCK"]
            warnings = [item for item in validations if item.level == "WARN"]
            machine_results.append(
                {
                    "machine_id": str(machine_row["id"]),
                    "machine_code": machine_row["code"],
                    "machine_name": machine_row["name"],
                    "verdict": (
                        "BLOCK"
                        if blockers
                        else ("WARN" if warnings else "PASS")
                    ),
                    "blockers": [item.model_dump(mode="json") for item in blockers],
                    "warnings": [item.model_dump(mode="json") for item in warnings],
                }
            )
        members.append(
            {
                "member_id": member_id,
                "member_label": label,
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
    return {
        "order_id": str(order_id),
        "order_code": bundle["order"]["order_code"],
        "members": members,
        "machines": [_public_machine(row) for row in machine_rows],
        "programs": list_programs(org_id=org_id, order_id=order_id),
    }


def _program_no(*, order_code: str, member_label: str, machine_code: str, seq: int) -> str:
    label = "".join(ch for ch in member_label if ch.isalnum())[:12] or "M"
    return f"{order_code}-{label}-{machine_code}-{seq:02d}"


def generate_program(
    *, org_id: UUID, order_id: UUID, machine_id: UUID, member_id: str,
    actor_id: UUID,
) -> dict[str, object]:
    bundle = _order_ops(org_id=org_id, order_id=order_id)
    tools_by_id = _tools_by_id(org_id=org_id)
    machine_row = one(
        """
        SELECT id, code, name, manufacturer, model, controller_family,
               coordinate_systems, supported_kinds, supported_faces,
               max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
               postprocessor_id, postprocessor_version, units, encoding, active
        FROM public.cnc_machines
        WHERE id = %s AND org_id = %s AND active
        """,
        [str(machine_id), str(org_id)],
        "cnc_machine_not_found",
    )
    profile = _machine_profile(machine_row, tools_by_id)
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
    )
    files = NeutralOpsPostProcessor().render(
        {
            "schema": "dekopen_ops_v1",
            "order_code": bundle["identity"]["order_code"],
            "plan_seed": bundle["identity"]["plan_seed"],
            "machine": profile.model_dump(mode="json"),
            "operation_count": document["operation_count"],
            "counts_by_kind": document["counts_by_kind"],
            "unemitted_kinds": [],
            "piece_labels": bundle["member_labels"],
            "operations": document["operations"],
        }
    )
    seq_row = one(
        """
        SELECT COUNT(*) + 1 AS seq FROM public.cnc_programs
        WHERE org_id = %s AND work_order_id = %s AND machine_id = %s AND member_id = %s
        """,
        [str(org_id), str(order_id), str(machine_id), member_id],
        "cnc_program_invalid",
    )
    with transaction.atomic(), documentary_backend():
        rows(
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
                _program_no(
                    order_code=str(bundle["order"]["order_code"]),
                    member_label=str(document["identity"]["member_label"]),
                    machine_code=str(machine_row["code"]),
                    seq=int(seq_row["seq"]),
                ),
                int(document["operation_count"]),
                str(document["verdict"]),
                str(document["fingerprint"]),
                str(bundle["input_fingerprint"]),
                json.dumps(document["identity"]),
                json.dumps(files),
                str(actor_id),
            ],
            "cnc_program_invalid",
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
               p.created_at, p.machine_id::text, m.code AS machine_code
        FROM public.cnc_programs p
        LEFT JOIN public.cnc_machines m ON m.id = p.machine_id
        WHERE p.org_id = %s AND p.work_order_id = %s
        ORDER BY p.created_at DESC
        """,
        [str(org_id), str(order_id)],
    )
    if not program_rows:
        return []
    # Fresh staleness: a program whose inputs changed since generation is
    # reported stale even if it still reads CURRENT (lazy supersede on
    # read — operators see the truth without a background job).
    try:
        bundle = _order_ops(org_id=org_id, order_id=order_id)
        current_input = str(bundle["input_fingerprint"])
    except DocumentaryError:
        current_input = ""
    output: list[dict[str, object]] = []
    for row in program_rows:
        stale = row["input_fingerprint"] != current_input or bool(
            row["status"] == "SUPERSEDED"
        )
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
               p.work_order_id::text
        FROM public.cnc_programs p
        WHERE p.id = %s AND p.org_id = %s
        """,
        [str(program_id), str(org_id)],
        "cnc_program_not_found",
    )
    if program["status"] == "SUPERSEDED":
        raise DocumentaryError("cnc_program_superseded")
    bundle = _order_ops(org_id=org_id, order_id=UUID(str(program["work_order_id"])))
    if str(bundle["input_fingerprint"]) != str(program["input_fingerprint"]):
        # The plan moved under the program — flip it so downloads stop
        # pretending this file is current.
        with documentary_backend():
            rows(
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


def cnc_workspace(*, org_id: UUID) -> dict[str, object]:
    """Org-level CNC desk: machines, tools, and every optimized order's
    machining readiness at a glance (what needs CNC / what is blocked)."""
    machine_rows = [
        _public_machine(row)
        for row in rows(
            """
            SELECT id, code, name, manufacturer, model, controller_family,
                   coordinate_systems, supported_kinds, supported_faces,
                   max_member_length_mm, safe_margin_mm, clamp_zones, tool_ids,
                   postprocessor_id, postprocessor_version, units, encoding, active
            FROM public.cnc_machines WHERE org_id = %s ORDER BY code
            """,
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
    }
