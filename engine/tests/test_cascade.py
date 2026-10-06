"""P07 — cascade exactness and delta telescoping.

The waterfall is the estimator's trust surface: every row must add up in
Decimal to the stored project totals, or the operation is inconsistent and
we refuse to draw it. The delta decomposition telescopes by construction —
this file pins that contract plus the band's edge cases.
"""

from decimal import Decimal

import pytest

from dekopen_engine.cascade import (
    CascadeComponent,
    CascadePosition,
    DeltaLine,
    DeltaStage,
    band_state,
    delta_contributions,
    price_cascade,
)
from dekopen_engine.commercial import (
    CommercialLine,
    CommercialResult,
    PricingError,
    finish_lines,
    quantize_currency,
)

D = Decimal
TAX = D("0.19")


def _position(
    *,
    index: int = 1,
    quantity: int = 1,
    unit_cost: D | None = None,
    materials: D = D("80000"),
    waste: D = D("0"),
    labour_per_m2: D = D("0"),
    area_m2: D = D("4.8"),
    components: tuple[CascadeComponent, ...] = (),
    sell_delta: D = D("0"),
    exact: D = D("200000"),
    discount: D = D("0"),
) -> CascadePosition:
    if unit_cost is None:
        unit_cost = materials * (D("1") + waste) + area_m2 * labour_per_m2
    line_net = finish_lines(
        [
            CommercialLine(
                position_index=index,
                quantity=quantity,
                unit_cost=unit_cost,
                exact_unit_price=exact,
                discount=discount,
            )
        ],
        "CLP",
        TAX,
    ).lines[0][1]
    return CascadePosition(
        position_index=index,
        quantity=quantity,
        unit_cost=unit_cost,
        materials_cost=materials,
        waste_pct=waste,
        labour_per_m2=labour_per_m2,
        area_m2=area_m2,
        components=components,
        sell_delta=sell_delta,
        exact_unit_price=exact,
        discount=discount,
        line_net=line_net,
    )


def _totals(
    positions: list[CascadePosition],
    extras: tuple[Decimal, ...] = (),
) -> CommercialResult:
    return finish_lines(
        [
            CommercialLine(
                position_index=p.position_index,
                quantity=p.quantity,
                unit_cost=p.unit_cost,
                exact_unit_price=p.exact_unit_price,
                discount=p.discount,
            )
            for p in positions
        ],
        "CLP",
        TAX,
        tuple(extras),
    )


def test_cascade_rows_close_exactly_to_project_totals() -> None:
    positions = [
        _position(
            index=1,
            quantity=2,
            components=(
                CascadeComponent("PROFILE", D("50000")),
                CascadeComponent("GLASS", D("20000")),
                CascadeComponent("GLASS_TEMPERED", D("5000")),
                CascadeComponent("HARDWARE", D("5000")),
                CascadeComponent("COLOR_SURCHARGE", D("3000")),
            ),
            sell_delta=D("3000"),
            exact=D("160000"),
            discount=D("0.05"),
        ),
        _position(
            index=2,
            quantity=1,
            materials=D("120000"),
            waste=D("0.1"),
            labour_per_m2=D("25000"),
            area_m2=D("0.52"),
            components=(
                CascadeComponent("PROFILE", D("90000")),
                CascadeComponent("PANEL", D("20000")),
                CascadeComponent("FITTING", D("10000")),
            ),
            exact=D("250000"),
        ),
    ]
    totals = _totals(positions, extras=(D("80000"),))
    total_cost = sum(
        (p.unit_cost * p.quantity for p in positions), D("0")
    )
    cascade = price_cascade(
        positions,
        extras_net=D("80000"),
        project_net=totals.project_net,
        project_tax=totals.project_tax,
        project_gross=totals.project_gross,
        total_cost=total_cost,
    )
    amounts = {row.key: row.amount for row in cascade.rows}
    # Cost side: families + waste + labour close to the stored cost.
    families = sum(
        (amounts[key] for key in (
            "profiles", "reinforcement", "glass", "glass_surcharges",
            "panels", "hardware", "fittings", "extras_material",
        ) if key in amounts),
        D("0"),
    )
    assert families == amounts["materials"]
    assert (
        amounts["materials"] + amounts["waste"] + amounts["labour"]
        == amounts["cost_total"] == total_cost
    )
    # Sell side: cost + margin + surcharges = list; list − discount = net.
    assert (
        amounts["cost_total"] + amounts["margin"] + amounts["sell_surcharges"]
        == amounts["list_price"]
    )
    assert amounts["list_price"] - amounts["discount"] == amounts["positions_net"]
    assert amounts["positions_net"] + amounts["extras_net"] == amounts["net"]
    assert amounts["net"] + amounts["tax"] == amounts["gross"] == totals.project_gross
    # Sell surcharge row carries the D05 recargo (2 units × $3.000).
    assert amounts["sell_surcharges"] == D("6000")
    # Composition cost is attributed per family at line scale.
    assert amounts["glass_surcharges"] == D("10000")
    # Margen realizado es fracción exacta sobre el neto (precisión 80 del motor).
    from decimal import localcontext

    with localcontext() as context:
        context.prec = 80
        expected_margin = (totals.project_net - total_cost) / totals.project_net
    assert cascade.margin_realized == expected_margin


