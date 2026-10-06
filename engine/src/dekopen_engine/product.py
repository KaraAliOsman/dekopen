"""Compositional product model: assemblies of modules joined by couplings.

A DEKOPEN product is a `CoupledAssembly`: one or more `ProductModule`s
(rectangular parametric units reusing the proven per-module geometry)
joined by `CouplingDef`s — angled posts between adjacent module frames.
A single-unit window is the degenerate assembly: one module, no couplings.

`evaluate_product` separates two questions the UI must keep apart:

- Is the geometry constructible? (plan polygon, angle accumulation)
- Is the manufacturing definition complete? (module geometry evaluates,
  every coupling has a resolvable coupler profile, heights match)

The result status is INVALID / MANUFACTURING_INCOMPLETE / VALID. The engine
never invents catalog data: an unresolved coupler SKU is reported, never
faked.
"""

from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Literal

from pydantic import Field

from dekopen_engine.contour import (
    Contour,
    contour_area,
    contour_points,
    edge_length as contour_edge_length,
    ensure_ccw,
    interior_angle,
    offset_contour,
    validate_contour,
)
from dekopen_engine.geometry import (
    DomainRejection,
    calculate_geometry,
    joint_adjustment_per_end,
    rebate_depth,
    reinforcement_cut_length,
    resolve_bead_rule,
    resolved_sliding_layout,
    panel_travel,
    travel_inferred,
)
from dekopen_engine.finishes import apply_color_surcharges
from dekopen_engine.glass import derive_net_glass_thickness
from dekopen_engine.hardware import (
    HardwareSelectionError,
    NoCompatibleHardwareKit,
)
from dekopen_engine.manufacturing_trace import (
    Axis,
    GeometryManufacturingTraceV1,
    PlacementDomain,
    SemanticInfillTraceV1,
    SemanticMemberTraceV1,
    TracePointV1,
    TraceRectV1,
    TraceSegmentV1,
)
from dekopen_engine.models import (
    BayOpeningType,
    ColorSelection,
    EffectiveProfileArticle,
    EngineModel,
    EngineResult,
    ExtraSelection,
    ExtraSuggestion,
    FittingPiece,
    GlassPiece,
    MaterialType,
    NodeType,
    OpeningMovement,
    OpeningSpec,
    ParametricNode,
    PlanPoint,
    ProfileCut,
    ProfileRole,
    ReinforcementPiece,
    SlidingPanelKind,
    SlidingTravel,
    SystemParams,
    UnitKind,
)
from dekopen_engine.models import EdgeSide as EdgeSide
from dekopen_engine.extras import (
    ModuleExtraContext,
    OperableLeaf,
    evaluate_position_extras,
)
from dekopen_engine.technical_facts import (
    GeometryComputation,
    InfillTechnicalFacts,
    OpeningTechnicalFacts,
)
from dekopen_engine.openings import (
    resolve_opening_spec,
    resolve_unit_kind,
    spec_display_name_es,
)
from dekopen_engine.trig import cos_degrees, sin_degrees

QUANTUM_MM = Decimal("0.01")
_MAX_HEADING_DEG = Decimal("170")


class ProductStatus(str, Enum):
    VALID = "VALID"
    MANUFACTURING_INCOMPLETE = "MANUFACTURING_INCOMPLETE"
    INVALID = "INVALID"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class IssueCode(str, Enum):
    COUPLINGS_COUNT_MISMATCH = "couplings_count_mismatch"
    ASSEMBLY_FOLDS_BACK = "assembly_folds_back"
    PLAN_SELF_INTERSECTION = "plan_self_intersection"
    MODULE_GEOMETRY_FAILED = "module_geometry_failed"
    COUPLER_PROFILE_MISSING = "coupler_profile_missing"
    COUPLER_PROFILE_UNKNOWN = "coupler_profile_unknown"
    COUPLER_HEIGHT_MISMATCH = "coupler_height_mismatch"
    COUPLER_REINFORCEMENT_NONPOSITIVE = "coupler_reinforcement_nonpositive"
    CONTOUR_INVALID = "contour_invalid"
    CONTOUR_SPLITS_UNSUPPORTED = "contour_splits_unsupported"
    CONTOUR_OPENING_UNSUPPORTED = "contour_opening_unsupported"
    CONTOUR_PANEL_UNSUPPORTED = "contour_panel_unsupported"
    MEMBER_BENDING_REQUIRED = "member_bending_required"
    COUPLER_WIDTH_MISMATCH = "coupler_width_mismatch"
    COUPLER_MODULE_UNKNOWN = "coupler_module_unknown"
    COUPLER_EDGE_INVALID = "coupler_edge_invalid"
    COUPLER_EDGE_CONFLICT = "coupler_edge_conflict"
    # P06 — the picked coupler declares an angle envelope the joint's
    # deflection does not fit (catalog authority, never a hardcoded band).
    COUPLER_ANGLE_INCOMPATIBLE = "coupler_angle_incompatible"
    CONNECTION_TYPE_UNSUPPORTED = "connection_type_unsupported"
    ASSEMBLY_DISCONNECTED = "assembly_disconnected"
    STACKED_CYCLE = "stacked_cycle"
    INLINE_NOT_ADJACENT = "inline_not_adjacent"
    CONTOUR_COUPLING_UNSUPPORTED = "contour_coupling_unsupported"
    SLIDING_LAYOUT_INVALID = "sliding_layout_invalid"
    SLIDING_TRACKS_UNSUPPORTED = "sliding_tracks_unsupported"
    FRAMELESS_SPLITS_UNSUPPORTED = "frameless_splits_unsupported"
    FRAMELESS_OPENING_UNSUPPORTED = "frameless_opening_unsupported"
    FRAMELESS_PANEL_UNSUPPORTED = "frameless_panel_unsupported"
    FRAMELESS_CONTOUR_UNSUPPORTED = "frameless_contour_unsupported"
    FRAMELESS_ARTICLE_UNKNOWN = "frameless_article_unknown"
    MEMBER_EXCEEDS_STOCK = "member_exceeds_stock"
    HARDWARE_KIT_INCOMPATIBLE = "hardware_kit_incompatible"
    HARDWARE_KIT_OVERWEIGHT = "hardware_kit_overweight"
    HARDWARE_UNDECIDABLE = "hardware_undecidable"
    HARDWARE_SELECTION_UNKNOWN = "hardware_selection_unknown"
    HANDLE_HEIGHT_OUT_OF_RANGE = "handle_height_out_of_range"
    TYPOLOGY_FAMILY_INCOMPATIBLE = "typology_family_incompatible"
    LEAF_DIMENSIONAL_LIMIT = "leaf_dimensional_limit"
    # D02 structured-glass rule findings surfaced on the bay that carries
    # them — rule_code/severity live in params (rules are org data, so the
    # finding's own code is the constant).
    GLASS_SAFETY_FINDING = "glass_safety_finding"


class ConnectionKind(str, Enum):
    """Structural class of a module-to-module joint (mandate §6)."""

    INLINE = "INLINE"  # vertical post between same-height neighbors (any plan angle)
    STACKED = "STACKED"  # horizontal member — module on top of module
    TEE = "TEE"  # member landing mid-edge (declared; evaluated as unsupported)
    CORNER = "CORNER"  # framed corner assembly (declared; evaluated as unsupported)


class CouplingDef(EngineModel):
    """Joint between two modules of an assembly.

    `angle_deg` is the signed deflection of the front chain at the joint:
    positive turns the next module counterclockwise (plan view). Zero is a
    coplanar coupling.

    `modules`/`edges` name the two endpoints explicitly — `modules[i]`'s
    `edges[i]` side joins `modules[j]`'s `edges[j]` side. When absent the
    coupling keeps the legacy positional binding: modules[i] right to
    modules[i+1] left, in declaration order.
    """

    id: str
    angle_deg: Decimal = Decimal("0")
    coupler_profile_sku: str | None = None
    kind: ConnectionKind = ConnectionKind.INLINE
    modules: list[str] | None = None
    edges: list[EdgeSide] | None = None


class FramelessSupportKind(str, Enum):
    """How an exposed edge is held (mandate §14)."""

    CHANNEL = "CHANNEL"  # continuous channel run seating the edge
    CLAMPS = "CLAMPS"  # point clamps along the edge — `qty` is the count


class FramelessFittingKind(str, Enum):
    """Counted fitting kinds of the glass-only domain (mandate §14)."""

    PATCH_FITTING = "PATCH_FITTING"
    CLAMP = "CLAMP"
    HINGE = "HINGE"
    LOCK = "LOCK"
    CONNECTOR = "CONNECTOR"
    SEAL = "SEAL"
    SUPPORT = "SUPPORT"


class FramelessSupport(EngineModel):
    """One supported edge run of a frameless pane."""

    kind: FramelessSupportKind
    edge: EdgeSide
    article_sku: str
    qty: int = Field(default=1, gt=0)


class FramelessFitting(EngineModel):
    """A declared fitting on the pane — patch fitting, clamp, hinge, lock,
    connector, seal or point support, with its catalog sku and count."""

    kind: FramelessFittingKind
    sku: str
    qty: int = Field(default=1, gt=0)


class FramelessSpec(EngineModel):
    """Glass-only module spec (mandate §14): the pane IS the module — real
    support/fitting concepts, never fake FRAME/SASH profiles. `tree` must
    still be a single BAY leaf carrying the glass spec; when `contour` is
    also set, the pane takes the contour's boundary directly (no frame
    inset exists to offset)."""

    supports: list[FramelessSupport] = Field(default_factory=list)
    fittings: list[FramelessFitting] = Field(default_factory=list)
    # Edges of exposed glass — polishing authority's suggested preselection.
    # None means the whole pane is exposed (all four edges).
    exposed_edges: list[EdgeSide] | None = None


class ProductModule(EngineModel):
    id: str
    # Nominal bounding rectangle — still drives plan-view layout and module
    # pitch. For contour modules these equal the contour bounding box.
    width_mm: Decimal = Field(gt=0)
    height_mm: Decimal = Field(gt=0)
    # Non-rectangular outer shape (elevation, module-local mm). When set the
    # module evaluates through the contour path: frame members follow edges,
    # miters are corner interior / 2, and the fill region is the inward
    # offset. `tree` must then be a single BAY leaf carrying the region spec.
    contour: Contour | None = None
    # Glass-only evaluation (mandate §14): pane + supports + fittings.
    frameless: FramelessSpec | None = None
    tree: ParametricNode


class CoupledAssembly(EngineModel):
    modules: list[ProductModule] = Field(min_length=1)
    couplings: list[CouplingDef] = Field(default_factory=list)


class ProductModel(EngineModel):
    version: Literal["product-v2"]
    assembly: CoupledAssembly
    # Declared position extras (D06) — sealed inside the parametric_tree
    # so issued documents reproduce the accessories exactly.
    extras: list[ExtraSelection] = Field(default_factory=list)


class PlanModule(EngineModel):
    module_id: str
    # front-left, front-right, back-right, back-left
    corners: list[PlanPoint]


class PlanCoupling(EngineModel):
    coupling_id: str
    polygon: list[PlanPoint]


class PlanGeometry(EngineModel):
    front_chain: list[PlanPoint]
    modules: list[PlanModule]
    couplings: list[PlanCoupling]
    min_x_mm: Decimal
    min_y_mm: Decimal
    width_mm: Decimal
    height_mm: Decimal


class ProductIssue(EngineModel):
    code: str
    severity: Severity
    target: str
    params: dict[str, str] = Field(default_factory=dict)


