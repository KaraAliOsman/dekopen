"""§7 machine-neutral manufacturing operations — authority-bound derivation."""

from decimal import Decimal
from typing import Any


from dekopen_engine.cutting import (
    CutMaterial,
    CutPiece,
    CuttingProfile,
    StockRule,
    optimize_cut,
)
from dekopen_engine.manufacturing import (
    HandleLocationFactV1,
    ManufacturingFactsV1,
    PhysicalMemberFactV1,
    PhysicalMemberIdentityV1,
    VerticalReference,
)
from dekopen_engine.manufacturing_trace import Axis, TracePointV1
from dekopen_engine.models import MaterialType, ProfileRole
from dekopen_engine.operations import (
    NEUTRAL_MACHINE_PROFILE,
    CoordinateSystem,
    NeutralOpsPostProcessor,
    OperationKind,
    operations_from_plan,
    ops_document,
)


def _piece(pid: str, length: str, role: str = "FRAME") -> CutPiece:
    return CutPiece(
        piece_id=pid,
        source_kind="PROFILE",
        workshop_sku="WS-P1",
        material=CutMaterial.PVC,
        color="BLANCO",
        length_mm=Decimal(length),
        role=role,
        unit_index=1,
        angle_left=Decimal("90"),
        angle_right=Decimal("90"),
    )


def _stock() -> StockRule:
    return StockRule(
        stock_authority_id="auth-1",
        workshop_sku="WS-P1",
        commercial_sku="MARCO-60",
        manufacturer_name="DEMO",
        supplier_name=None,
        purchase_unit="BAR",
        material=CutMaterial.PVC,
        color="BLANCO",
        stock_length_mm=Decimal("6000"),
    )


def _profile() -> CuttingProfile:
    return CuttingProfile(
        id="cp-1", code="STD", kerf_mm=Decimal("5"), head_trim_mm=Decimal("10"),
        tail_trim_mm=Decimal("10"),
    )


def _member(role: ProfileRole, span: str, overlap: str = "0") -> PhysicalMemberFactV1:
    span_d = Decimal(span)
    cut = span_d + Decimal(overlap) * 2
    return PhysicalMemberFactV1(
        member_id="a" * 64,
        semantic_member_id="mem-1",
        identity=PhysicalMemberIdentityV1(
            position_id="pos-1", position_index=1, repetition_index=1,
            topology_path="root/split/leaf", assembly="A", leaf_slot=None,
            role=role, physical_member_slot="m1",
        ),
        bay_id="bay-1", leaf_id=None, workshop_sku="WS-P1",
        material=MaterialType.PVC, cut_length_mm=cut,
        angle_left=Decimal("90"), angle_right=Decimal("90"),
        axis=Axis.VERTICAL,
        start=TracePointV1(x_mm=Decimal("500"), y_mm=Decimal("0")),
        end=TracePointV1(x_mm=Decimal("500"), y_mm=span_d),
    )


def _unit(**kwargs: object) -> ManufacturingFactsV1:
    data: dict[str, object] = {
        "position_id": "pos-1", "position_index": 1, "repetition_index": 1,
        "nominal_width_mm": Decimal("1000"), "nominal_height_mm": Decimal("1200"),
        "placement_policy_id": "pp", "placement_policy_version": 1,
        "handle_policy_id": "hp", "handle_policy_version": 2,
        "reinforcement_policy_id": "rp", "reinforcement_policy_version": 1,
        "reinforcements": [], "leaves": [], "infills": [],
        "relationships": [], "members": [], "handles": [],
    }
    data.update(kwargs)
    return ManufacturingFactsV1.model_validate(data)


def _handle() -> HandleLocationFactV1:
    return HandleLocationFactV1(
        handle_id="b" * 64, position_id="pos-1", position_index=1,
        repetition_index=1, bay_id="bay-1", leaf_id="leaf-1",
        handle_domain_slot="main", host_member_id="a" * 64,
        point=TracePointV1(x_mm=Decimal("80"), y_mm=Decimal("1050")),
        requested_height_mm=Decimal("1050"),
        vertical_reference=VerticalReference.LEAF_BOTTOM,
        policy_id="hp-1", policy_version=3,
    )


