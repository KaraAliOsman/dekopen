"""D06 — position extras and project services.

Turns declared `ExtraSelection`s on the product model into:

- derived sellable sublines (`ExtraLine`: quantity × unit price = total),
- real cut pieces (`ProfileCut`, origin=EXTRA) that reach the cut plan
  and the OT BOM like any other member,
- counted `FittingPiece`s (mosquitero/aireador per operable leaf),
- accept/discard suggestions (`ExtraSuggestion`) for catalogued
  companions the position qualifies for.

`evaluate_service_lines` derives project services (instalación, sellado,
retiro, andamio, flete) from quoted-position measures — the same
quantity × price = total contract, at project level.

Everything is Decimal; nothing here does I/O or invents a number the
catalog did not declare.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Mapping, Sequence

from pydantic import Field

from dekopen_engine.engine_base import EngineModel
from dekopen_engine.models import (
    EXTRA_CUT_KINDS,
    EXTRA_COUNTED_KINDS,
    EXTRA_KIND_ROLE,
    EdgeSide,
    ExtraArticle,
    ExtraKind,
    ExtraLine,
    ExtraSelection,
    ExtraSuggestion,
    ExtraTemplate,
    FittingPiece,
    PieceOrigin,
    ProfileCut,
    ServiceArticle,
    ServiceLine,
    ServicePositionMeasure,
    ServiceQtyRule,
    SystemFamily,
    UnitKind,
)

_Q2 = Decimal("0.01")
_MM_PER_M = Decimal("1000")
_MM2_PER_M2 = Decimal("1000000")


class OperableLeaf(EngineModel):
    """One operable leaf inside a module — mosquitero/aireador scope."""

    bay_id: str
    leaf_id: str  # leaf slot: L1 / P1 / PRIMARY …


class ModuleExtraContext(EngineModel):
    """What extras evaluation needs from one product module.

    Built by `evaluate_product` (it owns the geometry/coupling context):
    the module's nominal dims, which outer edges stay exterior (a
    coupling-claimed edge gets no ensanche), the operable leaves the tree
    declares, the unit kind, and whether the module's boundary is a
    straight frame (contour/frameless panes take no profile cuts).
    """

    module_id: str
    column: int  # left→right layout index
    width_mm: Decimal
    height_mm: Decimal
    exterior_sides: frozenset[EdgeSide]
    operable_leaves: tuple[OperableLeaf, ...] = ()
    unit_kind: UnitKind = UnitKind.WINDOW
    # False on contour/frameless modules — a shaped or glass-only
    # boundary takes no straight profile member.
    straight_framed: bool = True


class ExtraEvaluation(EngineModel):
    """What the position's declared extras derived (D06)."""

    lines: list[ExtraLine] = Field(default_factory=list)
    cuts: list[ProfileCut] = Field(default_factory=list)
    fittings: list[FittingPiece] = Field(default_factory=list)
    suggestions: list[ExtraSuggestion] = Field(default_factory=list)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_Q2, rounding=ROUND_HALF_UP)


def _line(
    article: ExtraArticle,
    *,
    quantity: Decimal,
    detail: str | None,
) -> ExtraLine:
    return ExtraLine(
        sku=article.sku,
        name=article.name,
        kind=article.kind,
        quantity=quantity,
        unit=article.pricing_unit,
        unit_price=article.unit_price,
        unit_price_currency=article.unit_price_currency,
        total_price=(
            _money(quantity * article.unit_price)
            if article.unit_price is not None
            else None
        ),
        unit_cost=article.unit_cost,
        unit_cost_currency=article.unit_cost_currency,
        total_cost=(
            _money(quantity * article.unit_cost)
            if article.unit_cost is not None
            else None
        ),
        detail=detail,
    )


def _article_applies(
    article: ExtraArticle,
    contexts: Sequence[ModuleExtraContext],
    system_family: SystemFamily | None,
) -> bool:
    """Catalog applicability: family predicate and unit-kind predicate."""
    if article.families and (
        system_family is None or system_family not in article.families
    ):
        return False
    if article.unit_kinds and not any(
        ctx.unit_kind in article.unit_kinds for ctx in contexts
    ):
        return False
    return True


def _article_measurable(
    article: ExtraArticle,
    contexts: Sequence[ModuleExtraContext],
    selection: ExtraSelection | None = None,
) -> bool:
    """Whether the article could measure anything on these contexts —
    gates suggestions so a companion is only offered when it would
    produce a real subline."""
    if article.kind in EXTRA_COUNTED_KINDS:
        if selection is not None and selection.qty is not None:
            return True
        return any(ctx.operable_leaves for ctx in contexts)
    sides = (
        set(selection.sides)
        if selection is not None and selection.sides
        else {EdgeSide.BOTTOM}
        if article.kind is ExtraKind.SILL
        else set()
    )
    return any(
        ctx.straight_framed and sides & set(ctx.exterior_sides)
        for ctx in contexts
    )