class SlidingPanelFacts(EngineModel):
    """One evaluated sliding slot — the panel's declared kind, the rail it
    rides, its slide direction (resolved or declared), whether that
    direction was merely inferred, and the leaf id the BOM carries for it
    (moving panels only)."""

    slot: str
    kind: SlidingPanelKind
    track: int | None = None
    travel: SlidingTravel | None = None
    travel_inferred: bool = False
    leaf_id: str | None = None


class SlidingLayoutFacts(EngineModel):
    """The sliding topology a module's bay evaluated to — rails plus every
    panel left→right. Meeting stiles are every adjacent pair; a pair where
    one side is FIXED is the channel the moving leaf covers.
    `primary_index` is the stacking choice: which panel opens first."""

    bay_id: str
    tracks: int
    panels: list[SlidingPanelFacts]
    primary_index: int | None = None


class ModuleEvaluation(EngineModel):
    module_id: str
    issues: list[ProductIssue] = Field(default_factory=list)
    result: EngineResult | None = None
    sliding: list[SlidingLayoutFacts] = Field(default_factory=list)


class ProductEvaluation(EngineModel):
    status: ProductStatus
    issues: list[ProductIssue] = Field(default_factory=list)
    # Catalogued companions the position qualifies for and has not
    # selected (D06) — advisory; the user accepts or discards them.
    extra_suggestions: list[ExtraSuggestion] = Field(default_factory=list)
    plan: PlanGeometry | None = None
    modules: list[ModuleEvaluation] = Field(default_factory=list)
    bom: EngineResult | None = None


def _q(value: Decimal) -> Decimal:
    return value.quantize(QUANTUM_MM, rounding=ROUND_HALF_UP)


def _seg_intersects(
    a1: PlanPoint, a2: PlanPoint, b1: PlanPoint, b2: PlanPoint
) -> bool:
    def orient(p: PlanPoint, q: PlanPoint, r: PlanPoint) -> Decimal:
        return (q.x_mm - p.x_mm) * (r.y_mm - p.y_mm) - (q.y_mm - p.y_mm) * (
            r.x_mm - p.x_mm
        )

    o1 = orient(a1, a2, b1)
    o2 = orient(a1, a2, b2)
    o3 = orient(b1, b2, a1)
    o4 = orient(b1, b2, a2)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def _polygons_overlap(
    a: list[PlanPoint], b: list[PlanPoint], *, interior_only: bool = False
) -> bool:
    """SAT overlap test for convex polygons.

    Exact for our module rectangles and coupler wedges: any separating axis
    (an edge normal of either polygon) means disjoint; otherwise the polygons
    intersect — including containment and edge-touch, which both collide
    physically. With `interior_only`, touching at a vertex or edge does not
    count: only positive-area overlap is reported (adjacent modules always
    share their joint boundary, so only interior penetration is a collision).
    """

    def span(points: list[PlanPoint], nx: Decimal, ny: Decimal) -> tuple[Decimal, Decimal]:
        values = [p.x_mm * nx + p.y_mm * ny for p in points]
        return min(values), max(values)

    for poly in (a, b):
        count = len(poly)
        for i in range(count):
            edge = poly[(i + 1) % count]
            ex = edge.x_mm - poly[i].x_mm
            ey = edge.y_mm - poly[i].y_mm
            lo_a, hi_a = span(a, -ey, ex)
            lo_b, hi_b = span(b, -ey, ex)
            if interior_only:
                if hi_a <= lo_b or hi_b <= lo_a:
                    return False
            elif hi_a < lo_b or hi_b < lo_a:
                return False
    return True


def _resolved_pairs(
    modules: list[ProductModule], couplings: list[CouplingDef]
) -> list[tuple[CouplingDef, list[str]]]:
    """Explicit `modules` endpoints, or the positional binding index→index+1
    when a coupling leaves them implicit."""
    resolved: list[tuple[CouplingDef, list[str]]] = []
    for index, coupling in enumerate(couplings):
        pair = coupling.modules
        if pair is None and index < len(modules) - 1:
            pair = [modules[index].id, modules[index + 1].id]
        if pair is not None and len(pair) == 2:
            resolved.append((coupling, pair))
    return resolved


def _stack_parents(
    resolved: list[tuple[CouplingDef, list[str]]],
) -> dict[str, str]:
    """Map each stacked member id → the partner it hangs over.

    A STACKED coupling binds one member's TOP edge to the other member's
    BOTTOM edge; the member offering the TOP edge is the lower partner.
    """
    stack_parent: dict[str, str] = {}
    for coupling, pair in resolved:
        if coupling.kind is not ConnectionKind.STACKED:
            continue
        edges = coupling.edges or [EdgeSide.TOP, EdgeSide.BOTTOM]
        if len(edges) != 2:
            continue
        top_index = (
            0
            if edges[0] is EdgeSide.TOP
            else (1 if edges[1] is EdgeSide.TOP else None)
        )
        if top_index is not None:
            stack_parent[pair[1 - top_index]] = pair[top_index]
    return stack_parent


def _resolve_stack_roots(
    modules: list[ProductModule],
    resolved: list[tuple[CouplingDef, list[str]]],
) -> dict[str, str]:
    """Map each stacked member id → its root column id.

    Modules joined by a STACKED coupling project onto their lower partner —
    the endpoint whose TOP edge is the contact. Anchors resolve transitively
    for towers; cycles degrade to "no anchor" and lay out front-wise.
    """
    stack_parent = _stack_parents(resolved)
    module_ids = {module.id for module in modules}
    roots: dict[str, str] = {}
    for member_id in stack_parent:
        seen: set[str] = set()
        current = member_id
        while current in stack_parent and current not in seen:
            seen.add(current)
            current = stack_parent[current]
        anchor = None if current in stack_parent else current
        if anchor is not None and anchor in module_ids:
            roots[member_id] = anchor
    return roots


class ElevationMember(EngineModel):
    """A module's placement in the front elevation (mandate §6).

    `x_mm` is the member's left edge in assembly elevation coordinates and
    `sill_mm` its bottom edge above the common baseline — a member narrower
    than its column centres; a wider one overhangs honestly.
    """

    module_id: str
    x_mm: Decimal
    sill_mm: Decimal
    width_mm: Decimal
    height_mm: Decimal


class ElevationColumnJoint(EngineModel):
    """The vertical seam between two adjacent front columns."""

    coupling_id: str | None = None
    x_mm: Decimal
    top_mm: Decimal
    width_mm: Decimal
    angle_deg: Decimal | None = None


class ElevationStackJoint(EngineModel):
    """The horizontal contact a stacked member makes on its column."""

    coupling_id: str
    x_mm: Decimal
    y_mm: Decimal
    width_mm: Decimal


class ElevationLayout(EngineModel):
    members: list[ElevationMember]
    column_joints: list[ElevationColumnJoint] = Field(default_factory=list)
    stack_joints: list[ElevationStackJoint] = Field(default_factory=list)


def elevation_layout(assembly: CoupledAssembly) -> ElevationLayout:
    """The assembly's front-elevation layout (mandate §6).

    Front columns advance left→right in declaration order at each root's
    declared width. STACKED members share their root column, stacking
    bottom-up: a member's sill is its partner's top edge, towers resolving
    transitively (cycles degrade to the baseline, matching the plan's
    "no anchor" rule). Column seams carry the bound INLINE coupling's
    declared angle; stack contacts carry the coupling that declared them.
    """
    modules = assembly.modules
    by_id = {module.id: module for module in modules}
    resolved = _resolved_pairs(modules, assembly.couplings)
    stack_parent = _stack_parents(resolved)
    stack_root = _resolve_stack_roots(modules, resolved)

    sills: dict[str, Decimal] = {}

    def member_sill(module_id: str, seen: frozenset[str]) -> Decimal:
        if module_id in sills:
            return sills[module_id]
        parent = stack_parent.get(module_id)
        if parent is None or parent not in by_id or parent in seen:
            sills[module_id] = Decimal("0")
        else:
            sills[module_id] = member_sill(
                parent, seen | {module_id}
            ) + by_id[parent].height_mm
        return sills[module_id]

    members: list[ElevationMember] = []
    column_roots: list[ProductModule] = []
    column_tops: list[Decimal] = []
    cursor = Decimal("0")
    for column_root in modules:
        if column_root.id in stack_root:
            continue
        column_roots.append(column_root)
        top = Decimal("0")
        for member in modules:
            if member.id != column_root.id and stack_root.get(member.id) != column_root.id:
                continue
            sill = member_sill(member.id, frozenset({member.id}))
            top = max(top, sill + member.height_mm)
            members.append(
                ElevationMember(
                    module_id=member.id,
                    x_mm=cursor + (column_root.width_mm - member.width_mm) / Decimal("2"),
                    sill_mm=sill,
                    width_mm=member.width_mm,
                    height_mm=member.height_mm,
                )
            )
        column_tops.append(top)
        cursor += column_root.width_mm

    # Column seams: the INLINE coupling that binds the root pair carries the
    # declared angle; an undeclared seam is a straight joint.
    pair_coupling: dict[frozenset[str], CouplingDef] = {}
    for coupling, pair in resolved:
        root_pair = frozenset(
            {stack_root.get(pair[0], pair[0]), stack_root.get(pair[1], pair[1])}
        )
        if len(root_pair) == 2:
            pair_coupling.setdefault(root_pair, coupling)
    column_joints: list[ElevationColumnJoint] = []
    boundary = Decimal("0")
    for index, column_root in enumerate(column_roots):
        boundary += column_root.width_mm
        if index + 1 == len(column_roots):
            break
        seam_coupling = pair_coupling.get(
            frozenset({column_root.id, column_roots[index + 1].id})
        )
        column_joints.append(
            ElevationColumnJoint(
                coupling_id=seam_coupling.id if seam_coupling is not None else None,
                x_mm=boundary,
                top_mm=min(column_tops[index], column_tops[index + 1]),
                width_mm=min(
                    column_root.width_mm, column_roots[index + 1].width_mm
                ),
                angle_deg=(
                    seam_coupling.angle_deg
                    if seam_coupling is not None
                    and seam_coupling.kind is ConnectionKind.INLINE
                    else None
                ),
            )
        )

    # Stack contacts: every stacked member hangs on the coupling that
    # declared it — the seam is the member's own sill line.
    member_coupling: dict[str, str] = {}
    for coupling, pair in resolved:
        if coupling.kind is not ConnectionKind.STACKED:
            continue
        edges = coupling.edges or [EdgeSide.TOP, EdgeSide.BOTTOM]
        if len(edges) != 2:
            continue
        top_index = (
            0
            if edges[0] is EdgeSide.TOP
            else (1 if edges[1] is EdgeSide.TOP else None)
        )
        if top_index is not None:
            member_coupling[pair[1 - top_index]] = coupling.id
    by_member = {member.module_id: member for member in members}
    stack_joints = [
        ElevationStackJoint(
            coupling_id=member_coupling[member_id],
            x_mm=by_member[member_id].x_mm,
            y_mm=by_member[member_id].sill_mm,
            width_mm=by_member[member_id].width_mm,
        )
        for member_id in member_coupling
        if member_id in by_member
    ]
    return ElevationLayout(
        members=members,
        column_joints=column_joints,
        stack_joints=stack_joints,
    )


def elevation_envelope(assembly: CoupledAssembly) -> tuple[Decimal, Decimal]:
    """The assembly's nominal front-elevation envelope (mandate §6).

    Stacked members project into their root column: width spans across the
    front columns only, and each column's height is the sum of its members —
    a 1000×2200 door carrying a 1000×400 transom is 1000×2600, not
    2000×2200. This is THE nominal-dimension contract the API validates
    and the frontend sends.
    """
    layout = elevation_layout(assembly)
    members = layout.members
    if not members:
        return Decimal("0"), Decimal("0")
    left = min(member.x_mm for member in members)
    right = max(member.x_mm + member.width_mm for member in members)
    top = max(member.sill_mm + member.height_mm for member in members)
    bottom = min(member.sill_mm for member in members)
    return right - left, top - bottom


