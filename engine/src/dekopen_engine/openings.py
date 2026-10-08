"""D03 — Opening model resolution, legacy mapping and capability checks.

`Opening` (movement × hinge side × direction × leaf role × fixed_in_sash)
replaces `BayOpeningType` as the source of truth. This module owns the
total enum ↔ spec mapping, the canonical leaf keys, the hardware group a
leaf resolves against, the per-system capability admission and the
Spanish display names the whole product shares.
"""

from __future__ import annotations

from typing import Literal

from dekopen_engine.models import (
    BayLeaf,
    BayOpeningType,
    HingeSide,
    LeafRole,
    Opening,
    OpeningCapability,
    OpeningDirection,
    OpeningMovement,
    OpeningSpec,
    ParametricNode,
    ProfileRole,
    SystemFamily,
    SystemParams,
    UnitKind,
)


# Slide-family movements that fabricate inside a track topology — the
# same `_append_sliding` path serves corredera, elevable and
# osciloparalela; the movement only changes the leaf's hardware family
# and its symbology.
SLIDE_FAMILY_MOVEMENTS = frozenset(
    {
        OpeningMovement.SLIDE,
        OpeningMovement.LIFT_SLIDE,
        OpeningMovement.PARALLEL_SLIDE,
    }
)


# --- Legacy enum ↔ spec mapping ---------------------------------------

_SINGLE_LEAF_MAP: dict[BayOpeningType, Opening] = {
    BayOpeningType.FIXED: Opening(movement=OpeningMovement.FIXED),
    BayOpeningType.TURN_LEFT: Opening(
        movement=OpeningMovement.TURN,
        hinge_side=HingeSide.LEFT,
        direction=OpeningDirection.INWARD,
    ),
    BayOpeningType.TURN_RIGHT: Opening(
        movement=OpeningMovement.TURN,
        hinge_side=HingeSide.RIGHT,
        direction=OpeningDirection.INWARD,
    ),
    BayOpeningType.TILT_TURN_LEFT: Opening(
        movement=OpeningMovement.TILT_TURN,
        hinge_side=HingeSide.LEFT,
        direction=OpeningDirection.INWARD,
    ),
    BayOpeningType.TILT_TURN_RIGHT: Opening(
        movement=OpeningMovement.TILT_TURN,
        hinge_side=HingeSide.RIGHT,
        direction=OpeningDirection.INWARD,
    ),
    BayOpeningType.AWNING: Opening(
        movement=OpeningMovement.TOP_HUNG,
        hinge_side=HingeSide.TOP,
        direction=OpeningDirection.OUTWARD,
    ),
    BayOpeningType.SLIDING_2L: Opening(movement=OpeningMovement.SLIDE),
    BayOpeningType.SLIDING_3L: Opening(movement=OpeningMovement.SLIDE),
    BayOpeningType.SLIDING_4L: Opening(movement=OpeningMovement.SLIDE),
    BayOpeningType.SLIDING: Opening(movement=OpeningMovement.SLIDE),
}

_SLIDING_LEGACY_TYPES = frozenset(
    {
        BayOpeningType.SLIDING_2L,
        BayOpeningType.SLIDING_3L,
        BayOpeningType.SLIDING_4L,
        BayOpeningType.SLIDING,
    }
)


def _double_door_leaves(
    door_handedness: str | None,
) -> tuple[BayLeaf, BayLeaf]:
    """DOOR_DOUBLE as a leaf pair: the handedness names the ACTIVE leaf's
    hinge side — it sits on that side of the pair."""
    active_side = door_handedness or "LEFT"
    if active_side == "RIGHT":
        return (
            BayLeaf(
                slot="L1",
                opening=Opening(
                    movement=OpeningMovement.TURN,
                    hinge_side=HingeSide.LEFT,
                    direction=OpeningDirection.INWARD,
                    leaf_role=LeafRole.PASSIVE,
                ),
            ),
            BayLeaf(
                slot="L2",
                opening=Opening(
                    movement=OpeningMovement.TURN,
                    hinge_side=HingeSide.RIGHT,
                    direction=OpeningDirection.INWARD,
                    leaf_role=LeafRole.ACTIVE,
                ),
            ),
        )
    return (
        BayLeaf(
            slot="L1",
            opening=Opening(
                movement=OpeningMovement.TURN,
                hinge_side=HingeSide.LEFT,
                direction=OpeningDirection.INWARD,
                leaf_role=LeafRole.ACTIVE,
            ),
        ),
        BayLeaf(
            slot="L2",
            opening=Opening(
                movement=OpeningMovement.TURN,
                hinge_side=HingeSide.RIGHT,
                direction=OpeningDirection.INWARD,
                leaf_role=LeafRole.PASSIVE,
            ),
        ),
    )


