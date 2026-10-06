"""P07 — price cascade and deterministic delta decomposition.

Both surfaces read resolved numbers only — the same authority the pricing
operation stores — and return plain ``Decimal`` values. Nothing here does
I/O; the UI never recomputes money.

Cascade contract (per position and per project):

    costo por familia → +merma → +proceso/MO → costo unitario
    → +margen → +recargos de venta → precio lista
    → −descuento → neto → +servicios/cargos → +IVA → total

The two residual rows are *definitions*, not lookups: ``margin`` is the
list price minus cost minus sell surcharges, and ``discount`` is the list
price minus the stored net — so the waterfall closes exactly in Decimal,
absorbing the per-line quantization the engine itself applied.

Stored snapshots are quantized (4 dp per unit, display-grid money on the
project totals), so a stored ``unit_cost`` can sit a fraction of a
cent-hundredth off its stored components' recomputed sum. Differences at
that scale are quantization noise, not inconsistency: each check below
tolerates ``QUANTUM_SLACK`` per unit (and ``MONEY_SLACK`` on the project
landmarks) and surfaces the absorbed residue as an explicit
``rounding_residual`` row instead of hiding it inside another family. A
divergence beyond slack is a corrupt snapshot and still refuses.

Delta decomposition ("¿Por qué cambió?"): the backend feeds an ordered
list of scenarios — one per driver, in the documented canonical order —
and each driver's contribution is the net difference between consecutive
stage totals. The sum of contributions equals the total Δ exactly, by
telescoping; no attribution rule can drift the totals.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from dekopen_engine.commercial import (
    PricingError,
    number,
    quantize_currency,
    target_project,
)

D = Decimal
ZERO = D("0")
ONE = D("1")


# Cost-group keys: the estimator-facing families a waterfall row names.
# Composition kinds map onto them; COLOR_SURCHARGE is a sell-side delta
# (D05) and never enters materials cost, so it is excluded here.
COST_GROUP_BY_KIND = {
    "PROFILE": "profiles",
    "REINFORCEMENT": "reinforcement",
    "GLASS": "glass",
    "PANEL": "panels",
    "HARDWARE": "hardware",
    "FITTING": "fittings",
    "EXTRA": "extras_material",
}
GLASS_SURCHARGE_PREFIX = "GLASS_"

# Tolerance floors for the close-checks, at the snapshot's declared grid:
# 4 dp per-unit fields → half a mil per unit; stored money landmarks are
# quantized at display precision (integer CLP) → half a unit plus slack.
QUANTUM_SLACK = D("0.0001")
MONEY_SLACK = D("0.51")

# Canonical display order of the cost families — fixed so two renders of
# the same operation can never disagree.
COST_GROUP_ORDER = (
    "profiles",
    "reinforcement",
    "glass",
    "glass_surcharges",
    "panels",
    "hardware",
    "fittings",
    "extras_material",
)


def component_group(kind: str) -> str | None:
    """Composition kind → cost-family key; sell-side kinds map to None."""
    if kind.startswith(GLASS_SURCHARGE_PREFIX):
        return "glass_surcharges"
    return COST_GROUP_BY_KIND.get(kind)


@dataclass(frozen=True)
class CascadeComponent:
    kind: str
    cost: Decimal  # per position unit


@dataclass(frozen=True)
class CascadePosition:
    """One position's resolved economics, as stored on the operation."""

    position_index: int
    quantity: int
    unit_cost: Decimal
    materials_cost: Decimal
    waste_pct: Decimal
    labour_per_m2: Decimal  # labor + installation rates combined
    area_m2: Decimal
    components: tuple[CascadeComponent, ...]
    sell_delta: Decimal  # per-unit sell additions (hw options, color, extras)
    exact_unit_price: Decimal
    discount: Decimal
    line_net: Decimal  # the stored, quantized line total


@dataclass(frozen=True)
class CascadeRow:
    """A waterfall row. ``kind`` = 'group' | 'step' | 'subtotal' | 'total'."""

    key: str
    amount: Decimal
    kind: str = "step"


@dataclass(frozen=True)
class CascadeResult:
    rows: tuple[CascadeRow, ...]
    positions: tuple[dict[str, Any], ...]
    margin_realized: Decimal | None  # (net − cost) / net, exact fraction


