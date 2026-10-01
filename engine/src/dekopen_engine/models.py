"""Typed, serializable contracts for Dekopen's pure calculation engine."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EngineModel(BaseModel):
    """Strict shared configuration for deterministic engine values."""

    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class MaterialType(str, Enum):
    PVC = "PVC"
    ALUMINIUM = "ALUMINIUM"


class RailType(str, Enum):
    DUAL = "dual"
    MONO = "mono"


class ProfileRole(str, Enum):
    FRAME = "FRAME"
    SASH = "SASH"
    MULLION_V = "MULLION_V"
    MULLION_H = "MULLION_H"
    INVERSOR = "INVERSOR"
    GLAZING_BEAD = "GLAZING_BEAD"
    COUPLER = "COUPLER"
    ADDITIONAL = "ADDITIONAL"
    THRESHOLD = "THRESHOLD"
    # Continuous edge channel seating a frameless glass pane (mandate §14).
    CHANNEL = "CHANNEL"


class NodeType(str, Enum):
    ROOT = "ROOT"
    SPLIT_H = "SPLIT_H"
    SPLIT_V = "SPLIT_V"
    BAY = "BAY"


class BayOpeningType(str, Enum):
    FIXED = "FIXED"
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    TILT_TURN_LEFT = "TILT_TURN_LEFT"
    TILT_TURN_RIGHT = "TILT_TURN_RIGHT"
    SLIDING_2L = "SLIDING_2L"
    SLIDING_3L = "SLIDING_3L"
    SLIDING_4L = "SLIDING_4L"
    # Layout-driven sliding unit: the panel/track topology lives in
    # `sliding_layout`, so arbitrary X/O arrangements need no enum values.
    SLIDING = "SLIDING"
    AWNING = "AWNING"
    DOOR_ENTRY = "DOOR_ENTRY"
    DOOR_DOUBLE = "DOOR_DOUBLE"


class SlidingPanelKind(str, Enum):
    MOVING = "MOVING"  # rides a rail — a sliding sash leaf
    FIXED = "FIXED"  # glazed in-frame — an "O" panel


class SlidingPanel(EngineModel):
    """One slot of a sliding unit, ordered left→right in elevation."""

    slot: str
    kind: SlidingPanelKind
    # 0-based rail index. Required on MOVING panels, must be null on FIXED —
    # a fixed pane has no rail. Two adjacent MOVING panels may not share a
    # track (they would collide before overlapping).
    track: int | None = None


class SlidingLayout(EngineModel):
    """Track topology of a sliding bay (mandate §12).

    `tracks` is how many of the frame's rails the layout occupies and must
    not exceed the system profile's rail capacity. `panels` lists every
    slot left→right; adjacent slots overlap by the system's central
    overlap. X/O notation: MOVING=X, FIXED=O — e.g. O/X/X/O is
    panels [FIXED, MOVING@0, MOVING@1, FIXED] on 2 tracks.
    """

    tracks: int = Field(ge=1)
    panels: list[SlidingPanel] = Field(min_length=1)


class PlanPoint(EngineModel):
    x_mm: Decimal
    y_mm: Decimal


class GlassPiece(EngineModel):
    bay_id: str
    leaf_id: str | None = None
    width_mm: Decimal
    height_mm: Decimal
    # Boundary polygon for non-rectangular pieces (sampled at arc chords).
    # When set, width/height are the bounding box only — the piece is NOT
    # a rectangle and rect-only consumers (2D sheet nesting) must report
    # it as unnested rather than silently cutting a bounding rectangle.
    shape: list[PlanPoint] | None = None
    area_m2: Decimal
    # UNKNOWN is first-class: a spec the composition authority cannot parse
    # must not quietly borrow the package thickness and fabricate a mass.
    weight_kg: Decimal | None
    thickness_net_mm: Decimal | None
    # Composition (e.g. "4-16-4") and the supplier article the piece was
    # resolved against — None on results sealed before the fields existed.
    glass_spec: str | None = None
    article_sku: str | None = None
    # Frameless panes declare which edges are exposed glass (mandate §14) —
    # polishing authority consumes this as its suggested preselection; a
    # framed pane leaves it None.
    exposed_edges: list[str] | None = None


HARDWARE_COMPONENT_CATEGORIES = (
    "HANDLE", "HINGE", "LOCK", "ROLLER", "CONNECTOR", "DRAINAGE", "GASKET",
    "SEAL", "SCREW", "CONSUMABLE", "FITTING", "SUPPORT", "CHANNEL", "OTHER",
)

HardwareComponentCategory = Literal[
    "HANDLE", "HINGE", "LOCK", "ROLLER", "CONNECTOR", "DRAINAGE", "GASKET",
    "SEAL", "SCREW", "CONSUMABLE", "FITTING", "SUPPORT", "CHANNEL", "OTHER",
]


class HardwareComponent(EngineModel):
    sku: str
    name: str
    qty: Decimal = Field(gt=Decimal("0"))
    unit: str
    # Declared component kind — the catalog states what each kit line IS so
    # production can distinguish handles, hinges, locks, rollers, seals,
    # drainage and consumables instead of guessing from a name. Contents
    # sealed before the field existed decode as OTHER (mandate §9).
    category: HardwareComponentCategory = "OTHER"


class HardwareItem(EngineModel):
    kit_sku: str
    name: str
    qty: int = 1
    unit: Literal["kit"] = "kit"
    bay_id: str
    leaf_id: str | None = None
    contents: list[HardwareComponent] = Field(default_factory=list)


class HardwareKitRule(EngineModel):
    sku: str
    name: str
    opening_type: str
    min_leaf_width_mm: Decimal
    max_leaf_width_mm: Decimal
    min_leaf_height_mm: Decimal
    max_leaf_height_mm: Decimal
    max_leaf_weight_kg: Decimal
    rail_type: RailType = RailType.DUAL
    carriages_qty: int = 2
    stay_arms_qty: int = 1
    contents: list[HardwareComponent] = Field(default_factory=list)
    weight_kg: Decimal | None = None
    carriage_capacity_kg: Decimal | None = None


class SectionPoint(EngineModel):
    """One vertex of a catalog section polygon, profile-local mm."""

    x_mm: Decimal
    y_mm: Decimal


class SectionAxis(EngineModel):
    """A named reference axis through the section (glazing, web, fixing)."""

    name: str
    y_mm: Decimal


def _segments_properly_intersect(
    a1: tuple[Decimal, Decimal],
    a2: tuple[Decimal, Decimal],
    b1: tuple[Decimal, Decimal],
    b2: tuple[Decimal, Decimal],
) -> bool:
    """Proper crossing test — segments share no endpoint and cross in their
    interiors. Touches/collinear overlaps at a shared vertex are the polygon's
    normal edge adjacency, not a self-intersection."""

    def orient(p: tuple[Decimal, Decimal], q: tuple[Decimal, Decimal], r: tuple[Decimal, Decimal]) -> Decimal:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1 = orient(b1, b2, a1)
    d2 = orient(b1, b2, a2)
    d3 = orient(a1, a2, b1)
    d4 = orient(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def polygon_self_intersects(points: list[tuple[Decimal, Decimal]]) -> bool:
    """True when any two non-adjacent edges of the closed polygon properly
    cross. Adjacent edges share a vertex by construction and are skipped."""
    count = len(points)
    for i in range(count):
        a1, a2 = points[i], points[(i + 1) % count]
        for j in range(i + 1, count):
            # Adjacent edges (incl. the last-first wrap pair) share an endpoint.
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            b1, b2 = points[j], points[(j + 1) % count]
            if _segments_properly_intersect(a1, a2, b1, b2):
                return True
    return False


class ProfileSection(EngineModel):
    """Simplified technical cross-section of a catalog profile (mandate §15).

    The polygon is the cross-section across the face: x spans the face width,
    y runs the depth direction (0 = exterior face). `POLYGON` is a declared
    simplified section; `DXF_REFERENCE` says the shape was taken from a real
    manufacturer drawing (`drawing_ref` points at it). When `section` is
    absent the renderer falls back to an approximate box — a visibly
    different, explicitly approximate state, never a fake declaration."""

    source: Literal["POLYGON", "DXF_REFERENCE"]
    polygon: list[SectionPoint] = Field(min_length=3)
    depth_mm: Decimal = Field(gt=0)
    axes: list[SectionAxis] = Field(default_factory=list)
    drawing_ref: str | None = None
    # Declared interpretation facts (mandate §8): which polygon edge faces the
    # building exterior, and where the declared (0,0) anchor sits in polygon
    # space. They tell renderers how to orient the drawing — they never feed
    # fabrication math.
    orientation: Literal[
        "EXTERIOR_DOWN", "EXTERIOR_UP", "EXTERIOR_LEFT", "EXTERIOR_RIGHT"
    ] = "EXTERIOR_DOWN"
    local_origin: Literal[
        "TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT", "CENTROID"
    ] = "TOP_LEFT"

    @model_validator(mode="after")
    def _section_is_real(self) -> "ProfileSection":
        points = [(point.x_mm, point.y_mm) for point in self.polygon]
        if len(set(points)) != len(points):
            raise ValueError("section polygon repeats vertices")
        area = Decimal(0)
        for index, (x1, y1) in enumerate(points):
            x2, y2 = points[(index + 1) % len(points)]
            area += x1 * y2 - x2 * y1
        if area == 0:
            raise ValueError("section polygon encloses no area")
        if polygon_self_intersects(points):
            raise ValueError("section polygon self-intersects")
        if self.source == "DXF_REFERENCE" and not (self.drawing_ref or "").strip():
            raise ValueError("DXF_REFERENCE section needs a drawing_ref")
        return self


class EffectiveProfileArticle(EngineModel):
    sku: str
    role: ProfileRole
    material: MaterialType
    face_width_mm: Decimal
    section: ProfileSection | None = None
    # UNKNOWN (None) is a first-class state — a catalog that never stated a
    # welding loss or reinforcement gap must not gain an invented one; the
    # consumers that need it (PVC weld math, steel reinforcement cuts) raise
    # honestly when it is exercised.
    welding_loss_mm: Decimal | None
    reinforcement_gap_mm: Decimal | None
    weight_kg_m: Decimal | None
    steel_weight_kg_m: Decimal | None
    reinforcement_sku: str | None = None
    # Bar length the article sells in — None means the catalog never
    # declared one and no stock-length check can run (UNKNOWN, not infinite).
    commercial_length_mm: Decimal | None = None


class GlazingBeadRule(EngineModel):
    glass_thickness_mm: Decimal
    bead_article: EffectiveProfileArticle
    bead_width_mm: Decimal
    gasket_interior_mm: Decimal
    gasket_exterior_mm: Decimal
    cut_add_mm: Decimal


class PanelRule(EngineModel):
    sku: str
    name: str
    kind: Literal["SANDWICH_PANEL"]
    thickness_mm: Decimal
    weight_kg_m2: Decimal | None


class PanelPiece(EngineModel):
    sku: str
    name: str
    bay_id: str
    leaf_id: str | None = None
    width_mm: Decimal
    height_mm: Decimal
    area_m2: Decimal
    weight_kg: Decimal | None


class LeafWeight(EngineModel):
    bay_id: str
    leaf_id: str | None = None
    # Any component the catalog does not declare stays UNKNOWN (None); the
    # total is only present when every component resolved. Hardware
    # compatibility is never certified on a fabricated mass.
    pvc_weight_kg: Decimal | None
    steel_weight_kg: Decimal | None
    infill_weight_kg: Decimal | None
    hardware_weight_kg: Decimal | None
    total_weight_kg: Decimal | None
    weight_unknown_reasons: list[str] = Field(default_factory=list)


class SystemParams(EngineModel):
    system_code: str
    depth_mm: Decimal
    material: MaterialType = MaterialType.PVC
    effective_profile_articles: dict[ProfileRole, EffectiveProfileArticle]
    glazing_bead_rules: dict[Decimal, GlazingBeadRule]
    # Fabrication data the catalog must declare — the engine has no invented
    # constants for the rebate bite or the mullion end-milling overlap.
    rebate_depth_mm: Decimal | None = None
    end_milling_overlap_mm: Decimal | None = None
    sash_overlap_mm: Decimal = Decimal("8.00")
    glass_clearance_white_mm: Decimal = Decimal("3.00")
    glass_clearance_foil_mm: Decimal = Decimal("5.00")
    pulley_height_mm: Decimal = Decimal("12.00")
    central_overlap_mm: Decimal = Decimal("35.00")
    sliding_lateral_clearance_mm: Decimal = Decimal("0.00")
    sliding_end_add_mm: Decimal = Decimal("6.00")
    corner_bracket_loss_mm: Decimal = Decimal("0.00")
    hook_depth_mm: Decimal = Decimal("0.00")
    door_threshold_mm: Decimal = Decimal("30.00")
    door_bottom_clearance_mm: Decimal = Decimal("20.00")
    rail_type: RailType = RailType.DUAL
    # Physical rails the frame profile provides. None = derive from
    # rail_type (MONO=1, DUAL=2); a catalog with a triple-rail profile
    # declares it explicitly — layouts may never exceed this capacity.
    rail_count: int | None = None
    available_hardware_kits: list[HardwareKitRule] = Field(default_factory=list)
    # Finishes the series actually sells — the estimator picks only declared
    # ones; every non-WHITE finish consumes the foil clearances.
    finishes: tuple[str, ...] = ("WHITE",)
    sliding_glazing_deduction_width_mm: Decimal
    sliding_glazing_deduction_height_mm: Decimal
    door_leaf_side_clearance_mm: Decimal
    available_panel_rules: dict[str, PanelRule] = Field(default_factory=dict)


class ParametricNode(EngineModel):
    id: str
    type: NodeType
    width_mm: Decimal | None = None
    height_mm: Decimal | None = None
    split_offset_mm: Decimal | None = None
    mullion_profile_sku: str | None = None
    children: list[ParametricNode] = Field(default_factory=list)
    opening_type: BayOpeningType | None = None
    glass_thickness_mm: Decimal | None = None
    glass_spec: str | None = None
    glass_article_sku: str | None = None
    panel_article_sku: str | None = None
    hardware_set_sku: str | None = None
    handle_height_mm: Decimal | None = None
    # Declared hinge side of a DOOR_ENTRY leaf (DIN convention: LEFT =
    # hinges on the left, handle on the right). Doors carry no side in
    # their opening_type, so handedness must be declared — manufacturing
    # refuses to mount a handle on an undeclared door rather than assume.
    door_handedness: Literal["LEFT", "RIGHT"] | None = None
    # Sliding panel topology (mandate §12). Present on a sliding BAY it
    # fully defines the unit — slots, moving/fixed kind, rail assignment.
    # Absent, the SLIDING_*L presets map to canonical layouts.
    sliding_layout: SlidingLayout | None = None


class ProfileCut(EngineModel):
    sku: str
    role: ProfileRole
    material: MaterialType
    length_mm: Decimal
    angle_left: Decimal
    angle_right: Decimal
    qty: int
    bay_id: str | None = None
    leaf_id: str | None = None
    # Non-null marks a curved member: length_mm is the arc length and the
    # cut requires bending authority — without one it must surface as a
    # manufacturing-incomplete piece, never a straight cut of that length.
    sagitta_mm: Decimal | None = None


class FittingPiece(EngineModel):
    """A counted fitting — patch fitting, clamp, hinge, lock, connector,
    seal or point support (mandate §14 frameless domain). Unit pieces, not
    cut lengths; compatibility/mounting intelligence is the §22 concern."""

    kind: str
    sku: str
    qty: int = Field(gt=0)
    bay_id: str | None = None
    leaf_id: str | None = None


class ReinforcementPiece(EngineModel):
    parent_profile_sku: str
    reinforcement_sku: str | None = None
    role: ProfileRole
    length_mm: Decimal
    qty: int
    bay_id: str | None = None
    leaf_id: str | None = None
    # Curved reinforcement follows its parent member's arc.
    sagitta_mm: Decimal | None = None


class EngineResult(EngineModel):
    profile_cuts: list[ProfileCut]
    reinforcements: list[ReinforcementPiece]
    glasses: list[GlassPiece]
    panels: list[PanelPiece] = Field(default_factory=list)
    fittings: list[FittingPiece] = Field(default_factory=list)
    hardware_items: list[HardwareItem] = Field(default_factory=list)
    leaf_weights: list[LeafWeight] = Field(default_factory=list)
