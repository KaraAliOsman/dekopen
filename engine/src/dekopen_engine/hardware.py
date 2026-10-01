"""Deterministic kit selection against finished dimensions and exact mass."""

from decimal import Decimal
from dataclasses import dataclass

from dekopen_engine.models import BayOpeningType, HardwareKitRule, SystemParams
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


def normalize_opening_type(opening: BayOpeningType) -> str:
    if opening in (BayOpeningType.TURN_LEFT, BayOpeningType.TURN_RIGHT):
        return "TURN"
    if opening in (BayOpeningType.TILT_TURN_LEFT, BayOpeningType.TILT_TURN_RIGHT):
        return "TILT_TURN"
    if opening in (BayOpeningType.SLIDING_2L, BayOpeningType.SLIDING_3L,
                   BayOpeningType.SLIDING_4L, BayOpeningType.SLIDING):
        return "SLIDING"
    if opening in (BayOpeningType.DOOR_ENTRY, BayOpeningType.DOOR_DOUBLE):
        return "DOOR"
    return opening.value


@dataclass(frozen=True, slots=True)
class HardwareCandidateEvaluation:
    kit: HardwareKitRule
    opening_match: bool
    rail_match: bool
    width_match: bool
    height_match: bool
    exact_total_weight: ExactLeafWeight
    # None = the leaf mass is UNKNOWN — compatibility is undecidable, never
    # silently certified.
    weight_match: bool | None

    @property
    def compatible(self) -> bool:
        return (self.opening_match and self.rail_match and self.width_match
                and self.height_match and self.weight_match is True)


def evaluate_hardware_candidates(
    *, opening: BayOpeningType, width_mm: Decimal, height_mm: Decimal,
    base_weight: ExactLeafWeight, params: SystemParams, explicit_sku: str | None = None,
) -> list[HardwareCandidateEvaluation]:
    candidates: list[HardwareCandidateEvaluation] = []
    for kit in params.available_hardware_kits:
        if explicit_sku is not None and kit.sku != explicit_sku:
            continue
        exact = with_hardware_weight(base_weight, kit, params)
        total = exact.total_weight_kg
        candidates.append(HardwareCandidateEvaluation(
            kit=kit, opening_match=kit.opening_type == normalize_opening_type(opening),
            rail_match=kit.rail_type is params.rail_type,
            width_match=kit.min_leaf_width_mm <= width_mm <= kit.max_leaf_width_mm,
            height_match=kit.min_leaf_height_mm <= height_mm <= kit.max_leaf_height_mm,
            exact_total_weight=exact,
            weight_match=(None if total is None else total <= kit.max_leaf_weight_kg),
        ))
    return candidates


def resolve_hardware_evaluations(
    evaluations: list[HardwareCandidateEvaluation], *, opening: BayOpeningType,
    explicit_sku: str | None = None,
    leaf_width_mm: Decimal | None = None,
    leaf_height_mm: Decimal | None = None,
) -> tuple[HardwareKitRule, ExactLeafWeight]:
    candidates = [candidate for candidate in evaluations if candidate.compatible]
    # Kits matching opening and rail but failing a concrete check — their
    # merged envelope is the constraint the user must satisfy.
    matched = [
        candidate for candidate in evaluations
        if candidate.opening_match and candidate.rail_match
    ]

    def failure_context(axis: str) -> dict[str, str]:
        context: dict[str, str] = {"axis": axis, "opening": explicit_sku or opening.value}
        if leaf_width_mm is not None and leaf_height_mm is not None:
            context["leaf_width_mm"] = str(leaf_width_mm)
            context["leaf_height_mm"] = str(leaf_height_mm)
        if matched:
            context["kit_min_width_mm"] = str(min(c.kit.min_leaf_width_mm for c in matched))
            context["kit_max_width_mm"] = str(max(c.kit.max_leaf_width_mm for c in matched))
            context["kit_min_height_mm"] = str(min(c.kit.min_leaf_height_mm for c in matched))
            context["kit_max_height_mm"] = str(max(c.kit.max_leaf_height_mm for c in matched))
        return context

    if not candidates:
        undecidable = [
            candidate for candidate in evaluations
            if candidate.weight_match is None and candidate.opening_match
            and candidate.rail_match and candidate.width_match and candidate.height_match
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
        # Axis of failure: a kit whose envelope the leaf escapes fails on
        # size; a kit it fits that still rejects carries a mass violation.
        if matched and all(c.width_match and c.height_match for c in matched):
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
                context["kit_max_weight_kg"] = str(
                    max(c.kit.max_leaf_weight_kg for c in matched)
                )
        raise NoCompatibleHardwareKit(
            f"No compatible hardware kit: {explicit_sku or opening.value}", context=context,
        )
    if len(candidates) != 1:
        raise AmbiguousHardwareKit(f"Ambiguous hardware kits: {opening.value}")
    return candidates[0].kit, candidates[0].exact_total_weight


def resolve_hardware_kit(
    *, opening: BayOpeningType, width_mm: Decimal, height_mm: Decimal,
    base_weight: ExactLeafWeight, params: SystemParams, explicit_sku: str | None = None,
) -> tuple[HardwareKitRule, ExactLeafWeight]:
    return resolve_hardware_evaluations(evaluate_hardware_candidates(
        opening=opening, width_mm=width_mm, height_mm=height_mm, base_weight=base_weight,
        params=params, explicit_sku=explicit_sku,
    ), opening=opening, explicit_sku=explicit_sku)
