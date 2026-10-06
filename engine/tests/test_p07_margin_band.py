"""P07 — cascada comercial exacta, descomposición Δ y banda de margen.

Goldens del encargo: cada fila de la cascada se deriva en Decimal exacto
sobre un caso de dos posiciones (costos 100 y 12, como el escenario 12/100
del fixture de precios).
"""
from decimal import Decimal as D

import pytest

from dekopen_engine.cascade import (
    CascadeComponent,
    CascadePosition,
    CascadeResult,
    DeltaLine,
    DeltaStage,
    band_state,
    delta_contributions,
    price_cascade,
)
from dekopen_engine.commercial import PricingError

TAX = D('0.19')
# Posición golden: costo unitario 100 = materiales 80 + merma 8% (6.4) +
# proceso/MO (13.6 sobre 2 m²). Precio lista 160 con 10 u. de recargo de
# venta → margen fila 50. Descuento 10 %, qty 2 → neto línea 288.
COMPONENTS = (
    CascadeComponent(kind='PROFILE', cost=D('50')),
    CascadeComponent(kind='REINFORCEMENT', cost=D('10')),
    CascadeComponent(kind='GLASS', cost=D('15')),
    CascadeComponent(kind='HARDWARE', cost=D('5')),
)
POSITION = CascadePosition(
    position_index=1,
    quantity=2,
    unit_cost=D('100'),
    materials_cost=D('80'),
    waste_pct=D('0.08'),
    labour_per_m2=D('6.8'),          # 6.8/m² × 2 m² = 13.6
    area_m2=D('2'),
    components=COMPONENTS,
    sell_delta=D('5'),               # 5/u. → 10 línea
    exact_unit_price=D('160'),
    discount=D('0.10'),
    line_net=D('288'),               # 160×2×0.9
)
# Segunda posición barata: costo 12, lista 20, sin recargos, qty 1 → 18.
CHEAP = CascadePosition(
    position_index=2,
    quantity=1,
    unit_cost=D('12'),
    materials_cost=D('12'),
    waste_pct=D('0'),
    labour_per_m2=D('0'),
    area_m2=D('1'),
    components=(CascadeComponent(kind='GLASS', cost=D('12')),),
    sell_delta=D('0'),
    exact_unit_price=D('20'),
    discount=D('0.10'),
    line_net=D('18'),
)


def _cascade(
    positions: list[CascadePosition], extras: D = D('25')
) -> 'CascadeResult':
    nets = sum(p.line_net for p in positions)
    cost = sum((p.unit_cost * p.quantity for p in positions), D('0'))
    net = nets + extras
    return price_cascade(
        positions,
        extras_net=extras,
        project_net=net,
        project_tax=net * TAX,
        project_gross=net * (D('1') + TAX),
        total_cost=cost,
    )


def test_cascade_rows_close_exactly() -> None:
    result = _cascade([POSITION, CHEAP])
    rows = {row.key: row for row in result.rows}
    assert rows['materials'].amount == D('80') * 2 + D('12')
    assert rows['waste'].amount == D('80') * D('0.08') * 2
    assert rows['labour'].amount == D('6.8') * D('2') * 2
    assert rows['cost_total'].amount == D('212')
    assert rows['margin'].amount == (D('160') * 2 - D('10')) - D('200') + (D('20') - D('12'))
    assert rows['sell_surcharges'].amount == D('10')
    assert rows['list_price'].amount == D('340')
    assert rows['discount'].amount == D('34')
    assert rows['positions_net'].amount == D('306')
    assert rows['extras_net'].amount == D('25')
    assert rows['net'].amount == D('331')
    assert rows['tax'].amount == D('331') * TAX
    assert rows['gross'].amount == D('331') * (D('1') + TAX)
    assert rows['gross'].kind == 'total'
    # Telescopio: grupos + merma + MO = costo; +margen +recargos = lista.
    groups = sum(
        (row.amount for row in result.rows if row.kind == 'group'), D('0')
    )
    assert groups == rows['materials'].amount
    # (331−212)/331 = 0.35951661… exacto a la precisión de la autoridad.
    assert result.margin_realized is not None
    assert result.margin_realized.quantize(D('0.000001')) == D('0.359517')


