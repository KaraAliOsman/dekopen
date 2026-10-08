from decimal import Decimal

import pytest
from pydantic import ValidationError

from dekopen_engine.cutting import CutMaterial, CuttingProfile
from dekopen_engine.geometry import compute_geometry
from dekopen_engine.manufacturing import HandleIntentV1, VerticalReference, project_manufacturing_facts_v1
from dekopen_engine.models import ParametricNode, SystemParams
from dekopen_engine.purchasing import (
    AccessoryScheduleV1,
    EdgePolishingV1,
    FittingPurchaseMappingV1,
    FittingSelectionV1,
    GlassPolishingAuthorityV1,
    GlassPurchaseMappingV1,
    HardwarePurchaseMappingV1,
    HardwareSelectionV1,
    PanelPurchaseAuthorityV1,
    PhysicalSourceKind,
    PhysicalStockBindingV1,
    PositionPurchaseInputV1,
    PurchaseAuthorityError,
    PurchaseRequirementsV1,
    SupplierOrderType,
    project_purchase_requirements_v1,
)
from engine.tests.test_manufacturing import handles, placement, steel
from engine.tests.test_shot06_core import core_node

D = Decimal
CUTTING = CuttingProfile(
    id="CUT-DEMO-V1", code="DEMO", kerf_mm=D("4.00"),
    head_trim_mm=D("15.00"), tail_trim_mm=D("15.00"),
)


def position_source(
    node: ParametricNode,
    params: SystemParams,
    *,
    position_id: str,
    position_index: int,
    quantity: int = 1,
    location: str = "FACHADA-NORTE",
    accessories: AccessoryScheduleV1 | None = None,
) -> tuple[PositionPurchaseInputV1, list[PhysicalStockBindingV1]]:
    computation = compute_geometry(node, params)
    assert computation.result is not None and computation.manufacturing_trace is not None
    trace = computation.manufacturing_trace
    opening_types = sorted({leaf.opening_type for leaf in trace.leaves})
    roles_and_angles = sorted({
        (member.role, str(member.angle_left), str(member.angle_right))
        for member in trace.members if member.reinforcement_required
    }, key=lambda item: (item[0].value, item[1], item[2]))
    resolved = {
        member.workshop_sku: f"STEEL-{member.workshop_sku}"
        for member in trace.members if member.reinforcement_required
    }
    units = []
    hardware: list[HardwareSelectionV1] = []
    for repetition in range(1, quantity + 1):
        intents = [
            HandleIntentV1(
                bay_id=leaf.bay_id,
                leaf_id=leaf.leaf_id,
                handle_domain_slot="PRIMARY",
                requested_height_mm=D("300.00"),
                vertical_reference=VerticalReference.LEAF_TOP,
            )
            for leaf in trace.leaves
        ]
        units.append(project_manufacturing_facts_v1(
            trace=trace,
            position_id=position_id,
            position_index=position_index,
            repetition_index=repetition,
            placement_policy=placement(),
            handle_policy=handles(*opening_types),
            reinforcement_policy=steel(*roles_and_angles),
            handle_intents=intents,
            resolved_reinforcement_skus=resolved,
        ))
        hardware.extend(HardwareSelectionV1(
            repetition_index=repetition,
            bay_id=item.bay_id,
            leaf_id=item.leaf_id,
            technical_kit_sku=item.kit_sku,
            name=item.name,
            quantity=item.qty,
            contents=item.contents,
        ) for item in computation.result.hardware_items)
    glass_targets = sorted({
        (infill.bay_id, infill.leaf_id)
        for unit in units for infill in unit.infills if infill.kind == "GLASS"
    })
    position = PositionPurchaseInputV1(
        position_id=position_id,
        position_index=position_index,
        system_id="DEMO_60",
        quantity=quantity,
        color="WHITE",
        location_tag=location,
        manufacturing_units=units,
        hardware=hardware,
        glass_polishing=[
            GlassPolishingAuthorityV1(
                bay_id=bay_id,
                leaf_id=leaf_id,
                edges=EdgePolishingV1(top=False, right=False, bottom=False, left=False),
            )
            for bay_id, leaf_id in glass_targets
        ],
        accessory_schedule=accessories or AccessoryScheduleV1(
            schedule_id=f"SCHEDULE-{position_id}", coverage="NONE_REQUIRED", items=[]
        ),
    )
    bindings: dict[tuple[PhysicalSourceKind, str], PhysicalStockBindingV1] = {}
    for unit in units:
        for member in unit.members:
            key = (PhysicalSourceKind.PROFILE, member.workshop_sku)
            bindings[key] = PhysicalStockBindingV1(
                binding_id=f"PROFILE-BINDING-{member.workshop_sku}",
                binding_version=1,
                system_id="DEMO_60",
                source_kind=PhysicalSourceKind.PROFILE,
                workshop_sku=member.workshop_sku,
                purchasing_sku=f"BUY-{member.workshop_sku}",
                physical_stock_identity=f"STOCK-PROFILE-{member.workshop_sku}",
                manufacturer_name="DEMO",
                material=CutMaterial(member.material.value),
                color="WHITE",
                stock_length_mm=D("6000.00"),
                cutting_profile=CUTTING,
            )
        for reinforcement in unit.reinforcements:
            key = (PhysicalSourceKind.REINFORCEMENT, reinforcement.workshop_sku)
            bindings[key] = PhysicalStockBindingV1(
                binding_id=f"STEEL-BINDING-{reinforcement.workshop_sku}",
                binding_version=1,
                system_id="DEMO_60",
                source_kind=PhysicalSourceKind.REINFORCEMENT,
                workshop_sku=reinforcement.workshop_sku,
                purchasing_sku=f"BUY-{reinforcement.workshop_sku}",
                physical_stock_identity=f"STOCK-STEEL-{reinforcement.workshop_sku}",
                manufacturer_name="DEMO",
                material=CutMaterial.STEEL,
                color="WHITE",
                stock_length_mm=D("6000.00"),
                cutting_profile=CUTTING,
            )
    return position, list(bindings.values())