def spec_for_legacy(
    opening_type: BayOpeningType,
    door_handedness: str | None = None,
) -> OpeningSpec:
    """Total mapping: every enum value decodes to exactly one spec."""
    if opening_type is BayOpeningType.DOOR_ENTRY:
        side = door_handedness or "LEFT"
        return OpeningSpec(
            unit_kind=UnitKind.DOOR,
            leaves=[
                BayLeaf(
                    slot="PRIMARY",
                    opening=Opening(
                        movement=OpeningMovement.TURN,
                        hinge_side=HingeSide(side),
                        direction=OpeningDirection.INWARD,
                    ),
                )
            ],
        )
    if opening_type is BayOpeningType.DOOR_DOUBLE:
        return OpeningSpec(
            unit_kind=UnitKind.DOOR,
            leaves=list(_double_door_leaves(door_handedness)),
        )
    return OpeningSpec(
        unit_kind=UnitKind.WINDOW,
        leaves=[BayLeaf(slot="PRIMARY", opening=_SINGLE_LEAF_MAP[opening_type])],
    )


def legacy_openings_for_spec(spec: OpeningSpec) -> frozenset[BayOpeningType]:
    """Enum values a spec could equal — the set is empty for specs the
    enum could never express (outward turn, french window, fixed in
    sash, ...)."""
    if len(spec.leaves) != 1:
        if spec.unit_kind is UnitKind.DOOR and len(spec.leaves) == 2:
            if all(
                leaf.opening.movement is OpeningMovement.TURN
                and leaf.opening.direction is OpeningDirection.INWARD
                for leaf in spec.leaves
            ):
                return frozenset({BayOpeningType.DOOR_DOUBLE})
        return frozenset()
    opening = spec.leaves[0].opening
    if spec.unit_kind is UnitKind.DOOR:
        if (
            opening.movement is OpeningMovement.TURN
            and opening.hinge_side in (HingeSide.LEFT, HingeSide.RIGHT)
            and opening.direction is OpeningDirection.INWARD
        ):
            return frozenset({BayOpeningType.DOOR_ENTRY})
        return frozenset()
    for legacy, mapped in _SINGLE_LEAF_MAP.items():
        if mapped == opening:
            if legacy in _SLIDING_LEGACY_TYPES:
                return _SLIDING_LEGACY_TYPES
            return frozenset({legacy})
    return frozenset()


def declared_unit_kind(node: ParametricNode) -> UnitKind | None:
    """The unit kind a node explicitly carries — its own `unit_kind` or
    the one a legacy door enum implies."""
    if node.unit_kind is not None:
        return node.unit_kind
    if node.opening_type in (BayOpeningType.DOOR_ENTRY, BayOpeningType.DOOR_DOUBLE):
        return UnitKind.DOOR
    return None


def resolve_unit_kind(top: ParametricNode) -> UnitKind:
    """The unit kind a top-level node builds: declared on the node, or
    implied by a legacy door opening type."""
    return declared_unit_kind(top) or UnitKind.WINDOW


def resolve_opening_spec(
    node: ParametricNode, *, default_unit: UnitKind = UnitKind.WINDOW
) -> OpeningSpec:
    """The bay's canonical opening — whichever declaration form was used.

    `opening`/`leaves`/`unit_kind` is the canonical form (D03);
    `opening_type` stays accepted for one version. When both forms are
    present they must agree — a disagreement is a conflicting
    declaration, not a guess. `default_unit` is the enclosing unit's
    kind: a nested bay inherits it unless it declares its own."""
    declared: OpeningSpec | None = None
    if node.leaves:
        declared = OpeningSpec(
            unit_kind=node.unit_kind or default_unit,
            leaves=list(node.leaves),
        )
    elif node.opening is not None:
        declared = OpeningSpec(
            unit_kind=node.unit_kind or default_unit,
            leaves=[BayLeaf(slot="PRIMARY", opening=node.opening)],
        )
    legacy: OpeningSpec | None = None
    if node.opening_type is not None:
        legacy = spec_for_legacy(node.opening_type, node.door_handedness)
    if declared is not None:
        if node.opening_type is not None:
            if node.opening_type not in legacy_openings_for_spec(declared):
                raise ValueError(
                    f"BAY {node.id} declares {node.opening_type.value} but also an "
                    "opening spec that does not equal it — one declaration must go"
                )
        return declared
    if legacy is not None:
        return legacy
    raise ValueError(f"BAY {node.id} requires opening_type or opening")


def leaf_trace_opening(
    spec: OpeningSpec, leaf: BayLeaf, declared_type: BayOpeningType | None
) -> str:
    """The `opening_type` value a leaf trace emits (D03).

    A legacy-declared bay emits its enum verbatim — frozen documents and
    handle policies written against the old names keep resolving. A
    new-form spec that still maps to one enum value emits that value;
    everything else emits the leaf's canonical key (``DOOR:``-prefixed
    inside a door unit)."""
    if declared_type is not None:
        return declared_type.value
    unit_legacy = legacy_openings_for_spec(spec)
    if len(unit_legacy) == 1:
        return next(iter(unit_legacy)).value
    key = leaf.opening.key()
    return f"DOOR:{key}" if spec.unit_kind is UnitKind.DOOR else key