def _plan_geometry(
    assembly: CoupledAssembly, depth_mm: Decimal
) -> tuple[PlanGeometry, list[ProductIssue]]:
    """Project the assembly into a top-view polygon.

    Module i runs from front-chain point F_i to F_{i+1} along heading
    theta_i; theta_0 = 0 and theta_{i+1} = theta_i + coupling[i].angle_deg.
    The back edge of every module is offset by `depth_mm` along its local
    normal; the gap between two module rectangles at a joint is the coupler
    wedge polygon.
    """
    issues: list[ProductIssue] = []
    modules = assembly.modules
    couplings = assembly.couplings

    resolved_pairs = _resolved_pairs(modules, couplings)

    # Connectivity unions over the RAW pairs — a stacked member is connected
    # through the joint to its column. Front joints are keyed by ROOT pairs:
    # a coupling on a stacked member's side edge binds its whole column.
    union_parent = {module.id: module.id for module in modules}

    def _union_root(module_id: str) -> str:
        while union_parent[module_id] != module_id:
            union_parent[module_id] = union_parent[union_parent[module_id]]
            module_id = union_parent[module_id]
        return module_id

    for _coupling, pair in resolved_pairs:
        first, second = pair
        if first in union_parent and second in union_parent:
            union_parent[_union_root(first)] = _union_root(second)
    union_roots = {_union_root(module.id) for module in modules}
    if len(modules) > 1 and len(union_roots) > 1:
        issues.append(
            ProductIssue(
                code=IssueCode.ASSEMBLY_DISCONNECTED.value,
                severity=Severity.ERROR,
                target="assembly",
                params={"roots": str(len(union_roots))},
            )
        )

    # Stack roots resolve BEFORE layout, so an upper module declared ahead of
    # its column produces the same plan as one declared after it. A member
    # whose STACKED parent chain lands on a cycle has no physical bottom —
    # that is an error, not a layout variant: the union saw it as connected,
    # so nothing else would stop a cyclic stack from validating.
    stack_parent = _stack_parents(resolved_pairs)
    stack_root = _resolve_stack_roots(modules, resolved_pairs)
    for member_id in stack_parent:
        if member_id not in stack_root:
            issues.append(
                ProductIssue(
                    code=IssueCode.STACKED_CYCLE.value,
                    severity=Severity.ERROR,
                    target=f"module:{member_id}",
                )
            )

    coupling_pairs: set[frozenset[str]] = set()
    pair_coupling: dict[frozenset[str], CouplingDef] = {}
    for coupling, pair in resolved_pairs:
        root_pair = frozenset(
            {stack_root.get(pair[0], pair[0]), stack_root.get(pair[1], pair[1])}
        )
        if len(root_pair) == 2:
            coupling_pairs.add(root_pair)
            pair_coupling.setdefault(root_pair, coupling)

    front: list[PlanPoint] = [PlanPoint(x_mm=Decimal(0), y_mm=Decimal(0))]
    plan_modules_by_id: dict[str, PlanModule] = {}
    plan_couplings: list[PlanCoupling] = []
    plan_coupling_endpoints: list[frozenset[str]] = []
    all_points: list[PlanPoint] = []
    front_module_ids: list[str] = []
    front_indices = [
        index for index, module in enumerate(modules) if module.id not in stack_root
    ]
    next_front = {
        front_indices[position]: front_indices[position + 1]
        for position in range(len(front_indices) - 1)
    }

    # An INLINE coupling is the seam between two columns that are adjacent on
    # the front: only consecutive root pairs have a physical joint. A coupling
    # bridging non-consecutive columns (a–c over b) has no seam — the plan
    # would silently drop it while the BOM still cut its coupler.
    consecutive_pairs = {
        frozenset({modules[first].id, modules[second].id})
        for first, second in next_front.items()
    }
    for coupling, pair in resolved_pairs:
        if coupling.kind is not ConnectionKind.INLINE:
            continue
        root_pair = frozenset(
            {stack_root.get(pair[0], pair[0]), stack_root.get(pair[1], pair[1])}
        )
        if len(root_pair) == 2 and root_pair not in consecutive_pairs:
            issues.append(
                ProductIssue(
                    code=IssueCode.INLINE_NOT_ADJACENT.value,
                    severity=Severity.ERROR,
                    target=f"coupling:{coupling.id}",
                )
            )

    # Headings belong to the resolved front joints, not to declaration order:
    # an INLINE edge's angle applies at the joint it binds, wherever in the
    # coupling list it was declared; an undeclared joint stays straight.
    front_heading: dict[int, Decimal] = {}
    heading = Decimal(0)
    previous_index: int | None = None
    for index in front_indices:
        if previous_index is not None:
            joint_coupling = pair_coupling.get(
                frozenset({modules[previous_index].id, modules[index].id})
            )
            if joint_coupling is not None and joint_coupling.kind is ConnectionKind.INLINE:
                heading = heading + joint_coupling.angle_deg
                if abs(heading) > _MAX_HEADING_DEG:
                    issues.append(
                        ProductIssue(
                            code=IssueCode.ASSEMBLY_FOLDS_BACK.value,
                            severity=Severity.ERROR,
                            target=f"coupling:{joint_coupling.id}",
                            params={"heading_deg": str(_q(heading))},
                        )
                    )
        front_heading[index] = heading
        previous_index = index

    for index, module in enumerate(modules):
        if module.id in stack_root:
            continue
        front_module_ids.append(module.id)
        theta = front_heading[index]
        cos_t = cos_degrees(theta)
        sin_t = sin_degrees(theta)
        end_x = front[-1].x_mm + module.width_mm * cos_t
        end_y = front[-1].y_mm + module.width_mm * sin_t
        front.append(PlanPoint(x_mm=end_x, y_mm=end_y))
        normal = PlanPoint(x_mm=-sin_t, y_mm=cos_t)

        start = front[-2]
        end = front[-1]
        back_start = PlanPoint(
            x_mm=start.x_mm - depth_mm * normal.x_mm,
            y_mm=start.y_mm - depth_mm * normal.y_mm,
        )
        back_end = PlanPoint(
            x_mm=end.x_mm - depth_mm * normal.x_mm,
            y_mm=end.y_mm - depth_mm * normal.y_mm,
        )
        corners = [start, end, back_end, back_start]
        plan_modules_by_id[module.id] = PlanModule(
            module_id=module.id,
            corners=corners,
        )
        all_points.extend([start, end, back_start, back_end])

        next_index = next_front.get(index)
        if next_index is not None:
            joint_coupling = pair_coupling.get(
                frozenset({module.id, modules[next_index].id})
            )
            if joint_coupling is not None and joint_coupling.kind is ConnectionKind.INLINE:
                next_theta = front_heading[next_index]
                next_normal = PlanPoint(
                    x_mm=-sin_degrees(next_theta), y_mm=cos_degrees(next_theta)
                )
                joint = end
                back_left = PlanPoint(
                    x_mm=joint.x_mm - depth_mm * next_normal.x_mm,
                    y_mm=joint.y_mm - depth_mm * next_normal.y_mm,
                )
                plan_couplings.append(
                    PlanCoupling(
                        coupling_id=joint_coupling.id,
                        polygon=[joint, back_end, back_left],
                    )
                )
                plan_coupling_endpoints.append(
                    frozenset({module.id, modules[next_index].id})
                )
                all_points.extend([back_left])

    # Stacked members inherit their resolved root column's footprint.
    for module in modules:
        anchor = stack_root.get(module.id)
        if anchor is not None and anchor in plan_modules_by_id:
            plan_modules_by_id[module.id] = PlanModule(
                module_id=module.id,
                corners=plan_modules_by_id[anchor].corners,
            )
    plan_modules = [
        plan_modules_by_id[module.id]
        for module in modules
        if module.id in plan_modules_by_id
    ]

    # Non-adjacent front segments must not cross.
    for i in range(len(front) - 1):
        for j in range(i + 2, len(front) - 1):
            if _seg_intersects(front[i], front[i + 1], front[j], front[j + 1]):
                issues.append(
                    ProductIssue(
                        code=IssueCode.PLAN_SELF_INTERSECTION.value,
                        severity=Severity.ERROR,
                        target="assembly",
                        params={
                            "first": front_module_ids[i],
                            "second": front_module_ids[j],
                        },
                    )
                )

    # Depth polygons must not collide either: front chains can stay disjoint
    # while two module rectangles or a coupler wedge overlap in depth.
    # Modules stacked on one anchor share the footprint by design — excluded,
    # and coupling-declared endpoint pairs legitimately share a boundary.
    def _co_stacked(id_a: str, id_b: str) -> bool:
        return (
            id_a in stack_root
            and id_b in stack_root
            and stack_root[id_a] == stack_root[id_b]
        ) or stack_root.get(id_a) == id_b or stack_root.get(id_b) == id_a

    front_order = {module_id: position for position, module_id in enumerate(front_module_ids)}
    rects = [(module.module_id, module.corners) for module in plan_modules]
    for i, (id_a, poly_a) in enumerate(rects):
        for j in range(i + 1, len(rects)):
            id_b, poly_b = rects[j]
            if _co_stacked(id_a, id_b):
                continue
            # Adjacent chain slots touch; coupling-declared columns touch —
            # including anchored siblings stacked over declared partners.
            root_a, root_b = stack_root.get(id_a, id_a), stack_root.get(id_b, id_b)
            expected_contact = (
                abs(front_order[root_a] - front_order[root_b]) == 1
                or frozenset({root_a, root_b}) in coupling_pairs
            )
            if _polygons_overlap(poly_a, poly_b, interior_only=expected_contact):
                issues.append(
                    ProductIssue(
                        code=IssueCode.PLAN_SELF_INTERSECTION.value,
                        severity=Severity.ERROR,
                        target=f"module:{id_b}",
                        params={"other": id_a},
                    )
                )
    for index, plan_coupling in enumerate(plan_couplings):
        endpoints = plan_coupling_endpoints[index]
        for j, (id_b, poly_b) in enumerate(rects):
            if id_b in endpoints or stack_root.get(id_b) in endpoints:
                continue
            if _polygons_overlap(plan_coupling.polygon, poly_b):
                issues.append(
                    ProductIssue(
                        code=IssueCode.PLAN_SELF_INTERSECTION.value,
                        severity=Severity.ERROR,
                        target=f"module:{id_b}",
                        params={"other": f"coupling:{plan_coupling.coupling_id}"},
                    )
                )

    quantized = [PlanPoint(x_mm=_q(p.x_mm), y_mm=_q(p.y_mm)) for p in all_points]
    min_x = min(p.x_mm for p in quantized)
    min_y = min(p.y_mm for p in quantized)
    max_x = max(p.x_mm for p in quantized)
    max_y = max(p.y_mm for p in quantized)
    plan = PlanGeometry(
        front_chain=[
            PlanPoint(x_mm=_q(p.x_mm), y_mm=_q(p.y_mm)) for p in front
        ],
        modules=[
            PlanModule(
                module_id=m.module_id,
                corners=[
                    PlanPoint(x_mm=_q(c.x_mm), y_mm=_q(c.y_mm))
                    for c in m.corners
                ],
            )
            for m in plan_modules
        ],
        couplings=[
            PlanCoupling(
                coupling_id=c.coupling_id,
                polygon=[
                    PlanPoint(x_mm=_q(p.x_mm), y_mm=_q(p.y_mm))
                    for p in c.polygon
                ],
            )
            for c in plan_couplings
        ],
        min_x_mm=min_x,
        min_y_mm=min_y,
        width_mm=max_x - min_x,
        height_mm=max_y - min_y,
    )
    return plan, issues


