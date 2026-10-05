"""Typed, serializable contracts for Dekopen's pure calculation engine."""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from enum import Enum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from dekopen_engine.engine_base import EngineModel as EngineModel  # noqa: F401
from dekopen_engine.glass_composition import (
    GlassComposition as GlassComposition,  # noqa: F401  (re-export)
)


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
    # Sliding leaf stiles/rails — a dedicated sash article when the sliding
    # series does not reuse the casement sash profile.
    SLIDING_SASH = "SLIDING_SASH"
    # Meeting-stile (encuentro) profile on sliding leaves.
    INTERLOCK = "INTERLOCK"
    # Bottom rail/guide the sliding frame separates from its FRAME member.
    RAIL = "RAIL"
    # Entry-door leaf profile — heavier than a window sash.
    DOOR_SASH = "DOOR_SASH"
    # Ancillary members catalogued as cut lengths (finishing catalogue — D06).
    FRAME_EXTENSION = "FRAME_EXTENSION"
    SILL = "SILL"
    COVER_TRIM = "COVER_TRIM"
    SKIRT = "SKIRT"


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


class SystemFamily(str, Enum):
    """Fabrication family a profile system belongs to (D01).

    The family decides which opening typologies the system can honestly
    fabricate — the engine rejects an incompatible typology instead of
    silently cutting a sliding leaf out of a casement series.
    """

    CASEMENT = "CASEMENT"  # ventana/puerta practicable y oscilobatiente
    SLIDING = "SLIDING"  # corredera
    LIFT_SLIDE = "LIFT_SLIDE"  # corredera elevable
    DOOR = "DOOR"  # puerta de entrada
    FACADE_FIXED = "FACADE_FIXED"  # fijo fachada


_SLIDING_OPENINGS = frozenset(
    {
        BayOpeningType.SLIDING_2L,
        BayOpeningType.SLIDING_3L,
        BayOpeningType.SLIDING_4L,
        BayOpeningType.SLIDING,
    }
)

# Typologies each fabrication family can honestly cut (D01). Every family
# keeps FIXED — a fixed lite in the family's frame is always fabricable;
# operable leaves belong only to the family that physically drives them.
FAMILY_OPENINGS: dict[SystemFamily, frozenset[BayOpeningType]] = {
    SystemFamily.CASEMENT: frozenset(
        {
            BayOpeningType.FIXED,
            BayOpeningType.TURN_LEFT,
            BayOpeningType.TURN_RIGHT,
            BayOpeningType.TILT_TURN_LEFT,
            BayOpeningType.TILT_TURN_RIGHT,
            BayOpeningType.AWNING,
            # Casement series sell hinged door leaves (balcony/entry) — the
            # leaf profile is the dedicated DOOR_SASH when the catalog
            # carries one, else the standard sash.
            BayOpeningType.DOOR_ENTRY,
            BayOpeningType.DOOR_DOUBLE,
        }
    ),
    SystemFamily.SLIDING: frozenset({BayOpeningType.FIXED}) | _SLIDING_OPENINGS,
    SystemFamily.LIFT_SLIDE: frozenset({BayOpeningType.FIXED}) | _SLIDING_OPENINGS,
    SystemFamily.DOOR: frozenset(
        {BayOpeningType.FIXED, BayOpeningType.DOOR_ENTRY, BayOpeningType.DOOR_DOUBLE}
    ),
    SystemFamily.FACADE_FIXED: frozenset({BayOpeningType.FIXED}),
}


def openings_for_family(family: SystemFamily) -> frozenset[BayOpeningType]:
    return FAMILY_OPENINGS[family]


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


class GlassSurchargeSelection(EngineModel):
    """A per-piece glass extra declared on the design node (D02).

    - ``EDGE_POLISH``: ``edges`` lists the polished sides (top/right/
      bottom/left); no edges means every edge the piece exposes.
    - ``DRILL``: ``count`` perforations.
    - ``PALILLAJE`` (georgian bars): ``columns`` × ``rows`` grid inside the
      IGU; crossings = columns·rows. ``count`` overrides when the supplier
      prices a fixed qty."""

    kind: Literal["EDGE_POLISH", "DRILL", "PALILLAJE"]
    edges: list[Literal["top", "right", "bottom", "left"]] | None = None
    count: int | None = None
    columns: int | None = None
    rows: int | None = None