def glass_mapping() -> GlassPurchaseMappingV1:
    return GlassPurchaseMappingV1(
        authority_id="GLASS-MAP-V1",
        version=1,
        system_id="DEMO_60",
        technical_sku="GLASS-TECH",
        purchasing_sku="GLASS-BUY",
        manufacturer_name="DEMO GLASS",
        provenance={"source": "synthetic"},
    )


def hardware_mappings(position: PositionPurchaseInputV1) -> list[HardwarePurchaseMappingV1]:
    return [
        HardwarePurchaseMappingV1(
            authority_id=f"HARDWARE-MAP-{sku}",
            version=1,
            system_id="DEMO_60",
            technical_kit_sku=sku,
            purchasing_sku=f"BUY-{sku}",
            manufacturer_name="DEMO HARDWARE",
            provenance={"source": "synthetic"},
        )
        for sku in sorted({item.technical_kit_sku for item in position.hardware})
    ]


def project_one(
    position: PositionPurchaseInputV1,
    bindings: list[PhysicalStockBindingV1],
    *,
    panels: list[PanelPurchaseAuthorityV1] | None = None,
) -> PurchaseRequirementsV1:
    return project_purchase_requirements_v1(
        positions=[position],
        stock_bindings=bindings,
        glass_mappings=[glass_mapping()],
        hardware_mappings=hardware_mappings(position),
        panel_authorities=panels or [],
    )


def test_position_quantity_expands_every_source_exactly_once(
    demo_60_params: SystemParams,
) -> None:
    node = core_node("G6").model_copy(update={"glass_article_sku": "GLASS-TECH"})
    position, bindings = position_source(
        node, demo_60_params, position_id="P-1", position_index=1, quantity=2
    )
    result = project_one(position, bindings)
    glass = next(item for item in result.requirements if item.category == "GLASS")
    hardware = next(item for item in result.requirements if item.category == "HARDWARE_KIT")
    assert glass.quantity == hardware.quantity == 2
    expected_piece_ids = {
        member.member_id
        for unit in position.manufacturing_units
        for member in unit.members
    } | {
        reinforcement.reinforcement_id
        for unit in position.manufacturing_units
        for reinforcement in unit.reinforcements
    }
    assert expected_piece_ids == {
        piece_id for group in result.stock_groups for piece_id in group.source_piece_ids
    }
    assert expected_piece_ids == {
        cut.piece_id for group in result.stock_groups for bar in group.bars for cut in bar.cuts
    }
    with pytest.raises(ValidationError, match="expanded exactly once"):
        PositionPurchaseInputV1.model_validate({**position.model_dump(), "quantity": 3})


def test_project_bfd_pools_positions_only_by_physical_identity(
    demo_60_params: SystemParams,
) -> None:
    node = core_node("G6").model_copy(update={"glass_article_sku": "GLASS-TECH"})
    first, bindings = position_source(node, demo_60_params, position_id="P-1", position_index=1)
    second, _ = position_source(node, demo_60_params, position_id="P-2", position_index=2)
    result = project_purchase_requirements_v1(
        positions=[second, first],
        stock_bindings=list(reversed(bindings)),
        glass_mappings=[glass_mapping()],
        hardware_mappings=hardware_mappings(first),
        panel_authorities=[],
    )
    assert result == project_purchase_requirements_v1(
        positions=[first, second],
        stock_bindings=bindings,
        glass_mappings=[glass_mapping()],
        hardware_mappings=hardware_mappings(first),
        panel_authorities=[],
    )
    for group in result.stock_groups:
        assert {cut.source_position_id for bar in group.bars for cut in bar.cuts} == {"P-1", "P-2"}
    changed = [
        binding.model_copy(update={"physical_stock_identity": f"OTHER-{binding.physical_stock_identity}"})
        if binding.workshop_sku == "HOJA" else binding
        for binding in bindings
    ]
    with pytest.raises(PurchaseAuthorityError, match="missing or ambiguous"):
        project_purchase_requirements_v1(
            positions=[first, second],
            stock_bindings=bindings + changed,
            glass_mappings=[glass_mapping()],
            hardware_mappings=hardware_mappings(first),
            panel_authorities=[],
        )