def test_cascade_per_position_waterfall_closes() -> None:
    result = _cascade([POSITION], extras=D('0'))
    item = result.positions[0]
    assert item['cost'] == D('200')
    assert item['margin'] == D('110')       # 320 − 200 − 10
    assert item['sell'] == D('10')
    assert item['list_price'] == D('320')
    assert item['discount'] == D('32')
    assert item['net'] == D('288')
    assert item['groups']['profiles'] == D('100')
    assert item['groups']['glass'] == D('30')


def test_cascade_rejects_inconsistent_totals() -> None:
    with pytest.raises(PricingError):
        price_cascade(
            [POSITION],
            extras_net=D('0'), project_net=D('999'), project_tax=D('0'),
            project_gross=D('999'), total_cost=D('200'),
        )  # neto no cierra contra las líneas
    with pytest.raises(PricingError):
        price_cascade(
            [CascadePosition(
                position_index=1, quantity=1, unit_cost=D('999'),
                materials_cost=D('80'), waste_pct=D('0.08'),
                labour_per_m2=D('6.8'), area_m2=D('2'),
                components=COMPONENTS, sell_delta=D('0'),
                exact_unit_price=D('160'), discount=D('0'), line_net=D('160'),
            )],
            extras_net=D('0'), project_net=D('160'), project_tax=D('0'),
            project_gross=D('160'), total_cost=D('999'),
        )  # unit_cost ≠ materiales+merma+MO → cascada mentirosa, se rechaza


def test_delta_contributions_telescope() -> None:
    stages = (
        DeltaStage('baseline', (
            DeltaLine(1, 2, D('100'), D('160'), D('0.10')),
            DeltaLine(2, 1, D('12'), D('20'), D('0.10')),
        ), extras=(D('25'),)),
        DeltaStage('quantity', (
            DeltaLine(1, 3, D('100'), D('160'), D('0.10')),
            DeltaLine(2, 1, D('12'), D('20'), D('0.10')),
        ), extras=(D('25'),)),
        DeltaStage('cost_list', (
            DeltaLine(1, 3, D('105'), D('160'), D('0.10')),
            DeltaLine(2, 1, D('12'), D('20'), D('0.10')),
        ), extras=(D('25'),)),
        DeltaStage('commercial', (
            DeltaLine(1, 3, D('105'), D('170'), D('0.10')),
            DeltaLine(2, 1, D('12'), D('20'), D('0.10')),
        ), extras=(D('25'),)),
        DeltaStage('discount', (
            DeltaLine(1, 3, D('105'), D('170'), D('0.15')),
            DeltaLine(2, 1, D('12'), D('20'), D('0.15')),
        ), extras=(D('25'),)),
        DeltaStage('services', (
            DeltaLine(1, 3, D('105'), D('170'), D('0.15')),
            DeltaLine(2, 1, D('12'), D('20'), D('0.15')),
        ), extras=(D('40'),)),
    )
    contributions = delta_contributions(stages, 'CLP', TAX)
    by_driver = {c.driver: c for c in contributions}
    # baseline net = 160·2·0.9 + 20·0.9 + 25 = 288 + 18 + 25 = 331
    # quantity: +160·0.9 = +144        → 475
    # cost_list: sin efecto en venta    → 0
    # commercial: +10·3·0.9 = +27      → 502
    # discount: −0.05·(170·3 + 20)     → −26.5 → 475.5... neto final abajo
    # services: +15                    → +15
    assert by_driver['quantity'].net_delta == D('144')
    assert by_driver['quantity'].cost_delta == D('100')
    assert by_driver['cost_list'].net_delta == D('0')
    assert by_driver['cost_list'].cost_delta == D('15')
    assert by_driver['commercial'].net_delta == D('27')
    assert by_driver['services'].net_delta == D('15')
    first_net = D('288') + D('18') + D('25')
    last_net = contributions[-1].net_after
    assert sum((c.net_delta for c in contributions), D('0')) == last_net - first_net


