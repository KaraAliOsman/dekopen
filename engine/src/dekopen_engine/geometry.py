"""Pure deterministic geometry for the SHOT-06 Core Gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Literal

from dekopen_engine.bom import build_engine_result
from dekopen_engine.finishes import apply_color_surcharges
from dekopen_engine.glass import (
    build_glass_piece,
    exact_glass_weight,
    exact_glass_area_m2,
    resolve_composition,
)
from dekopen_engine.glass_composition import format_glass_notation
from dekopen_engine.glass_safety import (
    GlassPieceContext,
    bay_glass_contexts,
    evaluate_glass_limits,
    evaluate_glass_safety,
    requires_exact_cut,
)
from dekopen_engine.models import (
    GlassBayContext,
    GlassComposition,
    GlassSafetyFinding,
    GlassSurchargeSelection,
)
from dekopen_engine.hardware import (
    HardwareSelectionError,
    HardwareCandidateEvaluation,
    NoCompatibleHardwareKit,
    build_hardware_item,
    evaluate_hardware_candidates,
    resolve_hardware_evaluations,
)
from dekopen_engine.manufacturing_trace import (
    Axis,
    GeometryManufacturingTraceV1,
    PlacementDomain,
    SemanticInfillTraceV1,
    SemanticLeafTraceV1,
    SemanticMemberTraceV1,
    TracePointV1,
    TraceRectV1,
    TraceSegmentV1,
)
from dekopen_engine.technical_facts import (
    GeometryComputation,
    InfillTechnicalFacts,
    LeafTechnicalFacts,
    OpeningTechnicalFacts,
    SpanTechnicalFacts,
)
from dekopen_engine.panel import build_panel_piece, exact_panel_weight
from dekopen_engine.weight import (
    ExactLeafWeight, MissingFabricationAuthority, base_leaf_weight,
)
from dekopen_engine.models import (
    BayLeaf,
    BayOpeningType,
    ColorSelection,
    EffectiveProfileArticle,
    EngineResult,
    FittingPiece,
    GlassPiece,
    GlazingBeadRule,
    HardwareComponent,
    HardwareItem,
    HardwareKitRule,
    LeafRole,
    LeafWeight,
    PanelPiece,
    MaterialType,
    NodeType,
    Opening,
    OpeningMovement,
    OpeningSpec,
    ParametricNode,
    ProfileCut,
    ProfileRole,
    RailType,
    ReinforcementPiece,
    ReinforcementRule,
    SlidingLayout,
    SlidingPanel,
    SlidingPanelKind,
    SlidingTravel,
    SystemParams,
    TypologyLimit,
    UnitKind,
)
from dekopen_engine.openings import (
    UNIMPLEMENTED_MOVEMENTS,
    admitted_capabilities,
    declared_unit_kind,
    families_admitting_movement,
    families_admitting_spec,
    families_admitting_unit,
    leaf_hardware_group,
    leaf_hinge_handedness,
    leaf_sash_role_candidates,
    leaf_trace_opening,
    resolve_opening_spec,
    resolve_unit_kind,
    spec_display_name_es,
    spec_is_admitted,
    spec_movement_is_family_compatible,
)

_TWO = Decimal("2")
_ANGLE_WELDED = Decimal("45.0")
_ANGLE_SQUARE = Decimal("90.0")

SUPPORTED_OPENING_TYPES = frozenset(
    {
        BayOpeningType.FIXED,
        BayOpeningType.TURN_LEFT,
        BayOpeningType.TURN_RIGHT,
        BayOpeningType.TILT_TURN_LEFT,
        BayOpeningType.TILT_TURN_RIGHT,
        BayOpeningType.SLIDING_2L,
        BayOpeningType.SLIDING_3L,
        BayOpeningType.SLIDING_4L,
        BayOpeningType.SLIDING,
        BayOpeningType.AWNING,
        BayOpeningType.DOOR_ENTRY,
        BayOpeningType.DOOR_DOUBLE,
    }
)

_SLIDING_OPENING_TYPES = frozenset(
    {
        BayOpeningType.SLIDING_2L,
        BayOpeningType.SLIDING_3L,
        BayOpeningType.SLIDING_4L,
        BayOpeningType.SLIDING,
    }
)


class DomainRejection(ValueError):
    """A domain-level refusal carrying the issue code and params the
    product evaluator surfaces verbatim."""

    def __init__(self, code: str, message: str, params: dict[str, str]) -> None:
        super().__init__(message)
        self.code = code
        self.params = params


class SlidingLayoutError(DomainRejection):
    """Domain rejection of a sliding topology."""


class IncompatibleTypologyError(DomainRejection):
    """The opening typology does not belong to the system's fabrication
    family — the engine refuses instead of cutting a leaf the series
    cannot physically produce (D01)."""


class DimensionalLimitError(DomainRejection):
    """A leaf violated a declared dimensional limit of its typology (D01)."""


def assert_opening_allowed(
    node: ParametricNode,
    params: SystemParams,
    *,
    unit: UnitKind = UnitKind.WINDOW,
) -> OpeningSpec:
    """Reject a typology the system's fabrication family cannot make (D01).

    D03 resolves the node's opening spec first: the gate then applies at
    movement level (the family's physical repertoire) and at composition
    level (the system's declared capabilities, or the legacy-expressible
    fallback). `unit` is the enclosing unit kind — a nested bay's spec
    inherits it and may never contradict it. Returns the resolved spec
    for the caller."""
    declared = declared_unit_kind(node)
    if declared is not None and declared is not unit:
        raise IncompatibleTypologyError(
            "typology_family_incompatible",
            f"la bahía {node.id} declara unidad {declared.value} pero vive "
            f"dentro de una unidad {unit.value}",
            {
                "system": params.system_code,
                "family": params.system_family.value,
                "bay": node.id,
                "declared_unit": declared.value,
                "unit": unit.value,
            },
        )
    spec = resolve_opening_spec(node, default_unit=unit)
    for leaf in spec.leaves:
        if leaf.opening.movement in UNIMPLEMENTED_MOVEMENTS:
            raise NotImplementedError(
                f"{spec_display_name_es(spec)} usa movimiento "
                f"{leaf.opening.movement.value} — declarado en D03, fabricación en D08"
            )
    if not spec_movement_is_family_compatible(spec, params):
        failed = [
            leaf.opening.movement
            for leaf in spec.leaves
            if not spec_movement_is_family_compatible(
                OpeningSpec(unit_kind=spec.unit_kind, leaves=[leaf]), params
            )
        ]
        compatible: list[str] = []
        for movement in failed:
            for family in families_admitting_movement(movement):
                if family not in compatible:
                    compatible.append(family)
        if spec.unit_kind not in families_admitting_unit(spec.unit_kind):
            compatible = families_admitting_unit(spec.unit_kind)
        raise IncompatibleTypologyError(
            "typology_family_incompatible",
            f"tipología {spec_display_name_es(spec)} incompatible con un sistema de familia "
            f"{params.system_family.value}; "
            f"sistemas compatibles: {', '.join(compatible) or 'ninguno declarado'}",
            {
                "system": params.system_code,
                "family": params.system_family.value,
                "opening": node.opening_type.value if node.opening_type else spec_display_name_es(spec),
                "compatible_families": ",".join(compatible),
            },
        )
    if not spec_is_admitted(spec, params):
        reasons = capability_rejection_reasons(spec, params)
        # The rejection names which fabrication families physically cover
        # this composition — the catalog edge then names concrete systems.
        admitting = families_admitting_spec(spec)
        raise IncompatibleTypologyError(
            "opening_capability_incompatible",
            f"apertura {spec_display_name_es(spec)} incompatible con el sistema "
            f"{params.system_code}: {', '.join(reasons)}; "
            f"familias que sí la admiten: {', '.join(admitting) or 'ninguna'}",
            {
                "system": params.system_code,
                "family": params.system_family.value,
                "opening": spec_display_name_es(spec),
                "reasons": ",".join(reasons),
                "compatible_families": ",".join(admitting),
            },
        )
    return spec


def capability_rejection_reasons(spec: OpeningSpec, params: SystemParams) -> list[str]:
    """Why a spec fails the system's declared capabilities — each leaf's
    first uncovered axis, so the estimator reads exactly which part of
    the combination the catalog does not sell."""
    reasons: list[str] = []
    for leaf in spec.leaves:
        opening = leaf.opening
        rows = admitted_capabilities(params)
        movement_rows = [cap for cap in rows if cap.movement is opening.movement]
        if not movement_rows:
            reason = f"{opening.movement.value} no está declarado"
        else:
            unit_rows = [cap for cap in movement_rows if spec.unit_kind in cap.unit_kinds]
            if not unit_rows:
                reason = f"unidad {spec.unit_kind.value} no admitida para {opening.movement.value}"
            else:
                reason = ""
                if opening.direction is not None and all(
                    opening.direction not in cap.directions for cap in unit_rows
                ):
                    reason = f"dirección {opening.direction.value} no admitida para {opening.movement.value}"
                elif all(opening.leaf_role not in cap.leaf_roles for cap in unit_rows):
                    reason = f"rol {opening.leaf_role.value} no admitido para {opening.movement.value}"
                elif all(len(spec.leaves) > cap.max_leaves for cap in unit_rows):
                    reason = f"composición de {len(spec.leaves)} hojas supera el máximo declarado"
                elif opening.fixed_in_sash and not any(cap.fixed_in_sash for cap in unit_rows):
                    reason = "fijo en hoja no declarado"
        if reason and reason not in reasons:
            reasons.append(reason)
    if not reasons:
        reasons.append("combinación no admitida")
    return reasons


def _moving_panel(index: int, track: int, travel: "SlidingTravel") -> SlidingPanel:
    return SlidingPanel(
        slot=f"P{index + 1}", kind=SlidingPanelKind.MOVING, track=track,
        travel=travel,
    )


# Canonical topologies behind the legacy leaf-count presets: every panel is
# MOVING and adjacent leaves alternate rails — the physical requirement for
# consecutive panels to slide past each other on a dual-rail frame. Each
# preset declares its travel: leaves in the left half slide toward the
# right, leaves in the right half toward the left (the same convention
# `panel_travel` infers for layouts that never declared it).
_SLIDING_PRESETS: dict[BayOpeningType, SlidingLayout] = {
    BayOpeningType.SLIDING_2L: SlidingLayout(
        tracks=2,
        panels=[
            _moving_panel(0, 0, SlidingTravel.RIGHT),
            _moving_panel(1, 1, SlidingTravel.LEFT),
        ],
    ),
    BayOpeningType.SLIDING_3L: SlidingLayout(
        tracks=2,
        panels=[
            _moving_panel(0, 0, SlidingTravel.RIGHT),
            _moving_panel(1, 1, SlidingTravel.RIGHT),
            _moving_panel(2, 0, SlidingTravel.LEFT),
        ],
    ),
    BayOpeningType.SLIDING_4L: SlidingLayout(
        tracks=2,
        panels=[
            _moving_panel(0, 0, SlidingTravel.RIGHT),
            _moving_panel(1, 1, SlidingTravel.RIGHT),
            _moving_panel(2, 0, SlidingTravel.LEFT),
            _moving_panel(3, 1, SlidingTravel.LEFT),
        ],
    ),
}


def travel_inferred(panel: SlidingPanel) -> bool:
    """True when the panel's direction is the presentation convention, not
    a declaration — the symbology contract flags those `dirección inferida`."""
    return panel.kind is SlidingPanelKind.MOVING and panel.travel is None


def panel_travel(panel: SlidingPanel, index: int, count: int) -> "SlidingTravel | None":
    """Resolved slide direction of a panel: its declared `travel`, else
    the documented inference — left half of the bay travels right, right
    half travels left (a leaf slides over its neighbouring slot)."""
    if panel.kind is SlidingPanelKind.FIXED:
        return None
    if panel.travel is not None:
        return panel.travel
    return SlidingTravel.RIGHT if index * 2 < count else SlidingTravel.LEFT


def resolved_sliding_layout(node: ParametricNode) -> SlidingLayout:
    """Explicit layout wins; otherwise the SLIDING_*L preset supplies one."""
    if node.sliding_layout is not None:
        return node.sliding_layout
    if node.opening_type is BayOpeningType.SLIDING:
        raise SlidingLayoutError(
            "sliding_layout_invalid",
            f"BAY {node.id} opening SLIDING requires a sliding_layout",
            {"bay": node.id},
        )
    try:
        assert node.opening_type is not None
        return _SLIDING_PRESETS[node.opening_type]
    except KeyError as error:
        raise SlidingLayoutError(
            "sliding_layout_invalid",
            f"BAY {node.id} is not a sliding opening",
            {"bay": node.id},
        ) from error


def rail_count(params: SystemParams) -> int:
    """Rails the frame profile physically provides — explicit catalog value,
    else derived from the rail type (MONO=1, DUAL=2)."""
    if params.rail_count is not None:
        return params.rail_count
    return 1 if params.rail_type is RailType.MONO else 2


def validate_sliding_layout(layout: SlidingLayout, params: SystemParams) -> None:
    """Structural + track rules of a sliding topology (mandate §12).

    - every panel slot is unique and the unit keeps at least one MOVING leaf
    - FIXED panels have no rail; MOVING panels ride a track < layout.tracks
    - adjacent FIXED panels cannot join without a mullion (a split models it)
    - adjacent MOVING panels on the same rail would collide before they
      overlap — they must alternate tracks
    - layout.tracks may not exceed the profile's rail capacity
    """
    rails = rail_count(params)
    if layout.tracks > rails:
        raise SlidingLayoutError(
            "sliding_tracks_unsupported",
            f"layout needs {layout.tracks} tracks but the system provides {rails}",
            {"tracks": str(layout.tracks), "rails": str(rails)},
        )
    slots = [panel.slot for panel in layout.panels]
    if len(set(slots)) != len(slots):
        raise SlidingLayoutError(
            "sliding_layout_invalid", "duplicate panel slot", {"slots": ",".join(slots)}
        )
    moving = 0
    for index, panel in enumerate(layout.panels):
        if panel.kind is SlidingPanelKind.MOVING:
            moving += 1
            if panel.track is None or not (0 <= panel.track < layout.tracks):
                raise SlidingLayoutError(
                    "sliding_layout_invalid",
                    f"panel {panel.slot} rides an undeclared track",
                    {"slot": panel.slot},
                )
        elif panel.track is not None:
            raise SlidingLayoutError(
                "sliding_layout_invalid",
                f"fixed panel {panel.slot} cannot occupy a track",
                {"slot": panel.slot},
            )
        if (
            panel.kind is SlidingPanelKind.MOVING
            and (
                (index == 0 and panel.travel is SlidingTravel.LEFT)
                or (index == len(layout.panels) - 1 and panel.travel is SlidingTravel.RIGHT)
            )
        ):
            raise SlidingLayoutError(
                "sliding_layout_invalid",
                f"panel {panel.slot} cannot travel toward a jamb without space",
                {"slot": panel.slot},
            )
        if index == 0:
            continue
        previous = layout.panels[index - 1]
        if (
            panel.kind is SlidingPanelKind.FIXED
            and previous.kind is SlidingPanelKind.FIXED
        ):
            raise SlidingLayoutError(
                "sliding_layout_invalid",
                "adjacent fixed panels need a mullion — model them with a split",
                {"slot": panel.slot},
            )
        if (
            panel.kind is SlidingPanelKind.MOVING
            and previous.kind is SlidingPanelKind.MOVING
            and panel.track == previous.track
        ):
            raise SlidingLayoutError(
                "sliding_layout_invalid",
                "adjacent moving panels cannot share a track",
                {"slot": panel.slot},
            )
    if moving == 0:
        raise SlidingLayoutError(
            "sliding_layout_invalid",
            "a sliding unit needs at least one moving panel",
            {},
        )

_OPERABLE_OPENING_TYPES = frozenset(
    {
        BayOpeningType.TURN_LEFT,
        BayOpeningType.TURN_RIGHT,
        BayOpeningType.TILT_TURN_LEFT,
        BayOpeningType.TILT_TURN_RIGHT,
        BayOpeningType.AWNING,
    }
)

_DOOR_OPENING_TYPES = frozenset(
    {BayOpeningType.DOOR_ENTRY, BayOpeningType.DOOR_DOUBLE}
)


def _optional_article(
    params: SystemParams, role: ProfileRole
) -> EffectiveProfileArticle | None:
    """Catalog-declared article for a role, or None — never invented."""
    article = params.effective_profile_articles.get(role)
    if article is not None and article.role is not role:
        raise ValueError(
            f"Effective profile article key {role.value} has role {article.role.value}"
        )
    return article


def _leaf_sash_role(
    params: SystemParams, spec: OpeningSpec, leaf: BayLeaf
) -> ProfileRole:
    """Which profile role a leaf is cut from (D01/D03).

    Dedicated roles win when the catalog declares them: a sliding leaf rides
    on SLIDING_SASH, a door leaf on DOOR_SASH. When the series carries no
    dedicated article the honest answer is the standard sash profile — the
    catalog declared that the leaf uses it.
    """
    dedicated, fallback = leaf_sash_role_candidates(spec, leaf)
    if _optional_article(params, dedicated) is not None:
        return dedicated
    return fallback


def _meeting_stile_article(
    params: SystemParams, role: ProfileRole
) -> EffectiveProfileArticle | None:
    """The catalog-declared meeting-stile article for a role, or None —
    the leaf keeps its standard sash stile instead."""
    return _optional_article(params, role)


def _meeting_deduction(
    params: SystemParams, article: EffectiveProfileArticle
) -> Decimal:
    """Declared meeting-stile length deduction for the article's role
    (`cut_rules[role].interlock_deduction_mm`, 0 when undeclared)."""
    rule = params.cut_rules.get(article.role)
    return rule.interlock_deduction_mm if rule is not None else Decimal("0")


@dataclass(frozen=True, slots=True)
class _LeafCtx:
    """A physical leaf's resolved fabrication context (D03): which opening
    kinematics it has, which unit it lives in and what it emits as its
    trace identity. Built once per leaf; shared by every member, infill,
    kit and fact the leaf produces."""

    node: ParametricNode
    leaf: BayLeaf
    spec: OpeningSpec
    trace_opening: str
    handle_expected: bool


def _handle_expected(leaf: BayLeaf) -> bool:
    """Whether the leaf takes a user-operated handle (D03): a PASSIVE leaf
    closes with its falleba and a fixed-in-sash leaf never opens — the
    handle policy skips both instead of mounting phantom handles."""
    if leaf.opening.leaf_role is LeafRole.PASSIVE:
        return False
    if leaf.opening.movement is OpeningMovement.FIXED:
        return False
    return True


def resolve_reinforcement_rule(
    params: SystemParams,
    role: ProfileRole,
    *,
    finish_class: str,
    length_mm: Decimal,
) -> ReinforcementRule | None:
    """The declared reinforcement rule covering a member cut (D01).

    Rules are catalog data: a member is reinforced only when a declared
    rule matches its role, finish class and length. The most specific
    finish class wins (WHITE / NON_WHITE over ALL); ties go to the highest
    min_length still below the member length. D05 resolves the finish
    class from the color selection — NON_WHITE finishes (foil, dark,
    coextruded) get their declared mandatory steel.
    """
    best: ReinforcementRule | None = None
    for rule in params.reinforcement_rules:
        if rule.role is not role:
            continue
        if rule.finish_class not in ("ALL", finish_class):
            continue
        if length_mm < rule.min_length_mm:
            continue
        if best is None:
            best = rule
            continue
        specific = rule.finish_class == finish_class
        best_specific = best.finish_class == finish_class
        if specific and not best_specific:
            best = rule
        elif specific == best_specific and rule.min_length_mm >= best.min_length_mm:
            best = rule
    return best


def check_typology_limits(
    limit: TypologyLimit,
    *,
    width_mm: Decimal,
    height_mm: Decimal,
    weight_kg: Decimal | None,
) -> list[str]:
    """Violated dimensional bounds (D01) — only declared bounds enforce;
    a null bound or an unknown weight reports nothing."""
    violations: list[str] = []
    if limit.min_leaf_width_mm is not None and width_mm < limit.min_leaf_width_mm:
        violations.append("min_leaf_width_mm")
    if limit.max_leaf_width_mm is not None and width_mm > limit.max_leaf_width_mm:
        violations.append("max_leaf_width_mm")
    if limit.min_leaf_height_mm is not None and height_mm < limit.min_leaf_height_mm:
        violations.append("min_leaf_height_mm")
    if limit.max_leaf_height_mm is not None and height_mm > limit.max_leaf_height_mm:
        violations.append("max_leaf_height_mm")
    if (
        limit.max_leaf_weight_kg is not None
        and weight_kg is not None
        and weight_kg > limit.max_leaf_weight_kg
    ):
        violations.append("max_leaf_weight_kg")
    if (
        limit.max_aspect_ratio is not None
        and width_mm > Decimal("0")
        and height_mm / width_mm > limit.max_aspect_ratio
    ):
        violations.append("max_aspect_ratio")
    return violations


@dataclass(frozen=True, slots=True)
class _Rect:
    x_mm: Decimal
    y_mm: Decimal
    width_mm: Decimal
    height_mm: Decimal

    @property
    def right_mm(self) -> Decimal:
        return self.x_mm + self.width_mm

    @property
    def bottom_mm(self) -> Decimal:
        return self.y_mm + self.height_mm


@dataclass(frozen=True, slots=True)
class _MemberPlacement:
    semantic_member_id: str
    topology_path: str
    assembly: str
    leaf_slot: str | None
    physical_member_slot: str
    axis: Axis
    placement_domain: Literal[
        PlacementDomain.DIRECT, PlacementDomain.SLIDING_LEAF, PlacementDomain.BEAD_SET
    ]
    direct_segment: TraceSegmentV1 | None = None
    parent_leaf_id: str | None = None
    parent_infill_id: str | None = None


@dataclass(slots=True)
class _GeometryAccumulator:
    computation: GeometryComputation = field(default_factory=GeometryComputation)
    diagnostic: bool = False
    contract_valid: bool = True
    top_node_id: str = ""
    nominal_width_mm: Decimal = Decimal("0")
    nominal_height_mm: Decimal = Decimal("0")
    profile_cuts: list[ProfileCut] = field(default_factory=list)
    reinforcements: list[ReinforcementPiece] = field(default_factory=list)
    fittings: list[FittingPiece] = field(default_factory=list)
    # Screws declared per reinforced member aggregate per (sku, bay, leaf):
    # the BOM reports one counted line per fastening point set, so the
    # purchase projection sees each fitting source exactly once.
    screw_fittings: dict[tuple[str, str | None, str | None], int] = field(
        default_factory=dict)
    glasses: list[GlassPiece] = field(default_factory=list)
    panels: list[PanelPiece] = field(default_factory=list)
    hardware_items: list[HardwareItem] = field(default_factory=list)
    leaf_weights: list[LeafWeight] = field(default_factory=list)
    # D05: the machining finish class (WHITE / NON_WHITE) the resolved
    # color selection drives; the legacy is_foiled path maps NON_WHITE.
    finish_class: str = "WHITE"
    # D05: leaf-envelope multiplier from the declared per-finish size
    # factors — dark finishes shrink the admissible envelope (≤ 1).
    envelope_factor: Decimal = Decimal("1")
    semantic_members: list[SemanticMemberTraceV1] = field(default_factory=list)
    semantic_leaves: list[SemanticLeafTraceV1] = field(default_factory=list)
    semantic_infills: list[SemanticInfillTraceV1] = field(default_factory=list)
    # Per-BAY safety context (opening type, sill height, door adjacency)
    # derived once from the declared tree for the D02 glass rule pass.
    glass_contexts: dict[str, GlassBayContext] = field(default_factory=dict)


def _trace_point(x_mm: Decimal, y_mm: Decimal) -> TracePointV1:
    return TracePointV1(x_mm=x_mm, y_mm=y_mm)


def _trace_rect(rect: _Rect) -> TraceRectV1:
    return TraceRectV1(
        x_mm=rect.x_mm, y_mm=rect.y_mm, width_mm=rect.width_mm, height_mm=rect.height_mm
    )


def _trace_segment(x1: Decimal, y1: Decimal, x2: Decimal, y2: Decimal) -> TraceSegmentV1:
    return TraceSegmentV1(start=_trace_point(x1, y1), end=_trace_point(x2, y2))


def welding_loss_per_end(article: EffectiveProfileArticle) -> Decimal:
    """Derive a per-end loss from the effective article's sole DB authority.
    UNKNOWN (None) means the catalog never stated the welding loss — refuse
    rather than invent one; only welded (PVC) paths reach this."""

    if article.welding_loss_mm is None:
        raise ValueError(
            f"welding_loss_mm unknown for article {article.sku} — "
            "the catalog must state it before welded cutting math can run"
        )
    return article.welding_loss_mm / _TWO


def joint_adjustment_per_end(
    params: SystemParams,
    article: EffectiveProfileArticle,
) -> Decimal:
    """Per-end cut adjustment for the profile joint system.

    Welded systems (PVC) add a weld allowance so the fused corner lands on the
    finished size; mechanically jointed systems (aluminium) lose material to the
    corner bracket that seats inside the profile at each mitred end.
    """

    if params.material is MaterialType.ALUMINIUM:
        return -params.corner_bracket_loss_mm
    return welding_loss_per_end(article)


def _article(params: SystemParams, role: ProfileRole) -> EffectiveProfileArticle:
    try:
        article = params.effective_profile_articles[role]
    except KeyError as error:
        raise ValueError(f"Missing effective profile article for role {role.value}") from error
    if article.role is not role:
        raise ValueError(
            f"Effective profile article key {role.value} has role {article.role.value}"
        )
    return article


def _normalize_top_node(root: ParametricNode) -> tuple[ParametricNode, Decimal, Decimal]:
    if root.type is NodeType.ROOT:
        if len(root.children) != 1:
            raise ValueError("ROOT must wrap exactly one parametric node")
        top = root.children[0]
        width_mm = root.width_mm if root.width_mm is not None else top.width_mm
        height_mm = root.height_mm if root.height_mm is not None else top.height_mm
        if root.width_mm is not None and top.width_mm not in (None, root.width_mm):
            raise ValueError("ROOT and wrapped node widths disagree")
        if root.height_mm is not None and top.height_mm not in (None, root.height_mm):
            raise ValueError("ROOT and wrapped node heights disagree")
    else:
        top = root
        width_mm = root.width_mm
        height_mm = root.height_mm

    if width_mm is None or height_mm is None:
        raise ValueError("Top-level width_mm and height_mm are required")
    if width_mm <= Decimal("0") or height_mm <= Decimal("0"):
        raise ValueError("Top-level dimensions must be positive")
    return top, width_mm, height_mm


def reinforcement_cut_length(
    cut_mm: Decimal,
    article: EffectiveProfileArticle,
    welded_end_count: int,
) -> Decimal:
    if article.reinforcement_gap_mm is None:
        raise ValueError(
            f"reinforcement_gap_mm unknown for article {article.sku} — "
            "the catalog must state it before reinforcement cutting math can run"
        )
    return (
        cut_mm
        - Decimal(welded_end_count) * welding_loss_per_end(article)
        - _TWO * article.reinforcement_gap_mm
    )


def _append_profile(
    accumulator: _GeometryAccumulator,
    *,
    article: EffectiveProfileArticle,
    length_mm: Decimal,
    qty: int,
    welded_ends: int | None,
    placements: list[_MemberPlacement],
    angle_left: Decimal = _ANGLE_WELDED,
    angle_right: Decimal = _ANGLE_WELDED,
    bay_id: str | None = None,
    leaf_id: str | None = None,
    params: SystemParams | None = None,
) -> None:
    if length_mm <= Decimal("0"):
        raise ValueError("Profile cut must be positive")
    if qty != len(placements) or len({item.semantic_member_id for item in placements}) != qty:
        raise ValueError("Every physical profile requires one semantic placement")
    cut_rule = (
        params.cut_rules.get(article.role) if params is not None else None
    )
    if cut_rule is not None and cut_rule.rounding_mm > Decimal("0.01"):
        # Declared cut rounding: the saw only promises the rule's quantum —
        # the cut rounds UP to it rather than trusting finer fractions.
        length_mm = (
            (length_mm / cut_rule.rounding_mm).to_integral_value(
                rounding=ROUND_CEILING
            )
            * cut_rule.rounding_mm
        )
    accumulator.profile_cuts.append(
        ProfileCut(
            sku=article.sku,
            role=article.role,
            material=article.material,
            length_mm=length_mm,
            angle_left=angle_left,
            angle_right=angle_right,
            qty=qty,
            bay_id=bay_id,
            leaf_id=leaf_id,
        )
    )
    steel_length: Decimal | None = None
    steel_sku = article.reinforcement_sku
    if welded_ends is not None and article.material is MaterialType.PVC:
        reinf_rule = (
            resolve_reinforcement_rule(
                params,
                article.role,
                finish_class=accumulator.finish_class,
                length_mm=length_mm,
            )
            if params is not None
            else None
        )
        if params is not None and params.reinforcement_rules:
            # Declared rule table owns the decision (D01): a member is
            # reinforced only when a matching mandatory rule fires — the
            # catalog stated the requirement, the engine never invents it.
            if reinf_rule is not None and reinf_rule.mandatory:
                steel_length = (
                    reinforcement_cut_length(length_mm, article, welded_ends)
                    - reinf_rule.cut_deduction_mm
                )
                steel_sku = (
                    reinf_rule.reinforcement_sku
                    or (cut_rule.reinforcement_sku if cut_rule is not None else None)
                    or article.reinforcement_sku
                )
        else:
            # No declared rules: welded PVC members keep the canonical
            # unconditional steel — the catalog never stated otherwise.
            steel_length = reinforcement_cut_length(length_mm, article, welded_ends)
        if steel_length is not None:
            if steel_length <= Decimal("0"):
                raise ValueError("Reinforcement cut must be positive")
            accumulator.reinforcements.append(
                ReinforcementPiece(
                    parent_profile_sku=article.sku,
                    reinforcement_sku=steel_sku,
                    role=article.role,
                    length_mm=steel_length,
                    qty=qty,
                    bay_id=bay_id,
                    leaf_id=leaf_id,
                )
            )
            if reinf_rule is not None and reinf_rule.screws_per_m is not None:
                screws = (
                    length_mm
                    / Decimal("1000")
                    * reinf_rule.screws_per_m
                ).to_integral_value(rounding=ROUND_CEILING)
                if screws > 0:
                    assert reinf_rule.screw_sku is not None
                    key = (reinf_rule.screw_sku, bay_id, leaf_id)
                    accumulator.screw_fittings[key] = (
                        accumulator.screw_fittings.get(key, 0) + int(screws) * qty
                    )
    for placement in placements:
        accumulator.semantic_members.append(
            SemanticMemberTraceV1(
                semantic_member_id=placement.semantic_member_id,
                topology_path=placement.topology_path,
                assembly=placement.assembly,
                bay_id=bay_id,
                leaf_id=leaf_id,
                leaf_slot=placement.leaf_slot,
                role=article.role,
                physical_member_slot=placement.physical_member_slot,
                workshop_sku=article.sku,
                material=article.material,
                cut_length_mm=length_mm,
                angle_left=angle_left,
                angle_right=angle_right,
                axis=placement.axis,
                placement_domain=placement.placement_domain,
                direct_segment=placement.direct_segment,
                parent_leaf_id=placement.parent_leaf_id,
                parent_infill_id=placement.parent_infill_id,
                reinforcement_required=steel_length is not None,
                reinforcement_sku=(steel_sku if steel_length is not None else None),
                reinforcement_length_mm=steel_length,
            )
        )


def _append_frame(
    accumulator: _GeometryAccumulator,
    *,
    frame_article: EffectiveProfileArticle,
    params: SystemParams,
    nominal_width_mm: Decimal,
    nominal_height_mm: Decimal,
    bottom_article: EffectiveProfileArticle | None = None,
) -> None:
    horizontal = [
        _MemberPlacement(
            "outer-frame/TOP",
            "outer-frame",
            "OUTER_FRAME",
            None,
            "TOP",
            Axis.HORIZONTAL,
            PlacementDomain.DIRECT,
            _trace_segment(Decimal("0"), Decimal("0"), nominal_width_mm, Decimal("0")),
        ),
        _MemberPlacement(
            "outer-frame/BOTTOM",
            "outer-frame",
            "OUTER_FRAME",
            None,
            "BOTTOM",
            Axis.HORIZONTAL,
            PlacementDomain.DIRECT,
            _trace_segment(Decimal("0"), nominal_height_mm, nominal_width_mm, nominal_height_mm),
        ),
    ]
    vertical = [
        _MemberPlacement(
            "outer-frame/LEFT",
            "outer-frame",
            "OUTER_FRAME",
            None,
            "LEFT",
            Axis.VERTICAL,
            PlacementDomain.DIRECT,
            _trace_segment(Decimal("0"), Decimal("0"), Decimal("0"), nominal_height_mm),
        ),
        _MemberPlacement(
            "outer-frame/RIGHT",
            "outer-frame",
            "OUTER_FRAME",
            None,
            "RIGHT",
            Axis.VERTICAL,
            PlacementDomain.DIRECT,
            _trace_segment(nominal_width_mm, Decimal("0"), nominal_width_mm, nominal_height_mm),
        ),
    ]
    if bottom_article is None:
        _append_profile(
            accumulator,
            article=frame_article,
            length_mm=nominal_width_mm + _TWO * joint_adjustment_per_end(params, frame_article),
            qty=2,
            welded_ends=2,
            placements=horizontal,
            params=params,
        )
    else:
        # The sliding frame separates its bottom member as the rail/guide
        # article — only the horizontal members split then.
        _append_profile(
            accumulator,
            article=frame_article,
            length_mm=nominal_width_mm + _TWO * joint_adjustment_per_end(params, frame_article),
            qty=1,
            welded_ends=2,
            placements=horizontal[:1],
            params=params,
        )
        _append_profile(
            accumulator,
            article=bottom_article,
            length_mm=nominal_width_mm + _TWO * joint_adjustment_per_end(params, bottom_article),
            qty=1,
            welded_ends=2,
            placements=horizontal[1:],
            params=params,
        )
    _append_profile(
        accumulator,
        article=frame_article,
        length_mm=nominal_height_mm + _TWO * joint_adjustment_per_end(params, frame_article),
        qty=2,
        welded_ends=2,
        placements=vertical,
        params=params,
    )


def resolve_bead_rule(infill_thickness_mm: Decimal, params: SystemParams) -> GlazingBeadRule:
    try:
        rule = params.glazing_bead_rules[infill_thickness_mm]
    except KeyError as error:
        raise ValueError(
            f"Missing glazing bead rule for {infill_thickness_mm} mm infill"
        ) from error
    if rule.bead_article.role is not ProfileRole.GLAZING_BEAD:
        raise ValueError("Glazing bead rule must reference a GLAZING_BEAD article")
    return rule


def _append_glazing_beads(
    accumulator: _GeometryAccumulator,
    *,
    params: SystemParams,
    bay_id: str,
    leaf_id: str | None,
    leaf_slot: str | None,
    topology_path: str,
    assembly: str,
    semantic_infill_id: str,
    infill_thickness_mm: Decimal,
    width_mm: Decimal,
    height_mm: Decimal,
) -> None:
    if accumulator.diagnostic and infill_thickness_mm not in params.glazing_bead_rules:
        accumulator.contract_valid = False
        return
    rule = resolve_bead_rule(infill_thickness_mm, params)
    prefix = f"{semantic_infill_id}/bead-set"
    horizontal = [
        _MemberPlacement(
            f"{prefix}/TOP",
            topology_path,
            assembly,
            leaf_slot,
            "TOP",
            Axis.HORIZONTAL,
            PlacementDomain.BEAD_SET,
            parent_infill_id=semantic_infill_id,
        ),
        _MemberPlacement(
            f"{prefix}/BOTTOM",
            topology_path,
            assembly,
            leaf_slot,
            "BOTTOM",
            Axis.HORIZONTAL,
            PlacementDomain.BEAD_SET,
            parent_infill_id=semantic_infill_id,
        ),
    ]
    vertical = [
        _MemberPlacement(
            f"{prefix}/LEFT",
            topology_path,
            assembly,
            leaf_slot,
            "LEFT",
            Axis.VERTICAL,
            PlacementDomain.BEAD_SET,
            parent_infill_id=semantic_infill_id,
        ),
        _MemberPlacement(
            f"{prefix}/RIGHT",
            topology_path,
            assembly,
            leaf_slot,
            "RIGHT",
            Axis.VERTICAL,
            PlacementDomain.BEAD_SET,
            parent_infill_id=semantic_infill_id,
        ),
    ]
    _append_profile(
        accumulator,
        article=rule.bead_article,
        length_mm=width_mm + rule.cut_add_mm,
        qty=2,
        welded_ends=None,
        placements=horizontal,
        bay_id=bay_id,
        leaf_id=leaf_id,
        params=params,
    )
    _append_profile(
        accumulator,
        article=rule.bead_article,
        length_mm=height_mm + rule.cut_add_mm,
        qty=2,
        welded_ends=None,
        placements=vertical,
        bay_id=bay_id,
        leaf_id=leaf_id,
        params=params,
    )


@dataclass(frozen=True, slots=True)
class SashGeometry:
    finished_width_mm: Decimal
    finished_height_mm: Decimal
    cut_width_mm: Decimal
    cut_height_mm: Decimal


def _jointed_sash(
    width: Decimal,
    height: Decimal,
    article: EffectiveProfileArticle,
    params: SystemParams,
) -> SashGeometry:
    loss = _TWO * joint_adjustment_per_end(params, article)
    return SashGeometry(width, height, width + loss, height + loss)


def single_rectangular_sash_geometry(
    inner_width_mm: Decimal,
    inner_height_mm: Decimal,
    article: EffectiveProfileArticle,
    params: SystemParams,
) -> SashGeometry:
    """Shared finished-and-cut primitive for TURN, TILT_TURN and AWNING."""
    return _jointed_sash(
        inner_width_mm + _TWO * params.sash_overlap_mm,
        inner_height_mm + _TWO * params.sash_overlap_mm,
        article,
        params,
    )


def rebate_depth(params: SystemParams) -> Decimal:
    """Glass bite the catalog must declare — absent means the pane position
    cannot be established and the calculation refuses, never guesses."""
    if params.rebate_depth_mm is None:
        raise MissingFabricationAuthority("Missing rebate authority: rebate_depth_mm")
    return params.rebate_depth_mm


def _end_milling_overlap(params: SystemParams) -> Decimal:
    if params.end_milling_overlap_mm is None:
        raise MissingFabricationAuthority(
            "Missing end-milling authority: end_milling_overlap_mm")
    return params.end_milling_overlap_mm


def _pocket_dimension(
    finished_mm: Decimal,
    article: EffectiveProfileArticle,
    params: SystemParams,
    clearance_mm: Decimal,
    edge_faces: tuple[Decimal, Decimal] | None = None,
) -> Decimal:
    """Glazed pocket inside a frame; `edge_faces` overrides the two face widths
    when a member has asymmetric stiles (e.g. sash + encuentro)."""
    face_left, face_right = (
        edge_faces if edge_faces is not None else (article.face_width_mm, article.face_width_mm)
    )
    return (
        finished_mm
        - face_left
        - face_right
        + _TWO * rebate_depth(params)
        - _TWO * clearance_mm
    )


def _append_leaf(
    accumulator: _GeometryAccumulator,
    *,
    ctx: _LeafCtx,
    leaf_id: str | None,
    topology_path: str,
    reference_rect: _Rect,
    direct_rect: _Rect | None,
    sash: SashGeometry,
    params: SystemParams,
    clearance_mm: Decimal,
    slot_pitch_mm: Decimal | None = None,
    meeting_articles: dict[str, EffectiveProfileArticle] | None = None,
) -> None:
    node = ctx.node
    leaf = ctx.leaf
    leaf_slot = leaf.slot
    spec = ctx.spec
    sash_role = _leaf_sash_role(params, spec, leaf)
    article = _article(params, sash_role)
    # Meeting stiles (encuentro on sliding pairs, inversor on the passive
    # leaf of a hinged pair) are cut from their dedicated article when the
    # catalog carries one; its declared deduction shortens the member at
    # the meeting. `meeting_articles` maps physical edge → article.
    meetings = meeting_articles or {}
    meeting_deduction = {
        edge: _meeting_deduction(params, meeting_article)
        for edge, meeting_article in meetings.items()
    }
    # The pocket's width faces follow the real stiles: an edge that took the
    # encuentro/inversor profile pockets with its face, not the sash's.
    pocket_faces: tuple[Decimal, Decimal] | None = None
    if meetings:
        pocket_faces = (
            meetings["LEFT"].face_width_mm
            if "LEFT" in meetings
            else article.face_width_mm,
            meetings["RIGHT"].face_width_mm
            if "RIGHT" in meetings
            else article.face_width_mm,
        )
    cut_start = len(accumulator.profile_cuts)
    steel_start = len(accumulator.reinforcements)
    semantic_leaf_id = f"{topology_path}/leaf/{leaf_slot}"
    assembly = f"BAY:{node.id}:LEAF:{leaf_slot}"
    placement_domain: Literal[PlacementDomain.DIRECT, PlacementDomain.SLIDING_LEAF] = (
        PlacementDomain.SLIDING_LEAF
        if leaf.opening.movement is OpeningMovement.SLIDE
        else PlacementDomain.DIRECT
    )
    accumulator.semantic_leaves.append(
        SemanticLeafTraceV1(
            semantic_leaf_id=semantic_leaf_id,
            topology_path=topology_path,
            assembly=assembly,
            bay_id=node.id,
            leaf_id=leaf_id,
            leaf_slot=leaf_slot,
            opening_type=ctx.trace_opening,
            door_handedness=(
                (
                    # Single-leaf doors take the node's declared handedness;
                    # a legacy door enum leaves it undeclared so the policy
                    # keeps failing closed. Multi-leaf doors and new-form
                    # leaves always carry their own hinge side.
                    node.door_handedness
                    if len(spec.leaves) == 1
                    else leaf_hinge_handedness(leaf)
                    if node.door_handedness is not None
                    else leaf_hinge_handedness(leaf)
                    if node.opening is not None or node.leaves
                    else None
                )
                if spec.unit_kind is UnitKind.DOOR
                else None
            ),
            handle_expected=ctx.handle_expected,
            placement_domain=placement_domain,
            reference_rect=_trace_rect(reference_rect),
            slot_pitch_mm=slot_pitch_mm,
            finished_width_mm=sash.finished_width_mm,
            finished_height_mm=sash.finished_height_mm,
            direct_rect=None if direct_rect is None else _trace_rect(direct_rect),
        )
    )

    def member(side: str, axis: Axis) -> _MemberPlacement:
        segment = None
        if direct_rect is not None:
            if side == "TOP":
                segment = _trace_segment(
                    direct_rect.x_mm, direct_rect.y_mm, direct_rect.right_mm, direct_rect.y_mm
                )
            elif side == "BOTTOM":
                segment = _trace_segment(
                    direct_rect.x_mm,
                    direct_rect.bottom_mm,
                    direct_rect.right_mm,
                    direct_rect.bottom_mm,
                )
            elif side == "LEFT":
                segment = _trace_segment(
                    direct_rect.x_mm, direct_rect.y_mm, direct_rect.x_mm, direct_rect.bottom_mm
                )
            else:
                segment = _trace_segment(
                    direct_rect.right_mm,
                    direct_rect.y_mm,
                    direct_rect.right_mm,
                    direct_rect.bottom_mm,
                )
        return _MemberPlacement(
            semantic_member_id=f"{semantic_leaf_id}/{side}",
            topology_path=topology_path,
            assembly=assembly,
            leaf_slot=leaf_slot,
            physical_member_slot=side,
            axis=axis,
            placement_domain=placement_domain,
            direct_segment=segment,
            parent_leaf_id=semantic_leaf_id,
        )

    _append_profile(
        accumulator,
        article=article,
        length_mm=sash.cut_width_mm,
        qty=2,
        welded_ends=2,
        placements=[member("TOP", Axis.HORIZONTAL), member("BOTTOM", Axis.HORIZONTAL)],
        bay_id=node.id,
        leaf_id=leaf_id,
        params=params,
    )
    meeting_edges = {edge for edge in meetings if edge in ("LEFT", "RIGHT")}
    if meetings and len(meeting_edges) == 1:
        # Mixed stiles: the meeting edge takes the encuentro/inversor
        # profile with its declared deduction; the other edge stays a
        # sash member.
        meeting = next(iter(meeting_edges))
        meeting_article = meetings[meeting]
        deduction = meeting_deduction[meeting]
        plain = "RIGHT" if meeting == "LEFT" else "LEFT"
        _append_profile(
            accumulator,
            article=meeting_article,
            length_mm=sash.cut_height_mm - deduction,
            qty=1,
            welded_ends=2,
            placements=[member(meeting, Axis.VERTICAL)],
            bay_id=node.id,
            leaf_id=leaf_id,
            params=params,
        )
        _append_profile(
            accumulator,
            article=article,
            length_mm=sash.cut_height_mm,
            qty=1,
            welded_ends=2,
            placements=[member(plain, Axis.VERTICAL)],
            bay_id=node.id,
            leaf_id=leaf_id,
            params=params,
        )
    elif meeting_edges == {"LEFT", "RIGHT"}:
        _append_profile(
            accumulator,
            article=meetings["LEFT"],
            length_mm=sash.cut_height_mm - meeting_deduction["LEFT"],
            qty=1,
            welded_ends=2,
            placements=[member("LEFT", Axis.VERTICAL)],
            bay_id=node.id,
            leaf_id=leaf_id,
            params=params,
        )
        _append_profile(
            accumulator,
            article=meetings["RIGHT"],
            length_mm=sash.cut_height_mm - meeting_deduction["RIGHT"],
            qty=1,
            welded_ends=2,
            placements=[member("RIGHT", Axis.VERTICAL)],
            bay_id=node.id,
            leaf_id=leaf_id,
            params=params,
        )
    else:
        _append_profile(
            accumulator,
            article=article,
            length_mm=sash.cut_height_mm,
            qty=2,
            welded_ends=2,
            placements=[member("LEFT", Axis.VERTICAL), member("RIGHT", Axis.VERTICAL)],
            bay_id=node.id,
            leaf_id=leaf_id,
            params=params,
        )
    width = _pocket_dimension(
        sash.finished_width_mm, article, params, clearance_mm, pocket_faces
    )
    height = _pocket_dimension(sash.finished_height_mm, article, params, clearance_mm)
    if leaf.opening.movement is OpeningMovement.SLIDE:
        sliding = params.sliding
        if (
            sliding.sliding_glazing_deduction_width_mm is None
            or sliding.sliding_glazing_deduction_height_mm is None
        ):
            raise MissingFabricationAuthority(
                "Missing sliding authority: sliding_glazing_deduction_*"
            )
        width -= sliding.sliding_glazing_deduction_width_mm
        height -= sliding.sliding_glazing_deduction_height_mm
    infill_kind: Literal["GLASS", "PANEL"]
    thickness_source: str | None = None
    thickness_declared_mm: Decimal | None = None
    glass_spec_text = node.glass_spec
    if spec.unit_kind is UnitKind.DOOR:
        if node.panel_article_sku is None:
            raise ValueError(f"door leaf BAY {node.id} requires panel_article_sku")
        try:
            rule = params.available_panel_rules[node.panel_article_sku]
        except KeyError as error:
            raise ValueError(f"Missing panel article: {node.panel_article_sku}") from error
        infill_thickness = rule.thickness_mm
        thickness_source = "PANEL"
        infill_weight = exact_panel_weight(width, height, rule)
        infill_reason = (
            None if infill_weight is not None
            else f"missing_panel_mass:{rule.sku}"
        )
        technical_sku = node.panel_article_sku
        composition = f"SANDWICH_PANEL:{node.panel_article_sku}"
        infill_kind = "PANEL"
        accumulator.panels.append(
            build_panel_piece(
                bay_id=node.id,
                leaf_id=leaf_id,
                width_mm=width,
                height_mm=height,
                rule=rule,
            )
        )
    else:
        resolved = resolve_composition(node.glass_spec, node.glass_composition)
        # A bay carrying only the structured composition still names its
        # glass — the canonical notation regenerates from the stack.
        glass_spec_text = node.glass_spec or (
            format_glass_notation(resolved) if resolved else None
        )
        if glass_spec_text is None or (
            node.glass_thickness_mm is None and resolved is None
        ):
            raise ValueError(f"BAY {node.id} requires glass_thickness_mm and glass_spec")
        if resolved is not None:
            # The structured composition owns the package thickness — the
            # glazing bead keys off what is physically ordered, not off a
            # declaration that may drift. A declared thickness that disagrees
            # is drift worth a review warning, not a silent override.
            infill_thickness = resolved.total_thickness_mm()
            thickness_source = "COMPOSITION"
            if (
                node.glass_thickness_mm is not None
                and node.glass_thickness_mm != infill_thickness
            ):
                thickness_declared_mm = node.glass_thickness_mm
        else:
            assert node.glass_thickness_mm is not None
            infill_thickness = node.glass_thickness_mm
            thickness_source = "DECLARED"
        findings, exact_cut, selections = _evaluate_glass(
            accumulator,
            node=node,
            params=params,
            leaf_id=leaf_id,
            width_mm=width,
            height_mm=height,
            composition=resolved,
        )
        if thickness_declared_mm is not None:
            findings.append(
                GlassSafetyFinding(
                    rule_code="GLASS-THICKNESS-MISMATCH",
                    severity="WARNING",
                    message=(
                        f"El espesor declarado ({thickness_declared_mm} mm) "
                        f"no coincide con la composición ({infill_thickness} mm)."
                    ),
                )
            )
        infill_weight = exact_glass_weight(
            width, height, node.glass_spec, composition=resolved
        )
        infill_reason = (
            None if infill_weight is not None
            else f"missing_glass_composition:{glass_spec_text}"
        )
        technical_sku = node.glass_article_sku or ""
        composition = glass_spec_text
        infill_kind = "GLASS"
        accumulator.glasses.append(
            build_glass_piece(
                bay_id=node.id,
                leaf_id=leaf_id,
                width_mm=width,
                height_mm=height,
                glass_spec=glass_spec_text,
                article_sku=technical_sku or None,
                composition=resolved,
                surcharge_selections=selections,
                safety_findings=findings,
                requires_exact_cut=exact_cut,
            )
        )
    accumulator.computation.infills.append(
        InfillTechnicalFacts(
            bay_id=node.id,
            leaf_id=leaf_id,
            kind=infill_kind,
            thickness_mm=infill_thickness,
            glass_spec=glass_spec_text,
            width_mm=width,
            height_mm=height,
            exact_area_m2=exact_glass_area_m2(width, height),
            bead_supported=infill_thickness in params.glazing_bead_rules,
            thickness_source=thickness_source,
            thickness_declared_mm=thickness_declared_mm,
        )
    )
    semantic_infill_id = f"{semantic_leaf_id}/infill"
    sliding_infill = leaf.opening.movement is OpeningMovement.SLIDE
    direct_infill_rect = None
    if not sliding_infill:
        assert direct_rect is not None
        direct_infill_rect = _Rect(
            direct_rect.x_mm + article.face_width_mm - rebate_depth(params) + clearance_mm,
            direct_rect.y_mm + article.face_width_mm - rebate_depth(params) + clearance_mm,
            width,
            height,
        )
    accumulator.semantic_infills.append(
        SemanticInfillTraceV1(
            semantic_infill_id=semantic_infill_id,
            topology_path=topology_path,
            assembly=assembly,
            bay_id=node.id,
            leaf_id=leaf_id,
            leaf_slot=leaf_slot,
            kind=infill_kind,
            technical_sku=technical_sku,
            composition=composition,
            width_mm=width,
            height_mm=height,
            placement_domain=(
                PlacementDomain.SLIDING_INFILL if sliding_infill else PlacementDomain.DIRECT
            ),
            parent_leaf_id=semantic_leaf_id,
            direct_rect=None if direct_infill_rect is None else _trace_rect(direct_infill_rect),
        )
    )
    _append_glazing_beads(
        accumulator,
        params=params,
        bay_id=node.id,
        leaf_id=leaf_id,
        leaf_slot=leaf_slot,
        topology_path=topology_path,
        assembly=assembly,
        semantic_infill_id=semantic_infill_id,
        infill_thickness_mm=infill_thickness,
        width_mm=width,
        height_mm=height,
    )
    base = base_leaf_weight(
        profile_cuts=accumulator.profile_cuts[cut_start:],
        reinforcements=accumulator.reinforcements[steel_start:],
        infill_weight_kg=infill_weight,
        params=params,
        infill_unknown_reason=infill_reason,
    )
    hardware_group = leaf_hardware_group(spec, leaf)
    candidates: list[HardwareCandidateEvaluation] = []
    kit: HardwareKitRule | None = None
    exact_weight: ExactLeafWeight | None = None
    if hardware_group is not None:
        # D04: the leaf's declared sellable options ride the weight axis — a
        # microventilación or an antipalanca point adds real mass, so kit
        # compatibility is evaluated with them in place.
        option_components: list[HardwareComponent] = []
        for option_sku in dict.fromkeys(node.hardware_option_skus or []):
            option = params.hardware_options.get(option_sku)
            if option is None or option.opening_type != hardware_group:
                raise HardwareSelectionError(
                    "hardware_selection_unknown",
                    f"Opción de herraje {option_sku} no declarada para la familia {hardware_group}",
                    {"field": "hardware_option_skus", "sku": option_sku, "opening": hardware_group},
                )
            option_components.extend(option.components)
        candidates = evaluate_hardware_candidates(
            opening_group=hardware_group,
            opening_label=ctx.trace_opening,
            width_mm=sash.finished_width_mm,
            height_mm=sash.finished_height_mm,
            base_weight=base,
            params=params,
            explicit_sku=node.hardware_set_sku,
            option_components=option_components,
        )
        try:
            kit, exact_weight = resolve_hardware_evaluations(
                candidates,
                opening_group=hardware_group,
                opening_label=ctx.trace_opening,
                explicit_sku=node.hardware_set_sku,
                leaf_width_mm=sash.finished_width_mm,
                leaf_height_mm=sash.finished_height_mm,
            )
        except NoCompatibleHardwareKit:
            if not accumulator.diagnostic:
                raise
            accumulator.contract_valid = False
            kit, exact_weight = None, None
    # Declared dimensional limits per typology (D01/D03): the leaf envelope
    # is validated against the catalog bounds — the leaf's own key wins,
    # then the movement-level row, so a direction-specific bound and a
    # generic per-movement bound can coexist.
    limit = _typology_limit_for(params, spec, ctx)
    # D05: a declared per-finish size factor shrinks the admissible leaf
    # envelope — the bound scales by the factor, floored so a factor
    # never widens the declared limit.
    if limit is not None and accumulator.envelope_factor != Decimal("1"):
        factor = accumulator.envelope_factor
        limit = limit.model_copy(
            update={
                "max_leaf_width_mm": (
                    (limit.max_leaf_width_mm * factor).quantize(
                        Decimal("0.01"), rounding=ROUND_FLOOR)
                    if limit.max_leaf_width_mm is not None
                    else None
                ),
                "max_leaf_height_mm": (
                    (limit.max_leaf_height_mm * factor).quantize(
                        Decimal("0.01"), rounding=ROUND_FLOOR)
                    if limit.max_leaf_height_mm is not None
                    else None
                ),
            }
        )
    if limit is not None:
        violations = check_typology_limits(
            limit,
            width_mm=sash.finished_width_mm,
            height_mm=sash.finished_height_mm,
            weight_kg=(
                exact_weight.total_weight_kg if exact_weight is not None else None
            ),
        )
        if violations:
            raise DimensionalLimitError(
                "leaf_dimensional_limit",
                f"hoja {ctx.trace_opening} fuera de los límites "
                f"declarados del sistema ({', '.join(violations)})",
                {
                    "opening": ctx.trace_opening,
                    "violations": ",".join(violations),
                    "leaf_width_mm": str(sash.finished_width_mm),
                    "leaf_height_mm": str(sash.finished_height_mm),
                },
            )
    accumulator.computation.leaves.append(
        LeafTechnicalFacts(
            bay_id=node.id,
            leaf_id=leaf_id,
            opening_type=ctx.trace_opening,
            leaf_role=leaf.opening.leaf_role,
            rail_type=params.rail_type,
            finished_width_mm=sash.finished_width_mm,
            finished_height_mm=sash.finished_height_mm,
            base_weight=base,
            candidates=candidates,
            selected_kit=kit,
            exact_weight=exact_weight,
        )
    )
    if kit is None or exact_weight is None:
        return
    # A resolved kit means the leaf had a hardware group — fixed lites
    # with hardware_group None return above with kit/exact_weight unset.
    assert hardware_group is not None
    accumulator.hardware_items.append(
        build_hardware_item(
            kit=kit,
            exact_weight=exact_weight,
            opening=hardware_group,
            bay_id=node.id,
            leaf_id=leaf_id,
            leaf_width_mm=sash.finished_width_mm,
            leaf_height_mm=sash.finished_height_mm,
            params=params,
            handle_model_sku=node.handle_model_sku,
            handle_color_sku=node.handle_color_sku,
            handle_height_mm=node.handle_height_mm,
            option_skus=node.hardware_option_skus,
        )
    )
    accumulator.leaf_weights.append(exact_weight.public_result(node.id, leaf_id))


def _evaluate_glass(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
    params: SystemParams,
    leaf_id: str | None,
    width_mm: Decimal,
    height_mm: Decimal,
    composition: GlassComposition | None,
) -> tuple[list[GlassSafetyFinding], bool, list[GlassSurchargeSelection]]:
    """D02 glass rule pass for one resolved pane: situational safety
    rules, dimensional limits, the exact-cut flag and the declared extras
    — all derived once and attached to the piece."""
    context_data = accumulator.glass_contexts.get(node.id, GlassBayContext())
    context = GlassPieceContext(
        bay_id=node.id,
        leaf_id=leaf_id,
        opening_type=context_data.opening_type,
        sill_mm=context_data.sill_mm,
        adjacent_door=context_data.adjacent_door,
        width_mm=width_mm,
        height_mm=height_mm,
        area_m2=exact_glass_area_m2(width_mm, height_mm),
    )
    product = (
        params.glass_products.get(node.glass_article_sku)
        if node.glass_article_sku
        else None
    )
    declared_class = product.safety_class if product is not None else None
    findings = [
        *evaluate_glass_safety(
            context,
            composition,
            params.glass_safety_rules,
            declared_safety_class=declared_class,
        ),
        *evaluate_glass_limits(context, composition, params.glass_type_limits),
    ]
    return (
        findings,
        requires_exact_cut(composition, params.glass_type_limits),
        list(node.glass_options.surcharges) if node.glass_options else [],
    )


def _typology_limit_for(
    params: SystemParams, spec: OpeningSpec, ctx: _LeafCtx
) -> TypologyLimit | None:
    """The declared bound applying to this leaf (D03): the leaf's emitted
    key first, then the door-prefixed movement row on door units, then
    the bare movement row — the most specific bound wins."""
    candidates = [ctx.trace_opening]
    movement = ctx.leaf.opening.movement.value
    if spec.unit_kind is UnitKind.DOOR:
        candidates.append(f"DOOR:{movement}")
    candidates.append(movement)
    for key in candidates:
        limit = params.typology_limits.get(key)
        if limit is not None:
            return limit
    return None


def _append_frame_glazed_pane(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
    topology_path: str,
    rect: _Rect,
    assembly: str,
    semantic_infill_id: str,
    leaf_slot: str | None,
    params: SystemParams,
    clearance_mm: Decimal,
) -> None:
    """Glazing sealed directly into the frame region — a FIXED bay or a fixed
    "O" panel of a sliding unit. The pane extends `rebate_depth_mm` under the
    member covering each edge (frame rebate, or the neighbouring leaf's
    meeting stile for sliding slots) minus the glass clearance.

    Sliding "O" slots share the bay id, so the pane takes the slot-scoped
    leaf identity moving leaves already use — downstream targets
    (polishing, workshop annotations) can address each fixed pane."""
    resolved = resolve_composition(node.glass_spec, node.glass_composition)
    glass_spec_text = node.glass_spec or (
        format_glass_notation(resolved) if resolved else None
    )
    if glass_spec_text is None or (
        node.glass_thickness_mm is None and resolved is None
    ):
        raise ValueError(f"BAY {node.id} requires glass_thickness_mm and glass_spec")
    leaf_id = f"{node.id}:{leaf_slot}" if leaf_slot is not None else None
    width = rect.width_mm + _TWO * rebate_depth(params) - _TWO * clearance_mm
    height = rect.height_mm + _TWO * rebate_depth(params) - _TWO * clearance_mm
    if resolved is not None:
        # Same authority rule as the fixed-bay path: the composition owns the
        # thickness; a disagreeing declaration is review drift, not override.
        infill_thickness = resolved.total_thickness_mm()
        thickness_source = "COMPOSITION"
        thickness_declared_mm = (
            node.glass_thickness_mm
            if node.glass_thickness_mm is not None
            and node.glass_thickness_mm != infill_thickness
            else None
        )
    else:
        assert node.glass_thickness_mm is not None
        infill_thickness = node.glass_thickness_mm
        thickness_source = "DECLARED"
        thickness_declared_mm = None
    findings, exact_cut, selections = _evaluate_glass(
        accumulator,
        node=node,
        params=params,
        leaf_id=leaf_id,
        width_mm=width,
        height_mm=height,
        composition=resolved,
    )
    if thickness_declared_mm is not None:
        findings.append(
            GlassSafetyFinding(
                rule_code="GLASS-THICKNESS-MISMATCH",
                severity="WARNING",
                message=(
                    f"El espesor declarado ({thickness_declared_mm} mm) no "
                    f"coincide con la composición ({infill_thickness} mm)."
                ),
            )
        )
    accumulator.glasses.append(
        build_glass_piece(
            bay_id=node.id,
            leaf_id=leaf_id,
            width_mm=width,
            height_mm=height,
            glass_spec=glass_spec_text,
            article_sku=node.glass_article_sku or None,
            composition=resolved,
            surcharge_selections=selections,
            safety_findings=findings,
            requires_exact_cut=exact_cut,
        )
    )
    accumulator.computation.infills.append(
        InfillTechnicalFacts(
            bay_id=node.id,
            leaf_id=leaf_id,
            kind="GLASS",
            thickness_mm=infill_thickness,
            glass_spec=glass_spec_text,
            width_mm=width,
            height_mm=height,
            exact_area_m2=exact_glass_area_m2(width, height),
            bead_supported=infill_thickness in params.glazing_bead_rules,
            thickness_source=thickness_source,
            thickness_declared_mm=thickness_declared_mm,
        )
    )
    infill_rect = _Rect(
        rect.x_mm - rebate_depth(params) + clearance_mm,
        rect.y_mm - rebate_depth(params) + clearance_mm,
        width,
        height,
    )
    accumulator.semantic_infills.append(
        SemanticInfillTraceV1(
            semantic_infill_id=semantic_infill_id,
            topology_path=topology_path,
            assembly=assembly,
            bay_id=node.id,
            leaf_id=leaf_id,
            leaf_slot=leaf_slot,
            kind="GLASS",
            technical_sku=node.glass_article_sku or "",
            composition=glass_spec_text,
            width_mm=width,
            height_mm=height,
            placement_domain=PlacementDomain.DIRECT,
            direct_rect=_trace_rect(infill_rect),
        )
    )
    _append_glazing_beads(
        accumulator,
        params=params,
        bay_id=node.id,
        leaf_id=leaf_id,
        leaf_slot=leaf_slot,
        topology_path=topology_path,
        assembly=assembly,
        semantic_infill_id=semantic_infill_id,
        infill_thickness_mm=infill_thickness,
        width_mm=width,
        height_mm=height,
    )


def _append_sliding(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
    spec: OpeningSpec,
    topology_path: str,
    rect: _Rect,
    params: SystemParams,
    clearance_mm: Decimal,
) -> None:
    """Sliding unit on an explicit or preset track topology (mandate §12).

    The opening inside the frame is divided into N slots: every finished
    panel spans `pitch + central_overlap_mm`, so adjacent panels overlap by
    the system's central overlap. MOVING panels are sliding sash leaves;
    FIXED panels are glazed straight into their slot.
    """
    layout = resolved_sliding_layout(node)
    validate_sliding_layout(layout, params)
    sliding_leaf = BayLeaf(slot="PRIMARY", opening=Opening(movement=OpeningMovement.SLIDE))
    sliding_spec = OpeningSpec(unit_kind=spec.unit_kind, leaves=[sliding_leaf])
    article = _article(params, _leaf_sash_role(params, sliding_spec, sliding_leaf))
    sliding = params.sliding
    count = len(layout.panels)
    # Equal pitches floored to the canonical 0.01 mm grid; the last slot
    # absorbs the remainder so the slots tile the frame exactly and every
    # derived measure stays serializable (a raw n-division can repeat).
    pitch = (
        (rect.width_mm - sliding.central_overlap_mm) / count
    ).quantize(Decimal("0.01"))
    pitches = [pitch] * (count - 1) + [
        rect.width_mm - sliding.central_overlap_mm - pitch * (count - 1)
    ]
    cut_height = rect.height_mm - _TWO * sliding.pulley_height_mm
    adjustment = joint_adjustment_per_end(params, article)
    slot_x = rect.x_mm
    for index, panel in enumerate(layout.panels):
        finished_width = pitches[index] + sliding.central_overlap_mm
        if panel.kind is SlidingPanelKind.MOVING:
            leaf_slot = f"L{index + 1}"
            cut_width = finished_width + sliding.sliding_end_add_mm
            sash = SashGeometry(
                finished_width_mm=cut_width - _TWO * adjustment,
                finished_height_mm=cut_height - _TWO * adjustment,
                cut_width_mm=cut_width,
                cut_height_mm=cut_height,
            )
            # Meeting stiles: an edge of a moving panel interlocks when the
            # neighbouring slot is another moving panel on the other rail.
            interlock_edges = frozenset(
                edge
                for edge, neighbour in (
                    ("LEFT", layout.panels[index - 1] if index > 0 else None),
                    (
                        "RIGHT",
                        layout.panels[index + 1] if index + 1 < count else None,
                    ),
                )
                if neighbour is not None and neighbour.kind is SlidingPanelKind.MOVING
            )
            panel_leaf = BayLeaf(
                slot=leaf_slot,
                opening=Opening(movement=OpeningMovement.SLIDE),
            )
            meeting_articles: dict[str, EffectiveProfileArticle] = {}
            interlock_article = _meeting_stile_article(params, ProfileRole.INTERLOCK)
            if interlock_article is not None:
                meeting_articles = {
                    edge: interlock_article for edge in interlock_edges
                }
            _append_leaf(
                accumulator,
                ctx=_LeafCtx(
                    node=node,
                    leaf=panel_leaf,
                    spec=sliding_spec,
                    trace_opening=leaf_trace_opening(
                        sliding_spec, panel_leaf, node.opening_type
                    ),
                    handle_expected=True,
                ),
                leaf_id=f"{node.id}:{leaf_slot}",
                topology_path=topology_path,
                reference_rect=rect,
                direct_rect=None,
                sash=sash,
                params=params,
                clearance_mm=clearance_mm,
                slot_pitch_mm=pitch,
                meeting_articles=meeting_articles,
            )
        else:
            slot_rect = _Rect(
                slot_x,
                rect.y_mm,
                finished_width,
                rect.height_mm,
            )
            _append_frame_glazed_pane(
                accumulator,
                node=node,
                topology_path=topology_path,
                rect=slot_rect,
                assembly=f"BAY:{node.id}:SLIDING_FIXED:{panel.slot}",
                semantic_infill_id=f"{topology_path}/infill/{panel.slot}",
                leaf_slot=panel.slot,
                params=params,
                clearance_mm=clearance_mm,
            )
        slot_x += pitches[index]


def _append_bay(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
    rect: _Rect,
    topology_path: str,
    params: SystemParams,
    clearance_mm: Decimal,
    unit_kind: UnitKind,
) -> None:
    """A bay inside its enclosing unit (D03): resolve the opening spec,
    gate it against family and capability, then fabricate its leaves."""
    spec = assert_opening_allowed(node, params, unit=unit_kind)
    accumulator.computation.openings.append(
        OpeningTechnicalFacts(
            bay_id=node.id,
            width_mm=(
                accumulator.nominal_width_mm
                if node.id == accumulator.top_node_id
                else rect.width_mm
            ),
            height_mm=(
                accumulator.nominal_height_mm
                if node.id == accumulator.top_node_id
                else rect.height_mm
            ),
        )
    )
    first = spec.leaves[0]
    if len(spec.leaves) == 1:
        movement = first.opening.movement
        if movement is OpeningMovement.SLIDE:
            _append_sliding(
                accumulator,
                node=node,
                spec=spec,
                topology_path=topology_path,
                rect=rect,
                params=params,
                clearance_mm=clearance_mm,
            )
            return
        if unit_kind is UnitKind.DOOR and movement is not OpeningMovement.FIXED:
            _append_door_leaf(
                accumulator,
                node=node,
                spec=spec,
                leaf=first,
                rect=rect,
                topology_path=topology_path,
                params=params,
                clearance_mm=clearance_mm,
            )
            return
        if movement is OpeningMovement.FIXED and not first.opening.fixed_in_sash:
            _append_frame_glazed_pane(
                accumulator,
                node=node,
                topology_path=topology_path,
                rect=rect,
                assembly=f"BAY:{node.id}:FIXED",
                semantic_infill_id=f"{topology_path}/infill",
                leaf_slot=None,
                params=params,
                clearance_mm=clearance_mm,
            )
            return
        # Operable hinged leaf (TURN/TILT/TILT_TURN/TOP_HUNG/BOTTOM_HUNG)
        # or a fixed-in-sash lite — both wear the same rectangular sash
        # ring; fixed_in_sash only skips hardware and the handle.
        article = _article(params, _leaf_sash_role(params, spec, first))
        sash = single_rectangular_sash_geometry(
            rect.width_mm, rect.height_mm, article, params
        )
        direct_rect = _Rect(
            rect.x_mm - params.sash_overlap_mm,
            rect.y_mm - params.sash_overlap_mm,
            sash.finished_width_mm,
            sash.finished_height_mm,
        )
        _append_leaf(
            accumulator,
            ctx=_LeafCtx(
                node=node,
                leaf=first,
                spec=spec,
                trace_opening=leaf_trace_opening(spec, first, node.opening_type),
                handle_expected=_handle_expected(first),
            ),
            leaf_id=None,
            topology_path=topology_path,
            reference_rect=rect,
            direct_rect=direct_rect,
            sash=sash,
            params=params,
            clearance_mm=clearance_mm,
        )
        return
    _append_hinged_pair(
        accumulator,
        node=node,
        spec=spec,
        rect=rect,
        topology_path=topology_path,
        params=params,
        clearance_mm=clearance_mm,
        unit_kind=unit_kind,
    )


def _append_door_leaf(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
    spec: OpeningSpec,
    leaf: BayLeaf,
    rect: _Rect,
    topology_path: str,
    params: SystemParams,
    clearance_mm: Decimal,
) -> None:
    """One hinged leaf of a door unit (D03): the leaf clears its reveal
    sides by `door_leaf_side_clearance_mm`, overlaps the member above by
    `sash_overlap_mm` and keeps `door_bottom_clearance_mm` over the
    threshold. Rect is the leaf's reveal inside the door interior."""
    if params.door_leaf_side_clearance_mm is None:
        raise MissingFabricationAuthority(
            "Missing door authority: door_leaf_side_clearance_mm"
        )
    side = params.door_leaf_side_clearance_mm
    overlap = params.sash_overlap_mm
    outer_width = rect.width_mm - _TWO * side
    outer_height = rect.height_mm - params.door_bottom_clearance_mm + overlap
    sash = _jointed_sash(
        outer_width,
        outer_height,
        _article(params, _leaf_sash_role(params, spec, leaf)),
        params,
    )
    direct_rect = _Rect(
        rect.x_mm + side,
        rect.y_mm - overlap,
        sash.finished_width_mm,
        sash.finished_height_mm,
    )
    _append_leaf(
        accumulator,
        ctx=_LeafCtx(
            node=node,
            leaf=leaf,
            spec=spec,
            trace_opening=leaf_trace_opening(spec, leaf, node.opening_type),
            handle_expected=_handle_expected(leaf),
        ),
        leaf_id=None if leaf.slot == "PRIMARY" else f"{node.id}:{leaf.slot}",
        topology_path=topology_path,
        reference_rect=rect,
        direct_rect=direct_rect,
        sash=sash,
        params=params,
        clearance_mm=clearance_mm,
    )


def _append_hinged_pair(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
    spec: OpeningSpec,
    rect: _Rect,
    topology_path: str,
    params: SystemParams,
    clearance_mm: Decimal,
    unit_kind: UnitKind,
) -> None:
    """Two side-hinged leaves meeting inside one bay (D03): the french
    window and the double door.

    The reveal splits into equal pitches on the 0.01 mm grid (the last
    leaf absorbs the remainder). Meeting-edge offsets from each leaf's
    reveal boundary — positive means the finished edge covers into the
    neighbour's territory:

    * window: outer edges lap `sash_overlap_mm` onto the frame; the
      passive leaf's meeting edge is flush at the boundary; the active
      leaf covers the passive's edge by `sash_overlap_mm`.
    * door: outer edges and the passive meeting edge retract
      `door_leaf_side_clearance_mm`; the active covers the passive's
      finished edge by `sash_overlap_mm`.

    The passive leaf's meeting stile takes the INVERSOR article when the
    catalog declares one (SASH otherwise) and mounts the falleba kit —
    it carries no handle."""
    overlap = params.sash_overlap_mm
    if unit_kind is UnitKind.DOOR:
        if params.door_leaf_side_clearance_mm is None:
            raise MissingFabricationAuthority(
                "Missing door authority: door_leaf_side_clearance_mm"
            )
        side_clearance = params.door_leaf_side_clearance_mm
        bottom_clearance = params.door_bottom_clearance_mm
    else:
        side_clearance = Decimal("0")
        bottom_clearance = Decimal("0")
    count = len(spec.leaves)
    pitch = (rect.width_mm / count).quantize(Decimal("0.01"))
    pitches = [pitch] * (count - 1) + [
        rect.width_mm - pitch * (count - 1)
    ]
    inversor = _meeting_stile_article(params, ProfileRole.INVERSOR)
    x = rect.x_mm
    for index, leaf in enumerate(spec.leaves):
        reveal_x = x
        reveal_w = pitches[index]
        x += pitches[index]
        active = leaf.opening.leaf_role is LeafRole.ACTIVE
        if index == 0:
            left_ext = -side_clearance if unit_kind is UnitKind.DOOR else overlap
        else:
            # Meeting edge on the left: the passive leaf stops at its
            # clearance, the active covers the passive's finished edge by
            # the overlap.
            if unit_kind is UnitKind.DOOR:
                left_ext = (side_clearance + overlap) if active else -side_clearance
            else:
                left_ext = overlap if active else Decimal("0")
        if index == count - 1:
            right_ext = -side_clearance if unit_kind is UnitKind.DOOR else overlap
        else:
            if unit_kind is UnitKind.DOOR:
                right_ext = (side_clearance + overlap) if active else -side_clearance
            else:
                right_ext = overlap if active else Decimal("0")
        finished_left = reveal_x - left_ext
        finished_w = reveal_w + left_ext + right_ext
        finished_h = rect.height_mm - bottom_clearance + overlap
        leaf_rect = _Rect(reveal_x, rect.y_mm, reveal_w, rect.height_mm)
        direct_rect = _Rect(
            finished_left,
            rect.y_mm - overlap,
            finished_w,
            finished_h,
        )
        # The passive leaf's meeting stile is the inversor.
        meetings: dict[str, EffectiveProfileArticle] = {}
        if not active and inversor is not None:
            meetings["RIGHT" if index == 0 else "LEFT"] = inversor
        sash_role = _leaf_sash_role(params, spec, leaf)
        sash = _jointed_sash(
            finished_w,
            finished_h,
            _article(params, sash_role),
            params,
        )
        _append_leaf(
            accumulator,
            ctx=_LeafCtx(
                node=node,
                leaf=leaf,
                spec=spec,
                trace_opening=leaf_trace_opening(spec, leaf, node.opening_type),
                handle_expected=_handle_expected(leaf),
            ),
            leaf_id=f"{node.id}:{leaf.slot}",
            topology_path=topology_path,
            reference_rect=leaf_rect,
            direct_rect=direct_rect,
            sash=sash,
            params=params,
            clearance_mm=clearance_mm,
            meeting_articles=meetings,
        )


def _append_door_unit(
    accumulator: _GeometryAccumulator,
    *,
    top: ParametricNode,
    topology_path: str,
    params: SystemParams,
    nominal_width_mm: Decimal,
    nominal_height_mm: Decimal,
    clearance_mm: Decimal,
) -> None:
    """A door unit's frame (D03): three-sided frame plus a full-width
    threshold, then its bays — door leaves and fixed sidelights — are
    walked inside the door interior like any split tree."""
    frame = _article(params, ProfileRole.FRAME)
    per_end = joint_adjustment_per_end(params, frame)
    _append_profile(
        accumulator,
        article=frame,
        length_mm=nominal_width_mm + _TWO * per_end,
        qty=1,
        welded_ends=2,
        placements=[
            _MemberPlacement(
                "outer-frame/TOP",
                "outer-frame",
                "OUTER_FRAME",
                None,
                "TOP",
                Axis.HORIZONTAL,
                PlacementDomain.DIRECT,
                _trace_segment(Decimal("0"), Decimal("0"), nominal_width_mm, Decimal("0")),
            )
        ],
        params=params,
    )
    _append_profile(
        accumulator,
        article=frame,
        length_mm=nominal_height_mm + per_end,
        qty=2,
        welded_ends=1,
        angle_right=_ANGLE_SQUARE,
        placements=[
            _MemberPlacement(
                "outer-frame/LEFT",
                "outer-frame",
                "OUTER_FRAME",
                None,
                "LEFT",
                Axis.VERTICAL,
                PlacementDomain.DIRECT,
                _trace_segment(Decimal("0"), Decimal("0"), Decimal("0"), nominal_height_mm),
            ),
            _MemberPlacement(
                "outer-frame/RIGHT",
                "outer-frame",
                "OUTER_FRAME",
                None,
                "RIGHT",
                Axis.VERTICAL,
                PlacementDomain.DIRECT,
                _trace_segment(nominal_width_mm, Decimal("0"), nominal_width_mm, nominal_height_mm),
            ),
        ],
        params=params,
    )
    clear_width = nominal_width_mm - _TWO * frame.face_width_mm
    threshold_y = nominal_height_mm - params.door_threshold_mm
    _append_profile(
        accumulator,
        article=_article(params, ProfileRole.THRESHOLD),
        length_mm=clear_width,
        qty=1,
        welded_ends=None,
        angle_left=_ANGLE_SQUARE,
        angle_right=_ANGLE_SQUARE,
        bay_id=top.id,
        placements=[
            _MemberPlacement(
                f"{topology_path}/threshold",
                topology_path,
                f"BAY:{top.id}",
                None,
                "THRESHOLD",
                Axis.HORIZONTAL,
                PlacementDomain.DIRECT,
                _trace_segment(
                    frame.face_width_mm,
                    threshold_y,
                    nominal_width_mm - frame.face_width_mm,
                    threshold_y,
                ),
            )
        ],
        params=params,
    )
    interior = _Rect(
        frame.face_width_mm,
        frame.face_width_mm,
        clear_width,
        nominal_height_mm - frame.face_width_mm - params.door_threshold_mm,
    )
    if top.type is NodeType.BAY:
        _append_bay(
            accumulator,
            node=top,
            rect=interior,
            topology_path=topology_path,
            params=params,
            clearance_mm=clearance_mm,
            unit_kind=UnitKind.DOOR,
        )
        return
    _walk_node(
        accumulator,
        node=top,
        rect=interior,
        local_origin_x_mm=Decimal("0"),
        local_origin_y_mm=Decimal("0"),
        topology_path=topology_path,
        params=params,
        clearance_mm=clearance_mm,
        is_top=True,
        unit_kind=UnitKind.DOOR,
    )


def _append_mullion(
    accumulator: _GeometryAccumulator,
    *,
    article: EffectiveProfileArticle,
    length_mm: Decimal,
    topology_path: str,
    segment: TraceSegmentV1,
    params: SystemParams,
) -> None:
    _append_profile(
        accumulator,
        article=article,
        length_mm=length_mm,
        qty=1,
        welded_ends=0,
        angle_left=_ANGLE_SQUARE,
        angle_right=_ANGLE_SQUARE,
        params=params,
        placements=[
            _MemberPlacement(
                semantic_member_id=f"{topology_path}/mullion",
                topology_path=topology_path,
                assembly=f"SPLIT:{topology_path}",
                leaf_slot=None,
                physical_member_slot="CENTER",
                axis=(Axis.VERTICAL if article.role is ProfileRole.MULLION_V else Axis.HORIZONTAL),
                placement_domain=PlacementDomain.DIRECT,
                direct_segment=segment,
            )
        ],
    )


def _walk_node(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
    rect: _Rect,
    local_origin_x_mm: Decimal,
    local_origin_y_mm: Decimal,
    topology_path: str,
    params: SystemParams,
    clearance_mm: Decimal,
    is_top: bool,
    unit_kind: UnitKind,
) -> None:
    if not is_top and (node.width_mm is not None or node.height_mm is not None):
        raise ValueError("Child node dimensions are derived and must not be supplied")

    accumulator.computation.node_dimensions[node.id] = (
        (accumulator.nominal_width_mm, accumulator.nominal_height_mm)
        if is_top
        else (rect.width_mm, rect.height_mm)
    )

    if node.type is NodeType.BAY:
        _append_bay(
            accumulator,
            node=node,
            rect=rect,
            topology_path=topology_path,
            params=params,
            clearance_mm=clearance_mm,
            unit_kind=unit_kind,
        )
        return

    if node.type not in (NodeType.SPLIT_V, NodeType.SPLIT_H):
        raise ValueError("Only a top-level ROOT wrapper is allowed")
    if node.split_offset_mm is None or node.mullion_profile_sku is None:
        raise ValueError(f"{node.type.value} requires split offset and mullion SKU")
    if len(node.children) != 2:
        raise ValueError(f"{node.type.value} must contain exactly two children")

    if node.type is NodeType.SPLIT_V:
        mullion_role = ProfileRole.MULLION_V
    else:
        mullion_role = ProfileRole.MULLION_H
    mullion_article = _article(params, mullion_role)
    if mullion_article.sku != node.mullion_profile_sku:
        raise ValueError(
            f"Split requests {node.mullion_profile_sku}, but effective article is "
            f"{mullion_article.sku}"
        )

    half_mullion_face = mullion_article.face_width_mm / _TWO
    accumulator.computation.split_axes[node.id] = (
        node.type is NodeType.SPLIT_V,
        node.split_offset_mm,
    )
    if node.type is NodeType.SPLIT_V:
        centerline_mm = local_origin_x_mm + node.split_offset_mm
        first_width_mm = centerline_mm - half_mullion_face - rect.x_mm
        second_x_mm = centerline_mm + half_mullion_face
        second_width_mm = rect.right_mm - second_x_mm
        if first_width_mm <= Decimal("0") or second_width_mm <= Decimal("0"):
            raise ValueError("SPLIT_V produces a non-positive BAY width")
        first_rect = _Rect(rect.x_mm, rect.y_mm, first_width_mm, rect.height_mm)
        second_rect = _Rect(second_x_mm, rect.y_mm, second_width_mm, rect.height_mm)
        mullion_length_mm = rect.height_mm + _TWO * _end_milling_overlap(params)
        mullion_segment = _trace_segment(centerline_mm, rect.y_mm, centerline_mm, rect.bottom_mm)
    else:
        centerline_mm = local_origin_y_mm + node.split_offset_mm
        first_height_mm = centerline_mm - half_mullion_face - rect.y_mm
        second_y_mm = centerline_mm + half_mullion_face
        second_height_mm = rect.bottom_mm - second_y_mm
        if first_height_mm <= Decimal("0") or second_height_mm <= Decimal("0"):
            raise ValueError("SPLIT_H produces a non-positive BAY height")
        first_rect = _Rect(rect.x_mm, rect.y_mm, rect.width_mm, first_height_mm)
        second_rect = _Rect(rect.x_mm, second_y_mm, rect.width_mm, second_height_mm)
        mullion_length_mm = rect.width_mm + _TWO * _end_milling_overlap(params)
        mullion_segment = _trace_segment(rect.x_mm, centerline_mm, rect.right_mm, centerline_mm)

    _append_mullion(
        accumulator,
        article=mullion_article,
        length_mm=mullion_length_mm,
        topology_path=topology_path,
        segment=mullion_segment,
        params=params,
    )
    accumulator.computation.spans.append(
        SpanTechnicalFacts(
            target_id=node.id,
            parent_profile_sku=mullion_article.sku,
            span_mm=rect.height_mm if node.type is NodeType.SPLIT_V else rect.width_mm,
        )
    )
    _walk_node(
        accumulator,
        node=node.children[0],
        rect=first_rect,
        local_origin_x_mm=first_rect.x_mm,
        local_origin_y_mm=first_rect.y_mm,
        topology_path=f"{topology_path}/0",
        params=params,
        clearance_mm=clearance_mm,
        is_top=False,
        unit_kind=unit_kind,
    )
    _walk_node(
        accumulator,
        node=node.children[1],
        rect=second_rect,
        local_origin_x_mm=second_rect.x_mm,
        local_origin_y_mm=second_rect.y_mm,
        topology_path=f"{topology_path}/1",
        params=params,
        clearance_mm=clearance_mm,
        is_top=False,
        unit_kind=unit_kind,
    )


def compute_geometry(
    root: ParametricNode,
    params: SystemParams,
    *,
    is_foiled: bool = False,
    diagnostic: bool = False,
    color_selection: ColorSelection | None = None,
) -> GeometryComputation:
    """Calculate Core geometry, mobile-leaf weights and selected hardware."""

    if params.material not in (MaterialType.PVC, MaterialType.ALUMINIUM):
        raise NotImplementedError(f"{params.material.value} geometry is not supported")

    top, nominal_width_mm, nominal_height_mm = _normalize_top_node(root)
    frame_article = _article(params, ProfileRole.FRAME)
    clear_width_mm = nominal_width_mm - _TWO * frame_article.face_width_mm
    clear_height_mm = nominal_height_mm - _TWO * frame_article.face_width_mm
    if clear_width_mm <= Decimal("0") or clear_height_mm <= Decimal("0"):
        raise ValueError("FRAME face produces a non-positive clear rectangle")

    # D05: the resolved color selection drives the machining finish
    # class, the declared glazing clearance and the leaf-envelope factor;
    # the legacy is_foiled path maps to NON_WHITE + foil clearance.
    if color_selection is not None:
        finish_class = color_selection.finish_class
        envelope_factor = color_selection.envelope_factor()
        clearance_mm = color_selection.glass_clearance_mm(params)
    else:
        finish_class = "NON_WHITE" if is_foiled else "WHITE"
        envelope_factor = Decimal("1")
        clearance_mm = (
            params.glass_clearance_foil_mm if is_foiled else params.glass_clearance_white_mm
        )

    accumulator = _GeometryAccumulator(
        diagnostic=diagnostic,
        top_node_id=top.id,
        nominal_width_mm=nominal_width_mm,
        nominal_height_mm=nominal_height_mm,
        finish_class=finish_class,
        envelope_factor=envelope_factor,
    )
    top_path = f"root/{top.id}"
    # D02: every pane's situational context comes from the declared tree —
    # opening type, distance of the pane bottom to the module base and
    # whether a door leaf sits beside it.
    accumulator.glass_contexts = bay_glass_contexts(top, nominal_height_mm)
    # D03: the top node declares the unit kind — a DOOR unit gets the
    # three-sided frame plus threshold and its bays fabricate door
    # leaves; everything else is a window unit on a four-sided frame.
    # Legacy DOOR_ENTRY/DOOR_DOUBLE top bays resolve to DOOR via
    # `resolve_unit_kind`.
    unit_kind = resolve_unit_kind(top)
    if unit_kind is UnitKind.DOOR:
        accumulator.computation.node_dimensions[top.id] = (nominal_width_mm, nominal_height_mm)
        _append_door_unit(
            accumulator,
            top=top,
            topology_path=top_path,
            params=params,
            nominal_width_mm=nominal_width_mm,
            nominal_height_mm=nominal_height_mm,
            clearance_mm=clearance_mm,
        )
    else:
        # When the frame of a sliding unit separates its bottom rail as a
        # dedicated RAIL article, that member is cut from it (D01).
        bottom_article = None
        if top.type is NodeType.BAY:
            top_spec = assert_opening_allowed(top, params, unit=unit_kind)
            if top_spec.leaves[0].opening.movement is OpeningMovement.SLIDE:
                bottom_article = _optional_article(params, ProfileRole.RAIL)
        _append_frame(
            accumulator,
            frame_article=frame_article,
            params=params,
            nominal_width_mm=nominal_width_mm,
            nominal_height_mm=nominal_height_mm,
            bottom_article=bottom_article,
        )
        frame_clear_rect = _Rect(
            x_mm=frame_article.face_width_mm,
            y_mm=frame_article.face_width_mm,
            width_mm=clear_width_mm,
            height_mm=clear_height_mm,
        )
        _walk_node(
            accumulator,
            node=top,
            rect=frame_clear_rect,
            local_origin_x_mm=Decimal("0"),
            local_origin_y_mm=Decimal("0"),
            topology_path=top_path,
            params=params,
            clearance_mm=clearance_mm,
            is_top=True,
            unit_kind=unit_kind,
        )
    accumulator.computation.manufacturing_trace = GeometryManufacturingTraceV1(
        nominal_width_mm=nominal_width_mm,
        nominal_height_mm=nominal_height_mm,
        members=accumulator.semantic_members,
        leaves=accumulator.semantic_leaves,
        infills=accumulator.semantic_infills,
    )
    for (screw_sku, bay_id, leaf_id), screw_qty in sorted(
        accumulator.screw_fittings.items(),
        key=lambda item: (item[0][0], item[0][1] or "", item[0][2] or ""),
    ):
        accumulator.fittings.append(
            FittingPiece(
                kind="REINFORCEMENT_SCREW",
                sku=screw_sku,
                qty=screw_qty,
                bay_id=bay_id,
                leaf_id=leaf_id,
            )
        )
    if accumulator.contract_valid:
        accumulator.computation.result = build_engine_result(
            profile_cuts=accumulator.profile_cuts,
            reinforcements=accumulator.reinforcements,
            glasses=accumulator.glasses,
            panels=accumulator.panels,
            fittings=accumulator.fittings,
            hardware_items=accumulator.hardware_items,
            leaf_weights=accumulator.leaf_weights,
        )
        if color_selection is not None:
            # D05: stamp the finish pair's identity + declared surcharges
            # onto the BOM — stock, purchases and pricing key on them.
            result = accumulator.computation.result
            assert result is not None
            result.finish_key = color_selection.stock_key()
            result.finish_label = color_selection.display_name()
            result.finish_class = color_selection.finish_class
            result.color_surcharges = apply_color_surcharges(
                color_selection,
                result,
                area_m2=(nominal_width_mm * nominal_height_mm) / Decimal("1000000"),
            )
    return accumulator.computation


def calculate_geometry(
    root: ParametricNode,
    params: SystemParams,
    *,
    is_foiled: bool = False,
    color_selection: ColorSelection | None = None,
) -> EngineResult:
    """Strict public SHOT-06 contract; diagnostic facts never replace a valid BOM."""
    computation = compute_geometry(
        root,
        params,
        is_foiled=is_foiled,
        color_selection=color_selection,
    )
    assert computation.result is not None
    return computation.result