def _top_with_module_dims(module: ProductModule) -> ParametricNode:
    tree = module.tree
    if tree.width_mm is not None and tree.width_mm != module.width_mm:
        raise ValueError(f"{module.id}: tree width conflicts with module width")
    if tree.height_mm is not None and tree.height_mm != module.height_mm:
        raise ValueError(f"{module.id}: tree height conflicts with module height")
    return tree.model_copy(
        update={"width_mm": module.width_mm, "height_mm": module.height_mm}
    )


_SLIDING_OPENINGS = {
    BayOpeningType.SLIDING_2L,
    BayOpeningType.SLIDING_3L,
    BayOpeningType.SLIDING_4L,
    BayOpeningType.SLIDING,
}


def _resolved_spec_or_none(node: ParametricNode) -> "OpeningSpec | None":
    """The node's resolved opening spec, or None when it declares none.

    D03: product checks run on the canonical spec so nodes declared via
    `opening`/`leaves` behave identically to legacy `opening_type`."""
    try:
        return resolve_opening_spec(node)
    except ValueError:
        return None


def _node_is_fixed(node: ParametricNode) -> bool:
    spec = _resolved_spec_or_none(node)
    if spec is None:
        return True
    return all(
        leaf.opening.movement is OpeningMovement.FIXED for leaf in spec.leaves
    )


def _node_is_sliding(node: ParametricNode) -> bool:
    spec = _resolved_spec_or_none(node)
    if spec is None:
        return False
    return any(
        leaf.opening.movement is OpeningMovement.SLIDE for leaf in spec.leaves
    )


def _node_opening_label(node: ParametricNode) -> str:
    spec = _resolved_spec_or_none(node)
    if spec is not None:
        return spec_display_name_es(spec)
    return node.opening_type.value if node.opening_type is not None else ""


def _sliding_facts(module: ProductModule) -> list[SlidingLayoutFacts]:
    """Resolved sliding topology per sliding bay — the editor's rail/panel
    inspector facts, independent of whether the BOM evaluated."""
    facts: list[SlidingLayoutFacts] = []

    def _visit(node: ParametricNode) -> None:
        if node.type is NodeType.BAY and _node_is_sliding(node):
            try:
                layout = resolved_sliding_layout(node)
            except ValueError:
                layout = None
            if layout is not None:
                facts.append(
                    SlidingLayoutFacts(
                        bay_id=node.id,
                        tracks=layout.tracks,
                        primary_index=layout.primary_index,
                        panels=[
                            SlidingPanelFacts(
                                slot=panel.slot,
                                kind=panel.kind,
                                track=panel.track,
                                travel=panel_travel(panel, index, len(layout.panels)),
                                travel_inferred=travel_inferred(panel),
                                leaf_id=(
                                    f"{node.id}:L{index + 1}"
                                    if panel.kind is SlidingPanelKind.MOVING
                                    else None
                                ),
                            )
                            for index, panel in enumerate(layout.panels)
                        ],
                    )
                )
        for child in node.children:
            _visit(child)

    _visit(module.tree)
    return facts


def _glass_safety_issues(module_id: str, result: EngineResult) -> list[ProductIssue]:
    """BOM glass findings → one deduplicated issue per (rule, bay, leaf).

    The piece keeps the full GlassSafetyFinding; the issue is the readable
    pointer — a MANDATORY severity escalates to an error so a rule the org
    made mandatory actually blocks, while the default NCh-135 WARNING stays
    advisory."""
    seen: set[tuple[str, str, str]] = set()
    issues: list[ProductIssue] = []
    for glass in result.glasses:
        for finding in glass.safety_findings:
            key = (finding.rule_code, glass.bay_id, glass.leaf_id or "")
            if key in seen:
                continue
            seen.add(key)
            params: dict[str, str] = {
                "rule_code": finding.rule_code,
                "bay_id": glass.bay_id,
                "message": finding.message,
            }
            if glass.leaf_id is not None:
                params["leaf_id"] = glass.leaf_id
            if finding.required_safety is not None:
                params["required_safety"] = finding.required_safety
            if finding.source_ref is not None:
                params["source_ref"] = finding.source_ref
            issues.append(
                ProductIssue(
                    code=IssueCode.GLASS_SAFETY_FINDING.value,
                    severity=(
                        Severity.ERROR
                        if finding.severity == "MANDATORY"
                        else Severity.WARNING
                    ),
                    target=f"module:{module_id}",
                    params=params,
                )
            )
    return issues


def _operable_leaves(tree: ParametricNode) -> tuple[OperableLeaf, ...]:
    """Operable leaves a module's tree declares (D06 extra scope).

    Sliding bays count their MOVING panels; hinged bays count their
    non-FIXED spec leaves. The module's own evaluation already surfaces
    real opening problems — an unresolvable declaration here just counts
    no leaves.
    """
    leaves: list[OperableLeaf] = []

    def _visit(node: ParametricNode) -> None:
        if node.type is NodeType.BAY:
            if _node_is_sliding(node):
                try:
                    layout = resolved_sliding_layout(node)
                except ValueError:
                    layout = None
                if layout is not None:
                    leaves.extend(
                        OperableLeaf(bay_id=node.id, leaf_id=panel.slot)
                        for panel in layout.panels
                        if panel.kind is SlidingPanelKind.MOVING
                    )
            else:
                spec = _resolved_spec_or_none(node)
                if spec is not None:
                    leaves.extend(
                        OperableLeaf(bay_id=node.id, leaf_id=leaf.slot)
                        for leaf in spec.leaves
                        if leaf.opening.movement is not OpeningMovement.FIXED
                    )
        for child in node.children:
            _visit(child)

    _visit(tree)
    return tuple(leaves)


def _module_extra_contexts(
    modules: list[ProductModule],
    claimed_edges: set[tuple[str, EdgeSide]],
    column_index: dict[str, int],
) -> list[ModuleExtraContext]:
    """Extras scope per module: exterior edges are the sides no coupling
    claimed; unit kind comes off the unit's top node (ROOT wraps one)."""
    contexts: list[ModuleExtraContext] = []
    for module in modules:
        top = (
            module.tree.children[0]
            if module.tree.type is NodeType.ROOT and len(module.tree.children) == 1
            else module.tree
        )
        contexts.append(
            ModuleExtraContext(
                module_id=module.id,
                column=column_index.get(module.id, 0),
                width_mm=module.width_mm,
                height_mm=module.height_mm,
                exterior_sides=frozenset(
                    side
                    for side in EdgeSide
                    if (module.id, side) not in claimed_edges
                ),
                operable_leaves=_operable_leaves(module.tree),
                unit_kind=(
                    resolve_unit_kind(top)
                    if isinstance(top, ParametricNode)
                    else UnitKind.WINDOW
                ),
                straight_framed=module.contour is None and module.frameless is None,
            )
        )
    return contexts


def _prefix_result(module_id: str, result: EngineResult) -> EngineResult:
    prefix = f"{module_id}|"

    def bay(bay_id: str | None) -> str | None:
        return f"{prefix}{bay_id}" if bay_id is not None else None

    def leaf(leaf_id: str | None) -> str | None:
        return f"{prefix}{leaf_id}" if leaf_id is not None else None

    return EngineResult(
        profile_cuts=[
            cut.model_copy(
                update={"bay_id": bay(cut.bay_id), "leaf_id": leaf(cut.leaf_id)}
            )
            for cut in result.profile_cuts
        ],
        reinforcements=[
            piece.model_copy(
                update={
                    "bay_id": bay(piece.bay_id),
                    "leaf_id": leaf(piece.leaf_id),
                }
            )
            for piece in result.reinforcements
        ],
        glasses=[
            piece.model_copy(
                update={
                    "bay_id": bay(piece.bay_id),
                    "leaf_id": leaf(piece.leaf_id),
                }
            )
            for piece in result.glasses
        ],
        panels=[
            piece.model_copy(
                update={"bay_id": bay(piece.bay_id), "leaf_id": leaf(piece.leaf_id)}
            )
            for piece in result.panels
        ],
        fittings=[
            piece.model_copy(
                update={"bay_id": bay(piece.bay_id), "leaf_id": leaf(piece.leaf_id)}
            )
            for piece in result.fittings
        ],
        hardware_items=[
            item.model_copy(
                update={
                    "bay_id": bay(item.bay_id),
                    "leaf_id": leaf(item.leaf_id),
                }
            )
            for item in result.hardware_items
        ],
        leaf_weights=[
            weight.model_copy(
                update={
                    "bay_id": bay(weight.bay_id),
                    "leaf_id": leaf(weight.leaf_id),
                }
            )
            for weight in result.leaf_weights
        ],
    )


def _single_region_leaf(tree: ParametricNode) -> ParametricNode | None:
    """The region spec of a contour module: a bare BAY or ROOT wrapping one."""
    top = tree.children[0] if tree.type is NodeType.ROOT and len(tree.children) == 1 else tree
    return top if top.type is NodeType.BAY and not top.children else None


_ANGLE_Q = Decimal("0.1")


def _qa(value: Decimal) -> Decimal:
    """Canonical cut-angle quantum — serializer accepts angles at 0.1° only."""
    return value.quantize(_ANGLE_Q, rounding=ROUND_HALF_UP)


def _is_axis_rect(contour: Contour) -> bool:
    """Four straight axis-aligned edges — the classic glass rectangle."""
    if len(contour.vertices) != 4 or any(contour.bulges):
        return False
    n = 4
    return all(
        contour.vertices[i].x_mm == contour.vertices[(i + 1) % n].x_mm
        or contour.vertices[i].y_mm == contour.vertices[(i + 1) % n].y_mm
        for i in range(n)
    )