def leaf_policy_opening_candidates(opening_type: str) -> list[str]:
    """Keys a leaf trace tries against handle-policy rules, most specific
    first (D03): the emitted key itself, then the legacy enum whose mount
    geometry the leaf shares — direction never moves the lock jamb, so an
    OUTWARD abatible mounts exactly like its INWARD counterpart — then
    the bare movement axis for catalog-declared rows like TILT."""
    candidates = [opening_type]
    parts = opening_type.split(":")
    door = parts[0] == "DOOR"
    if door:
        parts = parts[1:]
    movement = parts[0]
    axes = [part for part in parts[1:] if part not in ("ACTIVE", "PASSIVE")]
    hinge = axes[0] if axes else None
    aliases: list[str] = []
    if movement == "TURN" and hinge in ("LEFT", "RIGHT"):
        aliases.append("DOOR_ENTRY" if door else f"TURN_{hinge}")
    elif movement == "TILT_TURN" and hinge in ("LEFT", "RIGHT"):
        aliases.append(f"TILT_TURN_{hinge}")
    elif movement == "TOP_HUNG":
        aliases.append("AWNING")
    if door:
        aliases.append(f"DOOR:{movement}")
    aliases.append(movement)
    for alias in aliases:
        if alias not in candidates:
            candidates.append(alias)
    return candidates


def leaf_hinge_handedness(leaf: BayLeaf) -> Literal["LEFT", "RIGHT"] | None:
    """The leaf's hinge side when it is a side-hinged leaf — the
    handedness handle policies pin door mounts on."""
    if leaf.opening.hinge_side in (HingeSide.LEFT, HingeSide.RIGHT):
        return "LEFT" if leaf.opening.hinge_side is HingeSide.LEFT else "RIGHT"
    return None


def leaf_hardware_group(spec: OpeningSpec, leaf: BayLeaf) -> str | None:
    """The hardware-kit family a leaf evaluates against (D03).

    None means the leaf takes no kit (fixed lites). A PASSIVE leaf takes
    the falleba/flush-bolt set; a door leaf the DOOR family; the rest map
    their movement to the legacy kit families so seeded catalogs keep
    matching."""
    opening = leaf.opening
    if opening.fixed_in_sash:
        return None
    # A folding pack leaf mounts the fold set (carriages, guides,
    # intermediate hinges) — not the falleba of a hinged passive leaf.
    if opening.movement is OpeningMovement.FOLD and opening.leaf_role is LeafRole.PASSIVE:
        return "FOLD"
    if opening.leaf_role is LeafRole.PASSIVE:
        return "FALLEBA"
    if spec.unit_kind is UnitKind.DOOR:
        # A sliding leaf inside a door unit is a puerta corredera — its
        # kit is the sliding-door family (rollers + patio lock), not the
        # hinged-door multipoint.
        if opening.movement in SLIDE_FAMILY_MOVEMENTS:
            return "DOOR_SLIDING"
        if opening.movement in (OpeningMovement.PIVOT_V, OpeningMovement.PIVOT_H):
            # Una puerta pivotante monta el kit de pivote (pivotes + tirador),
            # no el multipunto de puerta practicable.
            return "PIVOT"
        return "DOOR"
    return {
        OpeningMovement.TURN: "TURN",
        OpeningMovement.TILT: "TILT",
        OpeningMovement.TILT_TURN: "TILT_TURN",
        OpeningMovement.TOP_HUNG: "AWNING",
        OpeningMovement.BOTTOM_HUNG: "BOTTOM_HUNG",
        OpeningMovement.SLIDE: "SLIDING",
        # D08 kit families — declared per system in hardware_kits.
        OpeningMovement.LIFT_SLIDE: "LIFT_SLIDE",
        OpeningMovement.PARALLEL_SLIDE: "PARALLEL_SLIDE",
        # The fold pack's ACTIVE leaf is the hoja de paso: on a door unit
        # the branch above already resolved it as DOOR; on a window it is
        # a hinged leaf with lock and handle — a TURN-family kit.
        OpeningMovement.FOLD: "TURN",
        OpeningMovement.PIVOT_V: "PIVOT",
        OpeningMovement.PIVOT_H: "PIVOT",
        OpeningMovement.VERTICAL_SLIDE: "VERTICAL_SLIDE",
    }.get(opening.movement)


def leaf_sash_role_candidates(spec: OpeningSpec, leaf: BayLeaf) -> tuple[ProfileRole, ProfileRole]:
    """(dedicated role, fallback role) for a leaf's sash article (D08).

    Every leaf that runs on channels — corredera, elevable,
    osciloparalela, guillotina — is cut from the sliding sash profile
    when the catalog carries one, on window and door units alike. A
    pivot door leaf wears the door sash; folding and window pivots use
    the standard sash profile."""
    if leaf.opening.movement in SLIDE_FAMILY_MOVEMENTS | {
        OpeningMovement.VERTICAL_SLIDE
    }:
        return ProfileRole.SLIDING_SASH, ProfileRole.SASH
    if spec.unit_kind is UnitKind.DOOR:
        return ProfileRole.DOOR_SASH, ProfileRole.SASH
    return ProfileRole.SASH, ProfileRole.SASH


# --- Capabilities ------------------------------------------------------