class GlassOptions(EngineModel):
    """Per-bay glass extras the designer declared (tree payload, D02)."""

    surcharges: list[GlassSurchargeSelection] = []


class GlassSafetyRule(EngineModel):
    """One situational glazing-safety rule row (NCh 135 family, D02).

    Every predicate field is optional and narrows where the rule applies.
    ``severity`` is the org's call: WARNING advises, MANDATORY blocks —
    safety rules never block by default. ``source_ref`` cites the norm the
    row claims to implement; seeded examples are marked synthetic pending
    technical review."""

    code: str
    title: str
    message: str | None = None
    applies_openings: list[str] | None = None
    # Pane bottom edge within this distance of the module base — the
    # "glazing below 800 mm of finished floor" family of rules.
    sill_below_mm: Decimal | None = None
    min_area_m2: Decimal | None = None
    requires_door: bool | None = None
    requires_adjacent_door: bool | None = None
    required_safety: Literal[
        "TEMPERED", "LAMINATED", "SAFETY_GLASS",
        "SAFETY_CLASS_A", "SAFETY_CLASS_B", "SAFETY_CLASS_C",
    ]
    severity: Literal["WARNING", "MANDATORY"] = "WARNING"
    source_ref: str | None = None
    review_pending: bool = False


class GlassTypeLimit(EngineModel):
    """Manufacturing bounds for a lamina kind + thickness band (D02) —
    supplier data: min/max side, area limits, aspect ratio, and whether
    the pane must be ordered to exact measure (tempered is never trimmed)."""

    code: str
    lamina_kind: str = "ANY"
    thickness_min_mm: Decimal | None = None
    thickness_max_mm: Decimal | None = None
    min_side_mm: Decimal | None = None
    max_side_mm: Decimal | None = None
    min_area_m2: Decimal | None = None
    max_area_m2: Decimal | None = None
    max_aspect_ratio: Decimal | None = None
    requires_exact_cut: bool = False
    severity: Literal["WARNING", "MANDATORY"] = "WARNING"
    source_ref: str | None = None
    review_pending: bool = False


class GlassSafetyFinding(EngineModel):
    """A breached safety/limit rule on a concrete pane (D02)."""

    rule_code: str
    severity: Literal["WARNING", "MANDATORY"]
    required_safety: str | None = None
    message: str
    source_ref: str | None = None
    review_pending: bool = False


class GlassBayContext(EngineModel):
    """Situational context a BAY contributes to the glass rule pass (D02):
    its opening type, the distance of the pane bottom to the module base
    and whether a door leaf sits beside it."""

    opening_type: str | None = None
    sill_mm: Decimal | None = None
    adjacent_door: bool = False


class GlassSurchargeRate(EngineModel):
    """One priced extra a glass product supports (catalog data, D02)."""

    kind: Literal["TEMPERED", "EDGE_POLISH", "DRILL", "PALILLAJE"]
    unit: Literal["M2", "M", "EA", "CROSS"]
    amount: Decimal
    currency: str | None = None
    label: str | None = None


class GlassProduct(EngineModel):
    """A supplier's glass product — the composed SKU a bay chooses (D02).

    ``composition`` is the structured layer stack; ``None`` marks a
    product whose notation never parsed (UNKNOWN — it stays selectable
    but every derived number reports unknown instead of guessing).
    Ug / g / light transmission / safety class are supplier-declared data —
    shown, never computed. ``min_area_m2`` is the supplier's minimum
    billable cut area; ``surcharges`` are the product's priced extras."""

    sku: str
    name: str
    composition: GlassComposition | None = None
    safety_class: str | None = None
    ug_w_m2k: Decimal | None = None
    g_value: Decimal | None = None
    light_transmission_pct: Decimal | None = None
    weight_kg_m2: Decimal | None = None
    min_area_m2: Decimal | None = None
    # Declared 1..5 relative-price band for the selector's comparability
    # signal — real money stays in the cost lists.
    price_tier: int | None = None
    surcharges: list[GlassSurchargeRate] = []
    review_pending: bool = False


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
    # D02: structured composition the piece resolved to, the full package
    # thickness it implies (laminae + interlayers + chambers — the glazing
    # bead key), declared extras (polish, drills, palillaje), the exact-cut
    # flag ("tempered is ordered to measure, never trimmed") and every
    # safety/limit finding the pane triggered.
    composition: GlassComposition | None = None
    thickness_total_mm: Decimal | None = None
    requires_exact_cut: bool = False
    surcharge_selections: list[GlassSurchargeSelection] = []
    safety_findings: list[GlassSafetyFinding] = []