def test_profile_and_reinforcement_never_cross_pool_even_with_same_identity(
    demo_60_params: SystemParams,
) -> None:
    node = core_node("G6").model_copy(update={"glass_article_sku": "GLASS-TECH"})
    position, bindings = position_source(node, demo_60_params, position_id="P", position_index=1)
    forced = [binding.model_copy(update={
        "physical_stock_identity": "SHARED-PHYSICAL-TEXT",
        "purchasing_sku": "SHARED-PURCHASING-SKU",
    }) for binding in bindings]
    result = project_one(position, forced)
    shared = [group for group in result.stock_groups
              if group.physical_stock_identity == "SHARED-PHYSICAL-TEXT"]
    assert {group.source_kind for group in shared} == {
        PhysicalSourceKind.PROFILE, PhysicalSourceKind.REINFORCEMENT
    }
    assert len(shared) == 2


def test_glass_equivalence_preserves_orientation_location_and_polishing(
    demo_60_params: SystemParams,
) -> None:
    node = core_node("G6").model_copy(update={"glass_article_sku": "GLASS-TECH"})
    first, bindings = position_source(node, demo_60_params, position_id="P-1", position_index=1)
    second, _ = position_source(
        node, demo_60_params, position_id="P-2", position_index=2, location="FACHADA-SUR"
    )
    result = project_purchase_requirements_v1(
        positions=[first, second], stock_bindings=bindings,
        glass_mappings=[glass_mapping()], hardware_mappings=hardware_mappings(first),
        panel_authorities=[],
    )
    glass = [item for item in result.requirements if item.category == "GLASS"]
    assert len(glass) == 2
    assert {item.location_tag for item in glass} == {"FACHADA-NORTE", "FACHADA-SUR"}
    polished = first.model_copy(update={
        "glass_polishing": [GlassPolishingAuthorityV1(
            bay_id="G6",
            edges=EdgePolishingV1(top=True, right=False, bottom=False, left=False),
        )]
    })
    result = project_purchase_requirements_v1(
        positions=[polished, second], stock_bindings=bindings,
        glass_mappings=[glass_mapping()], hardware_mappings=hardware_mappings(first),
        panel_authorities=[],
    )
    assert len([item for item in result.requirements if item.category == "GLASS"]) == 2


def test_hardware_is_kit_only_and_contents_are_evidence_not_purchase_lines(
    demo_60_params: SystemParams,
) -> None:
    node = core_node("G6").model_copy(update={"glass_article_sku": "GLASS-TECH"})
    position, bindings = position_source(node, demo_60_params, position_id="P", position_index=1)
    result = project_one(position, bindings)
    kit = next(item for item in result.requirements if item.category == "HARDWARE_KIT")
    assert kit.unit == "KIT" and kit.hardware_contents
    assert {item.sku for item in kit.hardware_contents} == {"DEMO-STAY-16"}
    assert not any(item.purchasing_sku == "DEMO-STAY-16" for item in result.requirements)


def test_panel_and_accessory_authority_fail_closed(demo_60_params: SystemParams) -> None:
    panel_position, bindings = position_source(
        core_node("G7"), demo_60_params, position_id="PANEL", position_index=1
    )
    with pytest.raises(PurchaseAuthorityError, match="Panel purchasing authority"):
        project_one(panel_position, bindings)
    panel = PanelPurchaseAuthorityV1(
        authority_id="PANEL-AUTH-V1", version=1, system_id="DEMO_60",
        technical_sku="PANEL-SANDWICH-DEMO-24", purchasing_sku="PANEL-BUY",
        manufacturer_name="DEMO PANEL", provenance={"source": "synthetic"},
    )
    projected = project_purchase_requirements_v1(
        positions=[panel_position], stock_bindings=bindings, glass_mappings=[],
        hardware_mappings=hardware_mappings(panel_position), panel_authorities=[panel],
    )
    requirement = next(item for item in projected.requirements if item.category == "PANEL")
    assert requirement.supply_form == "CUT_TO_SIZE" and requirement.unit == "EA"

    duplicate_schedule = AccessoryScheduleV1.model_validate({
        "schedule_id": "ACCESSORY-SCHEDULE",
        "coverage": "DECLARED",
        "items": [{
            "obligation_id": "DUPLICATE-PROFILE",
            "obligation_kind": "FASTENING",
            "technical_sku": "MARCO",
            "purchasing_sku": "UNRELATED",
            "manufacturer_name": "DEMO",
            "order_type": SupplierOrderType.PROFILE,
            "quantity_per_position_unit": 1,
            "description": "Explicit but invalid duplicate",
        }],
    })
    duplicate, duplicate_bindings = position_source(
        core_node("G7"), demo_60_params, position_id="DUP", position_index=2,
        accessories=duplicate_schedule,
    )
    with pytest.raises(PurchaseAuthorityError, match="duplicates"):
        project_purchase_requirements_v1(
            positions=[duplicate], stock_bindings=duplicate_bindings, glass_mappings=[],
            hardware_mappings=hardware_mappings(duplicate), panel_authorities=[panel],
        )


