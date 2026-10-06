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
    HandleColorOption,
    HandleModelOption,
    HardwareFamily,
    HardwareOption,
    HardwareOptionKind,
    ProfileSection,
    HardwareKitRule,
    HardwareComponent,
    PanelRule,
    MaterialType,
    ProfileCutRule,
    ProfileRole,
    RailType,
    ReinforcementRule,
    SystemFamily,
    SystemParams,
    TypologyLimit,
    default_capabilities_for_family,
    openings_for_family,
    spec_options_from_capabilities,
)
from dekopen_engine.models import (
    ColorKind,
    ColorOption,
    ColorSurcharge,
    ExtraArticle,
    ExtraKind,
    ExtraPricingUnit,
    LeafRole,
    OpeningCapability,
    OpeningDirection,
    OpeningMovement,
    UnitKind,
)
from dekopen_engine.glass_composition import (
    GlassComposition,
    composition_from_dict,
)
from dekopen_engine.models import (
    GlassProduct,
    GlassSafetyRule,
    GlassSurchargeRate,
    GlassTypeLimit,
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
    system_family: SystemFamily
    typology_limits: tuple[dict[str, object], ...] = ()
    opening_capabilities: tuple[OpeningCapability, ...] = ()

    def public_dict(self) -> dict[str, object]:
        # The declared capability rows narrow the family's physical
        # repertoire (D03); an empty table falls back to the family.
        capabilities = (
            self.opening_capabilities
            or default_capabilities_for_family(self.system_family)
        )
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "is_demo": self.is_demo,
            "system_family": self.system_family.value,
            # The editor only offers typologies the family can cut.
            "allowed_openings": sorted(
                opening.value for opening in openings_for_family(self.system_family)
            ),
            # Declared leaf envelope per typology with its provenance — the
            # editor and quotation show it next to the chosen system.
            "typology_limits": list(self.typology_limits),
            # The concrete compositions the system admits — the editor,
            # the API and the IA only offer these (D03).
            "opening_options": spec_options_from_capabilities(capabilities),
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


def _glass_composition(raw: object) -> GlassComposition | None:
    """Stored composition JSONB → engine model. An unparsable payload keeps
    ``None`` (UNKNOWN product — never a fabricated stack)."""
    if raw is None:
        return None
    try:
        payload = raw if isinstance(raw, dict) else json.loads(str(raw))
        return composition_from_dict(payload)
    except (ValueError, TypeError, KeyError):
        return None


def _section(value: object) -> ProfileSection | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise UnsupportedCatalogContract("Section must be raw JSON text")
    return ProfileSection.model_validate(
        json.loads(value, parse_float=Decimal, parse_int=Decimal)
    )


def _article_from_row(
    row: Sequence[object],
    *,
    offset: int = 0,
    coupler_angle_min_deg: object = None,
    coupler_angle_max_deg: object = None,
) -> EffectiveProfileArticle:
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
        # P06 — declared deflection envelope over |angle_deg|; only the
        # coupler loader reads these columns, other loaders leave them NULL.
        coupler_angle_min_deg=_decimal_or_none(coupler_angle_min_deg),
        coupler_angle_max_deg=_decimal_or_none(coupler_angle_max_deg),
    )