def test_saw_ops_cover_every_piece_boundary() -> None:
    plan = optimize_cut(
        [_piece("p1", "2000"), _piece("p2", "1500")],
        [_stock()], _profile(),
    )
    assert len(plan.workshop_cut_plan) == 1
    ops = operations_from_plan(
        bars=plan.workshop_cut_plan, fact_units=[]
    )
    saw = [op for op in ops if op.kind == OperationKind.SAW_CUT]
    # head trim + 2 piece-end cuts + tail trim
    assert len(saw) == 4
    xs = [op.x_mm for op in saw]
    assert xs == [
        Decimal("10"),           # head trim
        Decimal("2010"),         # p1 end: 10 + 2000
        Decimal("3515"),         # p2 end: 10 + 2000 + 5 + 1500
        Decimal("5990"),         # tail trim: 6000 - 10
    ]
    # interior cut carries both face angles
    interior = saw[1]
    assert interior.angle_left_deg == Decimal("90")
    assert interior.detail["piece_id"] == "p1"
    assert interior.detail["next_piece_id"] == "p2"


def test_saw_ops_carry_angles() -> None:
    piece = _piece("p1", "2000")
    piece.angle_left = Decimal("45")
    piece.angle_right = Decimal("45")
    plan = optimize_cut([piece], [_stock()], _profile())
    ops = operations_from_plan(
        bars=plan.workshop_cut_plan, fact_units=[]
    )
    piece_cut = [op for op in ops if op.detail.get("piece_id") == "p1"][0]
    assert piece_cut.angle_left_deg == Decimal("45")
    # The head pass is the first piece's left face — it must carry the
    # miter, not a blanket 90° (hostile review: first piece lost it).
    head = [op for op in ops if op.detail.get("boundary") == "HEAD_TRIM"][0]
    assert head.angle_left_deg == Decimal("45")
    assert head.angle_right_deg == Decimal("45")
    assert head.detail["forms_piece_id"] == "p1"
    tail = [op for op in ops if op.detail.get("boundary") == "TAIL_TRIM"][0]
    assert tail.angle_left_deg == Decimal("45")


def test_saw_ops_order_is_numeric() -> None:
    """Cut order must track physical position — a 510 mm boundary can't
    sort after 4045 mm because of string collation."""
    pieces = [_piece(f"p{i}", "500") for i in range(8)]
    plan = optimize_cut(pieces, [_stock()], _profile())
    ops = operations_from_plan(
        bars=plan.workshop_cut_plan, fact_units=[]
    )
    xs = [op.x_mm for op in ops if op.x_mm is not None]
    assert xs == sorted(xs)
    assert len(xs) == len(ops)
    assert xs[1] < Decimal("1000")


def test_saw_boundary_conflict_is_flagged() -> None:
    """One blade pass cannot leave 45° left and 90° right — the op records
    both faces and the document reports the contradiction."""
    miter = _piece("pM", "2000")
    miter.angle_left = Decimal("45")
    miter.angle_right = Decimal("45")
    butt = _piece("pS", "1500")
    plan = optimize_cut([miter, butt], [_stock()], _profile())
    issues: list[dict[str, object]] = []
    ops = operations_from_plan(
        bars=plan.workshop_cut_plan, fact_units=[], issues=issues
    )
    boundary = [
        op for op in ops
        if op.detail.get("piece_id") == "pM" and "boundary" not in op.detail
    ][0]
    assert boundary.angle_left_deg == Decimal("45")
    assert boundary.angle_right_deg == Decimal("90")
    assert boundary.detail["boundary_conflict"] == "angle_mismatch"
    assert [issue["code"] for issue in issues] == ["boundary_conflict"]
    doc = ops_document(ops, order_code="OT-1", issues=issues)
    assert doc["issues"] == issues


def test_operation_ids_track_content_not_serialization() -> None:
    """Decimal cosmetics must not mint new ids; real geometry moves must."""
    member_a = _member(ProfileRole.MULLION_V, "1180", overlap="15")
    member_b = _member(ProfileRole.MULLION_V, "1180.00", overlap="15.000")
    member_b.member_id = member_a.member_id
    ops_a = operations_from_plan(
        bars=[], fact_units=[_unit(members=[member_a])]
    )
    ops_b = operations_from_plan(
        bars=[], fact_units=[_unit(members=[member_b])]
    )
    assert [op.operation_id for op in ops_a] == [
        op.operation_id for op in ops_b
    ]
    # Moving the member 200 mm in plan is a real change — ids must differ.
    member_c = _member(ProfileRole.MULLION_V, "1180", overlap="15")
    member_c.member_id = member_a.member_id
    member_c.start = member_a.start.model_copy(
        update={"x_mm": member_a.start.x_mm + Decimal("200")}
    )
    member_c.end = member_a.end.model_copy(
        update={"x_mm": member_a.end.x_mm + Decimal("200")}
    )
    ops_c = operations_from_plan(
        bars=[], fact_units=[_unit(members=[member_c])]
    )
    assert [op.operation_id for op in ops_a] != [
        op.operation_id for op in ops_c
    ]