def _position_cascade(position: CascadePosition) -> dict[str, Any]:
    """One position's waterfall, at line level (× quantity)."""
    for value in (
        position.unit_cost,
        position.materials_cost,
        position.waste_pct,
        position.labour_per_m2,
        position.area_m2,
        position.sell_delta,
        position.exact_unit_price,
        position.discount,
        position.line_net,
    ):
        number(value)
    if position.quantity < 1 or position.position_index < 1:
        raise PricingError("invalid_positions")
    qty = D(position.quantity)
    with localcontext() as context:
        context.prec = 80
        groups: dict[str, Decimal] = {}
        materials_seen = ZERO
        for component in position.components:
            number(component.cost)
            group = component_group(component.kind)
            if group is None:
                continue
            groups[group] = groups.get(group, ZERO) + component.cost
            materials_seen += component.cost
        # The declared materials subtotal is the authority; composition rows
        # that miss the group map (a future kind) stay visible via residual.
        residual = position.materials_cost - materials_seen
        if residual != ZERO:
            groups["extras_material"] = groups.get("extras_material", ZERO) + residual
        materials = position.materials_cost * qty
        waste = position.materials_cost * position.waste_pct * qty
        labour = position.area_m2 * position.labour_per_m2 * qty
        cost = position.unit_cost * qty
        rounding = cost - (materials + waste + labour)
        if rounding != ZERO and abs(rounding) > qty * QUANTUM_SLACK:
            # The stored unit_cost must equal direct_cost — a snapshot that
            # does not close would draw a lying waterfall. Sub-grid residue
            # (quantization of the stored fields) surfaces as its own row.
            raise PricingError("inconsistent_pricing_result")
        sell = position.sell_delta * qty
        list_price = position.exact_unit_price * qty
        margin = list_price - cost - sell
        discount_amount = list_price - position.line_net
        return {
            "position_index": position.position_index,
            "groups": {
                key: groups.get(key, ZERO) * qty for key in COST_GROUP_ORDER
            },
            "materials": materials,
            "waste": waste,
            "labour": labour,
            "rounding": rounding,
            "cost": cost,
            "margin": margin,
            "sell": sell,
            "list_price": list_price,
            "discount": discount_amount,
            "net": position.line_net,
        }


def price_cascade(
    positions: Sequence[CascadePosition],
    *,
    extras_net: Decimal,
    project_net: Decimal,
    project_tax: Decimal,
    project_gross: Decimal,
    total_cost: Decimal,
) -> CascadeResult:
    """Project waterfall + per-position waterfalls.

    The aggregate closes against the stored totals: if the composed rows
    do not add up to them, the operation's snapshot is inconsistent and we
    refuse rather than show a waterfall that does not close.
    """
    for value in (extras_net, project_net, project_tax, project_gross, total_cost):
        number(value)
    if not positions:
        raise PricingError("invalid_positions")
    per_position = [_position_cascade(position) for position in positions]
    with localcontext() as context:
        context.prec = 80
        groups = {
            key: sum((entry["groups"][key] for entry in per_position), ZERO)
            for key in COST_GROUP_ORDER
        }
        materials = sum((entry["materials"] for entry in per_position), ZERO)
        waste = sum((entry["waste"] for entry in per_position), ZERO)
        labour = sum((entry["labour"] for entry in per_position), ZERO)
        margin = sum((entry["margin"] for entry in per_position), ZERO)
        sell = sum((entry["sell"] for entry in per_position), ZERO)
        list_price = sum((entry["list_price"] for entry in per_position), ZERO)
        discount = sum((entry["discount"] for entry in per_position), ZERO)
        positions_net = sum((entry["net"] for entry in per_position), ZERO)
        net = positions_net + extras_net
        total_qty = D(sum((position.quantity for position in positions), 0))
        slack = total_qty * QUANTUM_SLACK + MONEY_SLACK
        # The cost landmark closes against the recomposed direct sum: the
        # residual thus covers both the stored total's own quantization and
        # the per-position sub-grid residues.
        cost_residual = total_cost - (materials + waste + labour)
        net_residual = project_net - net
        gross_residual = project_gross - net - project_tax
        if (
            abs(cost_residual) > slack
            or abs(net_residual) > slack
            or abs(gross_residual) > slack
        ):
            raise PricingError("inconsistent_pricing_result")
        rows: list[CascadeRow] = [
            CascadeRow(key, groups[key], "group")
            for key in COST_GROUP_ORDER
            if groups[key] != ZERO
        ]
        rows.extend(
            [
                CascadeRow("materials", materials, "subtotal"),
                CascadeRow("waste", waste),
                CascadeRow("labour", labour),
            ]
        )
        if cost_residual != ZERO:
            rows.append(CascadeRow("rounding_residual", cost_residual))
        rows.extend(
            [
                CascadeRow("cost_total", materials + waste + labour + cost_residual, "subtotal"),
                # The residual is absorbed inside the cost landmark, so the
                # margin row keeps the stored margin and the waterfall still
                # telescopes: cost_total + margin + sell = list_price.
                CascadeRow("margin", margin),
                CascadeRow("sell_surcharges", sell),
                CascadeRow("list_price", list_price, "subtotal"),
                CascadeRow("discount", discount),
                CascadeRow("positions_net", positions_net, "subtotal"),
                CascadeRow("extras_net", extras_net),
            ]
        )
        if net_residual != ZERO:
            rows.append(CascadeRow("rounding_residual", net_residual))
        rows.append(CascadeRow("net", net + net_residual, "subtotal"))
        rows.append(CascadeRow("tax", project_tax))
        if gross_residual != ZERO:
            rows.append(CascadeRow("rounding_residual", gross_residual))
        rows.append(CascadeRow("gross", project_gross, "total"))
        realized_net = net + net_residual
        margin_realized = (
            (realized_net - total_cost) / realized_net
            if realized_net > ZERO else None
        )
        return CascadeResult(
            rows=tuple(rows),
            positions=tuple(per_position),
            margin_realized=margin_realized,
        )


