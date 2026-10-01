"""RLS-bound DB-to-engine parameter loader; it contains no geometry formulas."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
import json
from typing import cast
from uuid import UUID

from django.db import connection

from dekopen_engine import (
    EffectiveProfileArticle,
    GlazingBeadRule,
    ProfileSection,
    HardwareKitRule,
    HardwareComponent,
    PanelRule,
    MaterialType,
    ProfileRole,
    RailType,
    SystemParams,
)
from dekopen_engine.manufacturing import HandleRequirementPolicyV1, handle_policy_from_json


class SystemNotFound(LookupError):
    pass


class UnsupportedCatalogContract(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VisibleProfileSystem:
    id: UUID
    code: str
    name: str
    is_demo: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "is_demo": self.is_demo,
        }


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
        raise UnsupportedCatalogContract("Catalog numbers must be exact decimals")
    result = Decimal(value)
    if not result.is_finite():
        raise UnsupportedCatalogContract("Catalog numbers must be finite")
    return result


def _decimal_or_none(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)


def _section(value: object) -> ProfileSection | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise UnsupportedCatalogContract("Section must be raw JSON text")
    return ProfileSection.model_validate(
        json.loads(value, parse_float=Decimal, parse_int=Decimal)
    )


def _article_from_row(row: Sequence[object], *, offset: int = 0) -> EffectiveProfileArticle:
    return EffectiveProfileArticle(
        sku=str(row[offset]),
        role=ProfileRole(str(row[offset + 1])),
        material=MaterialType(str(row[offset + 8])),
        face_width_mm=_decimal(row[offset + 2]),
        section=_section(row[offset + 9]),
        # NULL is UNKNOWN — welding/reinforcement/weight data the catalog does
        # not carry passes through so the honest consumers can refuse or flag.
        welding_loss_mm=_decimal_or_none(row[offset + 3]),
        reinforcement_gap_mm=_decimal_or_none(row[offset + 4]),
        weight_kg_m=_decimal_or_none(row[offset + 5]),
        steel_weight_kg_m=_decimal_or_none(row[offset + 6]),
        reinforcement_sku=(str(row[offset + 7]) if row[offset + 7] is not None else None),
        commercial_length_mm=_decimal_or_none(row[offset + 10]),
    )


def _hardware_contents(value: object) -> list[HardwareComponent]:
    # SELECT contents::text avoids driver JSON decoding through binary floats.
    if not isinstance(value, str):
        raise UnsupportedCatalogContract("Hardware contents must be raw JSON text")
    raw = json.loads(value, parse_float=Decimal, parse_int=Decimal)
    if not isinstance(raw, list):
        raise UnsupportedCatalogContract("Hardware contents must be an array")
    return [HardwareComponent.model_validate(component) for component in raw]


class SystemParamsRepository:
    def list_visible(self, active_org_id: UUID) -> tuple[VisibleProfileSystem, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, code, name, is_demo
                FROM public.profile_systems
                WHERE is_active = TRUE
                  AND (is_global = TRUE OR org_id = %s)
                ORDER BY is_demo DESC, code ASC, id ASC
                """,
                [active_org_id],
            )
            rows: Sequence[tuple[object, object, object, object]] = cursor.fetchall()
        return tuple(
            VisibleProfileSystem(
                id=row[0] if isinstance(row[0], UUID) else UUID(str(row[0])),
                code=str(row[1]),
                name=str(row[2]),
                is_demo=bool(row[3]),
            )
            for row in rows
        )

    def load_visible(self, system_id: UUID, active_org_id: UUID) -> SystemParams:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT code, depth_mm, material::text, sash_overlap_mm,
                       glass_clearance_white_mm, glass_clearance_foil_mm,
                       pulley_height_mm, central_overlap_mm,
                       sliding_lateral_clearance_mm, sliding_end_add_mm,
                       corner_bracket_loss_mm, hook_depth_mm,
                       door_threshold_mm, door_bottom_clearance_mm, rail_type,
                       sliding_glazing_deduction_width_mm,
                       sliding_glazing_deduction_height_mm, door_leaf_side_clearance_mm,
                       rail_count, rebate_depth_mm, end_milling_overlap_mm,
                       finishes::text
                FROM public.profile_systems
                WHERE id = %s AND is_active = TRUE
                  AND (is_global = TRUE OR org_id = %s)
                """,
                [system_id, active_org_id],
            )
            system = cursor.fetchone()
        if system is None:
            raise SystemNotFound

        articles = self._load_articles(system_id, active_org_id)
        rules = self._load_glazing_rules(system_id, active_org_id)
        kits = self._load_hardware_kits(system_id, active_org_id)
        frame = articles.get(ProfileRole.FRAME)
        if frame is None:
            raise UnsupportedCatalogContract("FRAME effective article is required")

        return SystemParams(
            system_code=str(system[0]),
            depth_mm=_decimal(system[1]),
            material=MaterialType(str(system[2])),
            effective_profile_articles=articles,
            glazing_bead_rules=rules,
            sash_overlap_mm=_decimal(system[3]),
            glass_clearance_white_mm=_decimal(system[4]),
            glass_clearance_foil_mm=_decimal(system[5]),
            pulley_height_mm=_decimal(system[6]),
            central_overlap_mm=_decimal(system[7]),
            sliding_lateral_clearance_mm=_decimal(system[8]),
            sliding_end_add_mm=_decimal(system[9]),
            corner_bracket_loss_mm=_decimal(system[10]),
            hook_depth_mm=_decimal(system[11]),
            door_threshold_mm=_decimal(system[12]),
            door_bottom_clearance_mm=_decimal(system[13]),
            rail_type=RailType(str(system[14])),
            sliding_glazing_deduction_width_mm=_decimal(system[15]),
            sliding_glazing_deduction_height_mm=_decimal(system[16]),
            door_leaf_side_clearance_mm=_decimal(system[17]),
            rail_count=None if system[18] is None else int(system[18]),
            rebate_depth_mm=_decimal_or_none(system[19]),
            end_milling_overlap_mm=_decimal_or_none(system[20]),
            finishes=tuple(json.loads(system[21])) if system[21] else ("WHITE",),
            available_panel_rules=self._load_panel_rules(system_id, active_org_id),
            available_hardware_kits=kits,
        )

    def _load_articles(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[ProfileRole, EffectiveProfileArticle]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT sku, role::text, face_width_mm, welding_loss_mm,
                       reinforcement_gap_mm, weight_kg_m, steel_weight_kg_m,
                       reinforcement_sku, material::text, section::text,
                       commercial_length_mm
                FROM public.profile_articles
                WHERE system_id = %s AND (org_id = %s OR (org_id IS NULL AND system_id IN (SELECT id FROM public.profile_systems WHERE org_id IS NULL AND is_global)))
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        result: dict[ProfileRole, EffectiveProfileArticle] = {}
        for row in rows:
            article = _article_from_row(row)
            # GLAZING_BEAD resolves per glass thickness; COUPLER is multi-valued
            # per system (assemblies pick any catalog SKU via load_coupler_articles).
            if article.role in (ProfileRole.GLAZING_BEAD, ProfileRole.COUPLER):
                continue
            if article.role in result:
                raise UnsupportedCatalogContract(
                    f"Multiple effective articles for role {article.role.value}"
                )
            result[article.role] = article
        return result

    def load_coupler_articles(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[str, EffectiveProfileArticle]:
        """All catalog coupler profiles for a system, keyed by SKU.

        Unlike effective articles (one per role), an assembly may reference
        any coupler SKU the catalog offers for that system.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT sku, role::text, face_width_mm, welding_loss_mm,
                       reinforcement_gap_mm, weight_kg_m, steel_weight_kg_m,
                       reinforcement_sku, material::text, section::text,
                       commercial_length_mm
                FROM public.profile_articles
                WHERE system_id = %s AND (org_id = %s OR (org_id IS NULL AND system_id IN (SELECT id FROM public.profile_systems WHERE org_id IS NULL AND is_global)))
                  AND role = 'COUPLER'
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        return {cast(str, row[0]): _article_from_row(row) for row in rows}

    def load_article_names(self, system_id: UUID, active_org_id: UUID) -> dict[str, str]:
        """Display names for every catalog profile article of a system.

        Names are presentation metadata, not engineering parameters, so they
        live outside EffectiveProfileArticle; options/design surfaces join
        them by SKU.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT sku, name
                FROM public.profile_articles
                WHERE system_id = %s AND (org_id = %s OR (org_id IS NULL AND system_id IN (SELECT id FROM public.profile_systems WHERE org_id IS NULL AND is_global)))
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def _load_glazing_rules(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[Decimal, GlazingBeadRule]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT matrix.glass_thickness_mm, matrix.bead_width_mm,
                       matrix.gasket_interior_mm, matrix.gasket_exterior_mm,
                       matrix.cut_add_mm,
                       article.sku, article.role::text, article.face_width_mm,
                       article.welding_loss_mm, article.reinforcement_gap_mm,
                       article.weight_kg_m, article.steel_weight_kg_m,
                       article.reinforcement_sku, article.material::text,
                       article.section::text, article.commercial_length_mm
                FROM public.glazing_bead_matrix AS matrix
                JOIN public.profile_articles AS article
                  ON article.id = matrix.bead_article_id
                WHERE matrix.system_id = %s AND matrix.is_active = TRUE
                  AND (matrix.org_id = %s OR (matrix.org_id IS NULL AND matrix.system_id IN (SELECT id FROM public.profile_systems WHERE org_id IS NULL AND is_global)))
                  AND article.system_id = matrix.system_id
                  AND (article.org_id = %s OR (article.org_id IS NULL AND article.system_id IN (SELECT id FROM public.profile_systems WHERE org_id IS NULL AND is_global)))
                ORDER BY matrix.glass_thickness_mm
                """,
                [system_id, active_org_id, active_org_id],
            )
            rows = cursor.fetchall()
        return {
            _decimal(row[0]): GlazingBeadRule(
                glass_thickness_mm=_decimal(row[0]),
                bead_article=_article_from_row(row, offset=5),
                bead_width_mm=_decimal(row[1]),
                gasket_interior_mm=_decimal(row[2]),
                gasket_exterior_mm=_decimal(row[3]),
                cut_add_mm=_decimal(row[4]),
            )
            for row in rows
        }

    def load_handle_policy(
        self, system_id: UUID, active_org_id: UUID
    ) -> HandleRequirementPolicyV1 | None:
        """Latest declared handle-mounting authority for the system — the org
        row wins over the global default, then the highest version. The design
        surface reads it to place handles on the declared datum instead of
        silently clamping inside the leaf."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT authority::text
                FROM public.handle_requirement_policies
                WHERE system_id = %s AND (org_id = %s OR org_id IS NULL)
                ORDER BY org_id NULLS LAST, version DESC
                LIMIT 1
                """,
                [system_id, active_org_id],
            )
            row = cursor.fetchone()
        if row is None:
            return None
        if not isinstance(row[0], str):
            raise UnsupportedCatalogContract("Handle policy must be raw JSON text")
        try:
            return handle_policy_from_json(
                json.loads(row[0], parse_float=Decimal, parse_int=Decimal)
            )
        except (ValueError, TypeError) as error:
            raise UnsupportedCatalogContract("invalid_handle_policy") from error

    def _load_hardware_kits(self, system_id: UUID, active_org_id: UUID) -> list[HardwareKitRule]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT sku, name, opening_type, min_leaf_width_mm,
                       max_leaf_width_mm, min_leaf_height_mm, max_leaf_height_mm,
                       max_leaf_weight_kg, rail_type, carriages_qty,
                       stay_arms_qty, contents::text, weight_kg, carriage_capacity_kg
                FROM public.hardware_kits
                WHERE system_id = %s AND is_active = TRUE
                  AND (org_id = %s OR (org_id IS NULL AND system_id IN (SELECT id FROM public.profile_systems WHERE org_id IS NULL AND is_global)))
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        return [
            HardwareKitRule(
                sku=str(row[0]),
                name=str(row[1]),
                opening_type=str(row[2]),
                min_leaf_width_mm=_decimal(row[3]),
                max_leaf_width_mm=_decimal(row[4]),
                min_leaf_height_mm=_decimal(row[5]),
                max_leaf_height_mm=_decimal(row[6]),
                max_leaf_weight_kg=_decimal(row[7]),
                rail_type=RailType(str(row[8])),
                carriages_qty=int(cast(int, row[9])),
                stay_arms_qty=int(cast(int, row[10])),
                contents=_hardware_contents(row[11]),
                weight_kg=_decimal(row[12]) if row[12] is not None else None,
                carriage_capacity_kg=_decimal(row[13]) if row[13] is not None else None,
            )
            for row in rows
        ]

    def _load_panel_rules(self, system_id: UUID, active_org_id: UUID) -> dict[str, PanelRule]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT sku, name, kind, thickness_mm, weight_kg_m2
                FROM public.infill_articles
                WHERE system_id = %s AND is_active = TRUE
                  AND (org_id = %s OR (org_id IS NULL AND system_id IN (SELECT id FROM public.profile_systems WHERE org_id IS NULL AND is_global)))
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        return {
            str(row[0]): PanelRule(
                sku=str(row[0]),
                name=str(row[1]),
                kind=row[2],
                thickness_mm=_decimal(row[3]),
                weight_kg_m2=_decimal(row[4]) if row[4] is not None else None,
            )
            for row in rows
        }