HARDWARE_COMPONENT_CATEGORIES = (
    "HANDLE", "HINGE", "LOCK", "ROLLER", "CONNECTOR", "DRAINAGE", "GASKET",
    "SEAL", "SCREW", "CONSUMABLE", "FITTING", "SUPPORT", "CHANNEL", "OTHER",
)

HardwareComponentCategory = Literal[
    "HANDLE", "HINGE", "LOCK", "ROLLER", "CONNECTOR", "DRAINAGE", "GASKET",
    "SEAL", "SCREW", "CONSUMABLE", "FITTING", "SUPPORT", "CHANNEL", "OTHER",
]


class ComponentQtyRule(EngineModel):
    """Quantity rule for a kit component, as catalog data (D04).

    The component count follows the leaf span instead of a fixed number —
    e.g. locking points = f(leaf height). `ceil(axis_mm / per_mm)`, clamped
    into [min_qty, max_qty]. The resolved quantity is what BOM/picking see.
    """

    kind: Literal["PER_WIDTH", "PER_HEIGHT"]
    per_mm: Decimal = Field(gt=Decimal("0"))
    min_qty: int = Field(default=1, ge=1)
    max_qty: int | None = Field(default=None, ge=1)

    @field_validator("min_qty", "max_qty", mode="before")
    @classmethod
    def _int_bound(cls, value: object) -> object:
        # NUMERIC catalog columns surface as Decimal; integral bounds stay ints.
        if isinstance(value, Decimal) and value == int(value):
            return int(value)
        return value

    @model_validator(mode="after")
    def _bounds_coherent(self) -> "ComponentQtyRule":
        if self.max_qty is not None and self.max_qty < self.min_qty:
            raise ValueError("max_qty must be >= min_qty")
        return self


class ComponentCutRule(EngineModel):
    """Cut rule for a cuttable component (e.g. transmisión = alto de hoja − X).

    The resolved `length_mm` is the leaf span along `axis` minus the
    declared deduction. A cut that resolves to a non-positive length is a
    catalog error and raises — never a zero-length pick line.
    """

    axis: Literal["WIDTH", "HEIGHT"]
    minus_mm: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


HARDWARE_MACHINING_KINDS = (
    "LOCK_PREP", "HINGE_PREP", "ESPAG_HOUSING", "DRAINAGE", "OTHER",
)

HardwareMachiningKind = Literal[
    "LOCK_PREP", "HINGE_PREP", "ESPAG_HOUSING", "DRAINAGE", "OTHER",
]


class MachiningDeclaration(EngineModel):
    """Machining operation the catalog declares for a component (D04, feeds
    P14): lock pocket, espag housing, hinge mortise…

    `u_mm`/`y_mm` are the declared position along the leaf edge — when the
    catalog never declared coordinates the engine emits the operation as
    `DECLARED_NOT_EMITTED`; coordinates are never invented downstream.
    """

    kind: HardwareMachiningKind
    side: str | None = None
    u_mm: Decimal | None = None
    y_mm: Decimal | None = None
    note: str | None = None
    # Emission verdict — the engine writes it on the emitted line (a catalog
    # declaration never carries one).
    status: Literal["EMITTED", "DECLARED_NOT_EMITTED"] | None = None