def test_end_machining_handles_reversed_member_direction() -> None:
    """A member traced end-to-start must not inflate the overlap."""
    member = _member(ProfileRole.MULLION_V, "1180", overlap="15")
    member.start, member.end = member.end, member.start
    ops = operations_from_plan(
        bars=[], fact_units=[_unit(members=[member])]
    )
    end_ops = [op for op in ops if op.kind == OperationKind.END_MACHINING]
    assert len(end_ops) == 2
    assert all(op.depth_mm == Decimal("15") for op in end_ops)


def test_end_machining_skips_arc_members() -> None:
    """An arc member's cut_length-minus-chord surplus is not end overlap."""
    member = _member(ProfileRole.MULLION_V, "1180", overlap="15")
    member.sagitta_mm = Decimal("120")
    ops = operations_from_plan(
        bars=[], fact_units=[_unit(members=[member])]
    )
    assert not [op for op in ops if op.kind == OperationKind.END_MACHINING]


def test_handle_without_member_is_reported_not_dropped() -> None:
    handle = _handle()
    handle.host_member_id = "f" * 64  # no member fact exists for it
    issues: list[dict[str, object]] = []
    ops = operations_from_plan(
        bars=[], fact_units=[_unit(handles=[handle])], issues=issues
    )
    assert not [op for op in ops if op.kind == OperationKind.HANDLE_PREP]
    assert [issue["code"] for issue in issues] == ["handle_without_member"]


