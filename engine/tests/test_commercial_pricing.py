"""Independent monetary examples for the SHOT-08 owner contracts."""

from decimal import Decimal
from fractions import Fraction
from itertools import permutations
from random import Random

import pytest

from dekopen_engine.commercial import (
    CommercialLine, PricingError, PricingMode, convert_cost, direct_cost,
    discount_state, finish_lines, matrix_price, quantize_currency,
    target_project, typology_price, unit_price, validate_segment,
)

D = Decimal


def fraction_oracle(
    costs: list[tuple[int, Decimal]], margin: Decimal, currency: str
) -> tuple[dict[int, int], int, dict[int, int]]:
    q = Fraction(1) if currency == 'CLP' else Fraction(1, 100)
    retention = Fraction(1) - Fraction(margin)
    exact = {index: Fraction(cost) / retention / q for index, cost in costs}
    total = sum((Fraction(cost) for _, cost in costs), Fraction(0)) / retention / q
    target_floor, target_remainder = divmod(total.numerator, total.denominator)
    target_units = target_floor + (2 * target_remainder >= total.denominator)
    minimum = {
        index: -(-Fraction(cost).numerator * q.denominator //
                 (Fraction(cost).denominator * q.numerator))
        for index, cost in costs
    }
    if sum(minimum.values()) > target_units:
        raise ValueError('target_below_non_loss_minimum')
    floor = {index: value.numerator // value.denominator for index, value in exact.items()}
    remainder = {index: exact[index] - floor[index] for index in exact}
    assigned = {index: max(floor[index], minimum[index]) for index in exact}
    while sum(assigned.values()) > target_units:
        donors = [index for index in assigned if assigned[index] > minimum[index]]
        assigned[min(donors, key=lambda index: (remainder[index], -index))] -= 1
    residual = target_units - sum(assigned.values())
    order = sorted(assigned, key=lambda index: (-remainder[index], index))
    for index in order[:residual]:
        assigned[index] += 1
    return assigned, target_units, minimum


def result_units(lines: tuple[tuple[int, Decimal], ...], currency: str) -> dict[int, int]:
    q = Fraction(1) if currency == 'CLP' else Fraction(1, 100)
    units = {index: Fraction(amount) / q for index, amount in lines}
    assert all(value.denominator == 1 for value in units.values())
    return {index: value.numerator for index, value in units.items()}


@pytest.mark.parametrize('currency,value,expected', [
    ('CLP','1.5','2'), ('CLP','1.4999','1'), ('USD','1.005','1.01'),
    ('USD','1.0049','1.00'),
])
def test_currency_half_up(currency: str, value: str, expected: str) -> None:
    assert quantize_currency(D(value), currency) == D(expected)


def test_line_quantity_discount_and_aggregate_tax() -> None:
    result = finish_lines([
        CommercialLine(2, 3, D('0.1'), D('1.49'), D('0.1')),
        CommercialLine(1, 1, D('0.1'), D('3')),
    ], 'CLP', D('0.19'))
    assert result.lines == ((1, D('3')), (2, D('4')))
    assert (result.project_net, result.project_tax, result.project_gross) == (
        D('7'), D('1'), D('8'))
    # Per-line taxes would be 1+1; the normative project tax is 1.


def test_mode_one_materials_fx_and_no_early_rounding() -> None:
    converted = convert_cost(D('0.1234'), 'USD', 'CLP', D('900'))
    assert converted == D('116.613')
    cost = direct_cost([converted, D('10')], D('2'), D('0.08'), D('15'), D('12'))
    assert cost == D('190.74204')
    price = unit_price(PricingMode.COST_PLUS_MARGIN, cost=D('100000'), margin=D('0.35'),
                       area=D('1'), width=D('1000'), height=D('1000'))
    assert finish_lines([CommercialLine(1, 1, D('100000'), price)], 'CLP', D('0')).project_net == D('153846')


@pytest.mark.parametrize('foil,selected,expected', [
    (False, '100', '2000'), (True, '100', '2500'),
    (False, '150', '2140'), (True, '150', '2640'),
])
def test_mode_two_foil_and_glass_separate(foil: bool, selected: str, expected: str) -> None:
    assert typology_price(D('2'), D('1000'), foil, D(selected), D('100')) == D(expected)


def test_negative_glass_is_not_a_credit_or_clamp() -> None:
    with pytest.raises(PricingError, match='negative_glass_differential'):
        typology_price(D('1'), D('100'), False, D('9.99'), D('10'))


def test_mode_three_bilinear_oracle_nodes_edges_and_interior() -> None:
    cells = {(600,600): D('100'), (800,600): D('200'),
             (600,800): D('300'), (800,800): D('500')}
    assert matrix_price(D('600'), D('600'), {(600,600): D('100')}) == D('100')
    assert matrix_price(D('700'), D('600'), cells) == D('150')
    assert matrix_price(D('650'), D('700'), cells) == D('237.5')
    with pytest.raises(PricingError, match='missing_matrix_cell'):
        matrix_price(D('700'), D('700'), {(600,600): D('100')})
    with pytest.raises(PricingError, match='matrix_out_of_domain'):
        matrix_price(D('2400.01'), D('700'), cells)


def test_mode_four_ties_use_position_index_under_every_permutation() -> None:
    costs = [(3,D('1')), (1,D('1')), (2,D('1'))]
    for order in permutations(costs):
        result = target_project(order, D('0.30'), 'CLP', D('0.19'))
        assert result.lines == ((1,D('2')), (2,D('1')), (3,D('1')))
        assert (result.project_net,result.project_tax,result.project_gross) == (D('4'),D('1'),D('5'))


def test_mode_four_non_loss_floors_take_precedence() -> None:
    # 100.1 needs 101, while the second line has room to absorb the allocation.
    result = target_project([(1,D('100.1')), (2,D('1000'))], D('0.001'), 'CLP', D('0'))
    assert result.project_net == D('1101')
    assert result.lines == ((1,D('101')), (2,D('1000')))
    with pytest.raises(PricingError, match='target_below_non_loss_minimum'):
        target_project([(1,D('1.01')), (2,D('1.01'))], D('0'), 'CLP', D('0'))


def test_mode_four_usd_residual() -> None:
    assert target_project([(2,D('0.01')), (1,D('0.01'))], D('0.2'), 'USD', D('0')).lines == (
        (1,D('0.02')), (2,D('0.01')))


@pytest.mark.parametrize(('currency', 'costs', 'expected'), [
    ('USD', [(1, D('136.2')), (2, D('28539.1'))], ((1, D('258.35')), (2, D('54133.34')))),
    ('CLP', [(1, D('13620')), (2, D('2853910'))], ((1, D('25835')), (2, D('5413334')))),
])
def test_mode_four_true_remainder_tie_uses_lower_index(
    currency: str, costs: list[tuple[int, Decimal]], expected: tuple[tuple[int, Decimal], ...]
) -> None:
    for order in permutations(costs):
        assert target_project(order, D('0.4728'), currency, D('0')).lines == expected


@pytest.mark.parametrize(('currency', 'costs', 'expected'), [
    ('CLP', [(1, D('9')), (2, D('9')), (3, D('0.1'))],
     ((1, D('10')), (2, D('9')), (3, D('1')))),
    ('USD', [(1, D('0.09')), (2, D('0.09')), (3, D('0.001'))],
     ((1, D('0.10')), (2, D('0.09')), (3, D('0.01')))),
])
def test_mode_four_true_remainder_tie_removes_from_higher_index(
    currency: str, costs: list[tuple[int, Decimal]], expected: tuple[tuple[int, Decimal], ...]
) -> None:
    for order in permutations(costs):
        assert target_project(order, D('0.1'), currency, D('0')).lines == expected


def test_mode_four_multiple_ties_subquantum_and_large_coefficients() -> None:
    tied = [(4, D('1')), (2, D('1')), (1, D('1')), (3, D('1'))]
    assert target_project(tied, D('0.30'), 'CLP', D('0')).lines == (
        (1, D('2')), (2, D('2')), (3, D('1')), (4, D('1')))
    assert target_project([(1, D('0.001')), (2, D('0.001'))], D('0.9'), 'USD', D('0')).lines == (
        (1, D('0.01')), (2, D('0.01')))
    costs = [
        (1, D('1234567890123456789012345678901234567890.123456789')),
        (2, D('9876543210987654321098765432109876543210.987654321')),
        (3, D('0.000000001')),
    ]
    expected, target_units, minimum = fraction_oracle(costs, D('0.123456789'), 'USD')
    result = target_project(costs, D('0.123456789'), 'USD', D('0'))
    assert result_units(result.lines, 'USD') == expected
    assert sum(expected.values()) == target_units
    assert all(expected[index] >= minimum[index] for index in expected)


def test_mode_four_matches_independent_fraction_oracle() -> None:
    for currency, seed in (('CLP', 8041), ('USD', 8042)):
        random = Random(seed)
        successful = impossible = 0
        for case in range(500):
            count = random.randint(2, 8)
            indices = list(range(1, count + 1))
            random.shuffle(indices)
            if case % 10 == 0:
                scale = -3 if currency == 'CLP' else -5
                costs = [(index, D(random.randint(1, 9)).scaleb(scale)) for index in indices]
                margin = D(random.randint(0, 5000)).scaleb(-4)
            else:
                costs = [
                    (index, D(random.randint(1, 10**15)).scaleb(-random.randint(0, 9)))
                    for index in indices
                ]
                margin = D(random.randint(0, 9500)).scaleb(-4)
            try:
                expected, target_units, minimum = fraction_oracle(costs, margin, currency)
            except ValueError:
                impossible += 1
                with pytest.raises(PricingError, match='target_below_non_loss_minimum'):
                    target_project(costs, margin, currency, D('0'))
                continue
            successful += 1
            result = target_project(costs, margin, currency, D('0'))
            actual = result_units(result.lines, currency)
            assert actual == expected
            assert sum(actual.values()) == target_units
            assert all(actual[index] >= minimum[index] for index in actual)
            random.shuffle(costs)
            assert result_units(target_project(costs, margin, currency, D('0')).lines, currency) == expected
        assert successful == 450
        assert impossible == 50


@pytest.mark.parametrize('role,discount,confirmed,expected', [
    ('OWNER','0.1',False,'APPLIED'), ('ESTIMATOR','0.1',False,'APPLIED'),
    ('OWNER','0.1001',False,'APPLIED'), ('ESTIMATOR','0.1001',False,'PENDING'),
    ('ESTIMATOR','0.2',False,'PENDING'), ('OWNER','0.25',True,'APPLIED'),
])
def test_discount_governance(role: str, discount: str, confirmed: bool, expected: str) -> None:
    assert discount_state(role,D(discount),confirmed) == expected


@pytest.mark.parametrize('role,discount', [('ESTIMATOR','0.2001'), ('OWNER','0.2001'),
                                         ('WORKSHOP_MANAGER','0'), ('INSTALLER','0')])
def test_discount_permission_denied(role: str, discount: str) -> None:
    with pytest.raises(PricingError):
        discount_state(role,D(discount),False)


def test_mode_five_catalog_segment_and_loss_even_for_owner() -> None:
    price = unit_price(PricingMode.COMMERCIAL_LIST_WITH_DISCOUNTS, cost=D('1'), margin=D('0'),
                       area=D('1'),width=D('1000'),height=D('1000'),catalog_price=D('100'))
    validate_segment('CONSTRUCTION',D('0.25'),51)
    assert finish_lines([CommercialLine(1,51,D('50'),price,D('0.25'))], 'CLP',D('0')).project_net == D('3825')
    with pytest.raises(PricingError,match='invalid_segment_discount'):
        validate_segment('CONSTRUCTION',D('0.25'),50)
    with pytest.raises(PricingError,match='negative_margin'):
        finish_lines([CommercialLine(1,1,D('75.01'),price,D('0.25'))],'CLP',D('0'))


@pytest.mark.parametrize('value', ['NaN','Infinity','-1'])
def test_invalid_numeric_authorities(value: str) -> None:
    with pytest.raises(PricingError):
        convert_cost(D(value),'CLP','CLP')


def test_missing_fx_and_missing_tariff_are_typed() -> None:
    with pytest.raises(PricingError, match='missing_fx_authority'):
        convert_cost(D('1'),'USD','CLP')
    with pytest.raises(PricingError, match='missing_typology_authority'):
        unit_price(PricingMode.PRICE_PER_M2_BY_TYPOLOGY,cost=D('1'),margin=D('0'),
                   area=D('1'),width=D('1000'),height=D('1000'))


def test_extras_raise_net_and_tax_but_never_discount() -> None:
    # Instalación / traslado are project-level charges: they add to the net
    # after every position discount and bear the same tax rate.
    lines = [CommercialLine(1, 1, D('80'), D('100'), D('0.1'))]
    base = finish_lines(lines, 'CLP', D('0.19'))
    charged = finish_lines(lines, 'CLP', D('0.19'), extras=[D('10'), D('5')])
    assert charged.extras_net == D('15')
    assert charged.project_net == base.project_net + D('15')
    assert charged.project_tax == quantize_currency(charged.project_net * D('0.19'), 'CLP')
    assert charged.project_gross == charged.project_net + charged.project_tax


def test_target_project_receives_extras() -> None:
    result = target_project([(1, D('100'))], D('0.5'), 'CLP', D('0.19'), extras=[D('7')])
    assert result.extras_net == D('7')
    assert result.project_net == D('200') + D('7')
    assert result.project_tax == quantize_currency(result.project_net * D('0.19'), 'CLP')


@pytest.mark.parametrize('value', [D('-0.01'), D('-1000')])
def test_extras_reject_negative_amounts(value: Decimal) -> None:
    with pytest.raises(PricingError):
        finish_lines([CommercialLine(1, 1, D('80'), D('100'), D('0'))],
                     'CLP', D('0.19'), extras=[value])


def test_extras_reject_non_decimal() -> None:
    with pytest.raises(PricingError):
        finish_lines([CommercialLine(1, 1, D('80'), D('100'), D('0'))],
                     'CLP', D('0.19'), extras=[0.1])  # type: ignore[list-item]