class HardwareComponent(EngineModel):
    sku: str
    name: str
    # Declared quantity. Optional because a rule-driven component carries no
    # fixed count — `qty_rule` must then be declared. On emitted lines this
    # is always the resolved quantity.
    qty: Decimal | None = Field(default=None, gt=Decimal("0"))
    unit: str
    # Declared component kind — the catalog states what each kit line IS so
    # production can distinguish handles, hinges, locks, rollers, seals,
    # drainage and consumables instead of guessing from a name. Contents
    # sealed before the field existed decode as OTHER (mandate §9).
    category: HardwareComponentCategory = "OTHER"
    # D04: component quantity/cut rules and physical data, all declared.
    qty_rule: ComponentQtyRule | None = None
    cut_rule: ComponentCutRule | None = None
    weight_kg: Decimal | None = Field(default=None, ge=Decimal("0"))
    cost_clp: Decimal | None = Field(default=None, ge=Decimal("0"))
    machining: list[MachiningDeclaration] = Field(default_factory=list)
    # Emitted-only: the resolved cut length for a cuttable component and the
    # sellable option that brought this component into the leaf's BOM.
    length_mm: Decimal | None = Field(default=None, gt=Decimal("0"))
    option_sku: str | None = None

    @model_validator(mode="after")
    def _qty_or_rule_declared(self) -> "HardwareComponent":
        if self.qty is None and self.qty_rule is None:
            raise ValueError("component needs a declared qty or a qty_rule")
        return self

    def resolved_qty(self, *, leaf_width_mm: Decimal, leaf_height_mm: Decimal) -> Decimal:
        """Declared quantity for this leaf — the fixed count, or the qty
        rule applied to the leaf span (ceil division, clamped)."""
        if self.qty_rule is None:
            # Model guarantees qty when no rule is declared.
            assert self.qty is not None
            return self.qty
        axis = (
            leaf_width_mm
            if self.qty_rule.kind == "PER_WIDTH"
            else leaf_height_mm
        )
        qty = int((axis / self.qty_rule.per_mm).to_integral_value(rounding=ROUND_CEILING))
        qty = max(qty, self.qty_rule.min_qty)
        if self.qty_rule.max_qty is not None:
            qty = min(qty, self.qty_rule.max_qty)
        return Decimal(qty)

    def resolved_length_mm(
        self, *, leaf_width_mm: Decimal, leaf_height_mm: Decimal
    ) -> Decimal | None:
        """Declared cut length for a cuttable component; None when the
        component is not cut from a leaf span. A non-positive result is a
        catalog defect and raises."""
        if self.cut_rule is None:
            return None
        axis = leaf_width_mm if self.cut_rule.axis == "WIDTH" else leaf_height_mm
        length = axis - self.cut_rule.minus_mm
        if length <= Decimal("0"):
            raise ValueError(
                f"cut rule on {self.sku} resolves a non-positive length "
                f"({axis} - {self.cut_rule.minus_mm} mm)"
            )
        return length

    def expanded(
        self,
        *,
        leaf_width_mm: Decimal,
        leaf_height_mm: Decimal,
        option_sku: str | None = None,
    ) -> "HardwareComponent":
        """The emitted line: resolved quantity and cut length, with the
        option provenance when an option brought the component in."""
        return self.model_copy(
            update={
                "qty": self.resolved_qty(
                    leaf_width_mm=leaf_width_mm, leaf_height_mm=leaf_height_mm
                ),
                "length_mm": self.resolved_length_mm(
                    leaf_width_mm=leaf_width_mm, leaf_height_mm=leaf_height_mm
                ),
                "option_sku": option_sku,
            }
        )


class HandleModelOption(EngineModel):
    """A handle model the family sells (D04): estándar, con llave, con
    botón o de puerta con escudo — with its declared price delta."""

    sku: str
    name: str
    kind: Literal["STANDARD", "LOCKABLE", "BUTTON", "DOOR_ESCUTCHEON"]
    price_delta_clp: Decimal | None = Field(default=None, ge=Decimal("0"))


class HandleColorOption(EngineModel):
    """A handle finish the family sells (D05 feeds more later)."""

    sku: str
    name: str
    price_delta_clp: Decimal | None = Field(default=None, ge=Decimal("0"))