def test_ops_document_ships_member_geometry() -> None:
    member = _member(ProfileRole.MULLION_V, "1180", overlap="15")
    unit = _unit(members=[member])
    ops = operations_from_plan(bars=[], fact_units=[unit])
    doc = ops_document(ops, order_code="OT-1", fact_units=[unit])
    members = doc["members"]
    assert isinstance(members, dict)
    entry = members[member.member_id]
    assert isinstance(entry, dict)
    start = entry["start"]
    end = entry["end"]
    assert entry["axis"] == "VERTICAL"
    assert entry["cut_length_mm"] == "1210"
    assert isinstance(start, dict) and start["y_mm"] == "0"
    assert isinstance(end, dict) and end["y_mm"] == "1180"
    coverage = doc["coverage"]
    assert isinstance(coverage, dict)
    assert coverage["members_total"] == 1
    assert coverage["members_with_ops"] == 1
    fingerprint = doc["fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    # same inputs → same fingerprint (determinism)
    doc_b = ops_document(
        operations_from_plan(bars=[], fact_units=[unit]),
        order_code="OT-1",
        fact_units=[unit],
    )
    assert doc["fingerprint"] == doc_b["fingerprint"]


def test_ops_fingerprint_changes_on_intentional_change() -> None:
    unit = _unit(members=[_member(ProfileRole.MULLION_V, "1180", overlap="15")])
    doc_a = ops_document(
        operations_from_plan(bars=[], fact_units=[unit]),
        order_code="OT-1",
        fact_units=[unit],
    )
    other = _unit(members=[_member(ProfileRole.MULLION_V, "900", overlap="15")])
    doc_b = ops_document(
        operations_from_plan(bars=[], fact_units=[other]),
        order_code="OT-1",
        fact_units=[other],
    )
    assert doc_a["fingerprint"] != doc_b["fingerprint"]


def test_ops_get_sequence_numbers() -> None:
    plan = optimize_cut([_piece("p1", "2000"), _piece("p2", "1500")],
                        [_stock()], _profile())
    ops = operations_from_plan(
        bars=plan.workshop_cut_plan, fact_units=[])
    assert [op.sequence_no for op in ops] == list(range(1, len(ops) + 1))


def test_no_ops_without_authority_kinds() -> None:
    """Kinds with no authority (drainage, hinges…) emit nothing."""
    plan = optimize_cut([_piece("p1", "2000")], [_stock()], _profile())
    ops = operations_from_plan(
        bars=plan.workshop_cut_plan, fact_units=[]
    )
    kinds = {op.kind for op in ops}
    assert OperationKind.DRAINAGE not in kinds
    assert OperationKind.HINGE_PREP not in kinds
    doc = ops_document(ops, order_code="OT-1")
    unemitted = doc["unemitted_kinds"]
    assert isinstance(unemitted, list) and "DRAINAGE" in unemitted
    assert doc["counts_by_kind"] == {"SAW_CUT": 3}


def test_handle_prep_from_facts() -> None:
    unit = _unit(members=[_member(ProfileRole.FRAME, "1200")], handles=[_handle()])
    ops = operations_from_plan(bars=[], fact_units=[unit])
    handle_ops = [op for op in ops if op.kind == OperationKind.HANDLE_PREP]
    assert len(handle_ops) == 1
    op = handle_ops[0]
    assert op.host == "a" * 64
    assert op.x_mm == Decimal("80") and op.y_mm == Decimal("1050")
    assert op.basis == "handle_requirement_policy:hp-1@3"
    assert op.coordinate_system == CoordinateSystem.MEMBER_PLAN


def test_end_machining_only_with_overlap_authority() -> None:
    member = _member(ProfileRole.MULLION_V, "1180", overlap="15")
    ops = operations_from_plan(
        bars=[], fact_units=[_unit(members=[member])]
    )
    end_ops = [op for op in ops if op.kind == OperationKind.END_MACHINING]
    assert len(end_ops) == 2  # both ends
    assert all(op.depth_mm == Decimal("15") for op in end_ops)
    assert {op.detail["edge"] for op in end_ops} == {"START", "END"}


def test_end_machining_absent_without_overlap() -> None:
    member = _member(ProfileRole.MULLION_V, "1180", overlap="0")
    ops = operations_from_plan(
        bars=[], fact_units=[_unit(members=[member])]
    )
    assert not [op for op in ops if op.kind == OperationKind.END_MACHINING]


def test_end_machining_only_on_mullions() -> None:
    member = _member(ProfileRole.FRAME, "1180", overlap="15")
    ops = operations_from_plan(
        bars=[], fact_units=[_unit(members=[member])]
    )
    assert not [op for op in ops if op.kind == OperationKind.END_MACHINING]


def test_determinism_and_ids() -> None:
    plan = optimize_cut([_piece("p1", "2000"), _piece("p2", "1500")],
                        [_stock()], _profile())
    unit = _unit(members=[_member(ProfileRole.MULLION_V, "1180", "15")],
                 handles=[_handle()])
    ops_a = operations_from_plan(
        bars=plan.workshop_cut_plan, fact_units=[unit])
    ops_b = operations_from_plan(
        bars=plan.workshop_cut_plan, fact_units=[unit])
    assert [op.operation_id for op in ops_a] == [op.operation_id for op in ops_b]
    assert len({op.operation_id for op in ops_a}) == len(ops_a)


def test_postprocessor_renders_deterministically() -> None:
    plan = optimize_cut([_piece("p1", "2000")], [_stock()], _profile())
    ops = operations_from_plan(
        bars=plan.workshop_cut_plan, fact_units=[])
    doc = ops_document(ops, order_code="OT-1", plan_seed="abc")
    files_a = NeutralOpsPostProcessor().render(doc)
    files_b = NeutralOpsPostProcessor().render(doc)
    assert files_a == files_b
    assert "operations.json" in files_a and "operations.csv" in files_a
    csv_lines = files_a["operations.csv"].strip().split("\n")
    assert len(csv_lines) == len(ops) + 1
    assert "SAW_CUT" in csv_lines[1]
    # machine profile declares the neutral target explicitly
    machine = doc["machine"]
    assert isinstance(machine, dict)
    assert machine["controller_family"] == "NEUTRAL"
    assert machine == NEUTRAL_MACHINE_PROFILE.model_dump(mode="json")


# --- CNC domain: member datums, machine validation, program documents ---

from dekopen_engine.operations import (  # noqa: E402
    ClampZone,
    MachineProfile,
    ManufacturingOperation,
    MemberFace,
    Tool,
    ToolKind,
    member_program,
    program_fingerprint,
    validate_operations,
)


def _cnc_machine(**overrides: Any) -> MachineProfile:
    base: dict[str, Any] = {
        "machine_id": "SBZ-01",
        "name": "Centro CNC 01",
        "controller_family": "NEUTRAL",
        "coordinate_systems": [
            CoordinateSystem.BAR_AXIS,
            CoordinateSystem.MEMBER_PLAN,
            CoordinateSystem.SHEET_PLAN,
        ],
        "tools": [],
    }
    base.update(overrides)
    return MachineProfile(**base)


def test_handle_prep_carries_member_local_datum() -> None:
    """HANDLE_PREP answers u/reference against the host member — machining
    never reads the elevation plan's screen coordinates."""
    member = _member(ProfileRole.FRAME, "1200")  # vertical member at x=500
    unit = _unit(members=[member], handles=[_handle()])
    ops = operations_from_plan(bars=[], fact_units=[unit])
    op = [o for o in ops if o.kind == OperationKind.HANDLE_PREP][0]
    # vertical axis: u = point.y - member.start.y
    assert op.u_mm == Decimal("1050")
    assert op.reference == "member_start"
    assert op.host == member.member_id


def test_end_machining_carries_edge_datum_and_face() -> None:
    member = _member(ProfileRole.MULLION_V, "1180", overlap="15")
    ops = operations_from_plan(bars=[], fact_units=[_unit(members=[member])])
    end_ops = [o for o in ops if o.kind == OperationKind.END_MACHINING]
    by_edge = {o.detail["edge"]: o for o in end_ops}
    assert by_edge["START"].u_mm == Decimal("0")
    assert by_edge["START"].face == MemberFace.START_EDGE
    assert by_edge["START"].reference == "member_start"
    assert by_edge["END"].u_mm == member.cut_length_mm
    assert by_edge["END"].face == MemberFace.END_EDGE
    assert by_edge["END"].reference == "member_end"


def test_saw_ops_reference_the_bar_edge() -> None:
    plan = optimize_cut([_piece("p1", "2000")], [_stock()], _profile())
    ops = operations_from_plan(bars=plan.workshop_cut_plan, fact_units=[])
    assert all(op.reference == "bar_left_edge" for op in ops)


def _member_ops() -> list[ManufacturingOperation]:
    member = _member(ProfileRole.FRAME, "1200")
    unit = _unit(members=[member], handles=[_handle()])
    return operations_from_plan(bars=[], fact_units=[unit])


def test_validate_blocks_when_no_compatible_tool() -> None:
    """No compatible tool in the magazine → BLOCK, never an invented one."""
    ops = _member_ops()
    machine = _cnc_machine(
        tools=[
            Tool(
                tool_id="endmill-10",
                kind=ToolKind.END_MILL,
                name="Fresa 10",
                compatible_kinds=[OperationKind.END_MACHINING],
            )
        ]
    )
    verdicts = validate_operations(ops, machine)
    handle = [v for v in verdicts if v.code == "no_compatible_tool"]
    assert len(handle) == 1
    assert handle[0].level == "BLOCK"
    assert handle[0].detail["tool_id"] == "drill"


def test_validate_blocks_unsupported_kind_and_face() -> None:
    ops = _member_ops()
    machine = _cnc_machine(
        supported_kinds=[OperationKind.DRILL],
        supported_faces=[MemberFace.INSIDE_FACE],
        tools=[
            Tool(
                tool_id="drill",
                kind=ToolKind.DRILL_BIT,
                name="Broca",
            )
        ],
    )
    verdicts = validate_operations(ops, machine)
    assert all(v.level == "BLOCK" for v in verdicts)
    codes = {v.code for v in verdicts}
    # kind gate wins first — the machine can't run HANDLE_PREP at all
    assert "unsupported_kind" in codes


def test_validate_warns_on_clamp_zone_and_margin() -> None:
    ops = _member_ops()
    machine = _cnc_machine(
        tools=[Tool(tool_id="drill", kind=ToolKind.DRILL_BIT, name="Broca")],
        clamp_zones=[
            ClampZone(
                start_mm=Decimal("1000"),
                end_mm=Decimal("1100"),
                label="Mordaza B",
            )
        ],
    )
    verdicts = validate_operations(
        ops,
        machine,
        member_lengths_mm={"a" * 64: Decimal("1200")},
    )
    handle = [
        v
        for v in verdicts
        if v.detail.get("host")
        and v.code == "clamp_conflict"
    ]
    assert handle and handle[0].level == "WARN"
    assert handle[0].detail["clamp_label"] == "Mordaza B"


def test_validate_blocks_envelope_overflow() -> None:
    ops = _member_ops()
    machine = _cnc_machine(
        max_member_length_mm=Decimal("1000"),
        tools=[Tool(tool_id="drill", kind=ToolKind.DRILL_BIT, name="Broca")],
    )
    verdicts = validate_operations(
        ops,
        machine,
        member_lengths_mm={"a" * 64: Decimal("1200")},
    )
    blocked = [v for v in verdicts if v.level == "BLOCK"]
    assert any(v.code == "envelope_exceeded" for v in blocked)


def test_validate_passes_compatible_setup() -> None:
    ops = _member_ops()
    machine = _cnc_machine(
        tools=[Tool(tool_id="drill", kind=ToolKind.DRILL_BIT, name="Broca")],
        safe_margin_mm=Decimal("10"),
    )
    verdicts = validate_operations(
        ops, machine, member_lengths_mm={"a" * 64: Decimal("1200")}
    )
    # HANDLE_PREP carries no declared face or hole pattern — the authority
    # gaps surface as WARN, never as a fabricated PASS.
    assert all(v.level == "WARN" for v in verdicts)
    assert {v.code for v in verdicts} <= {
        "face_undeclared",
        "feature_point_only",
        "margin_violation",
        "clamp_conflict",
    }


def test_validate_blocks_unsupported_coordinate_system() -> None:
    ops = _member_ops()
    machine = _cnc_machine(
        coordinate_systems=[CoordinateSystem.BAR_AXIS],
        tools=[Tool(tool_id="drill", kind=ToolKind.DRILL_BIT, name="Broca")],
    )
    verdicts = validate_operations(ops, machine)
    assert all(v.level == "BLOCK" for v in verdicts)
    assert {v.code for v in verdicts} == {"coordinate_unsupported"}


def test_tool_depth_limit_blocks() -> None:
    member = _member(ProfileRole.MULLION_V, "1180", overlap="40")
    ops = operations_from_plan(bars=[], fact_units=[_unit(members=[member])])
    machine = _cnc_machine(
        tools=[
            Tool(
                tool_id="end_mill",
                kind=ToolKind.END_MILL,
                name="Fresa",
                max_depth_mm=Decimal("25"),
            )
        ],
    )
    verdicts = validate_operations(ops, machine)
    assert any(
        v.code == "tool_depth_exceeded" and v.level == "BLOCK"
        for v in verdicts
    )


def test_member_program_is_deterministic_and_sequenced() -> None:
    ops = _member_ops()
    member_id = "a" * 64
    machine = _cnc_machine(
        tools=[Tool(tool_id="drill", kind=ToolKind.DRILL_BIT, name="Broca")]
    )
    identity = {"order_code": "OT-1", "revision_code": "REV-A"}
    a = member_program(
        ops, member_id=member_id, member_label="M-01",
        machine=machine, identity=identity,
    )
    b = member_program(
        ops, member_id=member_id, member_label="M-01",
        machine=machine, identity=identity,
    )
    assert a == b
    program_ops = a["operations"]
    assert isinstance(program_ops, list)
    assert [o["sequence_no"] for o in program_ops] == [1]
    # No dry run was passed in — a program is never PASS without one.
    assert a["verdict"] == "UNVERIFIED"
    assert a["fingerprint"] == program_fingerprint(a)
    # Program identity carries the piece/machine/postprocessor contract.
    ident = a["identity"]
    assert isinstance(ident, dict)
    assert ident["member_label"] == "M-01"
    assert ident["machine_id"] == "SBZ-01"
    assert ident["postprocessor_id"] == "neutral-ops-v1"


def test_member_program_marks_blocked_members() -> None:
    ops = _member_ops()
    machine = _cnc_machine()  # empty magazine — nothing is machinable
    program = member_program(
        ops,
        member_id="a" * 64,
        member_label="M-01",
        machine=machine,
        identity={"order_code": "OT-1"},
        validations=validate_operations(ops, machine),
    )
    assert program["verdict"] == "BLOCK"


def test_handle_prep_member_local_u_on_horizontal_member() -> None:
    """Mirrored products put the handle on a different stile — u stays a
    member datum regardless of which member/axis carries it."""
    member = _member(ProfileRole.MULLION_V, "1000")
    member.axis = Axis.HORIZONTAL
    member.start = TracePointV1(x_mm=Decimal("200"), y_mm=Decimal("900"))
    member.end = TracePointV1(x_mm=Decimal("1200"), y_mm=Decimal("900"))
    member.cut_length_mm = Decimal("1000")
    handle = _handle()
    handle.host_member_id = member.member_id
    handle.point = TracePointV1(x_mm=Decimal("900"), y_mm=Decimal("900"))
    ops = operations_from_plan(
        bars=[], fact_units=[_unit(members=[member], handles=[handle])]
    )
    op = [o for o in ops if o.kind == OperationKind.HANDLE_PREP][0]
    # horizontal axis: u = point.x - member.start.x
    assert op.u_mm == Decimal("700")
    assert op.reference == "member_start"