# The family's physical repertoire expressed as capability rows — the
# fallback for systems that never declared `opening_capabilities`. It
# admits what the family can physically fabricate, never what another
# family could; the catalog's declared rows narrow it per system.
def _legacy_capabilities(family: SystemFamily) -> tuple[OpeningCapability, ...]:
    window = (UnitKind.WINDOW,)
    door = (UnitKind.DOOR,)
    both_units = (UnitKind.WINDOW, UnitKind.DOOR)
    any_roles = (LeafRole.SINGLE, LeafRole.ACTIVE, LeafRole.PASSIVE)
    any_direction = (OpeningDirection.INWARD, OpeningDirection.OUTWARD)
    fixed = OpeningCapability(
        movement=OpeningMovement.FIXED,
        unit_kinds=both_units,
        max_leaves=2,
        fixed_in_sash=True,
    )
    if family is SystemFamily.CASEMENT:
        return (
            fixed,
            # The whole hinged repertoire on both units: abatible,
            # oscilobatiente, banderola, proyectante, abatimiento abajo,
            # hojas simples y pares (ventana francesa / puerta doble).
            OpeningCapability(
                movement=OpeningMovement.TURN,
                directions=any_direction,
                leaf_roles=any_roles,
                unit_kinds=both_units,
                max_leaves=2,
            ),
            OpeningCapability(
                movement=OpeningMovement.TILT_TURN,
                directions=(OpeningDirection.INWARD,),
                leaf_roles=any_roles,
                unit_kinds=window,
                max_leaves=2,
            ),
            OpeningCapability(
                movement=OpeningMovement.TILT,
                directions=(OpeningDirection.INWARD,),
                unit_kinds=window,
            ),
            OpeningCapability(
                movement=OpeningMovement.TOP_HUNG,
                directions=(OpeningDirection.OUTWARD,),
                unit_kinds=window,
            ),
            OpeningCapability(
                movement=OpeningMovement.BOTTOM_HUNG,
                directions=any_direction,
                unit_kinds=window,
            ),
        )
    if family is SystemFamily.SLIDING:
        # Sliding families physically build window and patio-door units —
        # a system may narrow this to window-only via declared rows.
        return (
            fixed,
            OpeningCapability(movement=OpeningMovement.SLIDE, unit_kinds=both_units),
        )
    if family is SystemFamily.LIFT_SLIDE:
        return (
            fixed,
            OpeningCapability(movement=OpeningMovement.SLIDE, unit_kinds=both_units),
            OpeningCapability(
                movement=OpeningMovement.LIFT_SLIDE, unit_kinds=both_units
            ),
        )
    if family is SystemFamily.PARALLEL_SLIDE:
        return (
            fixed,
            OpeningCapability(
                movement=OpeningMovement.PARALLEL_SLIDE, unit_kinds=both_units
            ),
        )
    if family is SystemFamily.FOLDING:
        # A folding series composes packs up to the family's physical
        # ceiling on windows and doors; the catalog narrows the count.
        return (
            fixed,
            OpeningCapability(
                movement=OpeningMovement.FOLD,
                directions=any_direction,
                leaf_roles=(LeafRole.ACTIVE, LeafRole.PASSIVE),
                unit_kinds=both_units,
                max_leaves=8,
            ),
        )
    if family is SystemFamily.PIVOT:
        return (
            fixed,
            OpeningCapability(
                movement=OpeningMovement.PIVOT_V, unit_kinds=both_units
            ),
            OpeningCapability(
                movement=OpeningMovement.PIVOT_H, unit_kinds=both_units
            ),
        )
    if family is SystemFamily.VERTICAL_SLIDE:
        return (
            fixed,
            OpeningCapability(
                movement=OpeningMovement.VERTICAL_SLIDE,
                unit_kinds=window,
                max_leaves=2,
            ),
        )
    if family is SystemFamily.DOOR:
        return (
            fixed,
            OpeningCapability(
                movement=OpeningMovement.TURN,
                directions=any_direction,
                leaf_roles=any_roles,
                unit_kinds=door,
                max_leaves=2,
            ),
        )
    return (fixed,)


def default_capabilities_for_family(
    family: SystemFamily,
) -> tuple[OpeningCapability, ...]:
    """The family-repertoire fallback — what a system fabricates when it
    declared no capability rows of its own."""
    return _legacy_capabilities(family)


def admitted_capabilities(params: SystemParams) -> tuple[OpeningCapability, ...]:
    """The rows that decide what a system may offer (D03): the declared
    catalog capability set, or the family's legacy-expressible openings
    when it was never declared."""
    if params.opening_capabilities:
        return params.opening_capabilities
    return _legacy_capabilities(params.system_family)


# Movements whose two-leaf compositions physically close (the spec
# validator shares this set): abatible y oscilobatiente forman pares.
_PAIRABLE_MOVEMENTS = frozenset(
    {OpeningMovement.TURN, OpeningMovement.TILT_TURN}
)


