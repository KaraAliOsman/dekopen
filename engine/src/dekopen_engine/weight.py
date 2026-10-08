"""Exact mobile-leaf mass; rounding belongs only to the public result.

UNKNOWN is a first-class state: when a catalog authority is missing for a
component the component is None, the total is None, and the reasons say which
authority is missing — no fabricated fallback ever enters a compatibility
decision."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from dekopen_engine.models import (
    HardwareComponent, HardwareKitRule, LeafWeight, ProfileCut, ProfileRole,
    ReinforcementPiece, SystemParams,
)

_KG = Decimal("0.01")
_METRE = Decimal("1000")


class MissingWeightAuthority(ValueError):
    pass


class MissingFabricationAuthority(ValueError):
    """A fabrication datum the catalog must declare is absent — refuse with a
    precise reason instead of computing on an invented constant."""


def _accumulate(
    total: Decimal | None, addend: Decimal | None,
) -> Decimal | None:
    if total is None or addend is None:
        return None
    return total + addend


@dataclass(frozen=True, slots=True)
class ExactLeafWeight:
    pvc_weight_kg: Decimal | None
    steel_weight_kg: Decimal | None
    infill_weight_kg: Decimal | None
    hardware_weight_kg: Decimal | None = Decimal("0")
    # Reasons naming the missing authority, e.g.
    # "missing_profile_mass:DEMO-HOJA" — empty when the mass is fully known.
    weight_unknown_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total_weight_kg(self) -> Decimal | None:
        components = (
            self.pvc_weight_kg, self.steel_weight_kg,
            self.infill_weight_kg, self.hardware_weight_kg,
        )
        if any(component is None for component in components):
            return None
        return sum(
            (component for component in components if component is not None),
            Decimal("0"),
        )

    @staticmethod
    def _quantize(value: Decimal | None) -> Decimal | None:
        return None if value is None else value.quantize(_KG, rounding=ROUND_HALF_UP)

    def public_result(self, bay_id: str, leaf_id: str | None) -> LeafWeight:
        total = self.total_weight_kg
        return LeafWeight(
            bay_id=bay_id, leaf_id=leaf_id,
            pvc_weight_kg=self._quantize(self.pvc_weight_kg),
            steel_weight_kg=self._quantize(self.steel_weight_kg),
            infill_weight_kg=self._quantize(self.infill_weight_kg),
            hardware_weight_kg=self._quantize(self.hardware_weight_kg),
            total_weight_kg=None if total is None else total.quantize(_KG, rounding=ROUND_HALF_UP),
            weight_unknown_reasons=list(self.weight_unknown_reasons),
        )


# Roles that make up a moving leaf: casement sashes, sliding sashes, the
# encuentro (interlock) between moving leaves, dedicated door sashes and
# the inversor — the passive leaf's meeting stile in a two-leaf pair (D03).
_LEAF_ROLES = frozenset({
    ProfileRole.SASH,
    ProfileRole.SLIDING_SASH,
    ProfileRole.INTERLOCK,
    ProfileRole.DOOR_SASH,
    ProfileRole.INVERSOR,
})


def base_leaf_weight(
    *, profile_cuts: Sequence[ProfileCut], reinforcements: Sequence[ReinforcementPiece],
    infill_weight_kg: Decimal | None, params: SystemParams,
    infill_unknown_reason: str | None = None,
) -> ExactLeafWeight:
    """Consume one leaf's cuts; frame, beads and threshold never enter its mass."""
    pvc: Decimal | None = Decimal("0")
    steel: Decimal | None = Decimal("0")
    reasons: list[str] = []
    for cut in profile_cuts:
        if cut.role not in _LEAF_ROLES:
            continue
        article = params.effective_profile_articles[cut.role]
        if article.sku != cut.sku:
            raise MissingWeightAuthority(f"Missing profile mass authority: {cut.sku}")
        density = article.weight_kg_m
        if density is None:
            pvc = None
            reason = f"missing_profile_mass:{article.sku}"
            if reason not in reasons:
                reasons.append(reason)
        else:
            pvc = _accumulate(pvc, cut.length_mm / _METRE * cut.qty * density)
    for piece in reinforcements:
        if piece.role not in _LEAF_ROLES:
            continue
        article = params.effective_profile_articles[piece.role]
        if article.sku != piece.parent_profile_sku:
            raise MissingWeightAuthority(f"Missing steel mass authority: {piece.parent_profile_sku}")
        density = article.steel_weight_kg_m
        if density is None:
            steel = None
            reason = f"missing_steel_mass:{article.sku}"
            if reason not in reasons:
                reasons.append(reason)
        else:
            steel = _accumulate(steel, piece.length_mm / _METRE * piece.qty * density)
    if infill_weight_kg is None:
        reasons.append(infill_unknown_reason or "missing_infill_mass")
    return ExactLeafWeight(pvc, steel, infill_weight_kg,
                           weight_unknown_reasons=tuple(reasons))


def _components_mass_kg(
    components: Sequence[HardwareComponent],
    *,
    leaf_width_mm: Decimal | None,
    leaf_height_mm: Decimal | None,
) -> Decimal | None:
    """Σ declared component mass — None when a component never declared a
    unit mass, or a rule-bound quantity cannot resolve without leaf dims.
    An empty list has no declared data either: None, not zero."""
    if not components:
        return None
    total = Decimal("0")
    for component in components:
        if component.weight_kg is None:
            return None
        if component.qty_rule is not None:
            if leaf_width_mm is None or leaf_height_mm is None:
                return None
            qty = component.resolved_qty(
                leaf_width_mm=leaf_width_mm, leaf_height_mm=leaf_height_mm
            )
        else:
            declared_qty = component.qty
            assert declared_qty is not None
            qty = declared_qty
        total += component.weight_kg * qty
    return total


def with_hardware_weight(
    base: ExactLeafWeight, kit: HardwareKitRule, params: SystemParams,
    *,
    leaf_width_mm: Decimal | None = None,
    leaf_height_mm: Decimal | None = None,
    extra_components: Sequence[HardwareComponent] = (),
) -> ExactLeafWeight:
    """Hardware mass on the leaf (D04): the kit's declared total when the
    catalog gives one, else the sum of its components' declared masses —
    plus the mass of the components the selected options add. Any
    undeclared piece keeps the axis UNKNOWN, never zero."""
    reasons = list(base.weight_unknown_reasons)
    kit_mass = kit.weight_kg
    if kit_mass is None:
        kit_mass = _components_mass_kg(
            kit.contents,
            leaf_width_mm=leaf_width_mm,
            leaf_height_mm=leaf_height_mm,
        )
        if kit_mass is None:
            reasons.append(f"missing_hardware_mass:{kit.sku}")
    extra_mass = (
        _components_mass_kg(
            extra_components,
            leaf_width_mm=leaf_width_mm,
            leaf_height_mm=leaf_height_mm,
        )
        if extra_components
        else Decimal("0")
    )
    if extra_components and extra_mass is None:
        reasons.append("missing_option_mass")
    hardware = (
        None
        if kit_mass is None or (extra_components and extra_mass is None)
        else kit_mass + (extra_mass or Decimal("0"))
    )
    return ExactLeafWeight(
        base.pvc_weight_kg, base.steel_weight_kg, base.infill_weight_kg,
        hardware, tuple(reasons),
    )
