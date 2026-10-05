"""Pure immutable V1 purchase projection from expanded frozen manufacturing facts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from dekopen_engine.cutting import (
    CutBar,
    CutMaterial,
    CutPiece,
    CuttingProfile,
    StockRule,
    optimize_cut,
)
from dekopen_engine.documentary_canonical import documentary_sha256_v1
from dekopen_engine.manufacturing import ManufacturingFactsV1
from dekopen_engine.models import EngineModel, HardwareComponent


class PurchaseAuthorityError(ValueError):
    pass


class SupplierOrderType(str, Enum):
    PROFILE = "SUPPLIER_PROFILE_PO"
    GLASS = "SUPPLIER_GLASS_PO"
    HARDWARE = "SUPPLIER_HARDWARE_PO"
    PANEL = "SUPPLIER_PANEL_PO"


class PhysicalSourceKind(str, Enum):
    PROFILE = "PROFILE"
    REINFORCEMENT = "REINFORCEMENT"


class EdgePolishingV1(EngineModel):
    top: bool
    right: bool
    bottom: bool
    left: bool


class GlassPolishingAuthorityV1(EngineModel):
    schema_version: Literal[1] = 1
    bay_id: str
    leaf_id: str | None = None
    edges: EdgePolishingV1


class PhysicalStockBindingV1(EngineModel):
    schema_version: Literal[1] = 1
    binding_id: str
    binding_version: int = Field(ge=1)
    system_id: str
    source_kind: PhysicalSourceKind
    workshop_sku: str
    purchasing_sku: str
    physical_stock_identity: str
    manufacturer_name: str
    material: CutMaterial
    color: str
    stock_length_mm: Decimal = Field(gt=Decimal("0"))
    cutting_profile: CuttingProfile


class GlassPurchaseMappingV1(EngineModel):
    schema_version: Literal[1] = 1
    authority_id: str
    version: int = Field(ge=1)
    system_id: str
    technical_sku: str
    purchasing_sku: str
    manufacturer_name: str
    purchase_unit: Literal["EA"] = "EA"
    provenance: dict[str, str]


class HardwarePurchaseMappingV1(EngineModel):
    schema_version: Literal[1] = 1
    authority_id: str
    version: int = Field(ge=1)
    system_id: str
    technical_kit_sku: str
    purchasing_sku: str
    manufacturer_name: str
    purchase_unit: Literal["KIT"] = "KIT"
    provenance: dict[str, str]


class PanelPurchaseAuthorityV1(EngineModel):
    schema_version: Literal[1] = 1
    authority_id: str
    version: int = Field(ge=1)
    system_id: str
    technical_sku: str
    purchasing_sku: str
    manufacturer_name: str
    supply_form: Literal["CUT_TO_SIZE"] = "CUT_TO_SIZE"
    purchase_unit: Literal["EA"] = "EA"
    provenance: dict[str, str]


class HardwareSelectionV1(EngineModel):
    repetition_index: int = Field(ge=1)
    bay_id: str
    leaf_id: str | None = None
    technical_kit_sku: str
    name: str
    quantity: int = Field(ge=1)
    contents: list[HardwareComponent]


class FittingPurchaseMappingV1(EngineModel):
    """Declared purchase authority for one counted fitting article
    (clamp, patch fitting, hinge, lock, connector, seal, point support).
    Mirrors the glass/hardware mapping contract: org NULL = global
    authority (mandate §9)."""

    schema_version: Literal[1] = 1
    authority_id: str
    version: int = Field(ge=1)
    system_id: str
    technical_sku: str
    purchasing_sku: str
    manufacturer_name: str
    purchase_unit: Literal["EA"] = "EA"
    provenance: dict[str, str]


class FittingSelectionV1(EngineModel):
    """A counted fitting line expanded per position unit — the BOM's
    declared pieces the purchase projection must buy (mandate §9)."""

    repetition_index: int = Field(ge=1)
    bay_id: str | None = None
    leaf_id: str | None = None
    technical_sku: str
    kind: str
    quantity: int = Field(ge=1)


class AccessoryLineV1(EngineModel):
    obligation_id: str
    obligation_kind: Literal[
        "SEALING", "FASTENING", "DRAINAGE", "INSTALLATION_ACCESSORY", "OTHER_DECLARED"
    ]
    technical_sku: str
    purchasing_sku: str
    manufacturer_name: str
    order_type: SupplierOrderType
    unit: Literal["EA"] = "EA"
    quantity_per_position_unit: int = Field(ge=1)
    description: str


class AccessoryScheduleV1(EngineModel):
    schema_version: Literal[1] = 1
    schedule_id: str
    coverage: Literal["DECLARED", "NONE_REQUIRED"]
    items: list[AccessoryLineV1]

    @model_validator(mode="after")
    def coverage_is_explicit(self) -> AccessoryScheduleV1:
        if self.coverage == "NONE_REQUIRED" and self.items:
            raise ValueError("NONE_REQUIRED accessory coverage cannot declare items")
        if self.coverage == "DECLARED" and not self.items:
            raise ValueError("DECLARED accessory coverage requires explicit items")
        identities = [item.obligation_id for item in self.items]
        if len(identities) != len(set(identities)):
            raise ValueError("Accessory obligations must be unique per position")
        return self


class PositionPurchaseInputV1(EngineModel):
    schema_version: Literal[1] = 1
    position_id: str
    position_index: int = Field(ge=1)
    system_id: str
    quantity: int = Field(ge=1)
    # The finish key the position's bars are stocked under (D05: a plain
    # finish code or the bicolor "EXT/INT" key). Steel carries its own
    # declared stock colors — `steel_colors` maps resolved sku -> color.
    color: str
    steel_colors: dict[str, str] = Field(default_factory=dict)
    location_tag: str
    manufacturing_units: list[ManufacturingFactsV1]
    hardware: list[HardwareSelectionV1]
    fittings: list[FittingSelectionV1] = Field(default_factory=list)
    glass_polishing: list[GlassPolishingAuthorityV1]
    accessory_schedule: AccessoryScheduleV1

    @model_validator(mode="after")
    def quantity_and_sources_reconcile(self) -> PositionPurchaseInputV1:
        if not self.location_tag.strip():
            raise ValueError("Purchasing requires an explicit location tag")
        repetitions = sorted(unit.repetition_index for unit in self.manufacturing_units)
        if repetitions != list(range(1, self.quantity + 1)):
            raise ValueError("Position quantity must be expanded exactly once")
        if any(
            unit.position_id != self.position_id or unit.position_index != self.position_index
            for unit in self.manufacturing_units
        ):
            raise ValueError("Manufacturing source belongs to another position")
        polishing_keys = [(item.bay_id, item.leaf_id) for item in self.glass_polishing]
        if len(polishing_keys) != len(set(polishing_keys)):
            raise ValueError("Glass polishing authority is duplicated")
        glass_keys = {
            (infill.bay_id, infill.leaf_id)
            for unit in self.manufacturing_units
            for infill in unit.infills
            if infill.kind == "GLASS"
        }
        if set(polishing_keys) != glass_keys:
            raise ValueError("Every glass source requires exactly one polishing authority")
        if any(item.repetition_index > self.quantity for item in self.hardware):
            raise ValueError("Hardware source repetition is outside position quantity")
        hardware_targets = [
            (item.repetition_index, item.bay_id, item.leaf_id, item.technical_kit_sku)
            for item in self.hardware
        ]
        if len(hardware_targets) != len(set(hardware_targets)):
            raise ValueError("Hardware source is duplicated")
        if any(item.repetition_index > self.quantity for item in self.fittings):
            raise ValueError("Fitting source repetition is outside position quantity")
        fitting_targets = [
            (
                item.repetition_index, item.bay_id, item.leaf_id,
                item.technical_sku, item.kind,
            )
            for item in self.fittings
        ]
        if len(fitting_targets) != len(set(fitting_targets)):
            raise ValueError("Fitting source is duplicated")
        return self


class StockGroupResultV1(EngineModel):
    physical_stock_identity: str
    source_kind: PhysicalSourceKind
    purchasing_sku: str
    workshop_skus: list[str]
    material: CutMaterial
    color: str
    stock_length_mm: Decimal
    cutting_profile: CuttingProfile
    binding_ids: list[str]
    source_piece_ids: list[str]
    purchased_bar_count: int
    bars: list[CutBar]


class PurchaseRequirementV1(EngineModel):
    requirement_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    order_type: SupplierOrderType
    category: Literal[
        "PROFILE", "REINFORCEMENT", "GLASS", "HARDWARE_KIT", "PANEL",
        "ACCESSORY", "FITTING",
    ]
    authority_ids: list[str]
    technical_skus: list[str]
    purchasing_sku: str
    physical_stock_identity: str | None = None
    manufacturer_name: str
    unit: Literal["BAR", "EA", "KIT"]
    quantity: int = Field(ge=1)
    stock_length_mm: Decimal | None = None
    cutting_profile_id: str | None = None
    color: str | None = None
    composition: str | None = None
    oriented_width_mm: Decimal | None = None
    oriented_height_mm: Decimal | None = None
    polishing: EdgePolishingV1 | None = None
    location_tag: str | None = None
    hardware_contents: list[HardwareComponent] | None = None
    supply_form: Literal["CUT_TO_SIZE"] | None = None
    accessory_obligation_id: str | None = None
    accessory_obligation_kind: str | None = None
    description: str | None = None
    source_trace: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def category_contract_is_complete(self) -> PurchaseRequirementV1:
        if self.authority_ids != sorted(set(self.authority_ids)):
            raise ValueError("Requirement authority identities must be unique and sorted")
        if self.technical_skus != sorted(set(self.technical_skus)):
            raise ValueError("Requirement technical identities must be unique and sorted")
        if self.source_trace != sorted(set(self.source_trace)):
            raise ValueError("Requirement source trace must be unique and sorted")
        if self.category in ("PROFILE", "REINFORCEMENT"):
            if (
                self.order_type is not SupplierOrderType.PROFILE
                or self.unit != "BAR"
                or self.physical_stock_identity is None
                or self.stock_length_mm is None
                or self.cutting_profile_id is None
            ):
                raise ValueError("Bar requirement lacks physical stock authority")
        elif self.category == "GLASS":
            if (
                self.order_type is not SupplierOrderType.GLASS
                or self.unit != "EA"
                or self.composition is None
                or self.oriented_width_mm is None
                or self.oriented_height_mm is None
                or self.polishing is None
                or self.location_tag is None
            ):
                raise ValueError("Glass requirement lacks its exact equivalence key")
        elif self.category == "HARDWARE_KIT":
            if (
                self.order_type is not SupplierOrderType.HARDWARE
                or self.unit != "KIT"
                or self.hardware_contents is None
            ):
                raise ValueError("Hardware requirement must preserve complete kit evidence")
        elif self.category == "PANEL":
            if (
                self.order_type is not SupplierOrderType.PANEL
                or self.unit != "EA"
                or self.supply_form != "CUT_TO_SIZE"
                or self.oriented_width_mm is None
                or self.oriented_height_mm is None
                or self.location_tag is None
            ):
                raise ValueError("Panel requirement lacks CUT_TO_SIZE authority")
        elif self.category == "FITTING":
            if (
                self.order_type is not SupplierOrderType.HARDWARE
                or self.unit != "EA"
                or self.hardware_contents is not None
            ):
                raise ValueError("Fitting requirement lacks declared fitting authority")
        elif (
            self.unit != "EA"
            or self.accessory_obligation_id is None
            or self.accessory_obligation_kind is None
            or self.description is None
        ):
            raise ValueError("Accessory requirement lacks explicit declared obligation")
        return self


class PurchaseRequirementsV1(EngineModel):
    schema_version: Literal[1] = 1
    requirements: list[PurchaseRequirementV1]
    stock_groups: list[StockGroupResultV1]
    projection_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class _RequirementDraft(EngineModel):
    order_type: SupplierOrderType
    category: Literal[
        "PROFILE", "REINFORCEMENT", "GLASS", "HARDWARE_KIT", "PANEL",
        "ACCESSORY", "FITTING",
    ]
    authority_ids: list[str]
    technical_skus: list[str]
    purchasing_sku: str
    physical_stock_identity: str | None = None
    manufacturer_name: str
    unit: Literal["BAR", "EA", "KIT"]
    quantity: int
    stock_length_mm: Decimal | None = None
    cutting_profile_id: str | None = None
    color: str | None = None
    composition: str | None = None
    oriented_width_mm: Decimal | None = None
    oriented_height_mm: Decimal | None = None
    polishing: EdgePolishingV1 | None = None
    location_tag: str | None = None
    hardware_contents: list[HardwareComponent] | None = None
    supply_form: Literal["CUT_TO_SIZE"] | None = None
    accessory_obligation_id: str | None = None
    accessory_obligation_kind: str | None = None
    description: str | None = None
    source_trace: list[str]


def _one_mapping(
    items: Sequence[
        GlassPurchaseMappingV1 | HardwarePurchaseMappingV1
        | PanelPurchaseAuthorityV1 | FittingPurchaseMappingV1
    ],
    technical_sku: str,
    system_id: str,
    label: str,
) -> GlassPurchaseMappingV1 | HardwarePurchaseMappingV1 | PanelPurchaseAuthorityV1 | FittingPurchaseMappingV1:
    matches = [
        item for item in items
        if item.system_id == system_id
        and (item.technical_kit_sku if isinstance(item, HardwarePurchaseMappingV1)
             else item.technical_sku) == technical_sku
    ]
    if len(matches) != 1:
        raise PurchaseAuthorityError(f"{label} purchasing authority is missing or ambiguous")
    return matches[0]


def _cut_piece(
    *, piece_id: str, source_kind: PhysicalSourceKind, workshop_sku: str,
    material: CutMaterial, color: str, length_mm: Decimal, position_id: str,
    bay_id: str | None, leaf_id: str | None, role: str,
    angle_left: Decimal, angle_right: Decimal,
) -> CutPiece:
    return CutPiece(
        piece_id=piece_id,
        source_kind=source_kind.value,
        workshop_sku=workshop_sku,
        material=material,
        color=color,
        length_mm=length_mm,
        source_position_id=position_id,
        bay_id=bay_id,
        leaf_id=leaf_id,
        role=role,
        unit_index=1,
        angle_left=angle_left,
        angle_right=angle_right,
    )


def _binding_for_piece(
    piece: CutPiece, bindings: list[PhysicalStockBindingV1], position_systems: dict[str, str]
) -> PhysicalStockBindingV1:
    source_kind = PhysicalSourceKind(piece.source_kind)
    if piece.source_position_id is None or piece.source_position_id not in position_systems:
        raise PurchaseAuthorityError("Cut piece has no project position authority")
    matches = [
        binding for binding in bindings
        if binding.system_id == position_systems[piece.source_position_id]
        and binding.source_kind is source_kind
        and binding.workshop_sku == piece.workshop_sku
        and binding.material is piece.material
        and binding.color == piece.color
    ]
    if len(matches) != 1:
        raise PurchaseAuthorityError("Physical stock binding is missing or ambiguous")
    return matches[0]


def _stock_group_key(binding: PhysicalStockBindingV1) -> tuple[str, ...]:
    profile = binding.cutting_profile
    return (
        binding.source_kind.value,
        binding.physical_stock_identity,
        binding.material.value,
        binding.color,
        str(binding.stock_length_mm),
        profile.id,
        str(profile.kerf_mm),
        str(profile.head_trim_mm),
        str(profile.tail_trim_mm),
    )


def _draft_key(value: _RequirementDraft) -> str:
    return documentary_sha256_v1(value)


def _merge_drafts(drafts: list[_RequirementDraft]) -> list[PurchaseRequirementV1]:
    merged: dict[str, _RequirementDraft] = {}
    for draft in drafts:
        semantic = draft.model_copy(update={"quantity": 1, "source_trace": []})
        key = _draft_key(semantic)
        previous = merged.get(key)
        if previous is None:
            merged[key] = draft.model_copy(update={
                "authority_ids": sorted(set(draft.authority_ids)),
                "technical_skus": sorted(set(draft.technical_skus)),
                "source_trace": sorted(set(draft.source_trace)),
            })
            continue
        overlap = set(previous.source_trace) & set(draft.source_trace)
        if overlap:
            raise PurchaseAuthorityError("Physical purchasing source was counted twice")
        merged[key] = previous.model_copy(update={
            "quantity": previous.quantity + draft.quantity,
            "authority_ids": sorted(set(previous.authority_ids + draft.authority_ids)),
            "technical_skus": sorted(set(previous.technical_skus + draft.technical_skus)),
            "source_trace": sorted(previous.source_trace + draft.source_trace),
        })
    requirements = []
    for draft in merged.values():
        payload = draft.model_dump(mode="python")
        requirement_key = documentary_sha256_v1(payload)
        requirements.append(PurchaseRequirementV1(requirement_key=requirement_key, **payload))
    return sorted(requirements, key=lambda item: (
        item.order_type.value, item.category, item.purchasing_sku,
        item.physical_stock_identity or "", item.requirement_key,
    ))


def project_purchase_requirements_v1(
    *,
    positions: list[PositionPurchaseInputV1],
    stock_bindings: list[PhysicalStockBindingV1],
    glass_mappings: list[GlassPurchaseMappingV1],
    hardware_mappings: list[HardwarePurchaseMappingV1],
    panel_authorities: list[PanelPurchaseAuthorityV1],
    fitting_mappings: list[FittingPurchaseMappingV1] = [],
) -> PurchaseRequirementsV1:
    position_ids = [item.position_id for item in positions]
    position_indexes = [item.position_index for item in positions]
    if len(position_ids) != len(set(position_ids)) or len(position_indexes) != len(
        set(position_indexes)
    ):
        raise PurchaseAuthorityError("Project position identity is duplicated")
    position_systems = {item.position_id: item.system_id for item in positions}

    pieces: list[CutPiece] = []
    drafts: list[_RequirementDraft] = []
    non_accessory_technical: set[str] = set()
    non_accessory_purchasing: set[str] = set()
    for position in sorted(positions, key=lambda item: (item.position_index, item.position_id)):
        polishing = {(item.bay_id, item.leaf_id): item.edges for item in position.glass_polishing}
        for unit in sorted(position.manufacturing_units, key=lambda item: item.repetition_index):
            member_by_id = {member.member_id: member for member in unit.members}
            for member in unit.members:
                pieces.append(_cut_piece(
                    piece_id=member.member_id,
                    source_kind=PhysicalSourceKind.PROFILE,
                    workshop_sku=member.workshop_sku,
                    material=CutMaterial(member.material.value),
                    color=position.color,
                    length_mm=member.cut_length_mm,
                    position_id=position.position_id,
                    bay_id=member.bay_id,
                    leaf_id=member.leaf_id,
                    role=member.identity.role.value,
                    angle_left=member.angle_left,
                    angle_right=member.angle_right,
                ))
                non_accessory_technical.add(member.workshop_sku)
            for reinforcement in unit.reinforcements:
                try:
                    parent = member_by_id[reinforcement.parent_member_id]
                except KeyError as error:
                    raise PurchaseAuthorityError("Reinforcement parent member is missing") from error
                pieces.append(_cut_piece(
                    piece_id=reinforcement.reinforcement_id,
                    source_kind=PhysicalSourceKind.REINFORCEMENT,
                    workshop_sku=reinforcement.workshop_sku,
                    material=CutMaterial.STEEL,
                    # D05: steel is colorless relative to the bar finish —
                    # its declared stock color rides the sealed input.
                    color=position.steel_colors.get(
                        reinforcement.workshop_sku, "WHITE"
                    ),
                    length_mm=reinforcement.cut_length_mm,
                    position_id=position.position_id,
                    bay_id=parent.bay_id,
                    leaf_id=parent.leaf_id,
                    role=parent.identity.role.value,
                    angle_left=reinforcement.angle_left,
                    angle_right=reinforcement.angle_right,
                ))
                non_accessory_technical.add(reinforcement.workshop_sku)
            for infill in unit.infills:
                if infill.kind == "GLASS":
                    mapping = _one_mapping(glass_mappings, infill.technical_sku, position.system_id, "Glass")
                    assert isinstance(mapping, GlassPurchaseMappingV1)
                    draft = _RequirementDraft(
                        order_type=SupplierOrderType.GLASS,
                        category="GLASS",
                        authority_ids=[mapping.authority_id],
                        technical_skus=[infill.technical_sku],
                        purchasing_sku=mapping.purchasing_sku,
                        manufacturer_name=mapping.manufacturer_name,
                        unit="EA",
                        quantity=1,
                        composition=infill.composition,
                        oriented_width_mm=infill.rect.width_mm,
                        oriented_height_mm=infill.rect.height_mm,
                        polishing=polishing[(infill.bay_id, infill.leaf_id)],
                        location_tag=position.location_tag,
                        source_trace=[infill.infill_id],
                    )
                else:
                    authority = _one_mapping(panel_authorities, infill.technical_sku, position.system_id, "Panel")
                    assert isinstance(authority, PanelPurchaseAuthorityV1)
                    draft = _RequirementDraft(
                        order_type=SupplierOrderType.PANEL,
                        category="PANEL",
                        authority_ids=[authority.authority_id],
                        technical_skus=[infill.technical_sku],
                        purchasing_sku=authority.purchasing_sku,
                        manufacturer_name=authority.manufacturer_name,
                        unit="EA",
                        quantity=1,
                        oriented_width_mm=infill.rect.width_mm,
                        oriented_height_mm=infill.rect.height_mm,
                        location_tag=position.location_tag,
                        supply_form=authority.supply_form,
                        description=infill.composition,
                        source_trace=[infill.infill_id],
                    )
                drafts.append(draft)
                non_accessory_technical.update(draft.technical_skus)
                non_accessory_purchasing.add(draft.purchasing_sku)
        for hardware in sorted(position.hardware, key=lambda item: (
            item.repetition_index, item.bay_id, item.leaf_id or "", item.technical_kit_sku
        )):
            mapping = _one_mapping(
                hardware_mappings, hardware.technical_kit_sku, position.system_id, "Hardware kit"
            )
            assert isinstance(mapping, HardwarePurchaseMappingV1)
            contents = sorted(hardware.contents, key=lambda item: (item.sku, item.name, item.unit, item.qty))
            for kit_index in range(1, hardware.quantity + 1):
                source_id = documentary_sha256_v1({
                    "kind": "hardware_kit",
                    "position_id": position.position_id,
                    "repetition_index": hardware.repetition_index,
                    "bay_id": hardware.bay_id,
                    "leaf_id": hardware.leaf_id,
                    "technical_kit_sku": hardware.technical_kit_sku,
                    "kit_index": kit_index,
                })
                drafts.append(_RequirementDraft(
                    order_type=SupplierOrderType.HARDWARE,
                    category="HARDWARE_KIT",
                    authority_ids=[mapping.authority_id],
                    technical_skus=[hardware.technical_kit_sku],
                    purchasing_sku=mapping.purchasing_sku,
                    manufacturer_name=mapping.manufacturer_name,
                    unit="KIT",
                    quantity=1,
                    hardware_contents=contents,
                    description=hardware.name,
                    source_trace=[source_id],
                ))
            non_accessory_technical.add(hardware.technical_kit_sku)
            non_accessory_purchasing.add(mapping.purchasing_sku)
        for fitting in sorted(position.fittings, key=lambda item: (
            item.repetition_index, item.bay_id or "", item.leaf_id or "",
            item.technical_sku, item.kind,
        )):
            # §9: counted fittings (frameless clamps/patch fittings/hinges/
            # locks/connectors/seals/supports) buy through their declared
            # fitting authority — never silently dropped from procurement.
            mapping = _one_mapping(
                fitting_mappings, fitting.technical_sku, position.system_id, "Fitting"
            )
            assert isinstance(mapping, FittingPurchaseMappingV1)
            source_trace = [
                documentary_sha256_v1({
                    "kind": "fitting",
                    "position_id": position.position_id,
                    "repetition_index": fitting.repetition_index,
                    "bay_id": fitting.bay_id,
                    "leaf_id": fitting.leaf_id,
                    "technical_sku": fitting.technical_sku,
                    "fitting_kind": fitting.kind,
                    "unit_index": unit_index,
                })
                for unit_index in range(1, fitting.quantity + 1)
            ]
            drafts.append(_RequirementDraft(
                order_type=SupplierOrderType.HARDWARE,
                category="FITTING",
                authority_ids=[mapping.authority_id],
                technical_skus=[fitting.technical_sku],
                purchasing_sku=mapping.purchasing_sku,
                manufacturer_name=mapping.manufacturer_name,
                unit="EA",
                quantity=len(source_trace),
                location_tag=position.location_tag,
                description=fitting.kind,
                source_trace=source_trace,
            ))
            non_accessory_technical.add(fitting.technical_sku)
            non_accessory_purchasing.add(mapping.purchasing_sku)

    bound_pieces: dict[tuple[str, ...], list[tuple[CutPiece, PhysicalStockBindingV1]]] = defaultdict(list)
    for piece in pieces:
        binding = _binding_for_piece(piece, stock_bindings, position_systems)
        bound_pieces[_stock_group_key(binding)].append((piece, binding))
        non_accessory_purchasing.add(binding.purchasing_sku)

    stock_groups: list[StockGroupResultV1] = []
    for group_key in sorted(bound_pieces):
        bound = bound_pieces[group_key]
        group_bindings = {item.binding_id: item for _, item in bound}
        authorities = list(group_bindings.values())
        first = authorities[0]
        if any(
            (
                item.source_kind, item.physical_stock_identity, item.purchasing_sku,
                item.manufacturer_name, item.material, item.color, item.stock_length_mm,
                item.cutting_profile,
            ) != (
                first.source_kind, first.physical_stock_identity, first.purchasing_sku,
                first.manufacturer_name, first.material, first.color, first.stock_length_mm,
                first.cutting_profile,
            )
            for item in authorities[1:]
        ):
            raise PurchaseAuthorityError("Physical stock identity has conflicting authority")
        stock_rules = [
            StockRule(
                stock_authority_id=item.binding_id,
                workshop_sku=item.workshop_sku,
                commercial_sku=item.purchasing_sku,
                manufacturer_name=item.manufacturer_name,
                supplier_name=None,
                purchase_unit="BAR",
                material=item.material,
                color=item.color,
                stock_length_mm=item.stock_length_mm,
            )
            for item in sorted(authorities, key=lambda value: value.binding_id)
        ]
        group_pieces = [piece for piece, _ in bound]
        optimized = optimize_cut(group_pieces, stock_rules, first.cutting_profile)
        if len(optimized.purchase_list) != 1:
            raise PurchaseAuthorityError("One physical stock group must produce one bar requirement")
        purchase = optimized.purchase_list[0]
        stock_group = StockGroupResultV1(
            physical_stock_identity=first.physical_stock_identity,
            source_kind=first.source_kind,
            purchasing_sku=first.purchasing_sku,
            workshop_skus=sorted({item.workshop_sku for item in authorities}),
            material=first.material,
            color=first.color,
            stock_length_mm=first.stock_length_mm,
            cutting_profile=first.cutting_profile,
            binding_ids=sorted(group_bindings),
            source_piece_ids=sorted(piece.piece_id for piece in group_pieces),
            purchased_bar_count=purchase.qty_bars,
            bars=optimized.workshop_cut_plan,
        )
        stock_groups.append(stock_group)
        drafts.append(_RequirementDraft(
            order_type=SupplierOrderType.PROFILE,
            category=("PROFILE" if first.source_kind is PhysicalSourceKind.PROFILE
                      else "REINFORCEMENT"),
            authority_ids=stock_group.binding_ids,
            technical_skus=stock_group.workshop_skus,
            purchasing_sku=first.purchasing_sku,
            physical_stock_identity=first.physical_stock_identity,
            manufacturer_name=first.manufacturer_name,
            unit="BAR",
            quantity=purchase.qty_bars,
            stock_length_mm=first.stock_length_mm,
            cutting_profile_id=first.cutting_profile.id,
            color=first.color,
            source_trace=stock_group.source_piece_ids,
        ))

    for position in sorted(positions, key=lambda item: (item.position_index, item.position_id)):
        for accessory in sorted(position.accessory_schedule.items, key=lambda item: item.obligation_id):
            if (
                accessory.technical_sku in non_accessory_technical
                or accessory.purchasing_sku in non_accessory_purchasing
            ):
                raise PurchaseAuthorityError("Accessory duplicates an existing material obligation")
            source_trace = [
                documentary_sha256_v1({
                    "kind": "accessory",
                    "position_id": position.position_id,
                    "repetition_index": repetition,
                    "obligation_id": accessory.obligation_id,
                    "unit_index": unit_index,
                })
                for repetition in range(1, position.quantity + 1)
                for unit_index in range(1, accessory.quantity_per_position_unit + 1)
            ]
            drafts.append(_RequirementDraft(
                order_type=accessory.order_type,
                category="ACCESSORY",
                authority_ids=[position.accessory_schedule.schedule_id],
                technical_skus=[accessory.technical_sku],
                purchasing_sku=accessory.purchasing_sku,
                manufacturer_name=accessory.manufacturer_name,
                unit=accessory.unit,
                quantity=len(source_trace),
                location_tag=position.location_tag,
                accessory_obligation_id=accessory.obligation_id,
                accessory_obligation_kind=accessory.obligation_kind,
                description=accessory.description,
                source_trace=source_trace,
            ))

    requirements = _merge_drafts(drafts)
    projection_preimage = {
        "schema_version": 1,
        "requirements": [item.model_dump(mode="python") for item in requirements],
        "stock_groups": [item.model_dump(mode="python") for item in stock_groups],
    }
    return PurchaseRequirementsV1(
        requirements=requirements,
        stock_groups=stock_groups,
        projection_hash=documentary_sha256_v1(projection_preimage),
    )
