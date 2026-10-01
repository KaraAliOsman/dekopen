"""RLS-bound SHOT-09 authority loaders and guarded evidence writes."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
import json
from uuid import UUID

from django.db import connection, DatabaseError

from authentication.rls import tx_aborted
from psycopg import sql

from dekopen_engine.cutting import CutMaterial, CuttingProfile
from dekopen_engine.inspection_models import StructuralInput, WorkshopAnnotations
from dekopen_engine.manufacturing import (
    handle_policy_from_json,
    placement_policy_from_json,
    reinforcement_policy_from_json,
    HandleIntentV1,
    HandleRequirementPolicyV1,
    ManufacturingPlacementPolicyV1,
    ReinforcementCutPolicyV1,
    VerticalReference,
)
from dekopen_engine.purchasing import (
    AccessoryLineV1,
    AccessoryScheduleV1,
    EdgePolishingV1,
    FittingPurchaseMappingV1,
    GlassPolishingAuthorityV1,
    GlassPurchaseMappingV1,
    HardwarePurchaseMappingV1,
    PanelPurchaseAuthorityV1,
    PhysicalSourceKind,
    PhysicalStockBindingV1,
    SupplierOrderType,
)
from engine_api.repository import _decimal
from pricing.repository import encode


class DocumentaryError(ValueError):
    def __init__(
        self,
        code: str,
        *,
        detail: str | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.public_detail = detail
        self.extra = dict(extra or {})


@dataclass(frozen=True)
class ManufacturingPolicies:
    placement: ManufacturingPlacementPolicyV1
    handles: HandleRequirementPolicyV1
    reinforcement: ReinforcementCutPolicyV1


@dataclass(frozen=True)
class PurchaseAuthorities:
    stock_bindings: list[PhysicalStockBindingV1]
    glass_mappings: list[GlassPurchaseMappingV1]
    hardware_mappings: list[HardwarePurchaseMappingV1]
    panel_authorities: list[PanelPurchaseAuthorityV1]
    fitting_mappings: list[FittingPurchaseMappingV1] = field(
        default_factory=list
    )


def json_text(value: object) -> str:
    return json.dumps(value, default=encode, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def decoded(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value, parse_float=Decimal)
    return value


def rows(query: object, parameters: Sequence[object] = ()) -> list[dict[str, object]]:
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def write(query: object, parameters: Sequence[object] = ()) -> int:
    """Statement without a row result (UPDATE/DELETE) — returns rowcount.
    `rows()` is SELECT-only: `cursor.description` is None on writes."""
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        return cursor.rowcount


def one(
    query: object, parameters: Sequence[object] = (), code: str = "documentary_authority_not_found"
) -> dict[str, object]:
    result = rows(query, parameters)
    if len(result) != 1:
        raise DocumentaryError("ambiguous_documentary_authority" if result else code)
    return result[0]


@contextmanager
def documentary_backend() -> Iterator[None]:
    """Switch to the documentary role, restoring the caller's role on exit.

    Nested contexts are safe: the previous role is captured rather than
    hard-resetting to ``authenticated``; an unset role restores to ``none``
    (the session user), which is what request and worker callers start in."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('role', true)")
        previous = str(cursor.fetchone()[0] or "none")
        cursor.execute("SET LOCAL ROLE documentary_backend")
    try:
        yield
    except DatabaseError:
        raise
    except BaseException:
        if not tx_aborted():
            with connection.cursor() as cursor:
                # set_config accepts 'none' (session user) where SET ROLE
                # "none" would fail looking for a literal role name.
                cursor.execute("SELECT set_config('role', %s, true)", [previous])
        raise
    else:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('role', %s, true)", [previous])


def effective_scope(
    values: list[dict[str, object]], org_id: UUID
) -> list[dict[str, object]]:
    tenant = [item for item in values if str(item["org_id"]) == str(org_id)]
    return tenant if tenant else [item for item in values if item["org_id"] is None]


def _authority_row(table: str, policy_id: UUID, system_id: UUID, org_id: UUID) -> dict[str, object]:
    values = rows(
        sql.SQL(
            "SELECT id,version,authority::text,org_id FROM public.{} "
            "WHERE id=%s AND system_id=%s AND (org_id IS NULL OR org_id=%s)"
        ).format(sql.Identifier(table)),
        [policy_id, system_id, org_id],
    )
    effective = effective_scope(values, org_id)
    if len(effective) != 1:
        raise DocumentaryError("manufacturing_policy_missing_or_ambiguous")
    return effective[0]