def spec_options_from_capabilities(
    capabilities: tuple[OpeningCapability, ...],
) -> list[dict[str, object]]:
    """The concrete opening options a system's capability rows offer
    (D03): one descriptor per admissible composition — movement × side ×
    direction × leaf count — with its Spanish display name and the spec
    payload the editor/API sends back.

    Descriptors: `{"key", "name", "unit_kind", "opening"|"leaves",
    "legacy"}`. `legacy` names the enum value the option equals (or None);
    `opening` is a single-leaf payload, `leaves` a pair payload. Only one
    of the two keys is present."""
    options: list[dict[str, object]] = []
    seen: set[str] = set()
    for cap in capabilities:
        if cap.movement is OpeningMovement.FOLD:
            _emit_fold_options(options, seen, cap)
            continue
        if cap.movement is OpeningMovement.VERTICAL_SLIDE:
            _emit_vertical_slide_options(options, seen, cap, capabilities)
            continue
        for unit_kind in cap.unit_kinds:
            # Directions the row admits; FIXED/SLIDE-family leaves carry
            # none (their kinematics forbid it).
            directions: tuple[OpeningDirection | None, ...] = (
                cap.directions or (None,)
            )
            single = LeafRole.SINGLE in cap.leaf_roles
            pairable = (
                cap.max_leaves == 2
                and cap.movement in _PAIRABLE_MOVEMENTS
                and LeafRole.ACTIVE in cap.leaf_roles
                and LeafRole.PASSIVE in cap.leaf_roles
            )
            for direction in directions:
                if single:
                    for hinge in _hinge_variants(cap.movement):
                        # FIXED rows emit the frame-fixed option plus the
                        # sash variant when the row allows fijo en hoja;
                        # every other movement emits its single form.
                        sash_variants = (
                            (False, True)
                            if cap.movement is OpeningMovement.FIXED
                            else (cap.fixed_in_sash,)
                        )
                        for fixed_in_sash in sash_variants:
                            spec = _single_spec(
                                cap.movement, hinge, direction, unit_kind,
                                fixed_in_sash,
                            )
                            if spec is None:
                                continue
                            _emit_option(options, seen, spec)
                if pairable and direction is not None:
                    for active_side in (HingeSide.RIGHT, HingeSide.LEFT):
                        spec = _pair_spec(
                            cap.movement, direction, unit_kind, active_side
                        )
                        if spec is None:
                            continue
                        _emit_option(options, seen, spec)
    return options


def _hinge_variants(movement: OpeningMovement) -> tuple[HingeSide, ...]:
    """The hinge sides an option enumerates for a movement — sides the
    kinematics fix (TOP/BOTTOM) emit once, side-hinged movements emit
    both hands."""
    if movement in (OpeningMovement.TURN, OpeningMovement.TILT_TURN):
        return (HingeSide.LEFT, HingeSide.RIGHT)
    if movement is OpeningMovement.TOP_HUNG:
        return (HingeSide.TOP,)
    if movement in (OpeningMovement.TILT, OpeningMovement.BOTTOM_HUNG):
        return (HingeSide.BOTTOM,)
    return (HingeSide.NONE,)


def _single_spec(
    movement: OpeningMovement,
    hinge: HingeSide,
    direction: OpeningDirection | None,
    unit_kind: UnitKind,
    fixed_in_sash: bool,
) -> OpeningSpec | None:
    try:
        leaf = BayLeaf(
            slot="PRIMARY",
            opening=Opening(
                movement=movement,
                hinge_side=hinge,
                direction=direction,
                leaf_role=LeafRole.SINGLE,
                fixed_in_sash=fixed_in_sash and movement is OpeningMovement.FIXED,
            ),
        )
        return OpeningSpec(unit_kind=unit_kind, leaves=[leaf])
    except ValueError:
        return None


def _pair_spec(
    movement: OpeningMovement,
    direction: OpeningDirection,
    unit_kind: UnitKind,
    active_hinge: HingeSide,
) -> OpeningSpec | None:
    """The french/double-door pair: outer hinges, the ACTIVE leaf on the
    given side carrying the handle and covering the meeting stile."""
    try:
        leaves = [
            BayLeaf(
                slot="L1",
                opening=Opening(
                    movement=movement,
                    hinge_side=HingeSide.LEFT,
                    direction=direction,
                    leaf_role=(
                        LeafRole.ACTIVE
                        if active_hinge is HingeSide.LEFT
                        else LeafRole.PASSIVE
                    ),
                ),
            ),
            BayLeaf(
                slot="L2",
                opening=Opening(
                    movement=movement,
                    hinge_side=HingeSide.RIGHT,
                    direction=direction,
                    leaf_role=(
                        LeafRole.ACTIVE
                        if active_hinge is HingeSide.RIGHT
                        else LeafRole.PASSIVE
                    ),
                ),
            ),
        ]
        return OpeningSpec(unit_kind=unit_kind, leaves=leaves)
    except ValueError:
        return None


def _fold_spec(
    count: int,
    left_count: int,
    direction: OpeningDirection,
    unit_kind: UnitKind,
    *,
    active_at: int | None = None,
) -> OpeningSpec | None:
    """One folding composition: `left_count` LEFT-hinged leaves pack
    against the left jamb, the rest pack right; `active_at` marks the
    hoja de paso (the pack's jamb leaf)."""
    try:
        leaves = [
            BayLeaf(
                slot=f"L{index + 1}",
                opening=Opening(
                    movement=OpeningMovement.FOLD,
                    hinge_side=(
                        HingeSide.LEFT if index < left_count else HingeSide.RIGHT
                    ),
                    direction=direction,
                    leaf_role=(
                        LeafRole.ACTIVE if index == active_at else LeafRole.PASSIVE
                    ),
                ),
            )
            for index in range(count)
        ]
        return OpeningSpec(unit_kind=unit_kind, leaves=leaves)
    except ValueError:
        return None