def _capability_from_row(
    row: Sequence[object], *, offset: int = 0
) -> OpeningCapability:
    return OpeningCapability(
        movement=OpeningMovement(str(row[offset])),
        directions=tuple(
            OpeningDirection(value) for value in row[offset + 1] or ()
        ),
        leaf_roles=tuple(LeafRole(value) for value in row[offset + 2] or ()),
        unit_kinds=tuple(UnitKind(value) for value in row[offset + 3] or ()),
        max_leaves=int(row[offset + 4]),
        fixed_in_sash=bool(row[offset + 5]),
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
                SELECT id, code, name, is_demo, system_family
                FROM public.profile_systems
                WHERE is_active = TRUE
                  AND (is_global = TRUE OR org_id = %s)
                ORDER BY is_demo DESC, code ASC, id ASC
                """,
                [active_org_id],
            )
            rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT system_id, opening_type, min_leaf_width_mm,
                       max_leaf_width_mm, min_leaf_height_mm,
                       max_leaf_height_mm, max_leaf_weight_kg,
                       max_aspect_ratio, data_provenance
                FROM public.system_typology_limits
                WHERE org_id IS NULL OR org_id = %s
                ORDER BY opening_type
                """,
                [active_org_id],
            )
            limit_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT system_id, movement, directions, leaf_roles,
                       unit_kinds, max_leaves, fixed_in_sash
                FROM public.system_opening_capabilities
                WHERE org_id IS NULL OR org_id = %s
                ORDER BY system_id, movement
                """,
                [active_org_id],
            )
            capability_rows = cursor.fetchall()
        capabilities_by_system: dict[str, list[OpeningCapability]] = {}
        for row in capability_rows:
            capabilities_by_system.setdefault(str(row[0]), []).append(
                _capability_from_row(row, offset=1)
            )
        limits_by_system: dict[str, list[dict[str, object]]] = {}
        for row in limit_rows:
            limits_by_system.setdefault(str(row[0]), []).append({
                "opening_type": str(row[1]),
                "min_leaf_width_mm": None if row[2] is None else str(row[2]),
                "max_leaf_width_mm": None if row[3] is None else str(row[3]),
                "min_leaf_height_mm": None if row[4] is None else str(row[4]),
                "max_leaf_height_mm": None if row[5] is None else str(row[5]),
                "max_leaf_weight_kg": None if row[6] is None else str(row[6]),
                "max_aspect_ratio": None if row[7] is None else str(row[7]),
                "source": str(row[8]),
            })
        return tuple(
            VisibleProfileSystem(
                id=row[0] if isinstance(row[0], UUID) else UUID(str(row[0])),
                code=str(row[1]),
                name=str(row[2]),
                is_demo=bool(row[3]),
                system_family=SystemFamily(str(row[4])),
                typology_limits=tuple(
                    limits_by_system.get(str(row[0]), [])
                ),
                opening_capabilities=tuple(
                    capabilities_by_system.get(str(row[0]), [])
                ),
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
                       finishes::text, system_family, bicolor_allowed
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
            system_family=SystemFamily(str(system[22])),
            cut_rules=self._load_cut_rules(system_id, active_org_id),
            reinforcement_rules=self._load_reinforcement_rules(system_id, active_org_id),
            typology_limits=self._load_typology_limits(system_id, active_org_id),
            glass_products=self._load_glass_products(system_id, active_org_id),
            glass_safety_rules=self._load_glass_safety_rules(active_org_id),
            glass_type_limits=self._load_glass_type_limits(active_org_id),
            hardware_families=self._load_hardware_families(system_id, active_org_id),
            hardware_options=self._load_hardware_options(system_id, active_org_id),
            opening_capabilities=self._load_opening_capabilities(
                system_id, active_org_id
            ),
            color_options=self._load_color_options(system_id, active_org_id),
            bicolor_allowed=bool(system[23]),
            extra_articles=self._load_extra_articles(system_id, active_org_id),
        )

    def _load_color_options(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[str, ColorOption]:
        """The declared per-system color catalog (D05). An empty map keeps
        the legacy binary WHITE/FOILED semantics at the engine layer."""
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT code, name, kind, manufacturer_code, gloss,
                       render_color, render_texture, finish_class,
                       film_clearance, glass_clearance_mm, dark, faces,
                       pair_code, size_factor, surcharge_kind,
                       surcharge_amount, surcharge_currency, surcharge_label,
                       sort_order, data_provenance
                FROM public.system_color_options
                WHERE {self._SCOPE_SQL}
                ORDER BY sort_order, code
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        options: dict[str, ColorOption] = {}
        for row in rows:
            surcharge = None
            if row[14] is not None and row[15] is not None:
                surcharge = ColorSurcharge(
                    kind=cast(str, row[14]),
                    amount=_decimal(row[15]),
                    currency=None if row[16] is None else str(row[16]),
                    label=None if row[17] is None else str(row[17]),
                )
            options[str(row[0])] = ColorOption(
                code=str(row[0]),
                name=str(row[1]),
                kind=ColorKind(str(row[2])),
                manufacturer_code=None if row[3] is None else str(row[3]),
                gloss=None if row[4] is None else str(row[4]),
                render_color=None if row[5] is None else str(row[5]),
                render_texture=None if row[6] is None else str(row[6]),
                finish_class=cast(str, row[7]),
                film_clearance=bool(row[8]),
                glass_clearance_mm=_decimal_or_none(row[9]),
                dark=bool(row[10]),
                faces=cast(str, row[11]),
                pair_code=None if row[12] is None else str(row[12]),
                size_factor=_decimal_or_none(row[13]),
                surcharge=surcharge,
                sort_order=int(row[18]),
                data_provenance=None if row[19] is None else str(row[19]),
            )
        return options

    def _load_opening_capabilities(
        self, system_id: UUID, active_org_id: UUID
    ) -> tuple[OpeningCapability, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT movement, directions, leaf_roles, unit_kinds,
                       max_leaves, fixed_in_sash
                FROM public.system_opening_capabilities
                WHERE {self._SCOPE_SQL}
                ORDER BY movement
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        return tuple(_capability_from_row(row) for row in rows)

    _SCOPE_SQL = (
        "system_id = %s AND (org_id = %s OR (org_id IS NULL AND system_id IN "
        "(SELECT id FROM public.profile_systems WHERE org_id IS NULL AND is_global)))"
    )

    def _load_cut_rules(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[ProfileRole, ProfileCutRule]:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT role::text, cut_angle_deg, welded_ends,
                       interlock_deduction_mm, rounding_mm, reinforcement_sku
                FROM public.profile_cut_rules
                WHERE {self._SCOPE_SQL}
                ORDER BY role
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        return {
            ProfileRole(str(row[0])): ProfileCutRule(
                role=ProfileRole(str(row[0])),
                cut_angle_deg=_decimal(row[1]),
                welded_ends=None if row[2] is None else int(row[2]),
                interlock_deduction_mm=_decimal(row[3]),
                rounding_mm=_decimal(row[4]),
                reinforcement_sku=str(row[5]) if row[5] is not None else None,
            )
            for row in rows
        }

    def _load_reinforcement_rules(
        self, system_id: UUID, active_org_id: UUID
    ) -> list[ReinforcementRule]:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT role::text, finish_class, min_length_mm, mandatory,
                       reinforcement_sku, cut_deduction_mm,
                       screws_per_m, screw_sku
                FROM public.profile_reinforcement_rules
                WHERE {self._SCOPE_SQL}
                ORDER BY role, finish_class, min_length_mm
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        return [
            ReinforcementRule(
                role=ProfileRole(str(row[0])),
                finish_class=cast(str, row[1]),
                min_length_mm=_decimal(row[2]),
                mandatory=bool(row[3]),
                reinforcement_sku=str(row[4]) if row[4] is not None else None,
                cut_deduction_mm=_decimal(row[5]),
                screws_per_m=_decimal_or_none(row[6]),
                screw_sku=str(row[7]) if row[7] is not None else None,
            )
            for row in rows
        ]

    def _load_typology_limits(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[str, TypologyLimit]:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT opening_type, min_leaf_width_mm, max_leaf_width_mm,
                       min_leaf_height_mm, max_leaf_height_mm,
                       max_leaf_weight_kg, max_aspect_ratio
                FROM public.system_typology_limits
                WHERE {self._SCOPE_SQL}
                ORDER BY opening_type
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        return {
            str(row[0]): TypologyLimit(
                opening_type=str(row[0]),
                min_leaf_width_mm=_decimal_or_none(row[1]),
                max_leaf_width_mm=_decimal_or_none(row[2]),
                min_leaf_height_mm=_decimal_or_none(row[3]),
                max_leaf_height_mm=_decimal_or_none(row[4]),
                max_leaf_weight_kg=_decimal_or_none(row[5]),
                max_aspect_ratio=_decimal_or_none(row[6]),
            )
            for row in rows
        }

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
                       commercial_length_mm, coupler_angle_min_deg,
                       coupler_angle_max_deg
                FROM public.profile_articles
                WHERE system_id = %s AND (org_id = %s OR (org_id IS NULL AND system_id IN (SELECT id FROM public.profile_systems WHERE org_id IS NULL AND is_global)))
                  AND role = 'COUPLER'
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        return {
            cast(str, row[0]): _article_from_row(
                row, coupler_angle_min_deg=row[11], coupler_angle_max_deg=row[12]
            )
            for row in rows
        }

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
                       stay_arms_qty, contents::text, weight_kg, carriage_capacity_kg,
                       class_label, max_aspect_ratio, min_stay_height_mm
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
                class_label=cast(str, row[14]) if row[14] is not None else None,
                max_aspect_ratio=_decimal(row[15]) if row[15] is not None else None,
                min_stay_height_mm=_decimal(row[16]) if row[16] is not None else None,
            )
            for row in rows
        ]

    def _load_glass_products(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[str, GlassProduct]:
        """Glass products visible to the org for this system: org-scoped rows
        beat global ones and system-scoped rows beat cross-system ones for
        the same SKU (DISTINCT ON + NULLS LAST, the purchase-mapping
        resolution)."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (p.sku)
                       p.sku, p.commercial_name, p.composition::text,
                       p.safety_class, p.ug_w_m2k::text, p.g_value::text,
                       p.light_transmission_pct::text, p.weight_kg_m2::text,
                       p.min_billable_area_m2::text, p.review_pending, p.id,
                       p.price_tier
                FROM public.glass_products p
                WHERE p.is_active = TRUE
                  AND (p.org_id = %s OR p.org_id IS NULL)
                  AND (p.system_id = %s OR p.system_id IS NULL)
                ORDER BY p.sku, p.org_id NULLS LAST, p.system_id NULLS LAST
                """,
                [active_org_id, system_id],
            )
            product_rows = cursor.fetchall()
            if not product_rows:
                return {}
            cursor.execute(
                """
                SELECT s.product_id::text, s.kind, s.unit, s.unit_cost::text,
                       s.label, s.currency::text
                FROM public.glass_product_surcharges s
                WHERE s.is_active = TRUE
                  AND (s.org_id = %s OR s.org_id IS NULL)
                  AND s.product_id = ANY(%s)
                ORDER BY s.product_id, s.kind, s.unit
                """,
                [active_org_id, [str(row[10]) for row in product_rows]],
            )
            surcharge_rows = cursor.fetchall()
        surcharges: dict[str, list[GlassSurchargeRate]] = {}
        for row in surcharge_rows:
            surcharges.setdefault(str(row[0]), []).append(
                GlassSurchargeRate(
                    kind=str(row[1]),
                    unit=str(row[2]),
                    amount=_decimal(row[3]),
                    label=str(row[4]) if row[4] is not None else None,
                    currency=str(row[5]) if row[5] is not None else None,
                )
            )
        products: dict[str, GlassProduct] = {}
        for row in product_rows:
            composition = _glass_composition(row[2])
            products[str(row[0])] = GlassProduct(
                sku=str(row[0]),
                name=str(row[1]),
                composition=composition,
                safety_class=str(row[3]) if row[3] is not None else None,
                ug_w_m2k=_decimal_or_none(row[4]),
                g_value=_decimal_or_none(row[5]),
                light_transmission_pct=_decimal_or_none(row[6]),
                weight_kg_m2=_decimal_or_none(row[7]),
                min_area_m2=_decimal_or_none(row[8]),
                review_pending=bool(row[9]),
                surcharges=surcharges.get(str(row[10]), []),
                price_tier=int(row[11]) if row[11] is not None else None,
            )
        return products

    def _load_glass_safety_rules(
        self, active_org_id: UUID
    ) -> list[GlassSafetyRule]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT code, title, message, applies_openings, sill_below_mm::text,
                       min_area_m2::text, requires_door, requires_adjacent_door,
                       required_safety, severity, source_ref, review_pending
                FROM public.glass_safety_rules
                WHERE is_active = TRUE
                  AND (org_id = %s OR org_id IS NULL)
                ORDER BY code, org_id NULLS LAST
                """,
                [active_org_id],
            )
            rows = cursor.fetchall()
        # Org-scoped row overrides the global rule carrying the same code.
        rules: dict[str, GlassSafetyRule] = {}
        for row in rows:
            rules[str(row[0])] = GlassSafetyRule(
                code=str(row[0]),
                title=str(row[1]),
                message=str(row[2]) if row[2] is not None else None,
                applies_openings=list(row[3]) if row[3] is not None else None,
                sill_below_mm=_decimal_or_none(row[4]),
                min_area_m2=_decimal_or_none(row[5]),
                requires_door=row[6],
                requires_adjacent_door=row[7],
                required_safety=str(row[8]),
                severity=str(row[9]),
                source_ref=str(row[10]) if row[10] is not None else None,
                review_pending=bool(row[11]),
            )
        return list(rules.values())

    def _load_glass_type_limits(
        self, active_org_id: UUID
    ) -> list[GlassTypeLimit]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT code, lamina_kind, thickness_min_mm::text,
                       thickness_max_mm::text, min_side_mm::text,
                       max_side_mm::text, min_area_m2::text, max_area_m2::text,
                       max_aspect_ratio::text, requires_exact_cut, severity,
                       source_ref, review_pending
                FROM public.glass_type_limits
                WHERE is_active = TRUE
                  AND (org_id = %s OR org_id IS NULL)
                ORDER BY code, org_id NULLS LAST
                """,
                [active_org_id],
            )
            rows = cursor.fetchall()
        limits: dict[str, GlassTypeLimit] = {}
        for row in rows:
            limits[str(row[0])] = GlassTypeLimit(
                code=str(row[0]),
                lamina_kind=str(row[1]),
                thickness_min_mm=_decimal_or_none(row[2]),
                thickness_max_mm=_decimal_or_none(row[3]),
                min_side_mm=_decimal_or_none(row[4]),
                max_side_mm=_decimal_or_none(row[5]),
                min_area_m2=_decimal_or_none(row[6]),
                max_area_m2=_decimal_or_none(row[7]),
                max_aspect_ratio=_decimal_or_none(row[8]),
                requires_exact_cut=bool(row[9]),
                severity=str(row[10]),
                source_ref=str(row[11]) if row[11] is not None else None,
                review_pending=bool(row[12]),
            )
        return list(limits.values())

    def _load_hardware_families(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[str, HardwareFamily]:
        """D04 family catalogue: one row per (system, opening) carries the
        declared handle-height rule; the model and colour lists live in
        their own tables keyed by the same opening."""
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT opening_type, handle_height_rule,
                       handle_height_min_mm, handle_height_max_mm,
                       handle_height_default_mm
                FROM public.hardware_families
                WHERE {self._SCOPE_SQL}
                ORDER BY opening_type
                """,
                [system_id, active_org_id],
            )
            family_rows = cursor.fetchall()
            cursor.execute(
                f"""
                SELECT opening_type, sku, name, kind, price_delta_clp
                FROM public.hardware_handle_models
                WHERE {self._SCOPE_SQL}
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            model_rows = cursor.fetchall()
            cursor.execute(
                f"""
                SELECT opening_type, sku, name, price_delta_clp
                FROM public.hardware_handle_colors
                WHERE {self._SCOPE_SQL}
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            color_rows = cursor.fetchall()
        models: dict[str, list[HandleModelOption]] = {}
        for row in model_rows:
            models.setdefault(str(row[0]), []).append(
                HandleModelOption(
                    sku=str(row[1]),
                    name=str(row[2]),
                    kind=cast(str, row[3]),
                    price_delta_clp=(
                        _decimal(row[4]) if row[4] is not None else None
                    ),
                )
            )
        colors: dict[str, list[HandleColorOption]] = {}
        for row in color_rows:
            colors.setdefault(str(row[0]), []).append(
                HandleColorOption(
                    sku=str(row[1]),
                    name=str(row[2]),
                    price_delta_clp=(
                        _decimal(row[3]) if row[3] is not None else None
                    ),
                )
            )
        families: dict[str, HardwareFamily] = {
            str(row[0]): HardwareFamily(
                opening_type=str(row[0]),
                handle_models=models.get(str(row[0]), []),
                handle_colors=colors.get(str(row[0]), []),
                handle_height_rule=cast(str, row[1]) if row[1] is not None else None,
                handle_height_min_mm=(
                    _decimal(row[2]) if row[2] is not None else None
                ),
                handle_height_max_mm=(
                    _decimal(row[3]) if row[3] is not None else None
                ),
                handle_height_default_mm=(
                    _decimal(row[4]) if row[4] is not None else None
                ),
            )
            for row in family_rows
        }
        # A family row is optional: model/colour rows alone still form the
        # family (the height rule stays undeclared then).
        for opening in set(models) | set(colors):
            families.setdefault(
                opening, HardwareFamily(
                    opening_type=opening,
                    handle_models=models.get(opening, []),
                    handle_colors=colors.get(opening, []),
                )
            )
        return families

    def _load_hardware_options(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[str, HardwareOption]:
        """D04 sellable options keyed by sku, scoped to the system's family."""
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT sku, name, kind, opening_type, price_delta_clp,
                       components::text
                FROM public.hardware_options
                WHERE {self._SCOPE_SQL}
                  AND is_active = TRUE
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        options: dict[str, HardwareOption] = {}
        for row in rows:
            option = HardwareOption(
                sku=str(row[0]),
                name=str(row[1]),
                kind=HardwareOptionKind(str(row[2])),
                opening_type=str(row[3]),
                price_delta_clp=_decimal(row[4]) if row[4] is not None else None,
                components=_hardware_contents(row[5]),
            )
            options[option.sku] = option
        return options

    def _load_extra_articles(
        self, system_id: UUID, active_org_id: UUID
    ) -> dict[str, ExtraArticle]:
        """D06 sellable extras — geometry-linked and counted articles the
        system declares. The engine measures them; the backend never invents
        a quantity or a price."""
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT sku, name, kind::text, pricing_unit::text,
                       unit_price, unit_price_currency,
                       unit_cost, unit_cost_currency,
                       cut_profile_sku, cut_material::text,
                       vuelo_default_mm,
                       array_to_json(families)::text,
                       array_to_json(unit_kinds)::text,
                       suggestion_reason
                FROM public.extra_articles
                WHERE {self._SCOPE_SQL}
                ORDER BY sku
                """,
                [system_id, active_org_id],
            )
            rows = cursor.fetchall()
        articles: dict[str, ExtraArticle] = {}
        for row in rows:
            families = tuple(
                SystemFamily(value)
                for value in (json.loads(row[11]) if row[11] else [])
            )
            unit_kinds = tuple(
                UnitKind(value)
                for value in (json.loads(row[12]) if row[12] else [])
            )
            article = ExtraArticle(
                sku=str(row[0]),
                name=str(row[1]),
                kind=ExtraKind(str(row[2])),
                pricing_unit=ExtraPricingUnit(str(row[3])),
                unit_price=_decimal_or_none(row[4]),
                unit_price_currency=(
                    None if row[5] is None else str(row[5])
                ),
                unit_cost=_decimal_or_none(row[6]),
                unit_cost_currency=(
                    None if row[7] is None else str(row[7])
                ),
                cut_profile_sku=(
                    None if row[8] is None else str(row[8])
                ),
                cut_material=(
                    None if row[9] is None else MaterialType(str(row[9]))
                ),
                vuelo_default_mm=_decimal_or_none(row[10]),
                families=families,
                unit_kinds=unit_kinds,
                suggestion_reason=(
                    None if row[13] is None else str(row[13])
                ),
            )
            articles[article.sku] = article
        return articles

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