class HardwareFamily(EngineModel):
    """Hardware family for system × opening (D04).

    The classes are the `hardware_kits` rows on this opening; the family
    carries the shared selection catalogue — handle models and colours the
    leaf may pick, validated against this list — plus the declared
    handle-height rule and its editable range.
    """

    opening_type: str
    handle_models: list[HandleModelOption] = Field(default_factory=list)
    handle_colors: list[HandleColorOption] = Field(default_factory=list)
    # Declared handle-height rule (D04): CENTERED resolves mid-leaf,
    # FIXED_FROM_BASE uses `handle_height_default_mm` measured from the
    # leaf base, RANGE leaves the declared default editable inside
    # [min_mm, max_mm]. None = the catalog declared no rule — the leaf's
    # declared height stands unvalidated by this axis.
    handle_height_rule: Literal["CENTERED", "FIXED_FROM_BASE", "RANGE"] | None = None
    handle_height_min_mm: Decimal | None = Field(default=None, gt=Decimal("0"))
    handle_height_max_mm: Decimal | None = Field(default=None, gt=Decimal("0"))
    handle_height_default_mm: Decimal | None = Field(default=None, gt=Decimal("0"))

    @model_validator(mode="after")
    def _handle_height_data_coherent(self) -> "HardwareFamily":
        if self.handle_height_rule == "FIXED_FROM_BASE" and (
            self.handle_height_default_mm is None
        ):
            raise ValueError(
                "FIXED_FROM_BASE needs a declared handle_height_default_mm"
            )
        if (self.handle_height_min_mm is None) != (self.handle_height_max_mm is None):
            raise ValueError("handle height range needs both bounds or neither")
        if (
            self.handle_height_min_mm is not None
            and self.handle_height_max_mm is not None
            and self.handle_height_min_mm > self.handle_height_max_mm
        ):
            raise ValueError("handle_height_min_mm must be <= handle_height_max_mm")
        return self


class HardwareOptionKind(str, Enum):
    """Sellable hardware option kinds (D04)."""

    SECURITY = "SECURITY"  # puntos antipalanca / clase RC when declared
    OPENING_LIMITER = "OPENING_LIMITER"
    MICROVENTILATION = "MICROVENTILATION"
    CONCEALED_HINGES = "CONCEALED_HINGES"


class HardwareOption(EngineModel):
    """A sellable hardware option per position — only sellable when the
    family's catalog declares it. Carries its declared price delta and the
    BOM lines it adds to the leaf."""

    sku: str
    name: str
    kind: HardwareOptionKind
    # Normalized opening family (TURN/TILT_TURN/SLIDING/DOOR/AWNING) —
    # same grain the kit classes are scoped at.
    opening_type: str
    price_delta_clp: Decimal | None = Field(default=None, ge=Decimal("0"))
    components: list[HardwareComponent] = Field(default_factory=list)
    data_provenance: str | None = None


class HardwareSelectionPrice(EngineModel):
    """One sellable selection's declared price delta (D04) — handle model,
    colour, or option. `price_delta_clp=None` means the catalog left the
    price undeclared: the selection stands, pricing must refuse to guess."""

    sku: str
    name: str
    source: Literal["HANDLE_MODEL", "HANDLE_COLOR", "OPTION"]
    price_delta_clp: Decimal | None = Field(default=None, ge=Decimal("0"))


class HardwareItem(EngineModel):
    kit_sku: str
    name: str
    qty: int = 1
    unit: Literal["kit"] = "kit"
    bay_id: str
    leaf_id: str | None = None
    # Resolved BOM: quantities and cut lengths already expanded against the
    # leaf — picking reads this verbatim (D04).
    contents: list[HardwareComponent] = Field(default_factory=list)
    # Resolved class + the leaf's sellable selections (D04) — display names
    # travel with the item so sealed documents never re-query the catalog.
    class_label: str | None = None
    handle_model_sku: str | None = None
    handle_model_name: str | None = None
    handle_color_sku: str | None = None
    handle_color_name: str | None = None
    option_skus: list[str] = Field(default_factory=list)
    option_names: list[str] = Field(default_factory=list)
    # Resolved handle height (leaf-declared or family-rule default); None =
    # undeclared — the design surface shows Sin dato, never a guessed mm.
    handle_height_mm: Decimal | None = None
    # Resolved sums; None = the catalog left the axis unknown (Sin dato).
    cost_clp: Decimal | None = None
    weight_kg: Decimal | None = None
    # Sum of the leaf's sellable deltas; None when a selected source left
    # its price undeclared. `price_deltas` keeps the per-source detail.
    price_delta_clp: Decimal | None = None
    price_deltas: list[HardwareSelectionPrice] = Field(default_factory=list)
    # Declared machining for P14 — entries without coordinates stay
    # DECLARED_NOT_EMITTED.
    machining: list[MachiningDeclaration] = Field(default_factory=list)


