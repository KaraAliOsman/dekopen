"""Semantic physical trace emitted during geometry without changing the public BOM."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from dekopen_engine.models import BayOpeningType, EngineModel, MaterialType, ProfileRole


class PlacementDomain(str, Enum):
    DIRECT = "DIRECT"
    SLIDING_LEAF = "SLIDING_LEAF"
    SLIDING_INFILL = "SLIDING_INFILL"
    BEAD_SET = "BEAD_SET"


class MemberSide(str, Enum):
    TOP = "TOP"
    RIGHT = "RIGHT"
    BOTTOM = "BOTTOM"
    LEFT = "LEFT"
    CENTER = "CENTER"
    THRESHOLD = "THRESHOLD"


class Axis(str, Enum):
    HORIZONTAL = "HORIZONTAL"
    VERTICAL = "VERTICAL"


class TracePointV1(EngineModel):
    x_mm: Decimal
    y_mm: Decimal


class TraceRectV1(EngineModel):
    x_mm: Decimal
    y_mm: Decimal
    width_mm: Decimal = Field(gt=Decimal("0"))
    height_mm: Decimal = Field(gt=Decimal("0"))


class TraceSegmentV1(EngineModel):
    start: TracePointV1
    end: TracePointV1


class SemanticLeafTraceV1(EngineModel):
    semantic_leaf_id: str
    topology_path: str
    assembly: str
    bay_id: str
    leaf_id: str | None
    leaf_slot: str
    opening_type: BayOpeningType
    # Declared hinge side for door leaves — handle slot rules can pin
    # themselves to a handedness so a mirrored door mounts its handle on
    # the correct free stile.
    door_handedness: Literal["LEFT", "RIGHT"] | None = None
    placement_domain: Literal[PlacementDomain.DIRECT, PlacementDomain.SLIDING_LEAF]
    reference_rect: TraceRectV1
    finished_width_mm: Decimal = Field(gt=Decimal("0"))
    finished_height_mm: Decimal = Field(gt=Decimal("0"))
    direct_rect: TraceRectV1 | None = None

    @model_validator(mode="after")
    def direct_placement_is_complete(self) -> SemanticLeafTraceV1:
        if self.placement_domain is PlacementDomain.DIRECT and self.direct_rect is None:
            raise ValueError("Direct leaf trace requires its exact rectangle")
        if self.placement_domain is PlacementDomain.SLIDING_LEAF and self.direct_rect is not None:
            raise ValueError("Sliding leaf placement belongs to policy authority")
        return self


class SemanticInfillTraceV1(EngineModel):
    semantic_infill_id: str
    topology_path: str
    assembly: str
    bay_id: str
    leaf_id: str | None
    leaf_slot: str | None
    kind: Literal["GLASS", "PANEL"]
    technical_sku: str
    composition: str
    width_mm: Decimal = Field(gt=Decimal("0"))
    height_mm: Decimal = Field(gt=Decimal("0"))
    # Boundary polygon for non-rectangular fills (contour modules): width/height
    # stay the bounding box while shape carries the real edge loop + bulges.
    shape: list[TracePointV1] | None = None
    placement_domain: Literal[PlacementDomain.DIRECT, PlacementDomain.SLIDING_INFILL]
    parent_leaf_id: str | None = None
    direct_rect: TraceRectV1 | None = None

    @model_validator(mode="after")
    def placement_is_complete(self) -> SemanticInfillTraceV1:
        if self.placement_domain is PlacementDomain.DIRECT and self.direct_rect is None:
            raise ValueError("Direct infill trace requires its exact rectangle")
        if self.placement_domain is PlacementDomain.SLIDING_INFILL:
            if self.parent_leaf_id is None or self.direct_rect is not None:
                raise ValueError("Sliding infill requires policy placement and a parent leaf")
        return self


class SemanticMemberTraceV1(EngineModel):
    semantic_member_id: str
    topology_path: str
    assembly: str
    bay_id: str | None
    leaf_id: str | None
    leaf_slot: str | None
    role: ProfileRole
    physical_member_slot: str
    workshop_sku: str
    material: MaterialType
    cut_length_mm: Decimal = Field(gt=Decimal("0"))
    angle_left: Decimal
    angle_right: Decimal
    axis: Axis
    # Signed sagitta of an arc edge (contour members); the direct_segment is
    # the chord and cut_length_mm already carries the true arc length.
    sagitta_mm: Decimal | None = None
    placement_domain: Literal[
        PlacementDomain.DIRECT, PlacementDomain.SLIDING_LEAF, PlacementDomain.BEAD_SET
    ]
    direct_segment: TraceSegmentV1 | None = None
    parent_leaf_id: str | None = None
    parent_infill_id: str | None = None
    reinforcement_required: bool = False
    reinforcement_sku: str | None = None
    reinforcement_length_mm: Decimal | None = Field(default=None, gt=Decimal("0"))

    @model_validator(mode="after")
    def placement_and_reinforcement_are_complete(self) -> SemanticMemberTraceV1:
        if self.placement_domain is PlacementDomain.DIRECT and self.direct_segment is None:
            raise ValueError("Direct member trace requires its exact segment")
        if self.placement_domain is PlacementDomain.SLIDING_LEAF and self.parent_leaf_id is None:
            raise ValueError("Sliding member trace requires a parent leaf")
        if self.placement_domain is PlacementDomain.BEAD_SET and self.parent_infill_id is None:
            raise ValueError("Bead member trace requires a parent infill")
        if self.placement_domain is not PlacementDomain.DIRECT and self.direct_segment is not None:
            raise ValueError("Policy-placed member cannot carry derived coordinates")
        if self.reinforcement_required and self.reinforcement_length_mm is None:
            raise ValueError("Required reinforcement needs its emitted cut length")
        if not self.reinforcement_required and (
            self.reinforcement_sku is not None or self.reinforcement_length_mm is not None
        ):
            raise ValueError("Non-reinforced member cannot carry reinforcement data")
        return self


class GeometryManufacturingTraceV1(EngineModel):
    schema_version: Literal[1] = 1
    nominal_width_mm: Decimal = Field(gt=Decimal("0"))
    nominal_height_mm: Decimal = Field(gt=Decimal("0"))
    members: list[SemanticMemberTraceV1]
    leaves: list[SemanticLeafTraceV1]
    infills: list[SemanticInfillTraceV1]

    @model_validator(mode="after")
    def semantic_identities_are_unique(self) -> GeometryManufacturingTraceV1:
        values = [member.semantic_member_id for member in self.members]
        values += [leaf.semantic_leaf_id for leaf in self.leaves]
        values += [infill.semantic_infill_id for infill in self.infills]
        if len(values) != len(set(values)):
            raise ValueError("Manufacturing trace identities must be unique")
        leaf_ids = {leaf.semantic_leaf_id for leaf in self.leaves}
        infill_ids = {infill.semantic_infill_id for infill in self.infills}
        if any(
            infill.parent_leaf_id is not None and infill.parent_leaf_id not in leaf_ids
            for infill in self.infills
        ) or any(
            (member.parent_leaf_id is not None and member.parent_leaf_id not in leaf_ids)
            or (member.parent_infill_id is not None and member.parent_infill_id not in infill_ids)
            for member in self.members
        ):
            raise ValueError("Manufacturing trace relationship target is missing")
        return self