def test_delta_rejects_unknown_driver_and_short_chain() -> None:
    with pytest.raises(PricingError):
        delta_contributions(
            (DeltaStage('baseline', (DeltaLine(1, 1, D('1'), D('2')),)),),
            'CLP', TAX)
    with pytest.raises(PricingError):
        delta_contributions(
            (
                DeltaStage('baseline', (DeltaLine(1, 1, D('1'), D('2')),)),
                DeltaStage('magic', (DeltaLine(1, 1, D('1'), D('2')),)),
            ),
            'CLP', TAX)


def test_band_state_thresholds() -> None:
    low, high = D('0.25'), D('0.50')
    assert band_state(D('0.30'), low, high) == 'IN_BAND'
    assert band_state(D('0.25'), low, high) == 'IN_BAND'   # frontera incluida
    assert band_state(D('0.50'), low, high) == 'IN_BAND'
    assert band_state(D('0.2499'), low, high) == 'BELOW_MIN'
    assert band_state(D('0.5001'), low, high) == 'ABOVE_MAX'
    # Sin margen computable nunca cae en banda: pide humano.
    assert band_state(None, low, high) == 'BELOW_MIN'
    with pytest.raises(PricingError):
        band_state(D('0.30'), high, low)                  # banda inválida


def _generated_position(index: int) -> CascadePosition:
    """Posición sintética pero consistente — cada campo cierra la cascada
    como lo haría una fila real del fixture (materiales + merma + MO)."""
    unit = D('40') + D(index % 7) * D('10')          # 40…100
    materials = unit * D('0.8')
    waste = D('0.05')
    labour_m2 = D('5')
    area = D('1') + D(index % 4) * D('0.5')          # 1…2.5 m²
    qty = 1 + index % 3                              # 1…3
    labour = labour_m2 * area
    unit_cost = materials * (D('1') + waste) + labour
    sell = D(index % 5)                               # 0…4/u.
    unit_price = unit_cost * D('1.4')                 # margen declarado
    discount = D('0.05')
    line_net = (unit_price * qty * (D('1') - discount)).quantize(D('0.0001'))
    return CascadePosition(
        position_index=index,
        quantity=qty,
        unit_cost=unit_cost,
        materials_cost=materials,
        waste_pct=waste,
        labour_per_m2=labour_m2,
        area_m2=area,
        components=(CascadeComponent(kind='PROFILE', cost=materials * D('0.6')),
                    CascadeComponent(kind='GLASS', cost=materials * D('0.4'))),
        sell_delta=sell,
        exact_unit_price=unit_price,
        discount=discount,
        line_net=line_net,
    )


@pytest.mark.parametrize('count', (12, 100))
def test_cascade_closes_on_fixture_sized_projects(count: int) -> None:
    """Golden del encargo: la cascada cierra exacto (Decimal) en proyectos
    de 12 y 100 posiciones — el total del motor es la suma de las filas."""
    positions = [_generated_position(i + 1) for i in range(count)]
    result = _cascade(positions)
    rows = {row.key: row for row in result.rows}
    positions_net = sum(p.line_net for p in positions)
    assert rows['positions_net'].amount == positions_net
    assert rows['net'].amount == positions_net + D('25')
    assert rows['gross'].amount == (positions_net + D('25')) * (D('1') + TAX)
    # Cada fila de posición cierra su propia cascada.
    assert len(result.positions) == count
    for item, position in zip(result.positions, positions):
        assert item['net'] == position.line_net
        assert item['cost'] == position.unit_cost * position.quantity
        # costo + margen + recargos de venta − descuento = neto de línea
        assert (item['cost'] + item['margin'] + item['sell']
                - item['discount'] == item['net'])
