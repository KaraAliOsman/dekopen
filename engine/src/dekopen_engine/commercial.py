"""SHOT-08 commercial arithmetic. Resolved authorities in; no I/O or H6 changes."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext
from enum import Enum

D = Decimal
ZERO = D('0')
ONE = D('1')


class PricingError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class PricingMode(str, Enum):
    COST_PLUS_MARGIN = 'COST_PLUS_MARGIN'
    PRICE_PER_M2_BY_TYPOLOGY = 'PRICE_PER_M2_BY_TYPOLOGY'
    FIXED_PRICE_MATRIX_DIMENSIONAL = 'FIXED_PRICE_MATRIX_DIMENSIONAL'
    TARGET_GROSS_MARGIN_PROJECT = 'TARGET_GROSS_MARGIN_PROJECT'
    COMMERCIAL_LIST_WITH_DISCOUNTS = 'COMMERCIAL_LIST_WITH_DISCOUNTS'


def number(value: Decimal, *, positive: bool = False) -> Decimal:
    if (not isinstance(value, Decimal) or not value.is_finite()
            or value < ZERO or (positive and value == ZERO)):
        raise PricingError('invalid_decimal')
    return value


def fraction(value: Decimal, *, margin: bool = False) -> Decimal:
    number(value)
    if value > ONE or (margin and value == ONE):
        raise PricingError('invalid_fraction')
    return value


def quantum(currency: str) -> Decimal:
    if currency not in ('CLP', 'USD'):
        raise PricingError('unsupported_currency')
    return ONE if currency == 'CLP' else D('0.01')


def quantize_currency(value: Decimal, currency: str) -> Decimal:
    number(value)
    with localcontext() as context:
        context.prec = 80
        return value.quantize(quantum(currency), rounding=ROUND_HALF_UP)


def convert_cost(value: Decimal, source: str, target: str,
                 observed_rate: Decimal | None = None) -> Decimal:
    number(value)
    quantum(source)
    quantum(target)
    if source == target:
        return value
    if source != 'USD' or target != 'CLP' or observed_rate is None:
        raise PricingError('missing_fx_authority')
    number(observed_rate, positive=True)
    with localcontext() as context:
        context.prec = 80
        return value * observed_rate * D('1.05')


def direct_cost(materials: Sequence[Decimal], area_m2: Decimal, waste: Decimal,
                labor: Decimal, installation: Decimal) -> Decimal:
    for value in (*materials, area_m2, waste, labor, installation):
        number(value)
    with localcontext() as context:
        context.prec = 80
        return sum(materials, ZERO) * (ONE + waste) + area_m2 * (labor + installation)


def matrix_price(width: Decimal, height: Decimal,
                 cells: Mapping[tuple[int, int], Decimal]) -> Decimal:
    for value in (width, height):
        number(value)
        if not D('600') <= value <= D('2400'):
            raise PricingError('matrix_out_of_domain')
    x0, y0 = int(width // D('200')) * 200, int(height // D('200')) * 200
    x1 = x0 if width == D(x0) else x0 + 200
    y1 = y0 if height == D(y0) else y0 + 200
    keys = {(x0, y0), (x1, y0), (x0, y1), (x1, y1)}
    if any(key not in cells for key in keys):
        raise PricingError('missing_matrix_cell')
    for key in keys:
        number(cells[key])
    with localcontext() as context:
        context.prec = 80
        tx = ZERO if x0 == x1 else (width - D(x0)) / D(x1 - x0)
        ty = ZERO if y0 == y1 else (height - D(y0)) / D(y1 - y0)
        return ((ONE-tx)*(ONE-ty)*cells[x0, y0] + tx*(ONE-ty)*cells[x1, y0]
                + (ONE-tx)*ty*cells[x0, y1] + tx*ty*cells[x1, y1])


def typology_price(area: Decimal, rate: Decimal, foil: bool,
                   selected_glass_cost: Decimal, base_glass_cost: Decimal) -> Decimal:
    for value in (area, rate, selected_glass_cost, base_glass_cost):
        number(value)
    if selected_glass_cost < base_glass_cost:
        raise PricingError('negative_glass_differential')
    with localcontext() as context:
        context.prec = 80
        base = area * rate
        return (base * (D('1.25') if foil else ONE)
                + (selected_glass_cost-base_glass_cost)*area*D('1.40'))


def discount_state(role: str, discount: Decimal, confirmed: bool) -> str:
    fraction(discount)
    if role not in ('OWNER', 'ESTIMATOR'):
        raise PricingError('pricing_permission_denied')
    if discount <= D('0.10'):
        return 'APPLIED'
    if discount <= D('0.20'):
        return 'APPLIED' if role == 'OWNER' else 'PENDING'
    if role != 'OWNER' or not confirmed:
        raise PricingError('owner_confirmation_required')
    return 'APPLIED'


def validate_segment(segment: str, discount: Decimal, total_quantity: int) -> None:
    fraction(discount)
    valid = (segment == 'RETAIL' and discount == ZERO
             or segment == 'ARCHITECT' and D('0.08') <= discount <= D('0.12')
             or segment == 'CONSTRUCTION' and total_quantity > 50
             and D('0.18') <= discount <= D('0.25'))
    if not valid:
        raise PricingError('invalid_segment_discount')


def unit_price(mode: PricingMode, *, cost: Decimal, margin: Decimal,
               area: Decimal, width: Decimal, height: Decimal, foil: bool = False,
               rate: Decimal | None = None, selected_glass: Decimal | None = None,
               base_glass: Decimal | None = None,
               cells: Mapping[tuple[int, int], Decimal] | None = None,
               catalog_price: Decimal | None = None) -> Decimal:
    number(cost)
    fraction(margin, margin=True)
    with localcontext() as context:
        context.prec = 80
        if mode == PricingMode.COST_PLUS_MARGIN:
            return cost / (ONE-margin)
        if mode == PricingMode.PRICE_PER_M2_BY_TYPOLOGY:
            if rate is None or selected_glass is None or base_glass is None:
                raise PricingError('missing_typology_authority')
            return typology_price(area, rate, foil, selected_glass, base_glass)
        if mode == PricingMode.FIXED_PRICE_MATRIX_DIMENSIONAL:
            if cells is None:
                raise PricingError('missing_matrix_authority')
            return matrix_price(width, height, cells)
        if mode == PricingMode.COMMERCIAL_LIST_WITH_DISCOUNTS:
            if catalog_price is None:
                raise PricingError('missing_commercial_price')
            return number(catalog_price)
    raise PricingError('project_mode_requires_project')


@dataclass(frozen=True)
class CommercialLine:
    position_index: int
    quantity: int
    unit_cost: Decimal
    exact_unit_price: Decimal
    discount: Decimal = ZERO


@dataclass(frozen=True)
class CommercialResult:
    lines: tuple[tuple[int, Decimal], ...]
    project_net: Decimal
    project_tax: Decimal
    project_gross: Decimal
    extras_net: Decimal = ZERO


def totals(lines: Sequence[tuple[int, Decimal]], currency: str,
           tax_rate: Decimal, extras: Sequence[Decimal] = ()) -> CommercialResult:
    """Project totals: discounted position lines plus project-level charges
    (installation, freight) that are never discounted but do tax."""
    fraction(tax_rate)
    extras_net = ZERO
    for amount in extras:
        extras_net += number(amount)
    with localcontext() as context:
        context.prec = 80
        ordered = tuple(sorted(lines))
        net = sum((price for _, price in ordered), ZERO) + extras_net
        tax = quantize_currency(net * tax_rate, currency)
        return CommercialResult(ordered, net, tax, net + tax, extras_net)


def finish_lines(lines: Sequence[CommercialLine], currency: str,
                 tax_rate: Decimal, extras: Sequence[Decimal] = ()) -> CommercialResult:
    if not lines or len({line.position_index for line in lines}) != len(lines):
        raise PricingError('invalid_positions')
    result = []
    with localcontext() as context:
        context.prec = 80
        for line in lines:
            if line.quantity < 1 or line.position_index < 1:
                raise PricingError('invalid_positions')
            number(line.unit_cost)
            number(line.exact_unit_price)
            fraction(line.discount)
            net = quantize_currency(line.exact_unit_price * line.quantity
                                    * (ONE-line.discount), currency)
            if net < line.unit_cost * line.quantity:
                raise PricingError('negative_margin')
            result.append((line.position_index, net))
    return totals(result, currency, tax_rate, extras)


def _decimal_ratio(value: Decimal) -> tuple[int, int]:
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise PricingError('invalid_decimal')
    coefficient = 0
    for digit in digits:
        coefficient = coefficient * 10 + digit
    if sign:
        coefficient = -coefficient
    if exponent >= 0:
        return coefficient * 10 ** exponent, 1
    return coefficient, 10 ** -exponent


def _currency_amount(units: int, currency: str) -> Decimal:
    if currency == 'CLP':
        return D(units)
    return D((0, tuple(int(digit) for digit in str(units)), -2))


def target_project(costs: Sequence[tuple[int, Decimal]], margin: Decimal,
                   currency: str, tax_rate: Decimal,
                   extras: Sequence[Decimal] = ()) -> CommercialResult:
    fraction(margin, margin=True)
    q_numerator, q_denominator = _decimal_ratio(quantum(currency))
    if not costs or len({index for index, _ in costs}) != len(costs):
        raise PricingError('invalid_positions')
    cost_ratios = {}
    for index, cost in costs:
        if index < 1:
            raise PricingError('invalid_positions')
        cost_ratios[index] = _decimal_ratio(number(cost))
    common_cost_denominator = max(denominator for _, denominator in cost_ratios.values())
    total_cost_numerator = sum(
        numerator * (common_cost_denominator // denominator)
        for numerator, denominator in cost_ratios.values()
    )
    if total_cost_numerator == 0:
        raise PricingError('undefined_project_margin')
    margin_numerator, margin_denominator = _decimal_ratio(margin)
    divisor_numerator = (margin_denominator - margin_numerator) * q_numerator
    divisor_denominator = margin_denominator * q_denominator
    target_numerator = total_cost_numerator * divisor_denominator
    target_denominator = common_cost_denominator * divisor_numerator
    target_floor, target_remainder = divmod(target_numerator, target_denominator)
    target_units = target_floor + (2 * target_remainder >= target_denominator)
    minimum = {
        index: (numerator * q_denominator + denominator * q_numerator - 1)
        // (denominator * q_numerator)
        for index, (numerator, denominator) in cost_ratios.items()
    }
    if sum(minimum.values()) > target_units:
        raise PricingError('target_below_non_loss_minimum')
    floor = {}
    remainder = {}
    remainder_denominator = {}
    for index, (numerator, denominator) in cost_ratios.items():
        scaled_numerator = numerator * divisor_denominator
        scaled_denominator = denominator * divisor_numerator
        floor[index], remainder[index] = divmod(scaled_numerator, scaled_denominator)
        remainder_denominator[index] = scaled_denominator
    common_remainder_denominator = max(remainder_denominator.values())
    rank = {
        index: remainder[index] * (common_remainder_denominator // remainder_denominator[index])
        for index in remainder
    }
    assigned = {index: max(floor[index], minimum[index]) for index in floor}
    while sum(assigned.values()) > target_units:
        candidates = [index for index in assigned if assigned[index] > minimum[index]]
        assigned[min(candidates, key=lambda index: (rank[index], -index))] -= 1
    residual = target_units - sum(assigned.values())
    for index in sorted(assigned, key=lambda item: (-rank[item], item))[:residual]:
        assigned[index] += 1
    return totals([(index, _currency_amount(units, currency))
                   for index, units in assigned.items()], currency, tax_rate, extras)