def _eval_sill(
    article: ExtraArticle,
    selection: ExtraSelection,
    contexts: Sequence[ModuleExtraContext],
    cuts: list[ProfileCut],
) -> ExtraLine | None:
    """Vierteaguas/alféizar: the contiguous bottom-exterior run.

    Modules sit on the bottom edge left→right; consecutive columns join
    into one run. The run's end pieces take the declared vuelo — a single
    1 500 mm module with 30 mm reveals cuts 1 560 mm.
    """
    bottom = [
        ctx
        for ctx in contexts
        if EdgeSide.BOTTOM in ctx.exterior_sides and ctx.straight_framed
    ]
    if not bottom:
        return None
    ordered = sorted(bottom, key=lambda ctx: ctx.column)
    runs: list[list[ModuleExtraContext]] = []
    for ctx in ordered:
        if runs and runs[-1][-1].column + 1 == ctx.column:
            runs[-1].append(ctx)
        else:
            runs.append([ctx])
    vuelo_left = (
        selection.vuelo_left_mm
        if selection.vuelo_left_mm is not None
        else article.vuelo_default_mm
    ) or Decimal("0")
    vuelo_right = (
        selection.vuelo_right_mm
        if selection.vuelo_right_mm is not None
        else article.vuelo_default_mm
    ) or Decimal("0")
    total_mm = Decimal("0")
    pieces = 0
    assert article.cut_profile_sku is not None
    assert article.cut_material is not None
    for run in runs:
        for index, ctx in enumerate(run):
            length = ctx.width_mm
            if index == 0:
                length += vuelo_left
            if index == len(run) - 1:
                length += vuelo_right
            cuts.append(
                ProfileCut(
                    sku=article.cut_profile_sku,
                    role=EXTRA_KIND_ROLE[article.kind],
                    material=article.cut_material,
                    length_mm=length,
                    angle_left=Decimal("90.0"),
                    angle_right=Decimal("90.0"),
                    qty=1,
                    bay_id=ctx.module_id,
                    origin=PieceOrigin.EXTRA,
                )
            )
            total_mm += length
            pieces += 1
    return _line(
        article,
        quantity=(total_mm / _MM_PER_M).quantize(_Q2),
        detail=f"{int(total_mm)} mm en {pieces} corte{'s' if pieces != 1 else ''}",
    )


def _eval_sided(
    article: ExtraArticle,
    selection: ExtraSelection,
    contexts: Sequence[ModuleExtraContext],
    cuts: list[ProfileCut],
) -> ExtraLine | None:
    """Ensanche / tapajunta: one cut per declared exterior side."""
    sides = set(selection.sides)
    if not sides:
        return None
    total_mm = Decimal("0")
    pieces = 0
    assert article.cut_profile_sku is not None
    assert article.cut_material is not None
    for ctx in contexts:
        if not ctx.straight_framed:
            continue
        for side in sides & set(ctx.exterior_sides):
            length = (
                ctx.width_mm
                if side in (EdgeSide.TOP, EdgeSide.BOTTOM)
                else ctx.height_mm
            )
            cuts.append(
                ProfileCut(
                    sku=article.cut_profile_sku,
                    role=EXTRA_KIND_ROLE[article.kind],
                    material=article.cut_material,
                    length_mm=length,
                    angle_left=Decimal("90.0"),
                    angle_right=Decimal("90.0"),
                    qty=1,
                    bay_id=ctx.module_id,
                    origin=PieceOrigin.EXTRA,
                )
            )
            total_mm += length
            pieces += 1
    if not pieces:
        return None
    return _line(
        article,
        quantity=(total_mm / _MM_PER_M).quantize(_Q2),
        detail=(
            f"{int(total_mm)} mm en {pieces} corte{'s' if pieces != 1 else ''}"
        ),
    )


def _eval_counted(
    article: ExtraArticle,
    selection: ExtraSelection,
    contexts: Sequence[ModuleExtraContext],
    fittings: list[FittingPiece],
) -> ExtraLine | None:
    """Counted extra: one fitting per operable leaf (sel.qty overrides)."""
    if selection.qty is not None:
        count = selection.qty
        fittings.append(
            FittingPiece(
                kind=article.kind.value,
                sku=article.sku,
                qty=count,
                origin=PieceOrigin.EXTRA,
            )
        )
        detail = f"{count} declarada{'s' if count != 1 else ''}"
    else:
        leaves = [leaf for ctx in contexts for leaf in ctx.operable_leaves]
        count = len(leaves)
        for ctx in contexts:
            for leaf in ctx.operable_leaves:
                fittings.append(
                    FittingPiece(
                        kind=article.kind.value,
                        sku=article.sku,
                        qty=1,
                        bay_id=f"{ctx.module_id}|{leaf.bay_id}",
                        leaf_id=f"{ctx.module_id}|{leaf.bay_id}:{leaf.leaf_id}",
                        origin=PieceOrigin.EXTRA,
                    )
                )
        detail = f"{count} hoja{'s' if count != 1 else ''} corredera{'s' if count != 1 else ''}"
    if not count:
        return None
    return _line(article, quantity=Decimal(count), detail=detail)


