"""Pure V1 projection from geometry-time semantic trace to workshop facts."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from dekopen_engine.documentary_canonical import documentary_sha256_v1
from dekopen_engine.manufacturing_trace import (
    Axis,
    GeometryManufacturingTraceV1,
    MemberSide,
    PlacementDomain,
    SemanticMemberTraceV1,
    TracePointV1,
    TraceRectV1,
    TraceSegmentV1,
)
from dekopen_engine.models import BayOpeningType, EngineModel, MaterialType, ProfileRole


class ManufacturingAuthorityError(ValueError):
    pass


class VerticalReference(str, Enum):
    OUTER_TOP = "OUTER_TOP"
    OUTER_BOTTOM = "OUTER_BOTTOM"
    LEAF_TOP = "LEAF_TOP"
    LEAF_BOTTOM = "LEAF_BOTTOM"


class PlacementOffsetV1(EngineModel):
    x_mm: Decimal
    y_mm: Decimal
    # Slot-pitch multiplier: sliding leaf origins scale with the bay, so
    # the authority declares the slot multiple and the trace's slot_pitch_mm
    # resolves it to millimetres. x = x_mm + x_pitches · pitch.
    x_pitches: Decimal = Decimal("0")


class ManufacturingPlacementPolicyV1(EngineModel):
    schema_version: Literal[1] = 1
    policy_id: str
    version: int = Field(ge=1)
    sliding_leaf_offsets: dict[str, PlacementOffsetV1]
    sliding_infill_offsets: dict[str, PlacementOffsetV1]
    bead_offsets: dict[MemberSide, PlacementOffsetV1]

    @model_validator(mode="after")
    def all_bead_sides_are_explicit(self) -> ManufacturingPlacementPolicyV1:
        required = {MemberSide.TOP, MemberSide.RIGHT, MemberSide.BOTTOM, MemberSide.LEFT}
        if set(self.bead_offsets) != required:
            raise ValueError("Placement policy requires all four bead offsets")
        return self


class HandleIntentV1(EngineModel):
    schema_version: Literal[1] = 1
    bay_id: str
    leaf_id: str | None = None
    handle_domain_slot: str
    requested_height_mm: Decimal = Field(ge=Decimal("0"))
    vertical_reference: VerticalReference


class HandleSlotRuleV1(EngineModel):
    opening_type: BayOpeningType
    leaf_slot: str | None = None
    handle_domain_slot: str
    # Optional handedness pin: a rule carrying LEFT/RIGHT applies only to
    # leaves whose declared handedness (door hinge side) matches it, so a
    # mirrored door mounts its handle on the opposite free stile. A rule
    # with no handedness is a wildcard; declared-handedness rules win over
    # it when both would match.
    leaf_handedness: Literal["LEFT", "RIGHT"] | None = None
    host_member_side: Literal[MemberSide.LEFT, MemberSide.RIGHT, MemberSide.BOTTOM]
    horizontal_reference: Literal["HOST_MEMBER_AXIS", "HOST_MEMBER_CENTER"] = (
        "HOST_MEMBER_AXIS"
    )
    horizontal_offset_mm: Decimal
    permitted_vertical_references: list[VerticalReference] = Field(min_length=1)
    mounting_min_from_leaf_top_mm: Decimal = Field(ge=Decimal("0"))
    mounting_max_from_leaf_top_mm: Decimal = Field(gt=Decimal("0"))

    @model_validator(mode="after")
    def mounting_region_is_ordered(self) -> HandleSlotRuleV1:
        if self.mounting_min_from_leaf_top_mm > self.mounting_max_from_leaf_top_mm:
            raise ValueError("Handle mounting region is inverted")
        if len(self.permitted_vertical_references) != len(
            set(self.permitted_vertical_references)
        ):
            raise ValueError("Handle vertical references must be unique")
        return self


class HandleRequirementPolicyV1(EngineModel):
    schema_version: Literal[1] = 1
    policy_id: str
    version: int = Field(ge=1)
    slots: list[HandleSlotRuleV1]


class ReinforcementCutRuleV1(EngineModel):
    role: ProfileRole
    profile_angle_left: Decimal
    profile_angle_right: Decimal
    reinforcement_angle_left: Decimal
    reinforcement_angle_right: Decimal
    length_authority: Literal["EXISTING_ENGINE"] = "EXISTING_ENGINE"
    compatible_with_existing_length: Literal[True]


class ReinforcementCutPolicyV1(EngineModel):
    schema_version: Literal[1] = 1
    policy_id: str
    version: int = Field(ge=1)
    rules: list[ReinforcementCutRuleV1] = Field(min_length=1)


class PhysicalMemberIdentityV1(EngineModel):
    position_id: str
    position_index: int = Field(ge=1)
    repetition_index: int = Field(ge=1)
    topology_path: str
    assembly: str
    leaf_slot: str | None
    role: ProfileRole
    physical_member_slot: str


class PhysicalMemberFactV1(EngineModel):
    member_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_member_id: str
    identity: PhysicalMemberIdentityV1
    bay_id: str | None
    leaf_id: str | None
    workshop_sku: str
    material: MaterialType
    cut_length_mm: Decimal = Field(gt=Decimal("0"))
    angle_left: Decimal
    angle_right: Decimal
    axis: Axis
    start: TracePointV1
    end: TracePointV1
    # Signed sagitta when the member is an arc — start/end stay the chord.
    sagitta_mm: Decimal | None = None


class ReinforcementFactV1(EngineModel):
    reinforcement_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_member_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    workshop_sku: str
    cut_length_mm: Decimal = Field(gt=Decimal("0"))
    angle_left: Decimal
    angle_right: Decimal
    policy_id: str
    policy_version: int = Field(ge=1)


class LeafAssemblyFactV1(EngineModel):
    leaf_fact_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_leaf_id: str
    position_id: str
    position_index: int = Field(ge=1)
    repetition_index: int = Field(ge=1)
    topology_path: str
    assembly: str
    bay_id: str
    leaf_id: str | None
    leaf_slot: str
    opening_type: BayOpeningType
    # Declared door hinge side, when the leaf carries one.
    door_handedness: Literal["LEFT", "RIGHT"] | None = None
    rect: TraceRectV1


class InfillLocationFactV1(EngineModel):
    infill_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_infill_id: str
    position_id: str
    position_index: int = Field(ge=1)
    repetition_index: int = Field(ge=1)
    topology_path: str
    assembly: str
    bay_id: str
    leaf_id: str | None
    leaf_slot: str | None
    kind: Literal["GLASS", "PANEL"]
    technical_sku: str
    composition: str
    rect: TraceRectV1
    # Sampled boundary of a shaped infill — rect stays its bounding box.
    shape: list[TracePointV1] | None = None


class HandleLocationFactV1(EngineModel):
    handle_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    position_id: str
    position_index: int = Field(ge=1)
    repetition_index: int = Field(ge=1)
    bay_id: str
    leaf_id: str | None
    handle_domain_slot: str
    host_member_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    point: TracePointV1
    requested_height_mm: Decimal
    vertical_reference: VerticalReference
    policy_id: str
    policy_version: int = Field(ge=1)


class PhysicalRelationshipV1(EngineModel):
    relationship: Literal["BELONGS_TO_LEAF", "REINFORCES", "RETAINS_INFILL"]
    source_id: str
    target_id: str


class ManufacturingFactsV1(EngineModel):
    schema_version: Literal[1] = 1
    position_id: str
    position_index: int = Field(ge=1)
    repetition_index: int = Field(ge=1)
    view: Literal["BUILDING_INTERIOR_LOOKING_OUTWARD"] = (
        "BUILDING_INTERIOR_LOOKING_OUTWARD"
    )
    elevation: Literal["CLOSED"] = "CLOSED"
    origin: Literal["NOMINAL_OUTER_FRAME_TOP_LEFT"] = "NOMINAL_OUTER_FRAME_TOP_LEFT"
    x_axis: Literal["RIGHT"] = "RIGHT"
    y_axis: Literal["DOWN"] = "DOWN"
    unit: Literal["DECIMAL_MM"] = "DECIMAL_MM"
    nominal_width_mm: Decimal
    nominal_height_mm: Decimal
    placement_policy_id: str
    placement_policy_version: int
    handle_policy_id: str
    handle_policy_version: int
    reinforcement_policy_id: str
    reinforcement_policy_version: int
    members: list[PhysicalMemberFactV1]
    reinforcements: list[ReinforcementFactV1]
    leaves: list[LeafAssemblyFactV1]
    infills: list[InfillLocationFactV1]
    handles: list[HandleLocationFactV1]
    relationships: list[PhysicalRelationshipV1]


def _segment_for_side(rect: TraceRectV1, side: MemberSide) -> TraceSegmentV1:
    x, y = rect.x_mm, rect.y_mm
    right, bottom = x + rect.width_mm, y + rect.height_mm
    if side is MemberSide.TOP:
        return TraceSegmentV1(start=TracePointV1(x_mm=x, y_mm=y),
                              end=TracePointV1(x_mm=right, y_mm=y))
    if side is MemberSide.RIGHT:
        return TraceSegmentV1(start=TracePointV1(x_mm=right, y_mm=y),
                              end=TracePointV1(x_mm=right, y_mm=bottom))
    if side is MemberSide.BOTTOM:
        return TraceSegmentV1(start=TracePointV1(x_mm=x, y_mm=bottom),
                              end=TracePointV1(x_mm=right, y_mm=bottom))
    if side is MemberSide.LEFT:
        return TraceSegmentV1(start=TracePointV1(x_mm=x, y_mm=y),
                              end=TracePointV1(x_mm=x, y_mm=bottom))
    raise ManufacturingAuthorityError("A rectangle cannot resolve this physical member slot")


def _offset_rect(rect: TraceRectV1, offset: PlacementOffsetV1,
                 width_mm: Decimal, height_mm: Decimal,
                 slot_pitch_mm: Decimal | None = None) -> TraceRectV1:
    x = rect.x_mm + offset.x_mm
    if offset.x_pitches != 0:
        if slot_pitch_mm is None:
            raise ManufacturingAuthorityError(
                "Placement authority needs the leaf's slot pitch"
            )
        x += offset.x_pitches * slot_pitch_mm
    return TraceRectV1(x_mm=x, y_mm=rect.y_mm + offset.y_mm,
                       width_mm=width_mm, height_mm=height_mm)


def _offset_segment(segment: TraceSegmentV1, offset: PlacementOffsetV1) -> TraceSegmentV1:
    return TraceSegmentV1(
        start=TracePointV1(x_mm=segment.start.x_mm + offset.x_mm,
                           y_mm=segment.start.y_mm + offset.y_mm),
        end=TracePointV1(x_mm=segment.end.x_mm + offset.x_mm,
                         y_mm=segment.end.y_mm + offset.y_mm),
    )


def _one_offset(offsets: dict[str, PlacementOffsetV1], slot: str, domain: str) -> PlacementOffsetV1:
    try:
        return offsets[slot]
    except KeyError as error:
        raise ManufacturingAuthorityError(
            f"Missing {domain} placement authority for semantic slot {slot}"
        ) from error


def _member_side(value: str) -> MemberSide:
    try:
        return MemberSide(value)
    except ValueError as error:
        raise ManufacturingAuthorityError("Policy placement requires a rectangular member side") from error


def _vertical_coordinate(
    intent: HandleIntentV1, leaf_rect: TraceRectV1, nominal_height_mm: Decimal
) -> Decimal:
    if intent.vertical_reference is VerticalReference.OUTER_TOP:
        return intent.requested_height_mm
    if intent.vertical_reference is VerticalReference.OUTER_BOTTOM:
        return nominal_height_mm - intent.requested_height_mm
    if intent.vertical_reference is VerticalReference.LEAF_TOP:
        return leaf_rect.y_mm + intent.requested_height_mm
    return leaf_rect.y_mm + leaf_rect.height_mm - intent.requested_height_mm


def _matching_reinforcement_rule(
    policy: ReinforcementCutPolicyV1, member: SemanticMemberTraceV1
) -> ReinforcementCutRuleV1:
    matches = [
        rule
        for rule in policy.rules
        if rule.role is member.role
        and rule.profile_angle_left == member.angle_left
        and rule.profile_angle_right == member.angle_right
    ]
    if len(matches) != 1:
        raise ManufacturingAuthorityError("Reinforcement cut authority is missing or ambiguous")
    return matches[0]


def project_manufacturing_facts_v1(
    *,
    trace: GeometryManufacturingTraceV1,
    position_id: str,
    position_index: int,
    repetition_index: int,
    placement_policy: ManufacturingPlacementPolicyV1,
    handle_policy: HandleRequirementPolicyV1,
    reinforcement_policy: ReinforcementCutPolicyV1,
    handle_intents: list[HandleIntentV1],
    resolved_reinforcement_skus: dict[str, str],
    legacy_handle_height_present: bool = False,
    legacy_handle_migration_confirmed: bool = False,
    module_id: str | None = None,
) -> ManufacturingFactsV1:
    if legacy_handle_height_present and not legacy_handle_migration_confirmed:
        raise ManufacturingAuthorityError("Legacy handle height requires explicit migration confirmation")
    # Assembly modules share local topology, so the module namespaces every
    # minted identity; classic positions keep byte-identical ids (no key added).
    scope = {"module_id": module_id} if module_id is not None else {}

    leaf_rects: dict[str, TraceRectV1] = {}
    leaf_by_target: dict[tuple[str, str | None], str] = {}
    leaf_trace_by_id = {leaf.semantic_leaf_id: leaf for leaf in trace.leaves}
    leaf_facts: list[LeafAssemblyFactV1] = []
    leaf_fact_ids: dict[str, str] = {}
    for leaf in sorted(trace.leaves, key=lambda item: item.semantic_leaf_id):
        if leaf.placement_domain is PlacementDomain.DIRECT:
            assert leaf.direct_rect is not None
            rect = leaf.direct_rect
        else:
            rect = _offset_rect(
                leaf.reference_rect,
                _one_offset(placement_policy.sliding_leaf_offsets, leaf.leaf_slot, "sliding leaf"),
                leaf.finished_width_mm,
                leaf.finished_height_mm,
                leaf.slot_pitch_mm,
            )
        leaf_rects[leaf.semantic_leaf_id] = rect
        target = (leaf.bay_id, leaf.leaf_id)
        if target in leaf_by_target:
            raise ManufacturingAuthorityError("Leaf target identity is ambiguous")
        leaf_by_target[target] = leaf.semantic_leaf_id
        leaf_fact_id = documentary_sha256_v1({
            "kind": "leaf",
            **scope,
            "position_id": position_id,
            "position_index": position_index,
            "repetition_index": repetition_index,
            "semantic_leaf_id": leaf.semantic_leaf_id,
        })
        leaf_fact_ids[leaf.semantic_leaf_id] = leaf_fact_id
        leaf_facts.append(LeafAssemblyFactV1(
            leaf_fact_id=leaf_fact_id,
            semantic_leaf_id=leaf.semantic_leaf_id,
            position_id=position_id,
            position_index=position_index,
            repetition_index=repetition_index,
            topology_path=leaf.topology_path,
            assembly=leaf.assembly,
            bay_id=leaf.bay_id,
            leaf_id=leaf.leaf_id,
            leaf_slot=leaf.leaf_slot,
            opening_type=leaf.opening_type,
            door_handedness=leaf.door_handedness,
            rect=rect,
        ))

    infill_rects: dict[str, TraceRectV1] = {}
    infill_facts: list[InfillLocationFactV1] = []
    for infill in sorted(trace.infills, key=lambda item: item.semantic_infill_id):
        if infill.placement_domain is PlacementDomain.DIRECT:
            assert infill.direct_rect is not None
            rect = infill.direct_rect
        else:
            assert infill.parent_leaf_id is not None
            try:
                parent = leaf_rects[infill.parent_leaf_id]
            except KeyError as error:
                raise ManufacturingAuthorityError("Sliding infill parent leaf is missing") from error
            slot = leaf_trace_by_id[infill.parent_leaf_id].leaf_slot
            rect = _offset_rect(
                parent,
                _one_offset(placement_policy.sliding_infill_offsets, slot, "sliding infill"),
                infill.width_mm,
                infill.height_mm,
            )
        infill_rects[infill.semantic_infill_id] = rect
        infill_identity = {
            "kind": "infill",
            **scope,
            "position_id": position_id,
            "position_index": position_index,
            "repetition_index": repetition_index,
            "semantic_infill_id": infill.semantic_infill_id,
        }
        infill_facts.append(InfillLocationFactV1(
            infill_id=documentary_sha256_v1(infill_identity),
            semantic_infill_id=infill.semantic_infill_id,
            position_id=position_id,
            position_index=position_index,
            repetition_index=repetition_index,
            topology_path=infill.topology_path,
            assembly=infill.assembly,
            bay_id=infill.bay_id,
            leaf_id=infill.leaf_id,
            leaf_slot=infill.leaf_slot,
            kind=infill.kind,
            technical_sku=infill.technical_sku,
            composition=infill.composition,
            rect=rect,
            shape=infill.shape,
        ))

    infill_ids = {item.semantic_infill_id: item.infill_id for item in infill_facts}
    member_facts: list[PhysicalMemberFactV1] = []
    member_trace_by_id: dict[str, SemanticMemberTraceV1] = {}
    relationships: list[PhysicalRelationshipV1] = []
    for trace_member in sorted(trace.members, key=lambda item: item.semantic_member_id):
        if trace_member.placement_domain is PlacementDomain.DIRECT:
            assert trace_member.direct_segment is not None
            segment = trace_member.direct_segment
        elif trace_member.placement_domain is PlacementDomain.SLIDING_LEAF:
            assert trace_member.parent_leaf_id is not None
            try:
                segment = _segment_for_side(
                    leaf_rects[trace_member.parent_leaf_id],
                    _member_side(trace_member.physical_member_slot),
                )
            except KeyError as error:
                raise ManufacturingAuthorityError("Sliding member parent leaf is missing") from error
        else:
            assert trace_member.parent_infill_id is not None
            try:
                rect = infill_rects[trace_member.parent_infill_id]
                side = _member_side(trace_member.physical_member_slot)
                offset = placement_policy.bead_offsets[side]
            except KeyError as error:
                raise ManufacturingAuthorityError("Bead placement authority is incomplete") from error
            segment = _offset_segment(_segment_for_side(rect, side), offset)
        physical_identity = PhysicalMemberIdentityV1(
            position_id=position_id,
            position_index=position_index,
            repetition_index=repetition_index,
            topology_path=trace_member.topology_path,
            assembly=trace_member.assembly,
            leaf_slot=trace_member.leaf_slot,
            role=trace_member.role,
            physical_member_slot=trace_member.physical_member_slot,
        )
        member_id = documentary_sha256_v1({
            "kind": "physical_member", **scope, **physical_identity.model_dump()
        })
        member_facts.append(PhysicalMemberFactV1(
            member_id=member_id,
            semantic_member_id=trace_member.semantic_member_id,
            identity=physical_identity,
            bay_id=trace_member.bay_id,
            leaf_id=trace_member.leaf_id,
            workshop_sku=trace_member.workshop_sku,
            material=trace_member.material,
            cut_length_mm=trace_member.cut_length_mm,
            angle_left=trace_member.angle_left,
            angle_right=trace_member.angle_right,
            axis=trace_member.axis,
            start=segment.start,
            end=segment.end,
            sagitta_mm=trace_member.sagitta_mm,
        ))
        member_trace_by_id[member_id] = trace_member
        if trace_member.parent_leaf_id is not None:
            relationships.append(PhysicalRelationshipV1(
                relationship="BELONGS_TO_LEAF", source_id=member_id,
                target_id=leaf_fact_ids[trace_member.parent_leaf_id],
            ))
        if trace_member.parent_infill_id is not None:
            relationships.append(PhysicalRelationshipV1(
                relationship="RETAINS_INFILL", source_id=member_id,
                target_id=infill_ids[trace_member.parent_infill_id],
            ))

    reinforcements: list[ReinforcementFactV1] = []
    for member_fact in member_facts:
        source = member_trace_by_id[member_fact.member_id]
        if not source.reinforcement_required:
            continue
        assert source.reinforcement_length_mm is not None
        sku = source.reinforcement_sku or resolved_reinforcement_skus.get(source.workshop_sku)
        if not sku:
            raise ManufacturingAuthorityError("Reinforcement stock identity is unresolved")
        reinforcement_rule = _matching_reinforcement_rule(reinforcement_policy, source)
        reinforcement_id = documentary_sha256_v1({
            "kind": "reinforcement", "parent_member_id": member_fact.member_id,
            "workshop_sku": sku,
        })
        reinforcements.append(ReinforcementFactV1(
            reinforcement_id=reinforcement_id,
            parent_member_id=member_fact.member_id,
            workshop_sku=sku,
            cut_length_mm=source.reinforcement_length_mm,
            angle_left=reinforcement_rule.reinforcement_angle_left,
            angle_right=reinforcement_rule.reinforcement_angle_right,
            policy_id=reinforcement_policy.policy_id,
            policy_version=reinforcement_policy.version,
        ))
        relationships.append(PhysicalRelationshipV1(
            relationship="REINFORCES", source_id=reinforcement_id,
            target_id=member_fact.member_id,
        ))

    intent_map: dict[tuple[str, str | None, str], HandleIntentV1] = {}
    for intent in handle_intents:
        intent_key = (intent.bay_id, intent.leaf_id, intent.handle_domain_slot)
        if intent_key in intent_map:
            raise ManufacturingAuthorityError("Handle intent target is duplicated")
        intent_map[intent_key] = intent
    handles: list[HandleLocationFactV1] = []
    consumed: set[tuple[str, str | None, str]] = set()
    member_by_leaf_side: dict[tuple[str, str], PhysicalMemberFactV1] = {}
    for fact in member_facts:
        source = member_trace_by_id[fact.member_id]
        parent_leaf_id = source.parent_leaf_id
        if parent_leaf_id is None:
            continue
        leaf_side_key = (parent_leaf_id, source.physical_member_slot)
        if leaf_side_key in member_by_leaf_side:
            raise ManufacturingAuthorityError("Leaf member side is ambiguous")
        member_by_leaf_side[leaf_side_key] = fact
    for leaf in sorted(trace.leaves, key=lambda item: item.semantic_leaf_id):
        handle_rules = [
            slot_rule for slot_rule in handle_policy.slots
            if slot_rule.opening_type is leaf.opening_type
            and (slot_rule.leaf_slot is None or slot_rule.leaf_slot == leaf.leaf_slot)
            and (
                slot_rule.leaf_handedness is None
                or slot_rule.leaf_handedness == leaf.door_handedness
            )
        ]
        # A declared-handedness leaf prefers rules pinned to that
        # handedness over wildcard rules for the same domain slot.
        if leaf.door_handedness is not None and any(
            slot_rule.leaf_handedness == leaf.door_handedness
            for slot_rule in handle_rules
        ):
            handle_rules = [
                slot_rule
                for slot_rule in handle_rules
                if slot_rule.leaf_handedness is not None
            ]
        if not handle_rules:
            if leaf.opening_type is BayOpeningType.DOOR_ENTRY and any(
                slot_rule.opening_type is BayOpeningType.DOOR_ENTRY
                and slot_rule.leaf_handedness is not None
                for slot_rule in handle_policy.slots
            ):
                raise ManufacturingAuthorityError(
                    "Door leaf handedness is undeclared"
                )
            raise ManufacturingAuthorityError("Handle requirement policy has no rule for a physical leaf")
        rules_by_slot: dict[str, int] = {}
        for slot_rule in handle_rules:
            rules_by_slot[slot_rule.handle_domain_slot] = (
                rules_by_slot.get(slot_rule.handle_domain_slot, 0) + 1
            )
        if any(count != 1 for count in rules_by_slot.values()):
            raise ManufacturingAuthorityError(
                "Handle requirement policy is ambiguous for a physical leaf"
            )
        for handle_rule in sorted(handle_rules, key=lambda item: item.handle_domain_slot):
            handle_key = (leaf.bay_id, leaf.leaf_id, handle_rule.handle_domain_slot)
            try:
                intent = intent_map[handle_key]
            except KeyError as error:
                raise ManufacturingAuthorityError("Required handle intent is missing") from error
            if intent.vertical_reference not in handle_rule.permitted_vertical_references:
                raise ManufacturingAuthorityError("Handle vertical reference is not permitted")
            try:
                host = member_by_leaf_side[
                    (leaf.semantic_leaf_id, handle_rule.host_member_side.value)
                ]
            except KeyError as error:
                raise ManufacturingAuthorityError("Handle host semantic member is missing") from error
            leaf_rect = leaf_rects[leaf.semantic_leaf_id]
            y_mm = _vertical_coordinate(intent, leaf_rect, trace.nominal_height_mm)
            minimum = leaf_rect.y_mm + handle_rule.mounting_min_from_leaf_top_mm
            maximum = leaf_rect.y_mm + handle_rule.mounting_max_from_leaf_top_mm
            if y_mm < minimum or y_mm > maximum:
                raise ManufacturingAuthorityError("Handle point is outside its mounting region")
            if handle_rule.horizontal_reference == "HOST_MEMBER_CENTER":
                x_mm = (host.start.x_mm + host.end.x_mm) / Decimal("2") + handle_rule.horizontal_offset_mm
            else:
                x_mm = host.start.x_mm + handle_rule.horizontal_offset_mm
            handle_id = documentary_sha256_v1({
                "kind": "handle", **scope, "position_id": position_id,
                "position_index": position_index, "repetition_index": repetition_index,
                "bay_id": leaf.bay_id, "leaf_id": leaf.leaf_id,
                "handle_domain_slot": handle_rule.handle_domain_slot,
            })
            handles.append(HandleLocationFactV1(
                handle_id=handle_id,
                position_id=position_id,
                position_index=position_index,
                repetition_index=repetition_index,
                bay_id=leaf.bay_id,
                leaf_id=leaf.leaf_id,
                handle_domain_slot=handle_rule.handle_domain_slot,
                host_member_id=host.member_id,
                point=TracePointV1(x_mm=x_mm, y_mm=y_mm),
                requested_height_mm=intent.requested_height_mm,
                vertical_reference=intent.vertical_reference,
                policy_id=handle_policy.policy_id,
                policy_version=handle_policy.version,
            ))
            consumed.add(handle_key)
    if consumed != set(intent_map):
        raise ManufacturingAuthorityError("Handle intent has no required policy slot")

    relationships.sort(key=lambda item: (item.relationship, item.source_id, item.target_id))
    return ManufacturingFactsV1(
        position_id=position_id,
        position_index=position_index,
        repetition_index=repetition_index,
        nominal_width_mm=trace.nominal_width_mm,
        nominal_height_mm=trace.nominal_height_mm,
        placement_policy_id=placement_policy.policy_id,
        placement_policy_version=placement_policy.version,
        handle_policy_id=handle_policy.policy_id,
        handle_policy_version=handle_policy.version,
        reinforcement_policy_id=reinforcement_policy.policy_id,
        reinforcement_policy_version=reinforcement_policy.version,
        members=member_facts,
        reinforcements=reinforcements,
        leaves=leaf_facts,
        infills=infill_facts,
        handles=handles,
        relationships=relationships,
    )