def _placement_policy(value: object) -> ManufacturingPlacementPolicyV1:
    try:
        return placement_policy_from_json(decoded(value))
    except (KeyError, TypeError, ValueError) as error:
        raise DocumentaryError("invalid_placement_policy") from error


def _handle_policy(value: object) -> HandleRequirementPolicyV1:
    try:
        return handle_policy_from_json(decoded(value))
    except (KeyError, TypeError, ValueError) as error:
        raise DocumentaryError("invalid_handle_policy") from error


def _reinforcement_policy(value: object) -> ReinforcementCutPolicyV1:
    try:
        return reinforcement_policy_from_json(decoded(value))
    except (KeyError, TypeError, ValueError) as error:
        raise DocumentaryError("invalid_reinforcement_policy") from error


def load_manufacturing_policies(
    *, system_id: UUID, org_id: UUID, placement_id: UUID,
    handle_id: UUID, reinforcement_id: UUID,
) -> ManufacturingPolicies:
    placement = _authority_row(
        "manufacturing_placement_policies", placement_id, system_id, org_id
    )
    handles = _authority_row("handle_requirement_policies", handle_id, system_id, org_id)
    reinforcement = _authority_row(
        "reinforcement_cut_policies", reinforcement_id, system_id, org_id
    )
    return ManufacturingPolicies(
        _placement_policy(placement["authority"]),
        _handle_policy(handles["authority"]),
        _reinforcement_policy(reinforcement["authority"]),
    )


def workshop_annotations(value: object) -> list[WorkshopAnnotations]:
    raw = decoded(value)
    if not isinstance(raw, list):
        raise DocumentaryError("invalid_workshop_annotations")
    result = []
    try:
        for item in raw:
            if not isinstance(item, dict):
                raise DocumentaryError("invalid_workshop_annotations")
            result.append(WorkshopAnnotations(
                bay_id=str(item["bay_id"]),
                leaf_id=None if item.get("leaf_id") is None else str(item["leaf_id"]),
                bottom_drain_holes_mm=(None if item.get("bottom_drain_holes_mm") is None else
                                       [_decimal(number) for number in item["bottom_drain_holes_mm"]]),
                closing_points_perimeter_mm=(
                    None if item.get("closing_points_perimeter_mm") is None else
                    [_decimal(number) for number in item["closing_points_perimeter_mm"]]
                ),
                continuous_width_mm=(None if item.get("continuous_width_mm") is None else
                                     _decimal(item["continuous_width_mm"])),
                finish_class=item.get("finish_class"),
                has_coupler=item.get("has_coupler"),
            ))
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, DocumentaryError):
            raise
        raise DocumentaryError("invalid_workshop_annotations") from error
    return result


def structural_inputs(value: object) -> list[StructuralInput]:
    raw = decoded(value)
    if not isinstance(raw, list):
        raise DocumentaryError("invalid_structural_inputs")
    try:
        if not all(isinstance(item, dict) for item in raw):
            raise DocumentaryError("invalid_structural_inputs")
        return [StructuralInput(
            target_id=str(item["target_id"]),
            required_ix_cm4=(None if item.get("required_ix_cm4") is None else
                             _decimal(item["required_ix_cm4"])),
            structural_basis=(None if item.get("structural_basis") is None else
                              str(item["structural_basis"])),
        ) for item in raw]
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, DocumentaryError):
            raise
        raise DocumentaryError("invalid_structural_inputs") from error


def handle_intents(value: object) -> list[HandleIntentV1]:
    raw = decoded(value)
    if not isinstance(raw, list):
        raise DocumentaryError("invalid_handle_intents")
    try:
        if not all(isinstance(item, dict) for item in raw):
            raise DocumentaryError("invalid_handle_intents")
        return [HandleIntentV1(
            schema_version=int(item.get("schema_version", 1)),
            bay_id=str(item["bay_id"]),
            leaf_id=None if item.get("leaf_id") is None else str(item["leaf_id"]),
            handle_domain_slot=str(item["handle_domain_slot"]),
            requested_height_mm=_decimal(item["requested_height_mm"]),
            vertical_reference=VerticalReference(str(item["vertical_reference"])),
        ) for item in raw]
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, DocumentaryError):
            raise
        raise DocumentaryError("invalid_handle_intents") from error


