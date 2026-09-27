"""Machine-neutral manufacturing operations (mandate §7).

The cut CSV/DXF exports answer "where on the bar/sheet do I cut" — they are
handoff documents, not a machine program. This module models the operations
a machining cell performs on the produced members: saw cuts, secondary
machining (handle prep, end milling), and marks.

Honesty contract:
- An operation is emitted only where sealed authority exists — cut plan
  placements, manufacturing facts (handle locations carry their policy id),
  or system-declared fabrication parameters (a mullion's end-milling overlap
  is recoverable from its sealed cut length and plan span). Kinds without
  authority (drainage, lock/hinge prep, routing, …) are part of the model so
  postprocessors can target them later, but the engine emits nothing for
  them — it never invents a machining step.
- ``MachineProfile`` names no brand. ``NEUTRAL_MACHINE_PROFILE`` is the
  reference target; vendor controllers are postprocessors over this model,
  not new derivations.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import Enum
from typing import Protocol

from .cutting import CutBar
from .manufacturing import ManufacturingFactsV1
from .models import EngineModel, ProfileRole


class OperationKind(str, Enum):
    SAW_CUT = "SAW_CUT"
    DRILL = "DRILL"
    SLOT = "SLOT"
    DRAINAGE = "DRAINAGE"
    VENTILATION = "VENTILATION"
    HANDLE_PREP = "HANDLE_PREP"
    LOCK_PREP = "LOCK_PREP"
    HINGE_PREP = "HINGE_PREP"
    CORNER_CONNECTOR = "CORNER_CONNECTOR"
    T_CONNECTOR = "T_CONNECTOR"
    MILLING = "MILLING"
    END_MACHINING = "END_MACHINING"
    ROUTING = "ROUTING"
    GASKET_MARK = "GASKET_MARK"
    CUSTOM = "CUSTOM"


class CoordinateSystem(str, Enum):
    """Datum a postprocessor must honor. Coordinates are DECIMAL mm."""

    # Scalar x along the stock bar, origin at the bar's left edge (before
    # head trim). Used by saw and end-machining-on-bar operations.
    BAR_AXIS = "BAR_AXIS"
    # (x, y) in the member's assembly plan — the same NOMINAL_OUTER_FRAME_
    # TOP_LEFT space the manufacturing facts are projected into.
    MEMBER_PLAN = "MEMBER_PLAN"
    # (x, y) on a nested sheet, origin at the sheet's top-left after trims.
    SHEET_PLAN = "SHEET_PLAN"


class ToolKind(str, Enum):
    SAW_BLADE = "SAW_BLADE"
    DRILL_BIT = "DRILL_BIT"
    END_MILL = "END_MILL"
    ROUTER_BIT = "ROUTER_BIT"
    PUNCH = "PUNCH"
    MARKING = "MARKING"
    CUSTOM = "CUSTOM"


class Tool(EngineModel):
    tool_id: str
    kind: ToolKind
    name: str
    diameter_mm: Decimal | None = None


class MachineProfile(EngineModel):
    """A machining target. The neutral profile claims no vendor controller —
    it exists so the ops document always carries an explicit target."""

    machine_id: str
    name: str
    controller_family: str = "NEUTRAL"
    coordinate_systems: list[CoordinateSystem]
    tools: list[Tool]


NEUTRAL_MACHINE_PROFILE = MachineProfile(
    machine_id="machine-neutral-v1",
    name="Machine-neutral cell (cut-off saw + machining)",
    controller_family="NEUTRAL",
    coordinate_systems=[
        CoordinateSystem.BAR_AXIS,
        CoordinateSystem.MEMBER_PLAN,
        CoordinateSystem.SHEET_PLAN,
    ],
    tools=[
        Tool(tool_id="saw", kind=ToolKind.SAW_BLADE, name="Cut-off saw blade"),
        Tool(tool_id="end_mill", kind=ToolKind.END_MILL, name="End milling cutter"),
        Tool(tool_id="drill", kind=ToolKind.DRILL_BIT, name="Drill"),
        Tool(tool_id="mark", kind=ToolKind.MARKING, name="Marking"),
    ],
)


class ManufacturingOperation(EngineModel):
    """One deterministic, machine-translatable operation on a produced part.

    ``basis`` records the authority the op derives from (cut placement,
    ``handle_policy:<id>@v<n>``, ``member_end_overlap``) — a postprocessor or
    auditor can always answer "why does this operation exist"."""

    operation_id: str  # sha256 of the identity bundle below
    kind: OperationKind
    host_kind: str  # BAR | MEMBER | SHEET
    host: str
    coordinate_system: CoordinateSystem
    x_mm: Decimal | None = None
    y_mm: Decimal | None = None
    # For saw boundaries: the face angles each side of the cut must form.
    angle_left_deg: Decimal | None = None
    angle_right_deg: Decimal | None = None
    depth_mm: Decimal | None = None
    tool_id: str | None = None
    basis: str
    detail: dict[str, str] = {}


def _op_id(*parts: object) -> str:
    canonical = "|".join(str(part) for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _saw_ops(bar: CutBar) -> list[ManufacturingOperation]:
    """Cuts on one bar: the head-trim boundary, one cut per piece's right
    edge, and the tail-trim boundary. Piece j occupies
    ``head_trim + Σ_{k<j}(len+kerf)``; its right cut sits at
    ``start + len`` and the blade's kerf is consumed after it — the same
    convention the optimizer and DXF marks use."""
    ops: list[ManufacturingOperation] = []
    head = bar.head_trim_mm
    kerf = bar.kerf_mm
    stock = bar.stock_length_mm
    cursor = head
    host = f"bar:{bar.bar_index}"
    base_detail = {
        "commercial_sku": bar.commercial_sku,
        "stock_length_mm": str(stock),
        "bar_source": bar.source,
    }
    ops.append(
        ManufacturingOperation(
            operation_id=_op_id("SAW_CUT", host, "head_trim", str(head)),
            kind=OperationKind.SAW_CUT,
            host_kind="BAR",
            host=host,
            coordinate_system=CoordinateSystem.BAR_AXIS,
            x_mm=head,
            angle_left_deg=Decimal("90"),
            angle_right_deg=Decimal("90"),
            tool_id="saw",
            basis="cut_plan.head_trim",
            detail={**base_detail, "boundary": "HEAD_TRIM"},
        )
    )
    for index, cut in enumerate(bar.cuts):
        cut_x = cursor + cut.length_mm
        next_cut = bar.cuts[index + 1] if index + 1 < len(bar.cuts) else None
        ops.append(
            ManufacturingOperation(
                operation_id=_op_id("SAW_CUT", host, cut.piece_id, str(cut_x)),
                kind=OperationKind.SAW_CUT,
                host_kind="BAR",
                host=host,
                coordinate_system=CoordinateSystem.BAR_AXIS,
                x_mm=cut_x,
                # Face angles each side of the blade: the left face closes
                # this piece, the right face opens the next.
                angle_left_deg=cut.angle_right,
                angle_right_deg=(next_cut.angle_left if next_cut else None),
                tool_id="saw",
                basis="cut_plan.placement",
                detail={
                    **base_detail,
                    "piece_id": cut.piece_id,
                    "sequence": str(cut.sequence),
                    "next_piece_id": next_cut.piece_id if next_cut else "",
                },
            )
        )
        cursor = cut_x + kerf
    tail_x = stock - bar.tail_trim_mm
    if bar.tail_trim_mm > Decimal("0"):
        ops.append(
            ManufacturingOperation(
                operation_id=_op_id("SAW_CUT", host, "tail_trim", str(tail_x)),
                kind=OperationKind.SAW_CUT,
                host_kind="BAR",
                host=host,
                coordinate_system=CoordinateSystem.BAR_AXIS,
                x_mm=tail_x,
                angle_left_deg=Decimal("90"),
                angle_right_deg=Decimal("90"),
                tool_id="saw",
                basis="cut_plan.tail_trim",
                detail={**base_detail, "boundary": "TAIL_TRIM"},
            )
        )
    return ops


_END_MILLED_ROLES = {ProfileRole.MULLION_V, ProfileRole.MULLION_H}


def _member_ops(unit: ManufacturingFactsV1) -> list[ManufacturingOperation]:
    """Secondary machining derivable from sealed facts only:
    - END_MACHINING on mullions whose cut length exceeds their plan span —
      the difference is the system-declared end-milling overlap baked into
      the cut length. Zero overlap -> no op (declared authority absent).
    - HANDLE_PREP at each declared handle location (authority is the handle
      requirement policy the fact was resolved under)."""
    ops: list[ManufacturingOperation] = []
    members = {member.member_id: member for member in unit.members}
    for member in unit.members:
        role = member.identity.role
        if role not in _END_MILLED_ROLES:
            continue
        if member.axis.value == "HORIZONTAL":
            span = member.end.x_mm - member.start.x_mm
        else:
            span = member.end.y_mm - member.start.y_mm
        overlap = (member.cut_length_mm - span) / Decimal("2")
        if overlap <= Decimal("0"):
            continue
        for edge, point in (("START", member.start), ("END", member.end)):
            ops.append(
                ManufacturingOperation(
                    operation_id=_op_id(
                        "END_MACHINING", member.member_id, edge, str(overlap)
                    ),
                    kind=OperationKind.END_MACHINING,
                    host_kind="MEMBER",
                    host=member.member_id,
                    coordinate_system=CoordinateSystem.MEMBER_PLAN,
                    x_mm=point.x_mm,
                    y_mm=point.y_mm,
                    depth_mm=overlap,
                    tool_id="end_mill",
                    basis="member_end_overlap",
                    detail={
                        "role": role.value,
                        "edge": edge,
                        "workshop_sku": member.workshop_sku,
                        "overlap_mm": str(overlap),
                    },
                )
            )
    for handle in unit.handles:
        if handle.host_member_id not in members:
            continue
        ops.append(
            ManufacturingOperation(
                operation_id=_op_id(
                    "HANDLE_PREP", handle.handle_id, str(handle.point.x_mm)
                ),
                kind=OperationKind.HANDLE_PREP,
                host_kind="MEMBER",
                host=handle.host_member_id,
                coordinate_system=CoordinateSystem.MEMBER_PLAN,
                x_mm=handle.point.x_mm,
                y_mm=handle.point.y_mm,
                tool_id="drill",
                basis=(
                    f"handle_requirement_policy:{handle.policy_id}"
                    f"@{handle.policy_version}"
                ),
                detail={
                    "handle_domain_slot": handle.handle_domain_slot,
                    "requested_height_mm": str(handle.requested_height_mm),
                    "vertical_reference": handle.vertical_reference.value,
                    "bay_id": handle.bay_id,
                    "leaf_id": handle.leaf_id or "",
                },
            )
        )
    return ops


def operations_from_plan(
    *,
    bars: list[CutBar],
    fact_units: list[ManufacturingFactsV1],
) -> list[ManufacturingOperation]:
    """All derivable operations for a work order's sealed plan. Deterministic:
    ops sort by (host, kind, x_mm, y_mm, operation_id)."""
    ops: list[ManufacturingOperation] = []
    for bar in bars:
        ops.extend(_saw_ops(bar))
    for unit in fact_units:
        ops.extend(_member_ops(unit))
    # bar hosts sort numerically — "bar:10" must not precede "bar:2" on a saw
    # sequence; every other host stays lexicographic and stable.
    def host_key(host: str) -> tuple[int, object]:
        if host.startswith("bar:"):
            try:
                return (0, int(host[4:]))
            except ValueError:
                return (0, 0)
        return (1, host)

    ops.sort(
        key=lambda op: (
            host_key(op.host),
            op.kind.value,
            str(op.x_mm or Decimal("0")),
            str(op.y_mm or Decimal("0")),
            op.operation_id,
        )
    )
    return ops


def ops_document(
    ops: list[ManufacturingOperation],
    *,
    machine: MachineProfile = NEUTRAL_MACHINE_PROFILE,
    order_code: str,
    plan_seed: str | None = None,
    piece_labels: dict[str, str] | None = None,
) -> dict[str, object]:
    """Canonical machine-neutral ops document (dekopen_ops_v1).
    ``piece_labels`` maps piece/member ids to shop codes (M-xx/R-xx/…):
    presentation metadata, never dimensional authority."""
    emitted = {op.kind.value for op in ops}
    all_kinds = {kind.value for kind in OperationKind}
    return {
        "schema": "dekopen_ops_v1",
        "order_code": order_code,
        "plan_seed": plan_seed,
        "machine": machine.model_dump(mode="json"),
        "operation_count": len(ops),
        "counts_by_kind": {kind: len(group) for kind, group in _group(ops).items()},
        "unemitted_kinds": sorted(all_kinds - emitted),
        "piece_labels": dict(piece_labels or {}),
        "operations": [op.model_dump(mode="json") for op in ops],
    }


def _group(
    ops: list[ManufacturingOperation],
) -> dict[str, list[ManufacturingOperation]]:
    grouped: dict[str, list[ManufacturingOperation]] = {}
    for op in ops:
        grouped.setdefault(op.kind.value, []).append(op)
    return grouped


def ops_fingerprint(document: dict[str, object]) -> str:
    """Stable fingerprint over the operations document (excluding volatile
    metadata) — an export re-verifies against this on download."""
    stable = {
        key: value
        for key, value in document.items()
        if key not in {"exported_at"}
    }
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class PostProcessor(Protocol):
    """Renders operations for one machine family. Implementations must be
    deterministic: same document -> byte-identical output."""

    processor_id: str

    def render(
        self, document: dict[str, object]
    ) -> dict[str, str]: ...


class NeutralOpsPostProcessor:
    """Reference postprocessor: emits the canonical JSON document plus a flat
    CSV ops sheet a shop can read or a vendor adapter can translate."""

    processor_id = "neutral-ops-v1"

    _CSV_HEADER = (
        "operation_id,kind,host_kind,host,coordinate_system,"
        "x_mm,y_mm,angle_left_deg,angle_right_deg,depth_mm,tool_id,basis,"
        "piece_id,piece_label,sequence,bar_sku"
    )

    def render(self, document: dict[str, object]) -> dict[str, str]:
        raw_ops = document.get("operations")
        ops = raw_ops if isinstance(raw_ops, list) else []
        labels = document.get("piece_labels")
        piece_labels = labels if isinstance(labels, dict) else {}
        rows = [self._CSV_HEADER]
        for op in ops:
            if not isinstance(op, dict):
                continue
            detail = op.get("detail")
            detail = detail if isinstance(detail, dict) else {}
            piece_id = detail.get("piece_id") or (
                op.get("host") if op.get("host_kind") == "MEMBER" else ""
            )
            rows.append(
                ",".join(
                    _cell(op.get(key))
                    for key in (
                        "operation_id", "kind", "host_kind", "host",
                        "coordinate_system", "x_mm", "y_mm",
                        "angle_left_deg", "angle_right_deg", "depth_mm",
                        "tool_id", "basis",
                    )
                )
                + "," + _cell(piece_id)
                + "," + _cell(piece_labels.get(str(piece_id), ""))
                + "," + _cell(detail.get("sequence"))
                + "," + _cell(detail.get("commercial_sku"))
            )
        return {
            "operations.json": json.dumps(
                document, indent=2, sort_keys=True, default=str
            )
            + "\n",
            "operations.csv": "\n".join(rows) + "\n",
        }


def _cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if any(ch in text for ch in (",", '"', "\n")):
        text = '"' + text.replace('"', '""') + '"'
    return text