# ——— Delta decomposition ———

# Canonical driver order: physical changes first, commercial decisions
# last, so each contribution answers "what did THIS decision move".
# Documented in docs/wiki (P07) and fixed by golden tests.
DELTA_DRIVER_ORDER = (
    "quantity",      # cantidades y posiciones agregadas/eliminadas
    "dimensions",    # medidas del vano (arrastra toda su composición)
    "glass",         # vidrio seleccionado y sus recargos
    "hardware",      # herrajes y accesorios (kit, fitting)
    "cost_list",     # lista de costos / materiales restante
    "fx",            # moneda o cotización
    "selections",    # opciones vendibles: herraje, color, extras
    "commercial",    # margen, modo, segmento, lista comercial
    "discount",      # descuento aplicado
    "services",      # servicios y cargos de proyecto
)


@dataclass(frozen=True)
class DeltaLine:
    position_index: int
    quantity: int
    unit_cost: Decimal
    exact_unit_price: Decimal
    discount: Decimal = ZERO


@dataclass(frozen=True)
class DeltaStage:
    """The project state after applying every driver up to ``driver``."""

    driver: str
    lines: tuple[DeltaLine, ...]
    extras: tuple[Decimal, ...] = ()
    target_margin: Decimal | None = None  # TARGET mode repricing


@dataclass(frozen=True)
class DeltaContribution:
    driver: str
    net_delta: Decimal
    cost_delta: Decimal
    net_after: Decimal


def _stage_net(stage: DeltaStage, currency: str, tax_rate: Decimal) -> Decimal:
    """The stage's project net with the engine's own rounding — but without
    the sale guard: an intermediate stage may legitimately price below cost
    (a cost driver applied before the commercial reprice), and that must
    not abort the decomposition."""
    number(tax_rate)
    if stage.target_margin is not None:
        costs = [(line.position_index, line.unit_cost * line.quantity) for line in stage.lines]
        return target_project(costs, stage.target_margin, currency, tax_rate, stage.extras).project_net
    for amount in stage.extras:
        number(amount)
    with localcontext() as context:
        context.prec = 80
        net = sum(
            (
                quantize_currency(
                    line.exact_unit_price * line.quantity * (ONE - line.discount),
                    currency,
                )
                for line in stage.lines
            ),
            ZERO,
        )
        return net + sum(stage.extras, ZERO)


def delta_contributions(
    stages: Sequence[DeltaStage], currency: str, tax_rate: Decimal
) -> tuple[DeltaContribution, ...]:
    """Consecutive stage totals → per-driver contribution to the net Δ.

    Σ contributions == net(last) − net(first) exactly, and the cost side
    telescopes the same way — the sum can never drift from the total.
    """
    if len(stages) < 2:
        raise PricingError("invalid_delta_stages")
    contributions: list[DeltaContribution] = []
    with localcontext() as context:
        context.prec = 80
        nets: list[Decimal] = []
        costs: list[Decimal] = []
        for stage in stages:
            if stage.driver not in DELTA_DRIVER_ORDER and stage.driver != "baseline":
                raise PricingError("unknown_delta_driver")
            nets.append(_stage_net(stage, currency, tax_rate))
            costs.append(
                sum(
                    (line.unit_cost * line.quantity for line in stage.lines),
                    ZERO,
                )
            )
        for index in range(1, len(stages)):
            contributions.append(
                DeltaContribution(
                    driver=stages[index].driver,
                    net_delta=nets[index] - nets[index - 1],
                    cost_delta=costs[index] - costs[index - 1],
                    net_after=nets[index],
                )
            )
    return tuple(contributions)


# ——— Margin band ———


def band_state(
    margin: Decimal | None, band_min: Decimal, band_max: Decimal | None
) -> str:
    """'IN_BAND' | 'BELOW_MIN' | 'ABOVE_MAX' for the org's declared band.

    A margin the authority cannot compute (empty/zero-price project) is
    never silently in-band: it reports BELOW_MIN so the approval gate
    still asks a human.
    """
    number(band_min)
    if band_max is not None:
        number(band_max)
        if band_max <= band_min:
            raise PricingError("invalid_margin_band")
    if margin is None or not margin.is_finite():
        return "BELOW_MIN"
    if margin < band_min:
        return "BELOW_MIN"
    if band_max is not None and margin > band_max:
        return "ABOVE_MAX"
    return "IN_BAND"
