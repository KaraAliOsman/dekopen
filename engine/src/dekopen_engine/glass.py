"""Glass piece math — every derived number comes from the structured
composition (``glass_composition``), never from string heuristics.

``derive_net_glass_thickness`` and ``exact_glass_weight`` keep their
UNKNOWN-first contract: a spec the parser cannot read yields ``None``
rather than a fabricated mass, and the piece reports the gap."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from dekopen_engine.glass_composition import (
    GlassComposition,
    parse_glass_notation,
)
from dekopen_engine.models import (
    GlassPiece,
    GlassSafetyFinding,
    GlassSurchargeSelection,
    PlanPoint,
)

FLOAT_GLASS_DENSITY_KG_M3 = Decimal("2500")
GLASS_WEIGHT_FACTOR_KG_M2_PER_MM = Decimal("2.50")

_MM2_PER_M2 = Decimal("1000000")


def resolve_composition(
    glass_spec: str | None,
    declared: GlassComposition | None = None,
) -> GlassComposition | None:
    """The composition a node carries: an explicit structured declaration
    wins; otherwise the persisted notation string parses once more.
    Nothing parseable → None (UNKNOWN)."""
    if declared is not None:
        return declared
    return parse_glass_notation(glass_spec)


def derive_net_glass_thickness(
    glass_spec: str | None,
    *,
    composition: GlassComposition | None = None,
) -> Decimal | None:
    """Glass mass thickness in mm — plies only (no PVB, no chambers).

    ``None`` when the composition cannot be established."""
    resolved = resolve_composition(glass_spec, composition)
    return None if resolved is None else resolved.net_thickness_mm()


def exact_glass_area_m2(width_mm: Decimal, height_mm: Decimal) -> Decimal:
    return (width_mm * height_mm) / _MM2_PER_M2


def exact_glass_weight(
    width_mm: Decimal,
    height_mm: Decimal,
    glass_spec: str | None,
    *,
    composition: GlassComposition | None = None,
) -> Decimal | None:
    """Exact piece mass in kg — glass at 2.50 kg/m²·mm plus each PVB
    interlayer at 1.07 kg/m²·mm. ``None`` for an UNKNOWN composition."""
    resolved = resolve_composition(glass_spec, composition)
    if resolved is None:
        return None
    return exact_glass_area_m2(width_mm, height_mm) * resolved.weight_kg_m2()


def build_glass_piece(
    *,
    bay_id: str,
    leaf_id: str | None = None,
    width_mm: Decimal,
    height_mm: Decimal,
    glass_spec: str | None,
    article_sku: str | None = None,
    shape: list[PlanPoint] | None = None,
    exposed_edges: list[str] | None = None,
    composition: GlassComposition | None = None,
    surcharge_selections: list[GlassSurchargeSelection] | None = None,
    safety_findings: list[GlassSafetyFinding] | None = None,
    requires_exact_cut: bool = False,
) -> GlassPiece:
    resolved = resolve_composition(glass_spec, composition)
    weight = exact_glass_weight(
        width_mm, height_mm, glass_spec, composition=resolved
    )
    return GlassPiece(
        bay_id=bay_id,
        leaf_id=leaf_id,
        width_mm=width_mm,
        height_mm=height_mm,
        shape=shape,
        area_m2=exact_glass_area_m2(width_mm, height_mm).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        ),
        weight_kg=(
            None
            if weight is None
            else weight.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ),
        thickness_net_mm=(
            None
            if resolved is None
            else resolved.net_thickness_mm().quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        ),
        glass_spec=glass_spec,
        article_sku=article_sku,
        exposed_edges=exposed_edges,
        composition=resolved,
        thickness_total_mm=(
            None
            if resolved is None
            else resolved.total_thickness_mm().quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        ),
        requires_exact_cut=requires_exact_cut,
        surcharge_selections=list(surcharge_selections or []),
        safety_findings=list(safety_findings or []),
    )