def test_cascade_matches_finish_lines_line_nets() -> None:
    """The cascade never recomputes a line — it reuses the stored net."""
    positions = [
        _position(index=1, quantity=3, materials=D("25000"),
                  components=(CascadeComponent("PROFILE", D("25000")),),
                  exact=D("31578.9474"), discount=D("0.05")),
        _position(index=2, quantity=1, exact=D("76500"),
                  materials=D("35000"), area_m2=D("1.0"), labour_per_m2=D("5000"),
                  components=(CascadeComponent("PROFILE", D("35000")),)),
    ]
    totals = _totals(positions)
    cascade = price_cascade(
        positions,
        extras_net=D("0"),
        project_net=totals.project_net,
        project_tax=totals.project_tax,
        project_gross=totals.project_gross,
        total_cost=sum((p.unit_cost * p.quantity for p in positions), D("0")),
    )
    by_index = {p["position_index"]: p for p in cascade.positions}
    assert by_index[1]["net"] == D("90000")
    assert by_index[2]["net"] == D("76500")


def test_cascade_refuses_inconsistent_totals() -> None:
    positions = [_position(index=1)]
    totals = _totals(positions)
    with pytest.raises(PricingError) as error:
        price_cascade(
            positions,
            extras_net=D("0"),
            project_net=totals.project_net + D("1"),
            project_tax=totals.project_tax,
            project_gross=totals.project_gross,
            total_cost=sum((p.unit_cost * p.quantity for p in positions), D("0")),
        )
    assert error.value.code == "inconsistent_pricing_result"


def test_cascade_rejects_nonfinite_and_empty() -> None:
    with pytest.raises(PricingError):
        price_cascade(
            [], extras_net=D("0"), project_net=D("0"), project_tax=D("0"),
            project_gross=D("0"), total_cost=D("0"),
        )
    position = CascadePosition(
        position_index=1, quantity=1, unit_cost=D("NaN"),
        materials_cost=D("80000"), waste_pct=D("0"), labour_per_m2=D("0"),
        area_m2=D("1"), components=(), sell_delta=D("0"),
        exact_unit_price=D("100000"), discount=D("0"), line_net=D("100000"),
    )
    with pytest.raises(PricingError):
        price_cascade(
            [position], extras_net=D("0"), project_net=D("100000"),
            project_tax=D("0"), project_gross=D("100000"),
            total_cost=D("NaN"),
        )


def _line(
    index: int, qty: int, cost: Decimal, exact: Decimal, discount: Decimal = D("0")
) -> DeltaLine:
    return DeltaLine(
        position_index=index, quantity=qty, unit_cost=cost,
        exact_unit_price=exact, discount=discount,
    )


def test_delta_contributions_telescope_to_exact_total() -> None:
    """Canonical scenario: a list-price rise lands fully in 'cost_list'."""
    base = (_line(1, 2, D("100000"), D("160000")), _line(2, 1, D("50000"), D("80000")))
    stages = (
        DeltaStage("baseline", base),
        DeltaStage("quantity", base),
        DeltaStage(
            "cost_list",
            (
                DeltaLine(1, 2, D("112000"), D("179200"), D("0")),
                _line(2, 1, D("50000"), D("80000")),
            ),
        ),
        DeltaStage(
            "discount",
            (
                DeltaLine(1, 2, D("112000"), D("179200"), D("0.05")),
                _line(2, 1, D("50000"), D("80000")),
            ),
        ),
    )
    contributions = delta_contributions(stages, "CLP", TAX)
    assert [c.driver for c in contributions] == ["quantity", "cost_list", "discount"]
    nets = [
        _stage_net_reference(stage) for stage in stages
    ]
    deltas = [c.net_delta for c in contributions]
    assert sum(deltas, D("0")) == nets[-1] - nets[0]
    cost_deltas = [c.cost_delta for c in contributions]
    assert cost_deltas == [D("0"), D("24000"), D("0")]
    # discount driver carries exactly the quantized discount effect.
    stage_net_before = quantize_currency(D("179200") * 2, "CLP") + D("80000")
    stage_net_after = (
        quantize_currency(D("179200") * 2 * D("0.95"), "CLP") + D("80000")
    )
    assert contributions[-1].net_delta == stage_net_after - stage_net_before