def _emit_fold_options(
    options: list[dict[str, object]],
    seen: set[str],
    cap: OpeningCapability,
) -> None:
    """Every folding scheme the row admits: for each leaf count, every
    pack split (n+0 .. 0+n), all-PASSIVE plus the hoja-de-paso variants
    an anchor leaf can carry — per declared direction and unit kind."""
    pass_door = LeafRole.ACTIVE in cap.leaf_roles
    for unit_kind in cap.unit_kinds:
        for direction in cap.directions:
            for count in range(2, cap.max_leaves + 1):
                for left_count in range(0, count + 1):
                    anchors: list[int | None] = [None]
                    if pass_door:
                        if left_count > 0:
                            anchors.append(0)
                        if count - left_count > 0:
                            anchors.append(count - 1)
                    for anchor in anchors:
                        spec = _fold_spec(
                            count, left_count, direction, unit_kind,
                            active_at=anchor,
                        )
                        if spec is not None:
                            _emit_option(options, seen, spec)


def _emit_vertical_slide_options(
    options: list[dict[str, object]],
    seen: set[str],
    cap: OpeningCapability,
    capabilities: tuple[OpeningCapability, ...],
) -> None:
    """The guillotina compositions the row admits: the single full-height
    sash, the double-hung TOP/BOTTOM pair when the row allows two leaves,
    and the single-hung variant (fixed lite above + sliding sash below)
    when a FIXED row covers the same unit."""
    for unit_kind in cap.unit_kinds:
        single = _single_spec(
            OpeningMovement.VERTICAL_SLIDE, HingeSide.NONE, None, unit_kind, False
        )
        if single is not None:
            _emit_option(options, seen, single)
        if cap.max_leaves < 2:
            continue
        double = OpeningSpec(
            unit_kind=unit_kind,
            leaves=[
                BayLeaf(
                    slot="TOP",
                    opening=Opening(movement=OpeningMovement.VERTICAL_SLIDE),
                ),
                BayLeaf(
                    slot="BOTTOM",
                    opening=Opening(movement=OpeningMovement.VERTICAL_SLIDE),
                ),
            ],
        )
        _emit_option(options, seen, double)
        # Single-hung: the top sash stays a fixed pane — only offered when
        # the catalog also declares FIXED for this unit kind.
        fixed_covered = any(
            other.movement is OpeningMovement.FIXED
            and unit_kind in other.unit_kinds
            and LeafRole.SINGLE in other.leaf_roles
            for other in capabilities
        )
        if fixed_covered:
            _emit_option(
                options,
                seen,
                OpeningSpec(
                    unit_kind=unit_kind,
                    leaves=[
                        BayLeaf(
                            slot="TOP",
                            opening=Opening(movement=OpeningMovement.FIXED),
                        ),
                        BayLeaf(
                            slot="BOTTOM",
                            opening=Opening(movement=OpeningMovement.VERTICAL_SLIDE),
                        ),
                    ],
                ),
            )


def _emit_option(
    options: list[dict[str, object]],
    seen: set[str],
    spec: OpeningSpec,
) -> None:
    key = spec_key(spec)
    if key in seen:
        return
    seen.add(key)
    legacy = legacy_openings_for_spec(spec)
    descriptor: dict[str, object] = {
        "key": key,
        "name": spec_display_name_es(spec),
        "unit_kind": spec.unit_kind.value,
        "legacy": sorted(item.value for item in legacy)[0] if legacy else None,
    }
    if any(
        leaf.opening.movement in (OpeningMovement.PIVOT_V, OpeningMovement.PIVOT_H)
        for leaf in spec.leaves
    ):
        # A pivot option exists but its leaf is incomplete until the
        # estimator declares the displaced axis — surfaces must collect
        # axis_offset_mm before fabrication will accept the spec.
        descriptor["requires_axis"] = True
    if len(spec.leaves) == 1:
        descriptor["opening"] = _opening_payload(spec.leaves[0].opening)
    else:
        descriptor["leaves"] = [
            {"slot": leaf.slot, "opening": _opening_payload(leaf.opening)}
            for leaf in spec.leaves
        ]
    options.append(descriptor)


def _opening_payload(opening: Opening) -> dict[str, object]:
    payload: dict[str, object] = {"movement": opening.movement.value}
    if opening.hinge_side is not HingeSide.NONE:
        payload["hinge_side"] = opening.hinge_side.value
    if opening.direction is not None:
        payload["direction"] = opening.direction.value
    if opening.leaf_role is not LeafRole.SINGLE:
        payload["leaf_role"] = opening.leaf_role.value
    if opening.fixed_in_sash:
        payload["fixed_in_sash"] = True
    return payload


def spec_key(spec: OpeningSpec) -> str:
    """Stable option identity: DOOR: + per-leaf canonical keys."""
    prefix = "DOOR:" if spec.unit_kind is UnitKind.DOOR else ""
    return prefix + "|".join(
        f"{leaf.slot}:{leaf.opening.key()}" for leaf in spec.leaves
    )


def spec_is_admitted(spec: OpeningSpec, params: SystemParams) -> bool:
    """True when every leaf of the spec is covered by one capability row."""
    for leaf in spec.leaves:
        opening = leaf.opening
        covered = False
        for cap in admitted_capabilities(params):
            if cap.movement is not opening.movement:
                continue
            if spec.unit_kind not in cap.unit_kinds:
                continue
            if len(spec.leaves) > cap.max_leaves:
                continue
            if opening.leaf_role not in cap.leaf_roles:
                continue
            if opening.direction is not None and opening.direction not in cap.directions:
                continue
            if opening.fixed_in_sash and not cap.fixed_in_sash:
                continue
            covered = True
            break
        if not covered:
            return False
    return True