class HardwarePickingLine(EngineModel):
    """One picking line — a component and its resolved cut length across a
    work order's leaves (D04). `sources` names which kit/option skus
    contributed, so the floor can trace a line back to its classes."""

    sku: str
    name: str
    qty: Decimal = Field(gt=Decimal("0"))
    unit: str
    category: HardwareComponentCategory = "OTHER"
    length_mm: Decimal | None = None
    sources: list[str] = Field(default_factory=list)


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
    # D04 class identity and extra restrictions — None = undeclared, no
    # invented bound.
    class_label: str | None = None
    # Max leaf height/width ratio the class admits (slenderness).
    max_aspect_ratio: Decimal | None = Field(default=None, gt=Decimal("0"))
    # Min leaf height for a stay (compás) — only meaningful on kits that
    # carry stay arms.
    min_stay_height_mm: Decimal | None = Field(default=None, gt=Decimal("0"))


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


class SlidingParams(EngineModel):
    """Grouped view of a system's sliding parameters (D01).

    Engine math keeps the flat SystemParams fields for compatibility; this
    grouped shape is what the sliding family presents to catalog tooling
    and API consumers, and what a sliding system must fully declare.
    """

    rail_type: RailType = RailType.DUAL
    rail_count: int | None = None
    pulley_height_mm: Decimal = Decimal("12.00")
    central_overlap_mm: Decimal = Decimal("35.00")
    sliding_lateral_clearance_mm: Decimal = Decimal("0.00")
    sliding_end_add_mm: Decimal = Decimal("6.00")
    sliding_glazing_deduction_width_mm: Decimal | None = None
    sliding_glazing_deduction_height_mm: Decimal | None = None


class ProfileCutRule(EngineModel):
    """Declared cut convention for one profile role (D01).

    Geometry owns the physical cut sequence; the rule carries the catalog's
    declared convention so ingestion, readiness and the workspace can check
    and display it. The engine consumes `rounding_mm` (cut quantum) and
    `interlock_deduction_mm` (meeting-stile length deduction); the declared
    angle/welded-ends pair is verified by catalog tooling against the
    convention the engine actually cuts.
    """

    role: ProfileRole
    cut_angle_deg: Decimal = Decimal("45.0")
    welded_ends: int | None = None
    interlock_deduction_mm: Decimal = Decimal("0")
    rounding_mm: Decimal = Field(default=Decimal("0.01"), ge=Decimal("0.01"))
    # Compatible reinforcement article the catalog declares for the role.
    reinforcement_sku: str | None = None


class ReinforcementRule(EngineModel):
    """Steel reinforcement requirement as catalog data (D01).

    A rule fires when its role, finish class and member cut length match:
    `finish_class` picks the finish domain — WHITE covers unfoiled white
    members, NON_WHITE covers foiled/dark members (mandatory by regulation),
    ALL covers both. No matching declared rule means the member runs
    unreinforced — the catalog stated so. `mandatory=False` marks an
    informative recommendation; the deterministic BOM only emits required
    steel.
    """

    role: ProfileRole
    finish_class: Literal["ALL", "WHITE", "NON_WHITE"] = "ALL"
    min_length_mm: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    mandatory: bool = True
    # Overrides the article's own reinforcement_sku when the role needs a
    # specific steel (e.g. heavier section for long members).
    reinforcement_sku: str | None = None
    # Extra length deduction on top of welding loss + gap (topes, acople).
    cut_deduction_mm: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    # Fastening declared in BOM: screws per metre of reinforced member.
    screws_per_m: Decimal | None = Field(default=None, ge=Decimal("0"))
    screw_sku: str | None = None

    @model_validator(mode="after")
    def _screw_sku_declared_when_counted(self) -> "ReinforcementRule":
        if self.screws_per_m is not None and not (self.screw_sku or "").strip():
            raise ValueError("screw_sku is required when screws_per_m is declared")
        return self


