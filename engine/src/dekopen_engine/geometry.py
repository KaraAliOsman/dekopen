"""Pure deterministic geometry for the SHOT-06 Core Gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from dekopen_engine.bom import build_engine_result
from dekopen_engine.glass import build_glass_piece, exact_glass_weight, exact_glass_area_m2
from dekopen_engine.hardware import (
    NoCompatibleHardwareKit,
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
    MissingFabricationAuthority, base_leaf_weight,
)
from dekopen_engine.models import (
    BayOpeningType,
    EffectiveProfileArticle,
    EngineResult,
    GlassPiece,
    GlazingBeadRule,
    HardwareItem,
    LeafWeight,
    PanelPiece,
    MaterialType,
    NodeType,
    ParametricNode,
    ProfileCut,
    ProfileRole,
    RailType,
    ReinforcementPiece,
    SlidingLayout,
    SlidingPanel,
    SlidingPanelKind,
    SystemParams,
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


class SlidingLayoutError(ValueError):
    """Domain rejection of a sliding topology — carries the issue code and
    params the product evaluator surfaces verbatim."""

    def __init__(self, code: str, message: str, params: dict[str, str]) -> None:
        super().__init__(message)
        self.code = code
        self.params = params


def _moving_panel(index: int, track: int) -> SlidingPanel:
    return SlidingPanel(
        slot=f"P{index + 1}", kind=SlidingPanelKind.MOVING, track=track
    )


# Canonical topologies behind the legacy leaf-count presets: every panel is
# MOVING and adjacent leaves alternate rails — the physical requirement for
# consecutive panels to slide past each other on a dual-rail frame.
_SLIDING_PRESETS: dict[BayOpeningType, SlidingLayout] = {
    BayOpeningType.SLIDING_2L: SlidingLayout(
        tracks=2, panels=[_moving_panel(0, 0), _moving_panel(1, 1)]
    ),
    BayOpeningType.SLIDING_3L: SlidingLayout(
        tracks=2,
        panels=[_moving_panel(0, 0), _moving_panel(1, 1), _moving_panel(2, 0)],
    ),
    BayOpeningType.SLIDING_4L: SlidingLayout(
        tracks=2,
        panels=[
            _moving_panel(0, 0),
            _moving_panel(1, 1),
            _moving_panel(2, 0),
            _moving_panel(3, 1),
        ],
    ),
}


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
    glasses: list[GlassPiece] = field(default_factory=list)
    panels: list[PanelPiece] = field(default_factory=list)
    hardware_items: list[HardwareItem] = field(default_factory=list)
    leaf_weights: list[LeafWeight] = field(default_factory=list)
    semantic_members: list[SemanticMemberTraceV1] = field(default_factory=list)
    semantic_leaves: list[SemanticLeafTraceV1] = field(default_factory=list)
    semantic_infills: list[SemanticInfillTraceV1] = field(default_factory=list)


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
) -> None:
    if length_mm <= Decimal("0"):
        raise ValueError("Profile cut must be positive")
    if qty != len(placements) or len({item.semantic_member_id for item in placements}) != qty:
        raise ValueError("Every physical profile requires one semantic placement")
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
    if welded_ends is not None and article.material is MaterialType.PVC:
        steel_length = reinforcement_cut_length(length_mm, article, welded_ends)
        if steel_length <= Decimal("0"):
            raise ValueError("Reinforcement cut must be positive")
        accumulator.reinforcements.append(
            ReinforcementPiece(
                parent_profile_sku=article.sku,
                reinforcement_sku=article.reinforcement_sku,
                role=article.role,
                length_mm=steel_length,
                qty=qty,
                bay_id=bay_id,
                leaf_id=leaf_id,
            )
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
                reinforcement_sku=(article.reinforcement_sku if steel_length is not None else None),
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
    _append_profile(
        accumulator,
        article=frame_article,
        length_mm=nominal_width_mm + _TWO * joint_adjustment_per_end(params, frame_article),
        qty=2,
        welded_ends=2,
        placements=horizontal,
    )
    _append_profile(
        accumulator,
        article=frame_article,
        length_mm=nominal_height_mm + _TWO * joint_adjustment_per_end(params, frame_article),
        qty=2,
        welded_ends=2,
        placements=vertical,
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
) -> Decimal:
    return (
        finished_mm
        - _TWO * article.face_width_mm
        + _TWO * rebate_depth(params)
        - _TWO * clearance_mm
    )


def _append_leaf(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
    leaf_id: str | None,
    leaf_slot: str,
    topology_path: str,
    reference_rect: _Rect,
    direct_rect: _Rect | None,
    sash: SashGeometry,
    params: SystemParams,
    clearance_mm: Decimal,
) -> None:
    if node.opening_type is None:
        raise ValueError("Physical leaf requires an opening type")
    article = _article(params, ProfileRole.SASH)
    cut_start = len(accumulator.profile_cuts)
    steel_start = len(accumulator.reinforcements)
    semantic_leaf_id = f"{topology_path}/leaf/{leaf_slot}"
    assembly = f"BAY:{node.id}:LEAF:{leaf_slot}"
    placement_domain: Literal[PlacementDomain.DIRECT, PlacementDomain.SLIDING_LEAF] = (
        PlacementDomain.SLIDING_LEAF
        if node.opening_type in _SLIDING_OPENING_TYPES
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
            opening_type=node.opening_type,
            door_handedness=(
                node.door_handedness
                if node.opening_type is BayOpeningType.DOOR_ENTRY
                else None
            ),
            placement_domain=placement_domain,
            reference_rect=_trace_rect(reference_rect),
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
    )
    _append_profile(
        accumulator,
        article=article,
        length_mm=sash.cut_height_mm,
        qty=2,
        welded_ends=2,
        placements=[member("LEFT", Axis.VERTICAL), member("RIGHT", Axis.VERTICAL)],
        bay_id=node.id,
        leaf_id=leaf_id,
    )
    width = _pocket_dimension(sash.finished_width_mm, article, params, clearance_mm)
    height = _pocket_dimension(sash.finished_height_mm, article, params, clearance_mm)
    if node.opening_type in _SLIDING_OPENING_TYPES:
        width -= params.sliding_glazing_deduction_width_mm
        height -= params.sliding_glazing_deduction_height_mm
    infill_kind: Literal["GLASS", "PANEL"]
    if node.opening_type is BayOpeningType.DOOR_ENTRY:
        if node.panel_article_sku is None:
            raise ValueError(f"DOOR_ENTRY {node.id} requires panel_article_sku")
        try:
            rule = params.available_panel_rules[node.panel_article_sku]
        except KeyError as error:
            raise ValueError(f"Missing panel article: {node.panel_article_sku}") from error
        infill_thickness = rule.thickness_mm
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
        if node.glass_thickness_mm is None or node.glass_spec is None:
            raise ValueError(f"BAY {node.id} requires glass_thickness_mm and glass_spec")
        infill_thickness = node.glass_thickness_mm
        infill_weight = exact_glass_weight(width, height, node.glass_spec)
        infill_reason = (
            None if infill_weight is not None
            else f"missing_glass_composition:{node.glass_spec}"
        )
        technical_sku = node.glass_article_sku or ""
        composition = node.glass_spec
        infill_kind = "GLASS"
        accumulator.glasses.append(
            build_glass_piece(
                bay_id=node.id,
                leaf_id=leaf_id,
                width_mm=width,
                height_mm=height,
                glass_spec=node.glass_spec,
                article_sku=technical_sku or None,
            )
        )
    accumulator.computation.infills.append(
        InfillTechnicalFacts(
            bay_id=node.id,
            leaf_id=leaf_id,
            kind=infill_kind,
            thickness_mm=infill_thickness,
            glass_spec=node.glass_spec,
            width_mm=width,
            height_mm=height,
            exact_area_m2=exact_glass_area_m2(width, height),
            bead_supported=infill_thickness in params.glazing_bead_rules,
        )
    )
    semantic_infill_id = f"{semantic_leaf_id}/infill"
    sliding_infill = node.opening_type in _SLIDING_OPENING_TYPES
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
    assert node.opening_type is not None
    candidates = evaluate_hardware_candidates(
        opening=node.opening_type,
        width_mm=sash.finished_width_mm,
        height_mm=sash.finished_height_mm,
        base_weight=base,
        params=params,
        explicit_sku=node.hardware_set_sku,
    )
    try:
        kit, exact_weight = resolve_hardware_evaluations(
            candidates,
            opening=node.opening_type,
            explicit_sku=node.hardware_set_sku,
        )
    except NoCompatibleHardwareKit:
        if not accumulator.diagnostic:
            raise
        accumulator.contract_valid = False
        kit, exact_weight = None, None
    accumulator.computation.leaves.append(
        LeafTechnicalFacts(
            bay_id=node.id,
            leaf_id=leaf_id,
            opening_type=node.opening_type,
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
    accumulator.hardware_items.append(
        HardwareItem(
            kit_sku=kit.sku,
            name=kit.name,
            bay_id=node.id,
            leaf_id=leaf_id,
            contents=[component.model_copy() for component in kit.contents],
        )
    )
    accumulator.leaf_weights.append(exact_weight.public_result(node.id, leaf_id))


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
    if node.glass_thickness_mm is None or node.glass_spec is None:
        raise ValueError(f"BAY {node.id} requires glass_thickness_mm and glass_spec")
    leaf_id = f"{node.id}:{leaf_slot}" if leaf_slot is not None else None
    width = rect.width_mm + _TWO * rebate_depth(params) - _TWO * clearance_mm
    height = rect.height_mm + _TWO * rebate_depth(params) - _TWO * clearance_mm
    accumulator.glasses.append(
        build_glass_piece(
            bay_id=node.id,
            leaf_id=leaf_id,
            width_mm=width,
            height_mm=height,
            glass_spec=node.glass_spec,
            article_sku=node.glass_article_sku or None,
        )
    )
    accumulator.computation.infills.append(
        InfillTechnicalFacts(
            bay_id=node.id,
            leaf_id=leaf_id,
            kind="GLASS",
            thickness_mm=node.glass_thickness_mm,
            glass_spec=node.glass_spec,
            width_mm=width,
            height_mm=height,
            exact_area_m2=exact_glass_area_m2(width, height),
            bead_supported=node.glass_thickness_mm in params.glazing_bead_rules,
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
            composition=node.glass_spec,
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
        infill_thickness_mm=node.glass_thickness_mm,
        width_mm=width,
        height_mm=height,
    )


def _append_sliding(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
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
    article = _article(params, ProfileRole.SASH)
    count = len(layout.panels)
    # Equal pitches floored to the canonical 0.01 mm grid; the last slot
    # absorbs the remainder so the slots tile the frame exactly and every
    # derived measure stays serializable (a raw n-division can repeat).
    pitch = (
        (rect.width_mm - params.central_overlap_mm) / count
    ).quantize(Decimal("0.01"))
    pitches = [pitch] * (count - 1) + [
        rect.width_mm - params.central_overlap_mm - pitch * (count - 1)
    ]
    cut_height = rect.height_mm - _TWO * params.pulley_height_mm
    adjustment = joint_adjustment_per_end(params, article)
    slot_x = rect.x_mm
    for index, panel in enumerate(layout.panels):
        finished_width = pitches[index] + params.central_overlap_mm
        if panel.kind is SlidingPanelKind.MOVING:
            leaf_slot = f"L{index + 1}"
            cut_width = finished_width + params.sliding_end_add_mm
            sash = SashGeometry(
                finished_width_mm=cut_width - _TWO * adjustment,
                finished_height_mm=cut_height - _TWO * adjustment,
                cut_width_mm=cut_width,
                cut_height_mm=cut_height,
            )
            _append_leaf(
                accumulator,
                node=node,
                leaf_id=f"{node.id}:{leaf_slot}",
                leaf_slot=leaf_slot,
                topology_path=topology_path,
                reference_rect=rect,
                direct_rect=None,
                sash=sash,
                params=params,
                clearance_mm=clearance_mm,
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
) -> None:
    opening = node.opening_type
    if opening is None:
        raise ValueError(f"BAY {node.id} requires opening_type")
    if opening not in SUPPORTED_OPENING_TYPES:
        raise NotImplementedError(f"{opening.value} geometry is outside SHOT-06 Core")
    if opening is BayOpeningType.DOOR_ENTRY:
        raise NotImplementedError("DOOR_ENTRY requires a top-level BAY in SHOT-06 Core")
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
    if opening is BayOpeningType.FIXED:
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
    article = _article(params, ProfileRole.SASH)
    if opening in _OPERABLE_OPENING_TYPES:
        sash = single_rectangular_sash_geometry(rect.width_mm, rect.height_mm, article, params)
        direct_rect = _Rect(
            rect.x_mm - params.sash_overlap_mm,
            rect.y_mm - params.sash_overlap_mm,
            sash.finished_width_mm,
            sash.finished_height_mm,
        )
        _append_leaf(
            accumulator,
            node=node,
            leaf_id=None,
            leaf_slot="PRIMARY",
            topology_path=topology_path,
            reference_rect=rect,
            direct_rect=direct_rect,
            sash=sash,
            params=params,
            clearance_mm=clearance_mm,
        )
    elif opening in _SLIDING_OPENING_TYPES:
        _append_sliding(
            accumulator,
            node=node,
            topology_path=topology_path,
            rect=rect,
            params=params,
            clearance_mm=clearance_mm,
        )


def _append_door(
    accumulator: _GeometryAccumulator,
    *,
    node: ParametricNode,
    topology_path: str,
    params: SystemParams,
    nominal_width_mm: Decimal,
    nominal_height_mm: Decimal,
    clearance_mm: Decimal,
) -> None:
    accumulator.computation.openings.append(
        OpeningTechnicalFacts(
            bay_id=node.id,
            width_mm=nominal_width_mm,
            height_mm=nominal_height_mm,
        )
    )
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
        bay_id=node.id,
        placements=[
            _MemberPlacement(
                f"{topology_path}/threshold",
                topology_path,
                f"BAY:{node.id}",
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
    )
    outer_width = clear_width - _TWO * params.door_leaf_side_clearance_mm
    outer_height = (
        nominal_height_mm
        - frame.face_width_mm
        - params.door_threshold_mm
        - params.door_bottom_clearance_mm
        + params.sash_overlap_mm
    )
    sash = _jointed_sash(outer_width, outer_height, _article(params, ProfileRole.SASH), params)
    reference_rect = _Rect(
        frame.face_width_mm,
        frame.face_width_mm,
        clear_width,
        nominal_height_mm - frame.face_width_mm - params.door_threshold_mm,
    )
    direct_rect = _Rect(
        frame.face_width_mm + params.door_leaf_side_clearance_mm,
        frame.face_width_mm - params.sash_overlap_mm,
        sash.finished_width_mm,
        sash.finished_height_mm,
    )
    _append_leaf(
        accumulator,
        node=node,
        leaf_id=None,
        leaf_slot="PRIMARY",
        topology_path=topology_path,
        reference_rect=reference_rect,
        direct_rect=direct_rect,
        sash=sash,
        params=params,
        clearance_mm=clearance_mm,
    )


def _append_mullion(
    accumulator: _GeometryAccumulator,
    *,
    article: EffectiveProfileArticle,
    length_mm: Decimal,
    topology_path: str,
    segment: TraceSegmentV1,
) -> None:
    _append_profile(
        accumulator,
        article=article,
        length_mm=length_mm,
        qty=1,
        welded_ends=0,
        angle_left=_ANGLE_SQUARE,
        angle_right=_ANGLE_SQUARE,
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
    )


def compute_geometry(
    root: ParametricNode,
    params: SystemParams,
    *,
    is_foiled: bool = False,
    diagnostic: bool = False,
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

    accumulator = _GeometryAccumulator(
        diagnostic=diagnostic,
        top_node_id=top.id,
        nominal_width_mm=nominal_width_mm,
        nominal_height_mm=nominal_height_mm,
    )
    clearance_mm = params.glass_clearance_foil_mm if is_foiled else params.glass_clearance_white_mm
    top_path = f"root/{top.id}"
    if top.type is NodeType.BAY and top.opening_type is BayOpeningType.DOOR_ENTRY:
        accumulator.computation.node_dimensions[top.id] = (nominal_width_mm, nominal_height_mm)
        _append_door(
            accumulator,
            node=top,
            topology_path=top_path,
            params=params,
            nominal_width_mm=nominal_width_mm,
            nominal_height_mm=nominal_height_mm,
            clearance_mm=clearance_mm,
        )
    else:
        _append_frame(
            accumulator,
            frame_article=frame_article,
            params=params,
            nominal_width_mm=nominal_width_mm,
            nominal_height_mm=nominal_height_mm,
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
        )
    accumulator.computation.manufacturing_trace = GeometryManufacturingTraceV1(
        nominal_width_mm=nominal_width_mm,
        nominal_height_mm=nominal_height_mm,
        members=accumulator.semantic_members,
        leaves=accumulator.semantic_leaves,
        infills=accumulator.semantic_infills,
    )
    if accumulator.contract_valid:
        accumulator.computation.result = build_engine_result(
            profile_cuts=accumulator.profile_cuts,
            reinforcements=accumulator.reinforcements,
            glasses=accumulator.glasses,
            panels=accumulator.panels,
            hardware_items=accumulator.hardware_items,
            leaf_weights=accumulator.leaf_weights,
        )
    return accumulator.computation


def calculate_geometry(
    root: ParametricNode,
    params: SystemParams,
    *,
    is_foiled: bool = False,
) -> EngineResult:
    """Strict public SHOT-06 contract; diagnostic facts never replace a valid BOM."""
    computation = compute_geometry(root, params, is_foiled=is_foiled)
    assert computation.result is not None
    return computation.result
