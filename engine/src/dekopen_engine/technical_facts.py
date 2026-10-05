"""Internal facts emitted by the geometry execution, outside the public BOM."""

from dataclasses import dataclass, field
from decimal import Decimal

from dekopen_engine.hardware import HardwareCandidateEvaluation
from dekopen_engine.manufacturing_trace import GeometryManufacturingTraceV1
from dekopen_engine.models import BayOpeningType, EngineResult, HardwareKitRule, RailType
from dekopen_engine.weight import ExactLeafWeight


@dataclass(frozen=True, slots=True)
class InfillTechnicalFacts:
    bay_id: str
    leaf_id: str | None
    kind: str
    thickness_mm: Decimal
    glass_spec: str | None
    width_mm: Decimal
    height_mm: Decimal
    exact_area_m2: Decimal
    bead_supported: bool
    # D02: which authority produced `thickness_mm` — the bay's declared
    # package value ("DECLARED"), the structured composition's computed
    # total ("COMPOSITION") or a panel rule ("PANEL") — and the declared
    # value when it differs, so a divergence is visible instead of silent.
    thickness_source: str | None = None
    thickness_declared_mm: Decimal | None = None


@dataclass(frozen=True, slots=True)
class LeafTechnicalFacts:
    bay_id: str
    leaf_id: str | None
    opening_type: BayOpeningType
    rail_type: RailType
    finished_width_mm: Decimal
    finished_height_mm: Decimal
    base_weight: ExactLeafWeight
    candidates: list[HardwareCandidateEvaluation]
    selected_kit: HardwareKitRule | None
    exact_weight: ExactLeafWeight | None


@dataclass(frozen=True, slots=True)
class OpeningTechnicalFacts:
    bay_id: str
    width_mm: Decimal
    height_mm: Decimal


@dataclass(frozen=True, slots=True)
class SpanTechnicalFacts:
    target_id: str
    parent_profile_sku: str
    span_mm: Decimal


@dataclass(slots=True)
class GeometryComputation:
    result: EngineResult | None = None
    manufacturing_trace: GeometryManufacturingTraceV1 | None = None
    leaves: list[LeafTechnicalFacts] = field(default_factory=list)
    infills: list[InfillTechnicalFacts] = field(default_factory=list)
    openings: list[OpeningTechnicalFacts] = field(default_factory=list)
    spans: list[SpanTechnicalFacts] = field(default_factory=list)
    node_dimensions: dict[str, tuple[Decimal, Decimal]] = field(default_factory=dict)
    split_axes: dict[str, tuple[bool, Decimal]] = field(default_factory=dict)