# The family's physical repertoire of leaf movements — wider than the
# legacy enum could express: a casement series hinges every side-hinged
# movement, sliding families slide. Capability rows then narrow what a
# concrete system actually sells.
FAMILY_MOVEMENTS: dict[SystemFamily, frozenset[OpeningMovement]] = {
    SystemFamily.CASEMENT: frozenset(
        {
            OpeningMovement.FIXED,
            OpeningMovement.TURN,
            OpeningMovement.TILT,
            OpeningMovement.TILT_TURN,
            OpeningMovement.TOP_HUNG,
            OpeningMovement.BOTTOM_HUNG,
        }
    ),
    SystemFamily.SLIDING: frozenset({OpeningMovement.FIXED, OpeningMovement.SLIDE}),
    SystemFamily.LIFT_SLIDE: frozenset(
        {OpeningMovement.FIXED, OpeningMovement.SLIDE, OpeningMovement.LIFT_SLIDE}
    ),
    SystemFamily.DOOR: frozenset({OpeningMovement.FIXED, OpeningMovement.TURN}),
    SystemFamily.FACADE_FIXED: frozenset({OpeningMovement.FIXED}),
    # D08 — the advanced fabrication families: each builds its own
    # translational/rotational leaf machinery plus FIXED panes.
    SystemFamily.PARALLEL_SLIDE: frozenset(
        {OpeningMovement.FIXED, OpeningMovement.PARALLEL_SLIDE}
    ),
    SystemFamily.FOLDING: frozenset(
        {OpeningMovement.FIXED, OpeningMovement.FOLD}
    ),
    SystemFamily.PIVOT: frozenset(
        {OpeningMovement.FIXED, OpeningMovement.PIVOT_V, OpeningMovement.PIVOT_H}
    ),
    SystemFamily.VERTICAL_SLIDE: frozenset(
        {OpeningMovement.FIXED, OpeningMovement.VERTICAL_SLIDE}
    ),
}

# Unit kinds a family builds: casement series sell hinged door leaves,
# the door family lives on door units; the rest are window-only frames.
FAMILY_UNIT_KINDS: dict[SystemFamily, frozenset[UnitKind]] = {
    SystemFamily.CASEMENT: frozenset({UnitKind.WINDOW, UnitKind.DOOR}),
    # Translational families physically fabricate patio-door units too
    # (puerta corredera, elevable, osciloparalela, plegable, pivotante) —
    # capability rows then narrow what a concrete system actually sells.
    SystemFamily.SLIDING: frozenset({UnitKind.WINDOW, UnitKind.DOOR}),
    SystemFamily.LIFT_SLIDE: frozenset({UnitKind.WINDOW, UnitKind.DOOR}),
    SystemFamily.DOOR: frozenset({UnitKind.WINDOW, UnitKind.DOOR}),
    SystemFamily.FACADE_FIXED: frozenset({UnitKind.WINDOW}),
    SystemFamily.PARALLEL_SLIDE: frozenset({UnitKind.WINDOW, UnitKind.DOOR}),
    SystemFamily.FOLDING: frozenset({UnitKind.WINDOW, UnitKind.DOOR}),
    SystemFamily.PIVOT: frozenset({UnitKind.WINDOW, UnitKind.DOOR}),
    # Guillotina is a window typology — no sash-door product exists.
    SystemFamily.VERTICAL_SLIDE: frozenset({UnitKind.WINDOW}),
}


def spec_movement_is_family_compatible(spec: OpeningSpec, params: SystemParams) -> bool:
    """Coarse family gate (D01 vocabulary over movements): the unit kind
    and every leaf movement must belong to the fabrication family."""
    if spec.unit_kind not in FAMILY_UNIT_KINDS[params.system_family]:
        return False
    return all(
        leaf.opening.movement in FAMILY_MOVEMENTS[params.system_family]
        for leaf in spec.leaves
    )


def families_admitting_unit(unit_kind: UnitKind) -> list[str]:
    return [
        family.value for family, kinds in FAMILY_UNIT_KINDS.items() if unit_kind in kinds
    ]


def families_admitting_movement(movement: OpeningMovement) -> list[str]:
    """Families whose physical repertoire covers a movement — the
    compatible_families the rejection names."""
    return [
        family.value
        for family, movements in FAMILY_MOVEMENTS.items()
        if movement in movements
    ]


def families_admitting_spec(spec: OpeningSpec) -> list[str]:
    """Families physically able to fabricate the whole spec (unit kind +
    every leaf movement) — the families a capability rejection names."""
    return [
        family.value
        for family, units in FAMILY_UNIT_KINDS.items()
        if spec.unit_kind in units
        and all(
            leaf.opening.movement in FAMILY_MOVEMENTS[family]
            for leaf in spec.leaves
        )
    ]


# --- Spanish display names ----------------------------------------------

_DIRECTION_ES = {
    OpeningDirection.INWARD: "hacia adentro",
    OpeningDirection.OUTWARD: "hacia afuera",
}

