"""Glass safety and dimensional limits — rules as editable data, evaluated
by the engine.

Two rule families, both rows in catalog tables (org overrides win over
global rows, provenance + review flag on every row):

- ``GlassSafetyRule`` — situational glazing-safety rules of the NCh 135
  family: doors, panes beside a door, glazing near floor level, large
  windows. Each rule declares WHEN it applies (predicate fields) and the
  safety the pane must carry (``required_safety``). ``severity`` is the
  org's choice: WARNING (default — advise, never block) or MANDATORY
  (the org decided the rule blocks the design). ``source_ref`` cites the
  norm article the row claims to implement; seeded examples are marked
  synthetic pending technical review — the official tables are loaded via
  catalog ingestion, never invented by the engine.
- ``GlassTypeLimit`` — manufacturing bounds per lamina kind/thickness:
  min/max side, max area, max aspect ratio, exact-cut requirement (the
  "tempered cannot be trimmed" workshop rule — it is ordered to measure).

The evaluator is pure: it takes per-piece contexts + the declared rules
and returns findings — the caller decides where findings surface
(product issues in the editor, BOM facts, documentary review).
"""

from __future__ import annotations

from decimal import Decimal

from dekopen_engine.glass_composition import (
    GlassComposition,
    GlassTreatment,
)
from dekopen_engine.models import (
    GlassBayContext,
    GlassSafetyFinding,
    GlassSafetyRule,
    GlassTypeLimit,
    NodeType,
    ParametricNode,
)
from dekopen_engine.engine_base import EngineModel


class GlassPieceContext(EngineModel):
    """What the rule needs to know about where a pane sits."""

    bay_id: str
    leaf_id: str | None = None
    opening_type: str | None = None
    # Pane bottom edge measured from the module base (the only floor
    # reference the model knows). None when the pane's position in the
    # module cannot be established — a sill rule then cannot fire.
    sill_mm: Decimal | None = None
    adjacent_door: bool = False
    width_mm: Decimal
    height_mm: Decimal
    area_m2: Decimal


_DOOR_OPENINGS = {"DOOR_ENTRY", "DOOR_DOUBLE"}


def safety_satisfied(
    requirement: str,
    composition: GlassComposition | None,
    *,
    declared_safety_class: str | None = None,
) -> bool:
    """Does the pane meet the required safety level?

    Only structured evidence counts: a TEMPERED requirement is met by a
    tempered lamina in the composition, LAMINATED by a bonded laminate, and
    a NCh 135 class only by the product's declared class — the engine
    never infers a safety class from physics.
    """
    if requirement == "TEMPERED":
        return bool(
            composition
            and any(
                lamina.treatment is GlassTreatment.TEMPERED
                for lamina in composition.laminae
            )
        )
    if requirement == "LAMINATED":
        return bool(composition and composition.has_laminate)
    declared = (declared_safety_class or "").strip().upper()
    if requirement == "SAFETY_GLASS":
        # "Vidrio de seguridad" — any tempered or laminated pane, or a
        # supplier-declared NCh 135 class, satisfies the requirement.
        if declared in ("A", "B", "C"):
            return True
        return safety_satisfied(
            "TEMPERED", composition
        ) or safety_satisfied("LAMINATED", composition)
    class_map = {
        "SAFETY_CLASS_A": "A",
        "SAFETY_CLASS_B": "B",
        "SAFETY_CLASS_C": "C",
    }
    return declared == class_map.get(requirement, "")


def evaluate_glass_safety(
    context: GlassPieceContext,
    composition: GlassComposition | None,
    rules: list[GlassSafetyRule],
    *,
    declared_safety_class: str | None = None,
) -> list[GlassSafetyFinding]:
    """Rules whose predicate matches the context and whose required safety
    the pane does not satisfy → findings, one per breached rule."""
    findings: list[GlassSafetyFinding] = []
    for rule in rules:
        if rule.applies_openings is not None and (
            context.opening_type is None
            or context.opening_type not in rule.applies_openings
        ):
            continue
        if rule.requires_door is True and (
            context.opening_type is None
            or context.opening_type not in _DOOR_OPENINGS
        ):
            continue
        if rule.requires_adjacent_door is True and not context.adjacent_door:
            continue
        if rule.sill_below_mm is not None:
            if (
                context.sill_mm is None
                or context.sill_mm > rule.sill_below_mm
            ):
                continue
        if (
            rule.min_area_m2 is not None
            and context.area_m2 < rule.min_area_m2
        ):
            continue
        if safety_satisfied(
            rule.required_safety,
            composition,
            declared_safety_class=declared_safety_class,
        ):
            continue
        findings.append(
            GlassSafetyFinding(
                rule_code=rule.code,
                severity=rule.severity,
                required_safety=rule.required_safety,
                message=rule.message or rule.title,
                source_ref=rule.source_ref,
                review_pending=rule.review_pending,
            )
        )
    return findings


_LAMINA_KIND_ALIASES = {
    "ANY",
    "FLOAT",
    "TINTED",
    "TEMPERED",
    "HEAT_STRENGTHENED",
    "LAMINATED",
    "LOW_E",
    "SOLAR_CONTROL",
    "REFLECTIVE",
    "MIRROR",
    "SATIN",
    "PRINTED",
}