def evaluate_position_extras(
    selections: Sequence[ExtraSelection],
    articles: Mapping[str, ExtraArticle],
    contexts: Sequence[ModuleExtraContext],
    *,
    system_family: SystemFamily | None = None,
) -> ExtraEvaluation:
    """Evaluate a position's declared extras against catalog articles.

    Unknown skus and selections the predicates exclude emit nothing — the
    selection stays sealed in the tree for audit, but the BOM charges
    only what the catalog declares and the position qualifies for.
    Suggestions list every companion article the position qualifies for
    that is not already selected.
    """
    lines: list[ExtraLine] = []
    cuts: list[ProfileCut] = []
    fittings: list[FittingPiece] = []
    selected_skus: set[str] = set()
    for selection in selections:
        article = articles.get(selection.sku)
        if article is None:
            continue
        if not _article_applies(article, contexts, system_family):
            continue
        selected_skus.add(article.sku)
        line: ExtraLine | None
        if article.kind is ExtraKind.SILL:
            line = _eval_sill(article, selection, contexts, cuts)
        elif article.kind in EXTRA_CUT_KINDS:
            line = _eval_sided(article, selection, contexts, cuts)
        else:
            line = _eval_counted(article, selection, contexts, fittings)
        if line is not None:
            lines.append(line)
    suggestions = [
        ExtraSuggestion(
            sku=article.sku,
            name=article.name,
            kind=article.kind,
            reason=article.suggestion_reason,
        )
        for article in articles.values()
        if article.suggestion_reason is not None
        and article.sku not in selected_skus
        and _article_applies(article, contexts, system_family)
        and _article_measurable(article, contexts)
    ]
    return ExtraEvaluation(
        lines=lines, cuts=cuts, fittings=fittings, suggestions=suggestions
    )


def merge_extra_templates(
    selections: Sequence[ExtraSelection],
    templates: Sequence[ExtraTemplate],
) -> list[ExtraSelection]:
    """Org default extras merged into a position's selections.

    A template never overrides a declaration the estimator already made —
    same sku keeps the position's own parameters.
    """
    existing = {selection.sku for selection in selections}
    return [
        *selections,
        *(
            ExtraSelection(sku=template.sku, sides=template.sides, qty=template.qty)
            for template in templates
            if template.sku not in existing
        ),
    ]


_SERVICE_RULE_UNIT = {
    ServiceQtyRule.PER_POSITION_UNIT: "ud",
    ServiceQtyRule.PER_M2: "m²",
    ServiceQtyRule.PER_LINEAR_METER: "ml",
    ServiceQtyRule.FIXED: "servicio",
}

_SERVICE_RULE_DETAIL = {
    ServiceQtyRule.PER_POSITION_UNIT: "posiciones",
    ServiceQtyRule.PER_M2: "m² de ventanal",
    ServiceQtyRule.PER_LINEAR_METER: "ml de perímetro",
    ServiceQtyRule.FIXED: "cargo único del proyecto",
}


def evaluate_service_lines(
    articles: Sequence[ServiceArticle],
    positions: Sequence[ServicePositionMeasure],
) -> list[ServiceLine]:
    """Derive project services from the quoted positions' measures.

    Quantity per article by its declared rule: units, glazed area,
    perimeter in linear meters, or a single project charge. Money fields
    stay None when the article never declared a price.
    """
    total_units = sum(position.quantity for position in positions)
    total_area_m2 = _money(
        sum(
            position.width_mm * position.height_mm * position.quantity
            for position in positions
        )
        / _MM2_PER_M2
    )
    total_perimeter_m = _money(
        sum(
            Decimal("2")
            * (position.width_mm + position.height_mm)
            * position.quantity
            for position in positions
        )
        / _MM_PER_M
    )
    lines: list[ServiceLine] = []
    for article in articles:
        if article.qty_rule is ServiceQtyRule.PER_POSITION_UNIT:
            quantity = Decimal(total_units)
        elif article.qty_rule is ServiceQtyRule.PER_M2:
            quantity = total_area_m2
        elif article.qty_rule is ServiceQtyRule.PER_LINEAR_METER:
            quantity = total_perimeter_m
        else:
            quantity = Decimal("1")
        if quantity <= Decimal("0"):
            continue
        lines.append(
            ServiceLine(
                code=article.code,
                name=article.name,
                kind=article.kind,
                quantity=quantity,
                unit=_SERVICE_RULE_UNIT[article.qty_rule],
                unit_price=article.unit_price,
                unit_price_currency=article.unit_price_currency,
                total_price=(
                    _money(quantity * article.unit_price)
                    if article.unit_price is not None
                    else None
                ),
                unit_cost=article.unit_cost,
                unit_cost_currency=article.unit_cost_currency,
                total_cost=(
                    _money(quantity * article.unit_cost)
                    if article.unit_cost is not None
                    else None
                ),
                detail=_SERVICE_RULE_DETAIL[article.qty_rule],
            )
        )
    return lines