_HINGE_ES = {
    HingeSide.LEFT: "bisagras a la izquierda",
    HingeSide.RIGHT: "bisagras a la derecha",
    HingeSide.TOP: "bisagras arriba",
    HingeSide.BOTTOM: "bisagras abajo",
}

_DOOR_HINGE_ES = {
    HingeSide.LEFT: "bisagras a la izquierda",
    HingeSide.RIGHT: "bisagras a la derecha",
}


def opening_leaf_name_es(opening: Opening, unit_kind: UnitKind) -> str:
    """Human name for one leaf spec — the glossary the estimator sees."""
    movement = opening.movement
    if movement is OpeningMovement.FIXED:
        return "Fijo en hoja" if opening.fixed_in_sash else "Fijo"
    if movement is OpeningMovement.TURN:
        direction = opening.direction or OpeningDirection.INWARD
        if unit_kind is UnitKind.DOOR:
            return f"Puerta {_DOOR_HINGE_ES[opening.hinge_side]} {_DIRECTION_ES[direction]}"
        return f"Abatible {_DIRECTION_ES[direction]} — {_HINGE_ES[opening.hinge_side]}"
    if movement is OpeningMovement.TILT:
        return "Solo abatimiento (banderola)"
    if movement is OpeningMovement.TILT_TURN:
        return f"Oscilobatiente — {_HINGE_ES[opening.hinge_side]}"
    if movement is OpeningMovement.TOP_HUNG:
        return "Proyectante"
    if movement is OpeningMovement.BOTTOM_HUNG:
        return (
            f"Abatimiento {_DIRECTION_ES[opening.direction or OpeningDirection.INWARD]}"
            " — bisagras abajo"
        )
    if movement is OpeningMovement.SLIDE:
        return "Puerta corredera" if unit_kind is UnitKind.DOOR else "Corredera"
    if movement is OpeningMovement.LIFT_SLIDE:
        return (
            "Puerta corredera elevable"
            if unit_kind is UnitKind.DOOR
            else "Corredera elevable"
        )
    if movement is OpeningMovement.PARALLEL_SLIDE:
        return (
            "Puerta osciloparalela"
            if unit_kind is UnitKind.DOOR
            else "Osciloparalela"
        )
    if movement is OpeningMovement.FOLD:
        return "Hoja de paso plegable" if opening.leaf_role is LeafRole.ACTIVE else "Hoja plegable"
    if movement is OpeningMovement.PIVOT_V:
        return (
            "Puerta pivotante"
            if unit_kind is UnitKind.DOOR
            else "Pivotante de eje vertical"
        )
    if movement is OpeningMovement.PIVOT_H:
        return (
            "Puerta pivotante horizontal"
            if unit_kind is UnitKind.DOOR
            else "Pivotante de eje horizontal"
        )
    if movement is OpeningMovement.VERTICAL_SLIDE:
        return "Guillotina"
    raise ValueError(f"Movimiento sin nombre en español: {movement.value}")


def spec_display_name_es(spec: OpeningSpec) -> str:
    """Human name for a whole opening spec — multi-leaf compositions get
    their typology name (Francesa, Puerta doble, Plegable n+m,
    Guillotina simple/doble)."""
    if all(leaf.opening.movement is OpeningMovement.FOLD for leaf in spec.leaves):
        left_count = sum(
            1 for leaf in spec.leaves if leaf.opening.hinge_side is HingeSide.LEFT
        )
        right_count = len(spec.leaves) - left_count
        direction = spec.leaves[0].opening.direction
        parts = [f"Plegable {left_count}+{right_count}"]
        if spec.unit_kind is UnitKind.DOOR:
            parts[0] = f"Puerta plegable {left_count}+{right_count}"
        parts.append(_DIRECTION_ES.get(direction or OpeningDirection.INWARD, ""))
        name = " — ".join(part for part in parts if part)
        if any(leaf.opening.leaf_role is LeafRole.ACTIVE for leaf in spec.leaves):
            name += " — hoja de paso"
        return name
    if any(
        leaf.opening.movement is OpeningMovement.VERTICAL_SLIDE
        for leaf in spec.leaves
    ):
        if len(spec.leaves) == 2:
            if all(
                leaf.opening.movement is OpeningMovement.VERTICAL_SLIDE
                for leaf in spec.leaves
            ):
                return "Guillotina doble"
            return "Guillotina simple"
        return "Guillotina"
    if len(spec.leaves) == 2:
        movement = spec.leaves[0].opening.movement
        active = next(leaf for leaf in spec.leaves if leaf.opening.leaf_role is LeafRole.ACTIVE)
        side = "izquierda" if active.slot == "L1" else "derecha"
        direction = active.opening.direction
        # Inward is the naming default — the direction tail only travels
        # on outward-opening compositions.
        tail = " — hacia afuera" if direction is OpeningDirection.OUTWARD else ""
        if spec.unit_kind is UnitKind.DOOR:
            return f"Puerta doble — activa {side}{tail}"
        if movement is OpeningMovement.TILT_TURN:
            return f"Francesa oscilobatiente 2 hojas — activa {side}{tail}"
        return f"Francesa 2 hojas — activa {side}{tail}"
    leaf = spec.leaves[0]
    return opening_leaf_name_es(leaf.opening, spec.unit_kind)