def _lamina_kinds(composition: GlassComposition) -> set[str]:
    """Every material label a lamina carries — a laminate is LAMINATED and
    also FLOAT/TINTED/etc. by its plies."""
    kinds: set[str] = set()
    for lamina in composition.laminae:
        kinds.add("TINTED" if lamina.tint.value != "CLEAR" else "FLOAT")
        if lamina.is_laminate:
            kinds.add("LAMINATED")
        if lamina.treatment is GlassTreatment.TEMPERED:
            kinds.add("TEMPERED")
        elif lamina.treatment is GlassTreatment.HEAT_STRENGTHENED:
            kinds.add("HEAT_STRENGTHENED")
        if lamina.coating is not None:
            kinds.add(lamina.coating.value)
    return kinds


def evaluate_glass_limits(
    context: GlassPieceContext,
    composition: GlassComposition | None,
    limits: list[GlassTypeLimit],
) -> list[GlassSafetyFinding]:
    """Per-type/thickness manufacturing bounds. A limit applies when its
    kind band matches (ANY always does) and the package's net glass
    thickness falls inside its declared band (both bounds optional)."""
    findings: list[GlassSafetyFinding] = []
    kinds = _lamina_kinds(composition) if composition else {"ANY"}
    net_mm = composition.net_thickness_mm() if composition else None
    short = min(context.width_mm, context.height_mm)
    long = max(context.width_mm, context.height_mm)
    for limit in limits:
        kind = limit.lamina_kind.upper()
        if kind not in _LAMINA_KIND_ALIASES:
            continue
        if kind != "ANY" and kind not in kinds:
            continue
        if limit.thickness_min_mm is not None and (
            net_mm is None or net_mm < limit.thickness_min_mm
        ):
            continue
        if limit.thickness_max_mm is not None and (
            net_mm is None or net_mm > limit.thickness_max_mm
        ):
            continue
        breached: list[str] = []
        if limit.min_side_mm is not None and short < limit.min_side_mm:
            breached.append("min_side")
        if limit.max_side_mm is not None and long > limit.max_side_mm:
            breached.append("max_side")
        if limit.min_area_m2 is not None and context.area_m2 < limit.min_area_m2:
            breached.append("min_area")
        if limit.max_area_m2 is not None and context.area_m2 > limit.max_area_m2:
            breached.append("max_area")
        if (
            limit.max_aspect_ratio is not None
            and short > 0
            and long / short > limit.max_aspect_ratio
        ):
            breached.append("aspect")
        if not breached:
            continue
        findings.append(
            GlassSafetyFinding(
                rule_code=limit.code,
                severity=limit.severity,
                required_safety=None,
                message=(
                    f"{limit.code}: fuera de límite ({', '.join(breached)})"
                ),
                source_ref=limit.source_ref,
                review_pending=limit.review_pending,
            )
        )
    return findings


def requires_exact_cut(
    composition: GlassComposition | None,
    limits: list[GlassTypeLimit],
) -> bool:
    """Tempered panes cannot be trimmed on site — ordered to exact measure.
    A type limit may also flag it (e.g. laminated specials)."""
    if composition and composition.has_tempered:
        return True
    if composition is None:
        return False
    kinds = _lamina_kinds(composition)
    net_mm = composition.net_thickness_mm()
    for limit in limits:
        if not limit.requires_exact_cut:
            continue
        kind = limit.lamina_kind.upper()
        if kind != "ANY" and kind not in kinds:
            continue
        if limit.thickness_min_mm is not None and net_mm < limit.thickness_min_mm:
            continue
        if limit.thickness_max_mm is not None and net_mm > limit.thickness_max_mm:
            continue
        return True
    return False


def bay_glass_contexts(
    tree: ParametricNode,
    module_height_mm: Decimal,
) -> dict[str, GlassBayContext]:
    """Per-BAY safety context derived from the declared tree — opening
    type, sill height (pane bottom above module base) and adjacency to a
    door leaf. The y axis grows downward in the elevation, so a bay's
    distance to the module base is ``module_height - (top + height)``."""

    def subtree_has_door(node: ParametricNode) -> bool:
        if node.opening_type is not None and node.opening_type.value in _DOOR_OPENINGS:
            return True
        return any(subtree_has_door(child) for child in node.children)

    contexts: dict[str, GlassBayContext] = {}

    def walk(
        node: ParametricNode,
        top_offset_mm: Decimal,
        height_mm: Decimal,
        near_door: bool,
    ) -> None:
        if node.type is NodeType.BAY:
            sill = module_height_mm - (top_offset_mm + height_mm)
            contexts[node.id] = GlassBayContext(
                opening_type=(
                    node.opening_type.value if node.opening_type else None
                ),
                sill_mm=sill,
                adjacent_door=near_door,
            )
            return
        if node.type is NodeType.SPLIT_V and len(node.children) == 2:
            left_door = subtree_has_door(node.children[0])
            right_door = subtree_has_door(node.children[1])
            # A pane is "adjacent to the door" when its sibling pane IS a
            # door — the side-light rule. Door-adjacent flags propagate
            # into both subtrees.
            walk(node.children[0], top_offset_mm, height_mm, near_door or right_door)
            walk(node.children[1], top_offset_mm, height_mm, near_door or left_door)
            return
        if node.type is NodeType.SPLIT_H and len(node.children) == 2:
            offset = node.split_offset_mm or Decimal("0")
            # children[0] sits above the mullion, children[1] below.
            top_h = offset
            bottom_h = height_mm - offset
            walk(
                node.children[0], top_offset_mm, top_h, near_door
            )
            walk(
                node.children[1], top_offset_mm + offset, bottom_h, near_door
            )
            return
        for child in node.children:
            walk(child, top_offset_mm, height_mm, near_door)

    walk(tree, Decimal("0"), module_height_mm, False)
    return contexts