def test_missing_mapping_and_source_duplication_are_rejected(
    demo_60_params: SystemParams,
) -> None:
    node = core_node("G6").model_copy(update={"glass_article_sku": "GLASS-TECH"})
    position, bindings = position_source(node, demo_60_params, position_id="P", position_index=1)
    with pytest.raises(PurchaseAuthorityError, match="Glass purchasing authority"):
        project_purchase_requirements_v1(
            positions=[position], stock_bindings=bindings, glass_mappings=[],
            hardware_mappings=hardware_mappings(position), panel_authorities=[],
        )
    assert project_one(position, bindings).projection_hash == project_one(position, bindings).projection_hash
    assert all(
        requirement.order_type in set(SupplierOrderType)
        for requirement in project_one(position, bindings).requirements
    )


def _position_with_fittings(
    position: PositionPurchaseInputV1, fittings: list[FittingSelectionV1]
) -> PositionPurchaseInputV1:
    return PositionPurchaseInputV1.model_validate(
        {**position.model_dump(mode="python"), "fittings": [f.model_dump(mode="python") for f in fittings]}
    )


def _fitting_mapping(technical_sku: str) -> FittingPurchaseMappingV1:
    return FittingPurchaseMappingV1(
        authority_id=f"FITTING-MAP-{technical_sku}",
        version=1,
        system_id="DEMO_60",
        technical_sku=technical_sku,
        purchasing_sku=f"BUY-{technical_sku}",
        manufacturer_name="DEMO FITTINGS",
        provenance={"source": "synthetic"},
    )


def test_fittings_buy_through_declared_authority(demo_60_params: SystemParams) -> None:
    """§9: counted fittings reach purchasing only through a declared
    fitting_purchase_mapping — an unmapped sku fails closed."""
    node = core_node("G6").model_copy(update={"glass_article_sku": "GLASS-TECH"})
    position, bindings = position_source(node, demo_60_params, position_id="P", position_index=1)
    fittings = [
        FittingSelectionV1(
            repetition_index=repetition,
            bay_id="bay-1",
            leaf_id=None,
            technical_sku="CLAMP-SS-8",
            kind="CLAMP",
            quantity=4,
        )
        for repetition in range(1, position.quantity + 1)
    ]
    position = _position_with_fittings(position, fittings)

    with pytest.raises(PurchaseAuthorityError, match="Fitting purchasing authority"):
        project_one(position, bindings)

    result = project_purchase_requirements_v1(
        positions=[position],
        stock_bindings=bindings,
        glass_mappings=[glass_mapping()],
        hardware_mappings=hardware_mappings(position),
        panel_authorities=[],
        fitting_mappings=[_fitting_mapping("CLAMP-SS-8")],
    )
    requirement = next(item for item in result.requirements if item.category == "FITTING")
    assert requirement.order_type is SupplierOrderType.HARDWARE
    assert requirement.unit == "EA"
    assert requirement.purchasing_sku == "BUY-CLAMP-SS-8"
    assert requirement.quantity == 4 * position.quantity
    assert len(requirement.source_trace) == requirement.quantity
    assert requirement.authority_ids == ["FITTING-MAP-CLAMP-SS-8"]


def test_fitting_duplicates_are_rejected(demo_60_params: SystemParams) -> None:
    node = core_node("G6").model_copy(update={"glass_article_sku": "GLASS-TECH"})
    position, _ = position_source(node, demo_60_params, position_id="P", position_index=1)
    duplicate = FittingSelectionV1(
        repetition_index=1, bay_id="bay-1", leaf_id=None,
        technical_sku="CLAMP-SS-8", kind="CLAMP", quantity=2,
    )
    with pytest.raises(ValidationError, match="Fitting source is duplicated"):
        _position_with_fittings(position, [duplicate, duplicate])
    with pytest.raises(ValidationError, match="outside position quantity"):
        _position_with_fittings(position, [duplicate.model_copy(update={"repetition_index": 99})])