def _stage_net_reference(stage: DeltaStage) -> Decimal:
    return sum(
        (
            quantize_currency(
                line.exact_unit_price * line.quantity * (D("1") - line.discount),
                "CLP",
            )
            for line in stage.lines
        ),
        D("0"),
    ) + sum(stage.extras, D("0"))


def test_delta_every_driver_order_is_accepted_and_exact() -> None:
    """A full canonical chain — one stage per driver — still telescopes."""
    stages = (
        DeltaStage("baseline", (_line(1, 1, D("100000"), D("150000")),)),
        DeltaStage("quantity", (_line(1, 2, D("100000"), D("150000")),)),
        DeltaStage(
            "dimensions",
            (_line(1, 2, D("125000"), D("187500")), _line(2, 1, D("20000"), D("40000"))),
        ),
        DeltaStage(
            "glass",
            (_line(1, 2, D("127000"), D("190500")), _line(2, 1, D("20000"), D("40000"))),
        ),
        DeltaStage(
            "hardware",
            (_line(1, 2, D("130000"), D("195000")), _line(2, 1, D("20000"), D("40000"))),
        ),
        DeltaStage(
            "cost_list",
            (_line(1, 2, D("135000"), D("202500")), _line(2, 1, D("20000"), D("40000"))),
        ),
        DeltaStage(
            "fx",
            (_line(1, 2, D("137000"), D("205500")), _line(2, 1, D("20000"), D("40000"))),
        ),
        DeltaStage(
            "selections",
            (_line(1, 2, D("137000"), D("208500")), _line(2, 1, D("20000"), D("40000"))),
        ),
        DeltaStage(
            "commercial",
            (_line(1, 2, D("137000"), D("211500")), _line(2, 1, D("20000"), D("40000"))),
        ),
        DeltaStage(
            "discount",
            (_line(1, 2, D("137000"), D("211500"), D("0.03")), _line(2, 1, D("20000"), D("40000"))),
        ),
        DeltaStage(
            "services",
            (_line(1, 2, D("137000"), D("211500"), D("0.03")), _line(2, 1, D("20000"), D("40000"))),
            extras=(D("10000"), D("5000")),
        ),
    )
    contributions = delta_contributions(stages, "CLP", TAX)
    assert sum((c.net_delta for c in contributions), D("0")) == (
        contributions[-1].net_after - _stage_net_reference(stages[0])
    )
    # Each driver moved money exactly once.
    assert all(c.net_delta != 0 for c in contributions)
    # services contribution = the two added extras, undiscounted.
    assert contributions[-1].net_delta == D("15000")


def test_delta_rejects_unknown_driver() -> None:
    stages = (
        DeltaStage("baseline", (_line(1, 1, D("1"), D("2")),)),
        DeltaStage("mystery", (_line(1, 1, D("1"), D("3")),)),
    )
    with pytest.raises(PricingError) as error:
        delta_contributions(stages, "CLP", TAX)
    assert error.value.code == "unknown_delta_driver"


def test_band_state_edges() -> None:
    assert band_state(D("0.35"), D("0.25"), D("0.50")) == "IN_BAND"
    assert band_state(D("0.24"), D("0.25"), D("0.50")) == "BELOW_MIN"
    assert band_state(D("0.55"), D("0.25"), D("0.50")) == "ABOVE_MAX"
    assert band_state(None, D("0.25"), D("0.50")) == "BELOW_MIN"
    assert band_state(D("0.90"), D("0.25"), None) == "IN_BAND"
    with pytest.raises(PricingError) as error:
        band_state(D("0.30"), D("0.50"), D("0.25"))
    assert error.value.code == "invalid_margin_band"