def _evaluate_contour_module(
    module: ProductModule,
    params: SystemParams,
    *,
    is_foiled: bool,
    color_selection: ColorSelection | None = None,
) -> tuple[EngineResult | None, list[ProductIssue], GeometryComputation | None]:
    """Evaluate a non-rectangular module: frame follows the contour, one
    inward-offset fill region per module.

    Trapezoid/arch/triangle modules get real member lengths and miter cuts
    (corner interior / 2 — the welded-rect 45° rule generalized), an exact
    glass polygon, and bead cuts per edge. Anything the kernel cannot build
    honestly (split trees, operable leaves, panels, bends without a bending
    authority) is reported, never approximated into a rectangle.
    """
    issues: list[ProductIssue] = []
    target = f"module:{module.id}"
    assert module.contour is not None
    contour = ensure_ccw(module.contour)

    problems = validate_contour(contour)
    if problems:
        issues.append(
            ProductIssue(
                code=IssueCode.CONTOUR_INVALID.value,
                severity=Severity.ERROR,
                target=target,
                params={"reason": "; ".join(problems)},
            )
        )
        return None, issues, None

    leaf = _single_region_leaf(module.tree)
    if leaf is None:
        issues.append(
            ProductIssue(
                code=IssueCode.CONTOUR_SPLITS_UNSUPPORTED.value,
                severity=Severity.ERROR,
                target=target,
            )
        )
        return None, issues, None

    if not _node_is_fixed(leaf):
        issues.append(
            ProductIssue(
                code=IssueCode.CONTOUR_OPENING_UNSUPPORTED.value,
                severity=Severity.WARNING,
                target=target,
                params={"opening": _node_opening_label(leaf)},
            )
        )
        # The frame is still buildable; the operable leaf is not (v1).
        # Emit frame + infill as a fixed region so BOM stays honest about
        # what exists, while the warning keeps the module incomplete.
    if leaf.panel_article_sku is not None:
        issues.append(
            ProductIssue(
                code=IssueCode.CONTOUR_PANEL_UNSUPPORTED.value,
                severity=Severity.WARNING,
                target=target,
                params={"sku": leaf.panel_article_sku},
            )
        )

    frame = params.effective_profile_articles[ProfileRole.FRAME]
    per_end = joint_adjustment_per_end(params, frame)
    n = len(contour.vertices)
    topology_path = f"BAY:{leaf.id}"
    assembly = f"BAY:{leaf.id}:CONTOUR"

    profile_cuts: list[ProfileCut] = []
    reinforcements: list[ReinforcementPiece] = []
    glasses: list[GlassPiece] = []
    trace_members: list[SemanticMemberTraceV1] = []
    trace_infills: list[SemanticInfillTraceV1] = []
    technical_infills: list[InfillTechnicalFacts] = []

    for i in range(n):
        bulge = contour.bulges[i]
        length = contour_edge_length(contour, i) + 2 * per_end
        sagitta = bulge if bulge else None
        cut_length = _q(length)
        angle_left = _qa(interior_angle(contour, i) / 2)
        angle_right = _qa(interior_angle(contour, (i + 1) % n) / 2)
        profile_cuts.append(
            ProfileCut(
                sku=frame.sku,
                role=ProfileRole.FRAME,
                material=frame.material,
                length_mm=cut_length,
                angle_left=angle_left,
                angle_right=angle_right,
                qty=1,
                bay_id=leaf.id,
                sagitta_mm=_q(sagitta) if sagitta is not None else None,
            )
        )
        if sagitta is not None:
            issues.append(
                ProductIssue(
                    code=IssueCode.MEMBER_BENDING_REQUIRED.value,
                    severity=Severity.WARNING,
                    target=target,
                    params={"edge": str(i), "sagitta_mm": str(_q(sagitta))},
                )
            )
        if frame.material is MaterialType.PVC:
            # Same rule as _append_profile: a welded PVC member is reinforced
            # whether or not the catalog resolved the steel article yet — the
            # cutting authority resolves the SKU downstream. A missing
            # reinforcement_gap_mm raises honestly instead of skipping.
            steel_length = reinforcement_cut_length(length, frame, 2)
            if steel_length <= Decimal("0"):
                raise ValueError("Reinforcement cut must be positive")
            reinforcements.append(
                ReinforcementPiece(
                    parent_profile_sku=frame.sku,
                    reinforcement_sku=frame.reinforcement_sku,
                    role=ProfileRole.FRAME,
                    length_mm=_q(steel_length),
                    qty=1,
                    bay_id=leaf.id,
                    sagitta_mm=_q(sagitta) if sagitta is not None else None,
                )
            )

        start = contour.vertices[i]
        end = contour.vertices[(i + 1) % n]
        steel = _q(steel_length) if frame.material is MaterialType.PVC else None
        trace_members.append(
            SemanticMemberTraceV1(
                semantic_member_id=f"{topology_path}/member/E{i}",
                topology_path=topology_path,
                assembly=assembly,
                bay_id=leaf.id,
                leaf_id=None,
                leaf_slot=None,
                role=ProfileRole.FRAME,
                physical_member_slot=f"E{i}",
                workshop_sku=frame.sku,
                material=frame.material,
                cut_length_mm=cut_length,
                angle_left=angle_left,
                angle_right=angle_right,
                axis=(
                    Axis.HORIZONTAL
                    if abs(end.x_mm - start.x_mm) >= abs(end.y_mm - start.y_mm)
                    else Axis.VERTICAL
                ),
                sagitta_mm=_q(sagitta) if sagitta is not None else None,
                placement_domain=PlacementDomain.DIRECT,
                direct_segment=TraceSegmentV1(
                    start=TracePointV1(x_mm=start.x_mm, y_mm=start.y_mm),
                    end=TracePointV1(x_mm=end.x_mm, y_mm=end.y_mm),
                ),
                reinforcement_required=frame.material is MaterialType.PVC,
                reinforcement_sku=(
                    frame.reinforcement_sku
                    if frame.material is MaterialType.PVC
                    else None
                ),
                reinforcement_length_mm=steel,
            )
        )

    # D05: the resolved selection's declared clearance wins over the
    # legacy foil/white pair.
    if color_selection is not None:
        clearance_mm = color_selection.glass_clearance_mm(params)
    else:
        clearance_mm = (
            params.glass_clearance_foil_mm if is_foiled else params.glass_clearance_white_mm
        )
    # Inward offset that lands exactly on the rect-path pocket math:
    # pocket = finished - 2*face + 2*rebate - 2*clearance.
    inset = frame.face_width_mm - rebate_depth(params) + clearance_mm
    try:
        fill = offset_contour(contour, inset)
    except ValueError as error:
        issues.append(
            ProductIssue(
                code=IssueCode.CONTOUR_INVALID.value,
                severity=Severity.ERROR,
                target=target,
                params={"reason": str(error)},
            )
        )
        return None, issues, None

    fill_area_mm2 = contour_area(fill.vertices, fill.bulges)
    # A collapsed offset inverts the pocket (negative shoelace area) or
    # self-intersects — both are structural failures, not a small glass.
    if fill_area_mm2 <= 0 or validate_contour(fill):
        issues.append(
            ProductIssue(
                code=IssueCode.CONTOUR_INVALID.value,
                severity=Severity.ERROR,
                target=target,
                params={"reason": "frame inset collapsed the glass pocket"},
            )
        )
        return None, issues, None

    if leaf.glass_thickness_mm is None or leaf.glass_spec is None:
        raise ValueError(f"contour region {leaf.id} requires glass_thickness_mm and glass_spec")

    thickness_net = derive_net_glass_thickness(leaf.glass_spec)
    area_m2 = (fill_area_mm2 / Decimal("1000000")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    weight_kg = (
        None if thickness_net is None else
        (fill_area_mm2 / Decimal("1000000") * thickness_net * Decimal("2.50")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )
    # Bounds come from the sampled fill boundary, not the vertex box — an
    # arc bulging past its endpoints would otherwise shrink the reported
    # bounding box while `shape` still carried the bigger outline.
    fill_points = contour_points(fill)
    xs = [point.x_mm for point in fill_points]
    ys = [point.y_mm for point in fill_points]
    glass_width = _q(max(xs) - min(xs))
    glass_height = _q(max(ys) - min(ys))
    glass_shape = None if _is_axis_rect(fill) else fill_points
    glasses.append(
        GlassPiece(
            bay_id=leaf.id,
            width_mm=glass_width,
            height_mm=glass_height,
            area_m2=area_m2,
            weight_kg=weight_kg,
            thickness_net_mm=(None if thickness_net is None else
                              thickness_net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            glass_spec=leaf.glass_spec,
            article_sku=leaf.glass_article_sku,
            # An axis-aligned rect fill is the classic rectangle — `shape`
            # stays None so production sheet-nests it like any other pane.
            shape=glass_shape,
        )
    )
    infill_id = f"{topology_path}/infill"
    trace_infills.append(
        SemanticInfillTraceV1(
            semantic_infill_id=infill_id,
            topology_path=topology_path,
            assembly=assembly,
            bay_id=leaf.id,
            leaf_id=None,
            leaf_slot=None,
            kind="GLASS",
            technical_sku=leaf.glass_article_sku or "",
            composition=leaf.glass_spec,
            width_mm=glass_width,
            height_mm=glass_height,
            shape=(
                [TracePointV1(x_mm=point.x_mm, y_mm=point.y_mm) for point in fill_points]
                if glass_shape is not None
                else None
            ),
            placement_domain=PlacementDomain.DIRECT,
            direct_rect=TraceRectV1(
                x_mm=min(xs),
                y_mm=min(ys),
                width_mm=glass_width,
                height_mm=glass_height,
            ),
        )
    )
    technical_infills.append(
        InfillTechnicalFacts(
            bay_id=leaf.id,
            leaf_id=None,
            kind="GLASS",
            thickness_mm=leaf.glass_thickness_mm,
            glass_spec=leaf.glass_spec,
            width_mm=glass_width,
            height_mm=glass_height,
            exact_area_m2=fill_area_mm2 / Decimal("1000000"),
            bead_supported=leaf.glass_thickness_mm in params.glazing_bead_rules,
        )
    )

    # Glazing beads run the fill boundary, one cut per edge.
    rule = resolve_bead_rule(leaf.glass_thickness_mm, params)
    fill_n = len(fill.vertices)
    for i in range(fill_n):
        bulge = fill.bulges[i]
        bead_length = _q(contour_edge_length(fill, i) + rule.cut_add_mm)
        bead_left = _qa(interior_angle(fill, i) / 2)
        bead_right = _qa(interior_angle(fill, (i + 1) % fill_n) / 2)
        profile_cuts.append(
            ProfileCut(
                sku=rule.bead_article.sku,
                role=ProfileRole.GLAZING_BEAD,
                material=rule.bead_article.material,
                length_mm=bead_length,
                angle_left=bead_left,
                angle_right=bead_right,
                qty=1,
                bay_id=leaf.id,
                sagitta_mm=_q(bulge) if bulge else None,
            )
        )
        bstart = fill.vertices[i]
        bend = fill.vertices[(i + 1) % fill_n]
        trace_members.append(
            SemanticMemberTraceV1(
                semantic_member_id=f"{infill_id}/bead-set/E{i}",
                topology_path=topology_path,
                assembly=assembly,
                bay_id=leaf.id,
                leaf_id=None,
                leaf_slot=None,
                role=ProfileRole.GLAZING_BEAD,
                physical_member_slot=f"E{i}",
                workshop_sku=rule.bead_article.sku,
                material=rule.bead_article.material,
                cut_length_mm=bead_length,
                angle_left=bead_left,
                angle_right=bead_right,
                axis=(
                    Axis.HORIZONTAL
                    if abs(bend.x_mm - bstart.x_mm) >= abs(bend.y_mm - bstart.y_mm)
                    else Axis.VERTICAL
                ),
                sagitta_mm=_q(bulge) if bulge else None,
                # The bead's seat IS the fill edge — a contour has no
                # rectangular side to derive it from, so the trace carries
                # the chord directly (arcs stay honest via sagitta_mm).
                placement_domain=PlacementDomain.DIRECT,
                direct_segment=TraceSegmentV1(
                    start=TracePointV1(x_mm=bstart.x_mm, y_mm=bstart.y_mm),
                    end=TracePointV1(x_mm=bend.x_mm, y_mm=bend.y_mm),
                ),
                parent_infill_id=infill_id,
            )
        )
        if bulge:
            issues.append(
                ProductIssue(
                    code=IssueCode.MEMBER_BENDING_REQUIRED.value,
                    severity=Severity.WARNING,
                    target=target,
                    params={"edge": f"bead-{i}", "sagitta_mm": str(_q(bulge))},
                )
            )

    result = EngineResult(
        profile_cuts=profile_cuts,
        reinforcements=reinforcements,
        glasses=glasses,
    )
    computation = GeometryComputation(
        result=result,
        manufacturing_trace=GeometryManufacturingTraceV1(
            nominal_width_mm=module.width_mm,
            nominal_height_mm=module.height_mm,
            members=trace_members,
            leaves=[],
            infills=trace_infills,
        ),
        openings=[
            OpeningTechnicalFacts(
                bay_id=leaf.id,
                width_mm=module.width_mm,
                height_mm=module.height_mm,
            )
        ],
        infills=technical_infills,
        node_dimensions={leaf.id: (module.width_mm, module.height_mm)},
    )
    return result, issues, computation


def _evaluate_frameless_module(
    module: ProductModule,
    *,
    coupler_articles: dict[str, EffectiveProfileArticle],
) -> tuple[EngineResult | None, list[ProductIssue]]:
    """Evaluate a glass-only module (mandate §14): the pane IS the product —
    no fake FRAME/SASH members exist to fit the old model. BOM is the glass
    panel itself plus its real support/fitting concepts: channel runs as
    profile cuts, clamps and declared fittings as counted pieces."""
    issues: list[ProductIssue] = []
    target = f"module:{module.id}"
    assert module.frameless is not None
    spec = module.frameless

    if module.contour is not None:
        issues.append(
            ProductIssue(
                code=IssueCode.FRAMELESS_CONTOUR_UNSUPPORTED.value,
                severity=Severity.ERROR,
                target=target,
            )
        )
        return None, issues

    leaf = _single_region_leaf(module.tree)
    if leaf is None:
        issues.append(
            ProductIssue(
                code=IssueCode.FRAMELESS_SPLITS_UNSUPPORTED.value,
                severity=Severity.ERROR,
                target=target,
            )
        )
        return None, issues

    if not _node_is_fixed(leaf):
        issues.append(
            ProductIssue(
                code=IssueCode.FRAMELESS_OPENING_UNSUPPORTED.value,
                severity=Severity.WARNING,
                target=target,
                params={"opening": _node_opening_label(leaf)},
            )
        )
    if leaf.panel_article_sku is not None:
        issues.append(
            ProductIssue(
                code=IssueCode.FRAMELESS_PANEL_UNSUPPORTED.value,
                severity=Severity.WARNING,
                target=target,
                params={"sku": leaf.panel_article_sku},
            )
        )

    if leaf.glass_thickness_mm is None or leaf.glass_spec is None:
        raise ValueError(
            f"frameless module {module.id} requires glass_thickness_mm and glass_spec"
        )

    profile_cuts: list[ProfileCut] = []
    glasses: list[GlassPiece] = []
    fittings: list[FittingPiece] = []

    thickness_net = derive_net_glass_thickness(leaf.glass_spec)
    pane_area_mm2 = module.width_mm * module.height_mm
    area_m2 = (pane_area_mm2 / Decimal("1000000")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    weight_kg = (
        None if thickness_net is None else
        (pane_area_mm2 / Decimal("1000000") * thickness_net * Decimal("2.50")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )
    exposed = spec.exposed_edges or [
        EdgeSide.TOP,
        EdgeSide.RIGHT,
        EdgeSide.BOTTOM,
        EdgeSide.LEFT,
    ]
    glasses.append(
        GlassPiece(
            bay_id=leaf.id,
            width_mm=_q(module.width_mm),
            height_mm=_q(module.height_mm),
            area_m2=area_m2,
            weight_kg=weight_kg,
            thickness_net_mm=(None if thickness_net is None else
                              thickness_net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            glass_spec=leaf.glass_spec,
            article_sku=leaf.glass_article_sku,
            exposed_edges=[edge.value for edge in exposed],
        )
    )

    for support in spec.supports:
        edge_length = (
            module.width_mm
            if support.edge in (EdgeSide.TOP, EdgeSide.BOTTOM)
            else module.height_mm
        )
        if support.kind is FramelessSupportKind.CHANNEL:
            article = coupler_articles.get(support.article_sku)
            if article is None:
                issues.append(
                    ProductIssue(
                        code=IssueCode.FRAMELESS_ARTICLE_UNKNOWN.value,
                        severity=Severity.WARNING,
                        target=target,
                        params={"sku": support.article_sku},
                    )
                )
                continue
            profile_cuts.append(
                ProfileCut(
                    sku=article.sku,
                    role=ProfileRole.CHANNEL,
                    material=article.material,
                    length_mm=_q(edge_length),
                    angle_left=Decimal("90"),
                    angle_right=Decimal("90"),
                    qty=support.qty,
                    bay_id=leaf.id,
                )
            )
        else:
            fittings.append(
                FittingPiece(
                    kind=FramelessFittingKind.CLAMP.value,
                    sku=support.article_sku,
                    qty=support.qty,
                    bay_id=leaf.id,
                )
            )
    for fitting in spec.fittings:
        fittings.append(
            FittingPiece(
                kind=fitting.kind.value,
                sku=fitting.sku,
                qty=fitting.qty,
                bay_id=leaf.id,
            )
        )

    return (
        EngineResult(
            profile_cuts=profile_cuts,
            reinforcements=[],
            glasses=glasses,
            fittings=fittings,
        ),
        issues,
    )


def contour_module_computation(
    module: ProductModule,
    params: SystemParams,
    *,
    is_foiled: bool = False,
    color_selection: ColorSelection | None = None,
) -> tuple[GeometryComputation | None, list[ProductIssue]]:
    """Documentary-sealing entry for a contour module: the same evaluation
    the BOM path runs, returned as a GeometryComputation whose manufacturing
    trace carries the real contour members, glass polygon and bead sets
    instead of a rectangular approximation."""
    _result, issues, computation = _evaluate_contour_module(
        module, params, is_foiled=is_foiled, color_selection=color_selection
    )
    return computation, issues


_RETAINING_FITTINGS = frozenset(
    {
        FramelessFittingKind.PATCH_FITTING,
        FramelessFittingKind.CLAMP,
        FramelessFittingKind.HINGE,
        FramelessFittingKind.SUPPORT,
    }
)


def frameless_retention_declared(spec: FramelessSpec) -> bool:
    """Whether the frameless spec declares hardware that retains the pane —
    supported edges (channel/clamps) or retaining fittings. A pane with no
    retention at all is not production-ready (inspector R06)."""
    return bool(spec.supports) or any(
        fitting.kind in _RETAINING_FITTINGS for fitting in spec.fittings
    )


def frameless_module_computation(
    module: ProductModule,
    *,
    coupler_articles: dict[str, EffectiveProfileArticle],
) -> tuple[GeometryComputation | None, list[ProductIssue]]:
    """Documentary-sealing entry for a frameless module: the same evaluation
    the BOM path runs, returned as a GeometryComputation whose trace carries
    the pane infill and channel members instead of a framed approximation."""
    result, issues = _evaluate_frameless_module(
        module, coupler_articles=coupler_articles
    )
    if result is None:
        return None, issues
    assert module.frameless is not None
    spec = module.frameless
    leaf = _single_region_leaf(module.tree)
    assert leaf is not None  # evaluation errors out when the leaf is missing
    topology_path = f"BAY:{leaf.id}"
    assembly = f"BAY:{leaf.id}:FRAMELESS"

    trace_members: list[SemanticMemberTraceV1] = []
    for index, support in enumerate(spec.supports):
        if support.kind is not FramelessSupportKind.CHANNEL:
            continue
        article = coupler_articles.get(support.article_sku)
        if article is None:
            continue  # already a frameless_article_unknown warning
        horizontal = support.edge in (EdgeSide.TOP, EdgeSide.BOTTOM)
        cut_length = _q(
            module.width_mm if horizontal else module.height_mm
        )
        # manufacturing origin is top-left, y downward — TOP sits at y=0
        if support.edge is EdgeSide.TOP:
            segment = TraceSegmentV1(
                start=TracePointV1(x_mm=Decimal("0"), y_mm=Decimal("0")),
                end=TracePointV1(x_mm=module.width_mm, y_mm=Decimal("0")),
            )
        elif support.edge is EdgeSide.BOTTOM:
            segment = TraceSegmentV1(
                start=TracePointV1(x_mm=Decimal("0"), y_mm=module.height_mm),
                end=TracePointV1(
                    x_mm=module.width_mm, y_mm=module.height_mm
                ),
            )
        elif support.edge is EdgeSide.LEFT:
            segment = TraceSegmentV1(
                start=TracePointV1(x_mm=Decimal("0"), y_mm=Decimal("0")),
                end=TracePointV1(x_mm=Decimal("0"), y_mm=module.height_mm),
            )
        else:
            segment = TraceSegmentV1(
                start=TracePointV1(x_mm=module.width_mm, y_mm=Decimal("0")),
                end=TracePointV1(
                    x_mm=module.width_mm, y_mm=module.height_mm
                ),
            )
        for unit in range(support.qty):
            trace_members.append(
                SemanticMemberTraceV1(
                    semantic_member_id=(
                        f"{topology_path}/member/S{index}.{unit}"
                    ),
                    topology_path=topology_path,
                    assembly=assembly,
                    bay_id=leaf.id,
                    leaf_id=None,
                    leaf_slot=None,
                    role=ProfileRole.CHANNEL,
                    physical_member_slot=(
                        f"channel-{index}-{support.edge.value.lower()}"
                    ),
                    workshop_sku=article.sku,
                    material=article.material,
                    cut_length_mm=cut_length,
                    angle_left=Decimal("90"),
                    angle_right=Decimal("90"),
                    axis=Axis.HORIZONTAL if horizontal else Axis.VERTICAL,
                    placement_domain=PlacementDomain.DIRECT,
                    direct_segment=segment,
                )
            )

    pane = result.glasses[0]
    infill_id = f"{topology_path}/infill"
    computation = GeometryComputation(
        result=result,
        manufacturing_trace=GeometryManufacturingTraceV1(
            nominal_width_mm=module.width_mm,
            nominal_height_mm=module.height_mm,
            members=trace_members,
            leaves=[],
            infills=[
                SemanticInfillTraceV1(
                    semantic_infill_id=infill_id,
                    topology_path=topology_path,
                    assembly=assembly,
                    bay_id=leaf.id,
                    leaf_id=None,
                    leaf_slot=None,
                    kind="GLASS",
                    technical_sku=leaf.glass_article_sku or "",
                    composition=leaf.glass_spec or "",
                    width_mm=module.width_mm,
                    height_mm=module.height_mm,
                    placement_domain=PlacementDomain.DIRECT,
                    direct_rect=TraceRectV1(
                        x_mm=Decimal("0"),
                        y_mm=Decimal("0"),
                        width_mm=module.width_mm,
                        height_mm=module.height_mm,
                    ),
                )
            ],
        ),
        openings=[
            OpeningTechnicalFacts(
                bay_id=leaf.id,
                width_mm=module.width_mm,
                height_mm=module.height_mm,
            )
        ],
        infills=[
            InfillTechnicalFacts(
                bay_id=leaf.id,
                leaf_id=None,
                kind="GLASS",
                thickness_mm=leaf.glass_thickness_mm or Decimal("0"),
                glass_spec=leaf.glass_spec,
                width_mm=module.width_mm,
                height_mm=module.height_mm,
                exact_area_m2=pane.area_m2,
                bead_supported=frameless_retention_declared(spec),
            )
        ],
        node_dimensions={leaf.id: (module.width_mm, module.height_mm)},
    )
    return computation, issues


def evaluate_product(
    product: ProductModel,
    params: SystemParams,
    *,
    coupler_articles: dict[str, EffectiveProfileArticle] | None = None,
    is_foiled: bool = False,
    color_selection: ColorSelection | None = None,
) -> ProductEvaluation:
    """Evaluate an assembly: plan geometry, per-module geometry, couplers, BOM."""
    assembly = product.assembly
    modules = assembly.modules
    couplings = assembly.couplings
    issues: list[ProductIssue] = []
    coupler_articles = coupler_articles or {}

    if len({module.id for module in modules}) != len(modules) or len(
        {coupling.id for coupling in couplings}
    ) != len(couplings):
        raise ValueError("module and coupling ids must be unique")

    # The modules-1 chain count only constrains positional couplings — their
    # endpoints ARE the chain slots. Explicit-endpoint couplings declare a
    # structured graph (stacked towers, TEE joins) where any count is legal.
    positional = [c for c in couplings if c.modules is None]
    if positional and len(couplings) != len(modules) - 1:
        issues.append(
            ProductIssue(
                code=IssueCode.COUPLINGS_COUNT_MISMATCH.value,
                severity=Severity.ERROR,
                target="assembly",
                params={
                    "modules": str(len(modules)),
                    "couplings": str(len(couplings)),
                },
            )
        )

    plan, plan_issues = _plan_geometry(assembly, params.depth_mm)
    issues.extend(plan_issues)

    module_evals: list[ModuleEvaluation] = []
    aggregated: list[EngineResult] = []
    for module in modules:
        module_issues: list[ProductIssue] = []
        result: EngineResult | None = None
        try:
            if module.frameless is not None:
                result, frameless_issues = _evaluate_frameless_module(
                    module, coupler_articles=coupler_articles
                )
                module_issues.extend(frameless_issues)
            elif module.contour is not None:
                result, contour_issues, _computation = _evaluate_contour_module(
                    module,
                    params,
                    is_foiled=is_foiled,
                    color_selection=color_selection,
                )
                module_issues.extend(contour_issues)
            else:
                result = calculate_geometry(
                    _top_with_module_dims(module),
                    params,
                    is_foiled=is_foiled,
                    color_selection=color_selection,
                )
            if result is not None:
                module_issues.extend(_glass_safety_issues(module.id, result))
                aggregated.append(_prefix_result(module.id, result))
        except NoCompatibleHardwareKit as error:
            # The exception carries the failing envelope (leaf size vs kit
            # limits, or the mass axis) — surface it as a typed issue so the
            # UI names the constraint instead of an opaque geometry failure.
            axis = error.context.get("axis")
            code = (
                IssueCode.HARDWARE_UNDECIDABLE.value
                if axis == "undecidable"
                else IssueCode.HARDWARE_KIT_OVERWEIGHT.value
                if axis == "weight" and "leaf_weight_kg" in error.context
                else IssueCode.HARDWARE_KIT_INCOMPATIBLE.value
                if axis == "size"
                and "leaf_width_mm" in error.context
                and "kit_min_width_mm" in error.context
                else IssueCode.MODULE_GEOMETRY_FAILED.value
            )
            issue_params = dict(error.context)
            if code == IssueCode.MODULE_GEOMETRY_FAILED.value:
                issue_params["reason"] = str(error)
            module_issues.append(
                ProductIssue(
                    code=code,
                    severity=Severity.ERROR,
                    target=f"module:{module.id}",
                    params=issue_params,
                )
            )
        except DomainRejection as error:
            module_issues.append(
                ProductIssue(
                    code=error.code,
                    severity=Severity.ERROR,
                    target=f"module:{module.id}",
                    params={**error.params, "reason": str(error)},
                )
            )
        except HardwareSelectionError as error:
            # D04: a leaf picked a sellable datum the family never declared
            # or a handle height outside its declared range — the issue
            # names the field and the real bounds.
            module_issues.append(
                ProductIssue(
                    code=error.code,
                    severity=Severity.ERROR,
                    target=f"module:{module.id}",
                    params={**error.params, "reason": str(error)},
                )
            )
        except (ValueError, KeyError, NotImplementedError) as error:
            module_issues.append(
                ProductIssue(
                    code=IssueCode.MODULE_GEOMETRY_FAILED.value,
                    severity=Severity.WARNING,
                    target=f"module:{module.id}",
                    params={"reason": str(error)},
                )
            )
        module_evals.append(
            ModuleEvaluation(
                module_id=module.id,
                issues=module_issues,
                result=result,
                sliding=_sliding_facts(module),
            )
        )
        issues.extend(module_issues)

    coupler_cuts: list[ProfileCut] = []
    coupler_reinforcements: list[ReinforcementPiece] = []
    module_by_id = {module.id: module for module in modules}
    claimed_edges: set[tuple[str, EdgeSide]] = set()
    resolved_pairs = _resolved_pairs(modules, couplings)
    stack_root = _resolve_stack_roots(modules, resolved_pairs)
    column_index = {module.id: index for index, module in enumerate(modules)}
    for index, coupling in enumerate(couplings):
        target = f"coupling:{coupling.id}"
        if coupling.kind in (ConnectionKind.TEE, ConnectionKind.CORNER):
            # Declared in the model, honestly not yet manufacturable — a T or
            # framed-corner joint needs machining consequences we don't have.
            issues.append(
                ProductIssue(
                    code=IssueCode.CONNECTION_TYPE_UNSUPPORTED.value,
                    severity=Severity.WARNING,
                    target=target,
                    params={"kind": coupling.kind.value},
                )
            )
            continue
        # Endpoint resolution: explicit ids win; absent endpoints keep the
        # legacy positional binding (module i right to module i+1 left).
        if coupling.modules is not None:
            first = module_by_id.get(coupling.modules[0])
            second = (
                module_by_id.get(coupling.modules[1])
                if len(coupling.modules) > 1
                else None
            )
        elif index < len(modules) - 1:
            first, second = modules[index], modules[index + 1]
        else:
            first = second = None
        if first is None or second is None or first.id == second.id:
            issues.append(
                ProductIssue(
                    code=IssueCode.COUPLER_MODULE_UNKNOWN.value,
                    severity=Severity.WARNING,
                    target=target,
                )
            )
            continue
        if first.contour is not None or second.contour is not None:
            # A contour edge is a shaped boundary — no straight coupler can
            # close the seam until shaped joints have an authority.
            issues.append(
                ProductIssue(
                    code=IssueCode.CONTOUR_COUPLING_UNSUPPORTED.value,
                    severity=Severity.WARNING,
                    target=target,
                )
            )
            continue
        edges = coupling.edges
        if edges is None:
            edges = (
                [EdgeSide.RIGHT, EdgeSide.LEFT]
                if coupling.kind is ConnectionKind.INLINE
                else [EdgeSide.TOP, EdgeSide.BOTTOM]
            )
        if len(edges) != 2:
            issues.append(
                ProductIssue(
                    code=IssueCode.COUPLER_EDGE_INVALID.value,
                    severity=Severity.WARNING,
                    target=target,
                )
            )
            continue
        sides = set(edges)
        valid = (
            sides <= {EdgeSide.LEFT, EdgeSide.RIGHT}
            if coupling.kind is ConnectionKind.INLINE
            else sides <= {EdgeSide.TOP, EdgeSide.BOTTOM}
        )
        if not valid or len(sides) != 2:
            issues.append(
                ProductIssue(
                    code=IssueCode.COUPLER_EDGE_INVALID.value,
                    severity=Severity.WARNING,
                    target=target,
                    params={"kind": coupling.kind.value},
                )
            )
            continue
        # Edge direction on INLINE seams: edges[i] claims a side of
        # modules[i], and the join is only physical when the left column
        # offers its RIGHT and the right column its LEFT. Column order comes
        # from declaration order — a reversed pair otherwise cuts a coupler
        # across the assembly's outer edges. (STACKED direction is defined by
        # the edges themselves, so there is nothing to check there.)
        if coupling.kind is ConnectionKind.INLINE:
            first_is_left = column_index.get(
                stack_root.get(first.id, first.id), -1
            ) < column_index.get(stack_root.get(second.id, second.id), -1)
            expected = (
                (EdgeSide.RIGHT, EdgeSide.LEFT)
                if first_is_left
                else (EdgeSide.LEFT, EdgeSide.RIGHT)
            )
            if tuple(edges) != expected:
                issues.append(
                    ProductIssue(
                        code=IssueCode.COUPLER_EDGE_INVALID.value,
                        severity=Severity.WARNING,
                        target=target,
                        params={"kind": coupling.kind.value},
                    )
                )
                continue
        pair_claims = {(first.id, edges[0]), (second.id, edges[1])}
        if claimed_edges & pair_claims:
            issues.append(
                ProductIssue(
                    code=IssueCode.COUPLER_EDGE_CONFLICT.value,
                    severity=Severity.WARNING,
                    target=target,
                )
            )
            continue
        claimed_edges |= pair_claims
        sku = coupling.coupler_profile_sku
        article = coupler_articles.get(sku) if sku is not None else None
        if sku is None:
            issues.append(
                ProductIssue(
                    code=IssueCode.COUPLER_PROFILE_MISSING.value,
                    severity=Severity.WARNING,
                    target=target,
                )
            )
            continue
        if article is None:
            issues.append(
                ProductIssue(
                    code=IssueCode.COUPLER_PROFILE_UNKNOWN.value,
                    severity=Severity.WARNING,
                    target=target,
                    params={"sku": sku},
                )
            )
            continue
        # P06 — declared angle envelope: the catalog states which joint
        # deflections this coupler physically closes. Compared over
        # |angle_deg| — the same profile mounted mirrored serves the ± case.
        # An undeclared envelope stays UNKNOWN: no check can honestly run.
        if (
            article.coupler_angle_min_deg is not None
            and article.coupler_angle_max_deg is not None
            and not (
                article.coupler_angle_min_deg
                <= abs(coupling.angle_deg)
                <= article.coupler_angle_max_deg
            )
        ):
            issues.append(
                ProductIssue(
                    code=IssueCode.COUPLER_ANGLE_INCOMPATIBLE.value,
                    severity=Severity.WARNING,
                    target=target,
                    params={
                        "sku": article.sku,
                        "angle_deg": str(coupling.angle_deg),
                        "min_deg": str(article.coupler_angle_min_deg),
                        "max_deg": str(article.coupler_angle_max_deg),
                    },
                )
            )
        if coupling.kind is ConnectionKind.INLINE:
            if first.height_mm != second.height_mm:
                issues.append(
                    ProductIssue(
                        code=IssueCode.COUPLER_HEIGHT_MISMATCH.value,
                        severity=Severity.WARNING,
                        target=target,
                        params={
                            "left_mm": str(first.height_mm),
                            "right_mm": str(second.height_mm),
                        },
                    )
                )
                continue
            span = first.height_mm
        else:
            if first.width_mm != second.width_mm:
                issues.append(
                    ProductIssue(
                        code=IssueCode.COUPLER_WIDTH_MISMATCH.value,
                        severity=Severity.WARNING,
                        target=target,
                        params={
                            "below_mm": str(first.width_mm),
                            "above_mm": str(second.width_mm),
                        },
                    )
                )
                continue
            span = first.width_mm
        coupler_cuts.append(
            ProfileCut(
                sku=article.sku,
                role=ProfileRole.COUPLER,
                material=article.material,
                length_mm=span,
                angle_left=Decimal("90.0"),
                angle_right=Decimal("90.0"),
                qty=1,
                bay_id=coupling.id,
            )
        )
        if article.reinforcement_sku:
            steel_length = reinforcement_cut_length(span, article, 0)
            if steel_length <= Decimal("0"):
                issues.append(
                    ProductIssue(
                        code=IssueCode.COUPLER_REINFORCEMENT_NONPOSITIVE.value,
                        severity=Severity.WARNING,
                        target=target,
                        params={"sku": article.sku},
                    )
                )
            else:
                coupler_reinforcements.append(
                    ReinforcementPiece(
                        parent_profile_sku=article.sku,
                        reinforcement_sku=article.reinforcement_sku,
                        role=ProfileRole.COUPLER,
                        length_mm=steel_length,
                        qty=1,
                        bay_id=coupling.id,
                    )
                )

    bom: EngineResult | None = None
    if aggregated or coupler_cuts:
        all_cuts = [cut for r in aggregated for cut in r.profile_cuts] + coupler_cuts
        # Stock-length feasibility: a member longer than the bar its catalog
        # article sells in cannot be produced. Warning, not error — splicing
        # or a made-to-order bar remains a human call, but "Geometría válida"
        # must not stand next to a member no stock length can cut. One issue
        # per distinct (article, length) keeps repeat pieces readable.
        article_by_sku: dict[str, EffectiveProfileArticle] = {
            article.sku: article for article in params.effective_profile_articles.values()
        }
        article_by_sku.update(coupler_articles)
        article_by_sku.update(
            {
                rule.bead_article.sku: rule.bead_article
                for rule in params.glazing_bead_rules.values()
            }
        )
        flagged: set[tuple[str, Decimal]] = set()
        for cut in all_cuts:
            article = article_by_sku.get(cut.sku)
            if article is None or article.commercial_length_mm is None:
                continue
            if cut.length_mm > article.commercial_length_mm and (
                cut.sku,
                cut.length_mm,
            ) not in flagged:
                flagged.add((cut.sku, cut.length_mm))
                issues.append(
                    ProductIssue(
                        code=IssueCode.MEMBER_EXCEEDS_STOCK.value,
                        severity=Severity.WARNING,
                        target=f"piece:{cut.sku}",
                        params={
                            "sku": cut.sku,
                            "length_mm": str(cut.length_mm),
                            "stock_mm": str(article.commercial_length_mm),
                        },
                    )
                )
        extras_eval = evaluate_position_extras(
            product.extras,
            params.extra_articles,
            _module_extra_contexts(modules, claimed_edges, column_index),
            system_family=params.system_family,
        )
        bom = EngineResult(
            profile_cuts=[
                cut for r in aggregated for cut in r.profile_cuts
            ]
            + coupler_cuts
            + extras_eval.cuts,
            reinforcements=[
                piece for r in aggregated for piece in r.reinforcements
            ]
            + coupler_reinforcements,
            glasses=[piece for r in aggregated for piece in r.glasses],
            panels=[piece for r in aggregated for piece in r.panels],
            fittings=[piece for r in aggregated for piece in r.fittings]
            + extras_eval.fittings,
            hardware_items=[
                item for r in aggregated for item in r.hardware_items
            ],
            leaf_weights=[
                weight for r in aggregated for weight in r.leaf_weights
            ],
            extra_lines=extras_eval.lines,
        )
        if color_selection is not None:
            # D05: stamp the finish pair's identity + declared surcharges
            # onto the merged BOM — the assembly's plan area is the M²
            # basis (per-module totals are already inside it).
            bom.finish_key = color_selection.stock_key()
            bom.finish_label = color_selection.display_name()
            bom.finish_class = color_selection.finish_class
            bom.color_surcharges = apply_color_surcharges(
                color_selection,
                bom,
                area_m2=(plan.width_mm * plan.height_mm) / Decimal("1000000"),
            )
        extra_suggestions = extras_eval.suggestions
    else:
        extra_suggestions = []

    if any(issue.severity is Severity.ERROR for issue in issues):
        status = ProductStatus.INVALID
    elif issues:
        status = ProductStatus.MANUFACTURING_INCOMPLETE
    else:
        status = ProductStatus.VALID

    return ProductEvaluation(
        status=status,
        issues=issues,
        plan=plan,
        modules=module_evals,
        bom=bom,
        extra_suggestions=extra_suggestions,
    )


# --- Typed commands -------------------------------------------------------
# The only way the UI (and later the agent) mutates a product. Each command
# returns a new ProductModel; undo/redo is a stack of before/after states.


def _bay_node(
    opening: BayOpeningType,
    node_id: str,
    *,
    glass_thickness_mm: Decimal,
    glass_spec: str,
) -> ParametricNode:
    return ParametricNode(
        id=node_id,
        type=NodeType.BAY,
        opening_type=opening,
        glass_thickness_mm=glass_thickness_mm,
        glass_spec=glass_spec,
    )


def make_single_unit(
    *,
    width_mm: Decimal,
    height_mm: Decimal,
    opening: BayOpeningType = BayOpeningType.FIXED,
    glass_thickness_mm: Decimal,
    glass_spec: str,
) -> ProductModel:
    return ProductModel(
        version="product-v2",
        assembly=CoupledAssembly(
            modules=[
                ProductModule(
                    id="m1",
                    width_mm=width_mm,
                    height_mm=height_mm,
                    tree=_bay_node(
                        opening,
                        "m1",
                        glass_thickness_mm=glass_thickness_mm,
                        glass_spec=glass_spec,
                    ),
                )
            ],
            couplings=[],
        ),
    )


def make_bow_assembly(
    *,
    module_count: int,
    width_mm: Decimal,
    height_mm: Decimal,
    angle_deg: Decimal,
    opening: BayOpeningType = BayOpeningType.FIXED,
    glass_thickness_mm: Decimal,
    glass_spec: str,
) -> ProductModel:
    if module_count < 2:
        raise ValueError("A bow assembly requires at least two modules")
    share = (width_mm / module_count).quantize(QUANTUM_MM, rounding=ROUND_HALF_UP)
    modules = [
        ProductModule(
            id=f"m{index}",
            width_mm=share,
            height_mm=height_mm,
            tree=_bay_node(
                opening,
                f"m{index}",
                glass_thickness_mm=glass_thickness_mm,
                glass_spec=glass_spec,
            ),
        )
        for index in range(1, module_count)
    ]
    modules.append(
        ProductModule(
            id=f"m{module_count}",
            width_mm=width_mm - share * (module_count - 1),
            height_mm=height_mm,
            tree=_bay_node(
                opening,
                f"m{module_count}",
                glass_thickness_mm=glass_thickness_mm,
                glass_spec=glass_spec,
            ),
        )
    )
    couplings = [
        CouplingDef(id=f"c{index}", angle_deg=angle_deg)
        for index in range(1, module_count)
    ]
    return ProductModel(
        version="product-v2",
        assembly=CoupledAssembly(modules=modules, couplings=couplings),
    )


def _replace_module(
    product: ProductModel, module_id: str, module: ProductModule
) -> ProductModel:
    modules = [
        module if existing.id == module_id else existing
        for existing in product.assembly.modules
    ]
    return product.model_copy(
        update={"assembly": product.assembly.model_copy(update={"modules": modules})}
    )


def _replace_coupling(
    product: ProductModel, coupling_id: str, coupling: CouplingDef
) -> ProductModel:
    couplings = [
        coupling if existing.id == coupling_id else existing
        for existing in product.assembly.couplings
    ]
    return product.model_copy(
        update={
            "assembly": product.assembly.model_copy(
                update={"couplings": couplings}
            )
        }
    )


def set_module_count(product: ProductModel, module_count: int) -> ProductModel:
    modules = product.assembly.modules
    couplings = product.assembly.couplings
    current = len(modules)
    if module_count < 1:
        raise ValueError("An assembly requires at least one module")
    if module_count == current:
        return product
    if module_count < current:
        return product.model_copy(
            update={
                "assembly": CoupledAssembly(
                    modules=modules[:module_count],
                    couplings=couplings[: module_count - 1],
                )
            }
        )
    last = modules[-1]
    new_modules = list(modules)
    new_couplings = list(couplings)
    default_angle = couplings[-1].angle_deg if couplings else Decimal("15")
    for index in range(current + 1, module_count + 1):
        new_couplings.append(
            CouplingDef(
                id=f"c{index - 1}",
                angle_deg=default_angle,
                coupler_profile_sku=couplings[-1].coupler_profile_sku
                if couplings
                else None,
            )
        )
        new_modules.append(
            ProductModule(
                id=f"m{index}",
                width_mm=last.width_mm,
                height_mm=last.height_mm,
                tree=last.tree,
            )
        )
    return product.model_copy(
        update={
            "assembly": CoupledAssembly(
                modules=new_modules, couplings=new_couplings
            )
        }
    )


def set_module_width(
    product: ProductModel, module_id: str, width_mm: Decimal
) -> ProductModel:
    module = next(m for m in product.assembly.modules if m.id == module_id)
    return _replace_module(
        product, module_id, module.model_copy(update={"width_mm": width_mm})
    )


def set_module_height(
    product: ProductModel, module_id: str, height_mm: Decimal
) -> ProductModel:
    module = next(m for m in product.assembly.modules if m.id == module_id)
    return _replace_module(
        product, module_id, module.model_copy(update={"height_mm": height_mm})
    )


def equalize_module_widths(product: ProductModel) -> ProductModel:
    modules = product.assembly.modules
    total = sum((m.width_mm for m in modules), Decimal("0"))
    share = (total / len(modules)).quantize(QUANTUM_MM, rounding=ROUND_HALF_UP)
    new_modules = [
        m.model_copy(update={"width_mm": share}) for m in modules[:-1]
    ]
    new_modules.append(
        modules[-1].model_copy(
            update={"width_mm": total - share * (len(modules) - 1)}
        )
    )
    return product.model_copy(
        update={
            "assembly": product.assembly.model_copy(
                update={"modules": new_modules}
            )
        }
    )


def set_coupling_angle(
    product: ProductModel, coupling_id: str, angle_deg: Decimal
) -> ProductModel:
    coupling = next(
        c for c in product.assembly.couplings if c.id == coupling_id
    )
    return _replace_coupling(
        product, coupling_id, coupling.model_copy(update={"angle_deg": angle_deg})
    )


def equalize_coupling_angles(
    product: ProductModel, angle_deg: Decimal | None = None
) -> ProductModel:
    couplings = product.assembly.couplings
    if not couplings:
        return product
    angle = angle_deg if angle_deg is not None else couplings[0].angle_deg
    return product.model_copy(
        update={
            "assembly": product.assembly.model_copy(
                update={
                    "couplings": [
                        c.model_copy(update={"angle_deg": angle})
                        for c in couplings
                    ]
                }
            )
        }
    )


def set_coupler_sku(
    product: ProductModel, coupling_id: str, sku: str | None
) -> ProductModel:
    coupling = next(
        c for c in product.assembly.couplings if c.id == coupling_id
    )
    return _replace_coupling(
        product,
        coupling_id,
        coupling.model_copy(update={"coupler_profile_sku": sku}),
    )


def _with_opening(node: ParametricNode, opening: BayOpeningType) -> ParametricNode:
    if node.type is NodeType.BAY:
        return node.model_copy(update={"opening_type": opening})
    return node.model_copy(
        update={
            "children": [_with_opening(child, opening) for child in node.children]
        }
    )


def set_module_opening(
    product: ProductModel, module_id: str, opening: BayOpeningType
) -> ProductModel:
    module = next(m for m in product.assembly.modules if m.id == module_id)
    tree = module.tree
    if tree.type is NodeType.ROOT and len(tree.children) == 1:
        tree = tree.model_copy(
            update={"children": [_with_opening(tree.children[0], opening)]}
        )
    else:
        tree = _with_opening(tree, opening)
    return _replace_module(
        product, module_id, module.model_copy(update={"tree": tree})
    )


def set_module_tree(
    product: ProductModel, module_id: str, tree: ParametricNode
) -> ProductModel:
    module = next(m for m in product.assembly.modules if m.id == module_id)
    return _replace_module(
        product, module_id, module.model_copy(update={"tree": tree})
    )


# --- Queries --------------------------------------------------------------


def module_ids(product: ProductModel) -> list[str]:
    return [m.id for m in product.assembly.modules]


def coupling_ids(product: ProductModel) -> list[str]:
    return [c.id for c in product.assembly.couplings]


def nominal_width_mm(product: ProductModel) -> Decimal:
    return elevation_envelope(product.assembly)[0]


def nominal_height_mm(product: ProductModel) -> Decimal:
    return elevation_envelope(product.assembly)[1]