class TypologyLimit(EngineModel):
    """Leaf dimensional envelope for one typology on a system (D01).

    Nulls mean the catalog declared no bound on that axis — UNKNOWN stays
    honest; the engine only enforces declared bounds.
    """

    opening_type: str
    min_leaf_width_mm: Decimal | None = None
    max_leaf_width_mm: Decimal | None = None
    min_leaf_height_mm: Decimal | None = None
    max_leaf_height_mm: Decimal | None = None
    max_leaf_weight_kg: Decimal | None = None
    # Max finished leaf height/width ratio (slenderness).
    max_aspect_ratio: Decimal | None = None


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
    # Fabrication family — gates which opening typologies the system may
    # cut (FAMILY_OPENINGS). Declared in the catalog; the engine rejects an
    # incompatible typology instead of emitting a fake cut.
    system_family: SystemFamily = SystemFamily.CASEMENT
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
    # Sliding/door fabrication data — required only on families that can
    # emit the opening; a facade or pure-casement series may leave them
    # undeclared (None) and the consumer raises when exercised.
    sliding_glazing_deduction_width_mm: Decimal | None = None
    sliding_glazing_deduction_height_mm: Decimal | None = None
    door_leaf_side_clearance_mm: Decimal | None = None
    available_panel_rules: dict[str, PanelRule] = Field(default_factory=dict)
    # Declared catalog rules (D01): cut conventions per role, reinforcement
    # requirements per role+finish, and leaf dimensional limits per
    # typology. Empty maps mean the catalog never declared them — the
    # engine keeps its canonical behaviour and reports the gap, it never
    # invents the data.
    cut_rules: dict[ProfileRole, ProfileCutRule] = Field(default_factory=dict)
    reinforcement_rules: list[ReinforcementRule] = Field(default_factory=list)
    typology_limits: dict[str, TypologyLimit] = Field(default_factory=dict)
    # Declared glass authorities (D02): the products a bay may carry
    # (keyed by technical sku), situational safety rules (NCh 135 family)
    # and per-kind dimensional limits. Empty = the catalog never declared
    # them — the engine evaluates nothing and reports no data, it never
    # invents a table.
    glass_products: dict[str, GlassProduct] = Field(default_factory=dict)
    glass_safety_rules: list[GlassSafetyRule] = Field(default_factory=list)
    glass_type_limits: list[GlassTypeLimit] = Field(default_factory=list)
    # D04 hardware families keyed by normalized opening (TURN/TILT_TURN/…):
    # handle models/colours + vendible options the leaf may select. Empty
    # maps mean the catalog declared none — a leaf selecting one is refused.
    hardware_families: dict[str, HardwareFamily] = Field(default_factory=dict)
    hardware_options: dict[str, HardwareOption] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _family_data_coherence(self) -> "SystemParams":
        """Sliding glazing deductions must exist on sliding-capable families;
        they are meaningless on the rest."""
        if self.system_family in (SystemFamily.SLIDING, SystemFamily.LIFT_SLIDE) and (
            self.sliding_glazing_deduction_width_mm is None
            or self.sliding_glazing_deduction_height_mm is None
        ):
            raise ValueError(
                "sliding_glazing_deduction_* is required for sliding families"
            )
        return self

    @property
    def sliding(self) -> SlidingParams:
        """Grouped sliding parameter view (D01) — computed fresh so
        model_copy overrides on the flat fields stay visible."""
        return SlidingParams(
            rail_type=self.rail_type,
            rail_count=self.rail_count,
            pulley_height_mm=self.pulley_height_mm,
            central_overlap_mm=self.central_overlap_mm,
            sliding_lateral_clearance_mm=self.sliding_lateral_clearance_mm,
            sliding_end_add_mm=self.sliding_end_add_mm,
            sliding_glazing_deduction_width_mm=self.sliding_glazing_deduction_width_mm,
            sliding_glazing_deduction_height_mm=self.sliding_glazing_deduction_height_mm,
        )


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
    # D04 sellable leaf selections — the family catalog decides what exists;
    # the engine validates every declared sku against it.
    handle_model_sku: str | None = None
    handle_color_sku: str | None = None
    hardware_option_skus: list[str] = Field(default_factory=list)
    # Declared hinge side of a DOOR_ENTRY leaf (DIN convention: LEFT =
    # hinges on the left, handle on the right). Doors carry no side in
    # their opening_type, so handedness must be declared — manufacturing
    # refuses to mount a handle on an undeclared door rather than assume.
    door_handedness: Literal["LEFT", "RIGHT"] | None = None
    # Sliding panel topology (mandate §12). Present on a sliding BAY it
    # fully defines the unit — slots, moving/fixed kind, rail assignment.
    # Absent, the SLIDING_*L presets map to canonical layouts.
    sliding_layout: SlidingLayout | None = None
    # D02: the structured composition the bay's glass product carries.
    # When present it is the authoritative stack — `glass_spec` stays the
    # persisted notation string and `glass_thickness_mm` the declared
    # package thickness for older payloads.
    glass_composition: GlassComposition | None = None
    # Declared per-bay extras (edge polish, drills, palillaje grid).
    glass_options: GlassOptions | None = None


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