def glass_polishing(value: object) -> list[GlassPolishingAuthorityV1]:
    raw = decoded(value)
    if not isinstance(raw, list):
        raise DocumentaryError("invalid_glass_polishing")
    try:
        result = []
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("edges"), dict):
                raise DocumentaryError("invalid_glass_polishing")
            edges = item["edges"]
            if set(edges) != {"top", "right", "bottom", "left"} or not all(
                isinstance(edges[key], bool) for key in edges
            ):
                raise DocumentaryError("invalid_glass_polishing")
            result.append(GlassPolishingAuthorityV1(
                schema_version=int(item.get("schema_version", 1)),
                bay_id=str(item["bay_id"]),
                leaf_id=None if item.get("leaf_id") is None else str(item["leaf_id"]),
                edges=EdgePolishingV1(
                    top=edges["top"], right=edges["right"],
                    bottom=edges["bottom"], left=edges["left"],
                ),
            ))
        return result
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, DocumentaryError):
            raise
        raise DocumentaryError("invalid_glass_polishing") from error


def accessory_schedule(value: object, schedule_id: str) -> AccessoryScheduleV1:
    raw = decoded(value)
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise DocumentaryError("invalid_accessory_schedule")
    try:
        if not all(isinstance(item, dict) for item in raw["items"]):
            raise DocumentaryError("invalid_accessory_schedule")
        items = [AccessoryLineV1(
            obligation_id=str(item["obligation_id"]),
            obligation_kind=item["obligation_kind"],
            technical_sku=str(item["technical_sku"]),
            purchasing_sku=str(item["purchasing_sku"]),
            manufacturer_name=str(item["manufacturer_name"]),
            order_type=SupplierOrderType(str(item["order_type"])),
            unit="EA",
            quantity_per_position_unit=int(item["quantity_per_position_unit"]),
            description=str(item["description"]),
        ) for item in raw["items"]]
        return AccessoryScheduleV1(
            schema_version=int(raw.get("schema_version", 1)), schedule_id=schedule_id,
            coverage=raw["coverage"], items=items,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DocumentaryError("invalid_accessory_schedule") from error


def _cutting_profile(row: dict[str, object]) -> CuttingProfile:
    return CuttingProfile(
        id=str(row["cutting_profile_id"]), code=str(row["cutting_profile_code"]),
        kerf_mm=_decimal(row["kerf_mm"]), head_trim_mm=_decimal(row["head_trim_mm"]),
        tail_trim_mm=_decimal(row["tail_trim_mm"]),
    )


def _stock_binding(
    row: dict[str, object], source_kind: PhysicalSourceKind
) -> PhysicalStockBindingV1:
    required = ("physical_stock_identity", "stock_color", "cutting_profile_id", "binding_version")
    if any(row[name] is None for name in required):
        raise DocumentaryError("physical_stock_binding_required")
    return PhysicalStockBindingV1(
        binding_id=str(row["binding_id"]), binding_version=int(row["binding_version"]),
        system_id=str(row["system_id"]), source_kind=source_kind,
        workshop_sku=str(row["workshop_sku"]),
        purchasing_sku=str(row["purchasing_sku"]),
        physical_stock_identity=str(row["physical_stock_identity"]),
        manufacturer_name=str(row["manufacturer_name"]),
        material=CutMaterial(str(row["material"])), color=str(row["stock_color"]),
        stock_length_mm=_decimal(row["stock_length_mm"]),
        cutting_profile=_cutting_profile(row),
    )


def _effective_one(values: list[dict[str, object]], org_id: UUID, code: str) -> dict[str, object]:
    effective = effective_scope(values, org_id)
    if len(effective) != 1:
        raise DocumentaryError(code)
    return effective[0]


def load_purchase_authorities(
    *, system_id: UUID, org_id: UUID, color: str,
    profile_skus: set[str], reinforcement_skus: set[str], glass_skus: set[str],
    hardware_skus: set[str], panel_skus: set[str], fitting_skus: set[str],
) -> PurchaseAuthorities:
    def _by_sku(result: list[dict[str, object]], key: str) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for item in result:
            grouped.setdefault(str(item[key]), []).append(item)
        return grouped

    stocks: list[PhysicalStockBindingV1] = []
    # One query per SKU family — the per-SKU loops multiplied round-trips by
    # distinct SKUs in every DOC pack generation.
    if profile_skus:
        grouped = _by_sku(
            rows(
                "SELECT mapping.id AS binding_id,mapping.commercial_sku AS purchasing_sku,"
                "mapping.manufacturer_name,mapping.physical_stock_identity,mapping.stock_color,"
                "mapping.cutting_profile_id,mapping.binding_version,mapping.org_id,"
                "article.system_id,article.sku AS workshop_sku,article.material::text AS material,"
                "article.commercial_length_mm AS stock_length_mm,profile.code AS cutting_profile_code,"
                "profile.kerf_mm,profile.head_trim_mm,profile.tail_trim_mm "
                "FROM public.profile_purchase_mappings mapping "
                "JOIN public.profile_articles article ON article.id=mapping.profile_article_id "
                "JOIN public.cutting_profiles profile ON profile.id=mapping.cutting_profile_id "
                "WHERE article.system_id=%s AND article.sku = ANY(%s) AND mapping.is_active "
                "AND (mapping.org_id IS NULL OR mapping.org_id=%s)",
                [system_id, sorted(profile_skus), org_id],
            ),
            "workshop_sku",
        )
        for sku_value in sorted(profile_skus):
            row = _effective_one(
                grouped.get(sku_value, []), org_id,
                "profile_stock_binding_missing_or_ambiguous",
            )
            binding = _stock_binding(row, PhysicalSourceKind.PROFILE)
            if binding.color != color:
                raise DocumentaryError("physical_stock_color_mismatch")
            stocks.append(binding)
    if reinforcement_skus:
        grouped = _by_sku(
            rows(
                "SELECT reinforcement.id AS binding_id,reinforcement.commercial_sku AS purchasing_sku,"
                "reinforcement.manufacturer_name,reinforcement.physical_stock_identity,"
                "reinforcement.stock_color,reinforcement.cutting_profile_id,"
                "reinforcement.binding_version,reinforcement.org_id,reinforcement.system_id,"
                "reinforcement.sku AS workshop_sku,'STEEL' AS material,"
                "reinforcement.stock_length_mm,profile.code AS cutting_profile_code,"
                "profile.kerf_mm,profile.head_trim_mm,profile.tail_trim_mm "
                "FROM public.reinforcement_articles reinforcement "
                "JOIN public.cutting_profiles profile ON profile.id=reinforcement.cutting_profile_id "
                "WHERE reinforcement.system_id=%s AND reinforcement.sku = ANY(%s) "
                "AND reinforcement.is_active AND (reinforcement.org_id IS NULL OR reinforcement.org_id=%s)",
                [system_id, sorted(reinforcement_skus), org_id],
            ),
            "workshop_sku",
        )
        for sku_value in sorted(reinforcement_skus):
            row = _effective_one(
                grouped.get(sku_value, []), org_id,
                "reinforcement_stock_binding_missing_or_ambiguous",
            )
            binding = _stock_binding(row, PhysicalSourceKind.REINFORCEMENT)
            if binding.color != color:
                raise DocumentaryError("physical_stock_color_mismatch")
            stocks.append(binding)

    glasses = []
    if glass_skus:
        grouped = _by_sku(
            rows(
                "SELECT id,version,technical_sku,purchasing_sku,manufacturer_name,"
                "purchase_unit,provenance::text,org_id FROM public.glass_purchase_mappings "
                "WHERE system_id=%s AND technical_sku = ANY(%s) "
                "AND (org_id IS NULL OR org_id=%s)",
                [system_id, sorted(glass_skus), org_id],
            ),
            "technical_sku",
        )
        for sku_value in sorted(glass_skus):
            row = _effective_one(
                grouped.get(sku_value, []), org_id,
                "glass_purchase_mapping_missing_or_ambiguous",
            )
            provenance = decoded(row["provenance"])
            if not isinstance(provenance, dict) or not all(
                isinstance(key, str) and isinstance(item, str) for key, item in provenance.items()
            ):
                raise DocumentaryError("invalid_glass_purchase_provenance")
            glasses.append(GlassPurchaseMappingV1(
                authority_id=str(row["id"]), version=int(row["version"]),
                system_id=str(system_id), technical_sku=str(row["technical_sku"]),
                purchasing_sku=str(row["purchasing_sku"]),
                manufacturer_name=str(row["manufacturer_name"]), purchase_unit="EA",
                provenance=provenance,
            ))

    hardware = []
    if hardware_skus:
        grouped = _by_sku(
            rows(
                "SELECT mapping.id,mapping.version,kit.sku AS technical_kit_sku,"
                "mapping.purchasing_sku,mapping.manufacturer_name,mapping.purchase_unit,"
                "mapping.provenance::text,mapping.org_id FROM public.hardware_purchase_mappings mapping "
                "JOIN public.hardware_kits kit ON kit.id=mapping.hardware_kit_id "
                "WHERE kit.system_id=%s AND kit.sku = ANY(%s) AND (mapping.org_id IS NULL OR mapping.org_id=%s)",
                [system_id, sorted(hardware_skus), org_id],
            ),
            "technical_kit_sku",
        )
        for sku_value in sorted(hardware_skus):
            row = _effective_one(
                grouped.get(sku_value, []), org_id,
                "hardware_purchase_mapping_missing_or_ambiguous",
            )
            provenance = decoded(row["provenance"])
            if not isinstance(provenance, dict) or not all(
                isinstance(key, str) and isinstance(item, str) for key, item in provenance.items()
            ):
                raise DocumentaryError("invalid_hardware_purchase_provenance")
            hardware.append(HardwarePurchaseMappingV1(
                authority_id=str(row["id"]), version=int(row["version"]),
                system_id=str(system_id), technical_kit_sku=str(row["technical_kit_sku"]),
                purchasing_sku=str(row["purchasing_sku"]),
                manufacturer_name=str(row["manufacturer_name"]), purchase_unit="KIT",
                provenance=provenance,
            ))

    panels = []
    if panel_skus:
        grouped = _by_sku(
            rows(
                "SELECT authority.id,authority.version,panel.sku AS technical_sku,"
                "authority.purchasing_sku,authority.manufacturer_name,authority.supply_form,"
                "authority.purchase_unit,authority.provenance::text,authority.org_id "
                "FROM public.panel_purchase_authorities authority "
                "JOIN public.infill_articles panel ON panel.id=authority.infill_article_id "
                "WHERE panel.system_id=%s AND panel.sku = ANY(%s) "
                "AND (authority.org_id IS NULL OR authority.org_id=%s)",
                [system_id, sorted(panel_skus), org_id],
            ),
            "technical_sku",
        )
        for sku_value in sorted(panel_skus):
            row = _effective_one(
                grouped.get(sku_value, []), org_id,
                "panel_purchase_authority_missing_or_ambiguous",
            )
            provenance = decoded(row["provenance"])
            if not isinstance(provenance, dict) or not all(
                isinstance(key, str) and isinstance(item, str) for key, item in provenance.items()
            ):
                raise DocumentaryError("invalid_panel_purchase_provenance")
            panels.append(PanelPurchaseAuthorityV1(
                authority_id=str(row["id"]), version=int(row["version"]),
                system_id=str(system_id), technical_sku=str(row["technical_sku"]),
                purchasing_sku=str(row["purchasing_sku"]),
                manufacturer_name=str(row["manufacturer_name"]), supply_form="CUT_TO_SIZE",
                purchase_unit="EA", provenance=provenance,
            ))
    fittings = []
    if fitting_skus:
        grouped = _by_sku(
            rows(
                "SELECT id,version,technical_sku,purchasing_sku,manufacturer_name,"
                "purchase_unit,provenance::text,org_id FROM public.fitting_purchase_mappings "
                "WHERE system_id=%s AND technical_sku = ANY(%s) AND (org_id IS NULL OR org_id=%s)",
                [system_id, sorted(fitting_skus), org_id],
            ),
            "technical_sku",
        )
        for sku_value in sorted(fitting_skus):
            row = _effective_one(
                grouped.get(sku_value, []), org_id,
                "fitting_purchase_mapping_missing_or_ambiguous",
            )
            provenance = decoded(row["provenance"])
            if not isinstance(provenance, dict) or not all(
                isinstance(key, str) and isinstance(item, str) for key, item in provenance.items()
            ):
                raise DocumentaryError("invalid_fitting_purchase_provenance")
            fittings.append(FittingPurchaseMappingV1(
                authority_id=str(row["id"]), version=int(row["version"]),
                system_id=str(system_id), technical_sku=str(row["technical_sku"]),
                purchasing_sku=str(row["purchasing_sku"]),
                manufacturer_name=str(row["manufacturer_name"]), purchase_unit="EA",
                provenance=provenance,
            ))
    return PurchaseAuthorities(stocks, glasses, hardware, panels, fittings)
