"""Deterministic kit-class selection against finished dimensions and mass.

D04 contract: kits are classes inside a (system × opening) family. The
engine resolves the tightest compatible class, expands the components with
their declared quantity/cut rules, sums mass and cost, and validates the
declared restrictions — each refusal names the class, the real leaf value
and the way out (next class up, or a narrower/lighter leaf).
"""

from decimal import Decimal
from dataclasses import dataclass

from dekopen_engine.models import (
    BayOpeningType,
    HandleColorOption,
    HandleModelOption,
    HardwareComponent,
    HardwareItem,
    HardwareKitRule,
    HardwareOption,
    HardwarePickingLine,
    HardwareSelectionPrice,
    MachiningDeclaration,
    SystemParams,
)
from dekopen_engine.weight import ExactLeafWeight, with_hardware_weight


class NoCompatibleHardwareKit(ValueError):
    """No declared kit satisfies the leaf. `context` carries the leaf size
    and the compatible kits' dimensional envelope when the failure is
    dimensional, so the API can name the real constraint instead of an
    opaque identifier."""

    def __init__(self, message: str, *, context: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.context = context or {}


class AmbiguousHardwareKit(ValueError):
    pass


class HardwareSelectionError(ValueError):
    """A leaf selected a sellable datum the family catalog never declares
    (handle model/colour, option) or broke the family's declared handle
    range. Carries the issue code + params the evaluator surfaces
    verbatim."""

    def __init__(self, code: str, message: str, params: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.params = params or {}


def normalize_opening_type(opening: BayOpeningType | str) -> str:
    """The hardware family a leaf evaluates against (D03): a leaf's
    `Opening` resolves to its group in `leaf_hardware_group`; a legacy
    enum still decodes here for callers that kept it."""
    if not isinstance(opening, BayOpeningType):
        return opening
    if opening in (BayOpeningType.TURN_LEFT, BayOpeningType.TURN_RIGHT):
        return "TURN"
    if opening in (BayOpeningType.TILT_TURN_LEFT, BayOpeningType.TILT_TURN_RIGHT):
        return "TILT_TURN"
    if opening in (BayOpeningType.SLIDING_2L, BayOpeningType.SLIDING_3L,
                   BayOpeningType.SLIDING_4L, BayOpeningType.SLIDING):
        return "SLIDING"
    if opening in (BayOpeningType.DOOR_ENTRY, BayOpeningType.DOOR_DOUBLE):
        return "DOOR"
    return str(opening.value)


def expand_components(
    components: list[HardwareComponent], *,
    leaf_width_mm: Decimal, leaf_height_mm: Decimal,
    option_sku: str | None = None,
) -> list[HardwareComponent]:
    """Resolved BOM lines: declared qty/cut rules applied to the leaf."""
    return [
        component.expanded(
            leaf_width_mm=leaf_width_mm,
            leaf_height_mm=leaf_height_mm,
            option_sku=option_sku,
        )
        for component in components
    ]


def _components_cost_clp(components: list[HardwareComponent]) -> Decimal | None:
    """Σ resolved component cost; None when any line never declared one,
    and None on an empty list — undeclared is not zero."""
    if not components:
        return None
    total = Decimal("0")
    for component in components:
        if component.cost_clp is None:
            return None
        assert component.qty is not None
        total += component.cost_clp * component.qty
    return total


def kit_cost_clp(
    kit: HardwareKitRule, *, leaf_width_mm: Decimal, leaf_height_mm: Decimal
) -> Decimal | None:
    """Declared component cost of one class at this leaf size."""
    return _components_cost_clp(
        expand_components(
            kit.contents, leaf_width_mm=leaf_width_mm, leaf_height_mm=leaf_height_mm
        )
    )


def _machining_of(
    components: list[HardwareComponent],
) -> list[MachiningDeclaration]:
    """Machining the emitted components declare. Coordinates are only
    EMITTED when the catalog declared them — never invented (P14 input)."""
    emitted: list[MachiningDeclaration] = []
    for component in components:
        for declaration in component.machining:
            emitted.append(
                declaration.model_copy(
                    update={
                        "status": (
                            "EMITTED"
                            if declaration.u_mm is not None
                            else "DECLARED_NOT_EMITTED"
                        )
                    }
                )
            )
    return emitted


@dataclass(frozen=True, slots=True)
class HardwareCandidateEvaluation:
    kit: HardwareKitRule
    opening_match: bool
    rail_match: bool
    width_match: bool
    height_match: bool
    # Declared class restrictions beyond the envelope (D04): leaf
    # slenderness and the minimum height a stay (compás) needs.
    ratio_match: bool
    stay_height_match: bool
    exact_total_weight: ExactLeafWeight
    # None = the leaf mass is UNKNOWN — compatibility is undecidable, never
    # silently certified.
    weight_match: bool | None

    @property
    def compatible(self) -> bool:
        return (self.opening_match and self.rail_match and self.width_match
                and self.height_match and self.ratio_match
                and self.stay_height_match and self.weight_match is True)


def evaluate_hardware_candidates(
    *, opening_group: str, opening_label: str | None = None,
    width_mm: Decimal, height_mm: Decimal,
    base_weight: ExactLeafWeight, params: SystemParams, explicit_sku: str | None = None,
    option_components: list[HardwareComponent] | None = None,
) -> list[HardwareCandidateEvaluation]:
    """Every kit of the catalog, always — the explicit pick constrains
    resolution, never the evidence: the failure message and the inspector
    both need the sibling classes' verdicts to name the way out."""
    candidates: list[HardwareCandidateEvaluation] = []
    extras = list(option_components or [])
    for kit in params.available_hardware_kits:
        exact = with_hardware_weight(
            base_weight, kit, params,
            leaf_width_mm=width_mm, leaf_height_mm=height_mm,
            extra_components=extras,
        )
        total = exact.total_weight_kg
        candidates.append(HardwareCandidateEvaluation(
            kit=kit, opening_match=kit.opening_type == opening_group,
            rail_match=kit.rail_type is params.rail_type,
            width_match=kit.min_leaf_width_mm <= width_mm <= kit.max_leaf_width_mm,
            height_match=kit.min_leaf_height_mm <= height_mm <= kit.max_leaf_height_mm,
            ratio_match=(
                kit.max_aspect_ratio is None
                or (width_mm > Decimal("0")
                    and height_mm / width_mm <= kit.max_aspect_ratio)
            ),
            stay_height_match=(
                kit.stay_arms_qty <= 0
                or kit.min_stay_height_mm is None
                or height_mm >= kit.min_stay_height_mm
            ),
            exact_total_weight=exact,
            weight_match=(None if total is None else total <= kit.max_leaf_weight_kg),
        ))
    return candidates


def _class_tightness(candidate: HardwareCandidateEvaluation) -> tuple[Decimal, Decimal, Decimal]:
    """Tightest class first: the smallest admitted leaf mass, then the
    narrowest envelope. The sku is deliberately not a tie-break — two
    identical-envelope classes are a catalog ambiguity, never a coin
    flip."""
    kit = candidate.kit
    return (
        kit.max_leaf_weight_kg, kit.max_leaf_width_mm, kit.max_leaf_height_mm,
    )


def resolve_hardware_evaluations(
    evaluations: list[HardwareCandidateEvaluation], *, opening_group: str,
    opening_label: str | None = None,
    explicit_sku: str | None = None,
    leaf_width_mm: Decimal | None = None,
    leaf_height_mm: Decimal | None = None,
) -> tuple[HardwareKitRule, ExactLeafWeight]:
    label = explicit_sku or opening_label or opening_group
    candidates = [candidate for candidate in evaluations if candidate.compatible]
    if explicit_sku is not None:
        # The leaf pinned a class — resolution honours that pick only.
        candidates = [c for c in candidates if c.kit.sku == explicit_sku]
    # Kits matching opening and rail but failing a concrete check — their
    # merged envelope is the constraint the user must satisfy.
    matched = [
        candidate for candidate in evaluations
        if candidate.opening_match and candidate.rail_match
    ]

    def failure_context(axis: str) -> dict[str, str]:
        context: dict[str, str] = {"axis": axis, "opening": label}
        if leaf_width_mm is not None and leaf_height_mm is not None:
            context["leaf_width_mm"] = str(leaf_width_mm)
            context["leaf_height_mm"] = str(leaf_height_mm)
        if matched:
            context["kit_min_width_mm"] = str(min(c.kit.min_leaf_width_mm for c in matched))
            context["kit_max_width_mm"] = str(max(c.kit.max_leaf_width_mm for c in matched))
            context["kit_min_height_mm"] = str(min(c.kit.min_leaf_height_mm for c in matched))
            context["kit_max_height_mm"] = str(max(c.kit.max_leaf_height_mm for c in matched))
            labels = sorted({c.kit.class_label for c in matched if c.kit.class_label})
            if labels:
                context["class_label"] = labels[-1]
        # D04: the refusal names the way out. An explicit class that failed
        # while another family class fits → heavier/next class with its
        # price delta when both costs are declared. When nothing fits, the
        # heaviest matched class is named so the user can split the bay or
        # lighten the leaf.
        compatible = [candidate for candidate in matched if candidate.compatible]
        suggested = min(
            (c for c in compatible if explicit_sku is None or c.kit.sku != explicit_sku),
            key=_class_tightness,
            default=None,
        )
        if suggested is not None:
            context["suggestion"] = "heavier_class"
            context["suggested_sku"] = suggested.kit.sku
            context["suggested_name"] = suggested.kit.name
            if suggested.kit.class_label:
                context["suggested_class_label"] = suggested.kit.class_label
            context["suggested_max_weight_kg"] = str(suggested.kit.max_leaf_weight_kg)
            if leaf_width_mm is not None and leaf_height_mm is not None:
                delta = None
                if explicit_sku is not None:
                    failed = next(
                        (c.kit for c in matched if c.kit.sku == explicit_sku), None
                    )
                    if failed is not None:
                        failed_cost = kit_cost_clp(
                            failed,
                            leaf_width_mm=leaf_width_mm,
                            leaf_height_mm=leaf_height_mm,
                        )
                        suggested_cost = kit_cost_clp(
                            suggested.kit,
                            leaf_width_mm=leaf_width_mm,
                            leaf_height_mm=leaf_height_mm,
                        )
                        if failed_cost is not None and suggested_cost is not None:
                            delta = suggested_cost - failed_cost
                if delta is not None:
                    context["delta_clp"] = str(delta)
        elif matched:
            heaviest = max(matched, key=lambda c: c.kit.max_leaf_weight_kg)
            context["suggestion"] = "split_bay"
            context["heaviest_sku"] = heaviest.kit.sku
            context["heaviest_name"] = heaviest.kit.name
            if heaviest.kit.class_label:
                context["heaviest_class_label"] = heaviest.kit.class_label
            context["heaviest_max_weight_kg"] = str(heaviest.kit.max_leaf_weight_kg)
        return context

    if not candidates:
        undecidable = [
            candidate for candidate in evaluations
            if candidate.weight_match is None and candidate.opening_match
            and candidate.rail_match and candidate.width_match and candidate.height_match
            and candidate.ratio_match and candidate.stay_height_match
        ]
        if undecidable:
            reasons = sorted({
                reason
                for candidate in undecidable
                for reason in candidate.exact_total_weight.weight_unknown_reasons
            })
            raise NoCompatibleHardwareKit(
                "Hardware compatibility undecidable — leaf mass unknown: "
                + ", ".join(reasons),
                context=failure_context("undecidable"),
            )
        # Axis of failure. A pinned class reports its own broken bound;
        # auto-resolution aggregates the family: a kit whose envelope the
        # leaf escapes fails on size; a kit it fits that still rejects
        # carries a mass violation.
        pinned = (
            next((c for c in evaluations if c.kit.sku == explicit_sku), None)
            if explicit_sku is not None
            else None
        )
        if pinned is not None:
            if not pinned.width_match or not pinned.height_match:
                axis = "size"
            elif not pinned.ratio_match:
                axis = "ratio"
            elif not pinned.stay_height_match:
                axis = "stay_height"
            else:
                axis = "weight"
        elif matched and all(c.width_match and c.height_match for c in matched):
            if any(not c.stay_height_match for c in matched):
                axis = "stay_height"
            elif any(not c.ratio_match for c in matched):
                axis = "ratio"
            else:
                axis = "weight"
        elif matched:
            axis = "size"
        else:
            axis = ""
        context = failure_context(axis)
        if axis == "weight":
            overweight = [c for c in matched if c.weight_match is False]
            totals = [
                c.exact_total_weight.total_weight_kg
                for c in overweight
                if c.exact_total_weight.total_weight_kg is not None
            ]
            if totals:
                context["leaf_weight_kg"] = str(min(totals))
                # The bound the rejection names is the failed class's —
                # an explicit pick says "la clase estándar admite hasta
                # 80 kg"; an auto-resolution over the family says the
                # heaviest rejected bound.
                failed = (
                    [c for c in overweight if c.kit.sku == explicit_sku]
                    if explicit_sku is not None
                    else overweight
                )
                context["kit_max_weight_kg"] = str(
                    max(c.kit.max_leaf_weight_kg for c in (failed or overweight))
                )
        elif axis == "ratio" and leaf_width_mm and leaf_height_mm and leaf_width_mm > 0:
            context["leaf_aspect_ratio"] = str(
                (leaf_height_mm / leaf_width_mm).quantize(Decimal("0.001"))
            )
            ratios = [
                c.kit.max_aspect_ratio for c in matched if c.kit.max_aspect_ratio is not None
            ]
            if ratios:
                context["kit_max_aspect_ratio"] = str(max(ratios))
        elif axis == "stay_height":
            bounds = [
                c.kit.min_stay_height_mm
                for c in matched
                if c.kit.min_stay_height_mm is not None
            ]
            if bounds:
                context["stay_min_height_mm"] = str(min(bounds))
        raise NoCompatibleHardwareKit(
            f"No compatible hardware kit: {label}", context=context,
        )
    # D04: several compatible classes resolve to the tightest one — the
    # class whose envelope most closely admits the leaf. Identical
    # envelopes stay an ambiguity, never a coin flip.
    candidates.sort(key=_class_tightness)
    if len(candidates) > 1 and _class_tightness(candidates[0]) == _class_tightness(
        candidates[1]
    ):
        raise AmbiguousHardwareKit(f"Ambiguous hardware kits: {label}")
    return candidates[0].kit, candidates[0].exact_total_weight


def resolve_hardware_kit(
    *, opening_group: str, opening_label: str | None = None,
    width_mm: Decimal, height_mm: Decimal,
    base_weight: ExactLeafWeight, params: SystemParams, explicit_sku: str | None = None,
) -> tuple[HardwareKitRule, ExactLeafWeight]:
    return resolve_hardware_evaluations(evaluate_hardware_candidates(
        opening_group=opening_group, opening_label=opening_label,
        width_mm=width_mm, height_mm=height_mm, base_weight=base_weight,
        params=params, explicit_sku=explicit_sku,
    ), opening_group=opening_group, opening_label=opening_label, explicit_sku=explicit_sku)


def resolved_handle_height_mm(
    family: object, *, leaf_height_mm: Decimal, declared_mm: Decimal | None
) -> Decimal | None:
    """The leaf's handle height: its declared value, else the family's
    declared rule (centred / fixed from base / declared range default)."""
    if declared_mm is not None:
        return declared_mm
    if family is None:
        return None
    rule = getattr(family, "handle_height_rule", None)
    if rule == "CENTERED":
        return leaf_height_mm / Decimal("2")
    if rule == "FIXED_FROM_BASE":
        return getattr(family, "handle_height_default_mm", None)
    if rule == "RANGE":
        return getattr(family, "handle_height_default_mm", None)
    return getattr(family, "handle_height_default_mm", None)


def build_hardware_item(
    *,
    kit: HardwareKitRule,
    exact_weight: ExactLeafWeight,
    opening: BayOpeningType | str,
    bay_id: str,
    leaf_id: str | None,
    leaf_width_mm: Decimal,
    leaf_height_mm: Decimal,
    params: SystemParams,
    handle_model_sku: str | None = None,
    handle_color_sku: str | None = None,
    handle_height_mm: Decimal | None = None,
    option_skus: list[str] | None = None,
) -> HardwareItem:
    """Emission-time BOM line for the resolved class: expanded components,
    validated sellable selections, summed mass/cost, declared machining.

    Refuses (HardwareSelectionError) a model/colour/option the family never
    declares and a handle height outside the family's editable range.
    """
    family_key = normalize_opening_type(opening)
    family = params.hardware_families.get(family_key)

    handle_model: HandleModelOption | None = None
    if handle_model_sku is not None:
        handle_model = next(
            (m for m in (family.handle_models if family else []) if m.sku == handle_model_sku),
            None,
        )
        if handle_model is None:
            raise HardwareSelectionError(
                "hardware_selection_unknown",
                f"Manilla {handle_model_sku} no declarada en la familia {family_key}",
                {"field": "handle_model_sku", "sku": handle_model_sku, "opening": family_key},
            )
    handle_color: HandleColorOption | None = None
    if handle_color_sku is not None:
        handle_color = next(
            (c for c in (family.handle_colors if family else []) if c.sku == handle_color_sku),
            None,
        )
        if handle_color is None:
            raise HardwareSelectionError(
                "hardware_selection_unknown",
                f"Color de manilla {handle_color_sku} no declarado en la familia {family_key}",
                {"field": "handle_color_sku", "sku": handle_color_sku, "opening": family_key},
            )

    options: list[HardwareOption] = []
    for sku in dict.fromkeys(option_skus or []):
        option = params.hardware_options.get(sku)
        if option is None or option.opening_type != family_key:
            raise HardwareSelectionError(
                "hardware_selection_unknown",
                f"Opción de herraje {sku} no declarada para la familia {family_key}",
                {"field": "hardware_option_skus", "sku": sku, "opening": family_key},
            )
        options.append(option)

    # Declared editable range; a height outside it is refused with the real
    # bounds, not clamped.
    resolved_height = resolved_handle_height_mm(
        family, leaf_height_mm=leaf_height_mm, declared_mm=handle_height_mm
    )
    if (
        family is not None
        and family.handle_height_min_mm is not None
        and family.handle_height_max_mm is not None
        and resolved_height is not None
        and not (family.handle_height_min_mm <= resolved_height <= family.handle_height_max_mm)
    ):
        raise HardwareSelectionError(
            "handle_height_out_of_range",
            "Altura de manilla fuera del rango declarado de la familia",
            {
                "field": "handle_height_mm",
                "handle_height_mm": str(resolved_height),
                "min_mm": str(family.handle_height_min_mm),
                "max_mm": str(family.handle_height_max_mm),
            },
        )

    contents = expand_components(
        kit.contents, leaf_width_mm=leaf_width_mm, leaf_height_mm=leaf_height_mm
    )
    for option in options:
        contents.extend(
            expand_components(
                option.components,
                leaf_width_mm=leaf_width_mm,
                leaf_height_mm=leaf_height_mm,
                option_sku=option.sku,
            )
        )

    # Resolved sums; an axis stays None when the catalog left it undeclared.
    cost = _components_cost_clp(contents)
    weight = exact_weight.hardware_weight_kg
    price_deltas = [
        *( (
            HardwareSelectionPrice(
                sku=handle_model.sku,
                name=handle_model.name,
                source="HANDLE_MODEL",
                price_delta_clp=handle_model.price_delta_clp,
            ),
        ) if handle_model else ()),
        *( (
            HardwareSelectionPrice(
                sku=handle_color.sku,
                name=handle_color.name,
                source="HANDLE_COLOR",
                price_delta_clp=handle_color.price_delta_clp,
            ),
        ) if handle_color else ()),
        *(
            HardwareSelectionPrice(
                sku=option.sku,
                name=option.name,
                source="OPTION",
                price_delta_clp=option.price_delta_clp,
            )
            for option in options
        ),
    ]
    if not price_deltas:
        price_delta = None
    elif any(entry.price_delta_clp is None for entry in price_deltas):
        # A selected source without declared price makes the whole delta
        # unknown — pricing must refuse to guess rather than quote a sum.
        price_delta = None
    else:
        price_delta = sum(
            (entry.price_delta_clp for entry in price_deltas if entry.price_delta_clp is not None),
            Decimal("0"),
        )

    return HardwareItem(
        kit_sku=kit.sku,
        name=kit.name,
        bay_id=bay_id,
        leaf_id=leaf_id,
        contents=contents,
        class_label=kit.class_label,
        handle_model_sku=handle_model.sku if handle_model else None,
        handle_model_name=handle_model.name if handle_model else None,
        handle_color_sku=handle_color.sku if handle_color else None,
        handle_color_name=handle_color.name if handle_color else None,
        option_skus=[option.sku for option in options],
        option_names=[option.name for option in options],
        handle_height_mm=resolved_height,
        cost_clp=cost,
        weight_kg=weight,
        price_delta_clp=price_delta,
        price_deltas=price_deltas,
        machining=_machining_of(contents),
    )


def hardware_picking_list(
    items: list[HardwareItem], *, quantity: int = 1
) -> list[HardwarePickingLine]:
    """The OT picking list: components aggregated by (sku, cut length).

    Every line carries its resolved qty and cut length (transmisiones),
    and which kit/option skus produced it. The input items are one
    position's leaf BOM; `quantity` multiplies for the ordered count.
    """
    grouped: dict[tuple[str, Decimal | None], HardwarePickingLine] = {}
    order: list[tuple[str, Decimal | None]] = []
    for item in items:
        for component in item.contents:
            qty = component.qty
            if qty is None:
                raise ValueError(
                    f"hardware item {item.kit_sku} emits an unresolved qty "
                    f"for {component.sku}"
                )
            key = (component.sku, component.length_mm)
            units = qty * item.qty * quantity
            line = grouped.get(key)
            if line is None:
                line = HardwarePickingLine(
                    sku=component.sku,
                    name=component.name,
                    qty=units,
                    unit=component.unit,
                    category=component.category,
                    length_mm=component.length_mm,
                    sources=[],
                )
                grouped[key] = line
                order.append(key)
            else:
                line.qty = line.qty + units
            source = component.option_sku or item.kit_sku
            if source not in line.sources:
                line.sources.append(source)
    return [grouped[key] for key in sorted(order, key=lambda k: (k[0], k[1] or Decimal("0")))]
