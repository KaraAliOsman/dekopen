"""Canonical DEMO_60 test catalog; live DB parity is checked independently."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal


from dekopen_engine import (
    HardwareComponent,
    HardwareKitRule,
    LeafRole,
    OpeningCapability,
    OpeningDirection,
    OpeningMovement,
    PanelRule,
    EffectiveProfileArticle,
    GlazingBeadRule,
    MaterialType,
    ProfileCutRule,
    ProfileRole,
    RailType,
    ReinforcementRule,
    SystemFamily,
    SystemParams,
    TypologyLimit,
    UnitKind,
)
from dekopen_engine.glass_composition import parse_glass_notation
from dekopen_engine.models import (
    GlassProduct,
    GlassSafetyRule,
    GlassSurchargeRate,
    GlassTypeLimit,
)


def d(value: str) -> Decimal:
    return Decimal(value)


def _article(
    *,
    sku: str,
    role: ProfileRole,
    face_width_mm: str,
    welding_loss_mm: str,
    reinforcement_gap_mm: str,
    weight_kg_m: str = "1.2000",
) -> EffectiveProfileArticle:
    return EffectiveProfileArticle(
        sku=sku,
        role=role,
        material=MaterialType.PVC,
        face_width_mm=d(face_width_mm),
        # The live DEMO_60 seed declares a 6000 mm commercial length on every
        # profile/bead article; the fixture mirrors it so the RLS parity test
        # verifies the value reaches the typed model field-for-field.
        commercial_length_mm=d("6000.00"),
        welding_loss_mm=d(welding_loss_mm),
        reinforcement_gap_mm=d(reinforcement_gap_mm),
        weight_kg_m=d(weight_kg_m),
        steel_weight_kg_m=d("1.7000"),
    )


def demo_60_params() -> SystemParams:
    frame = _article(
        sku="MARCO",
        role=ProfileRole.FRAME,
        face_width_mm="60.00",
        welding_loss_mm="6.00",
        reinforcement_gap_mm="15.00",
    )
    sash = _article(
        sku="HOJA",
        role=ProfileRole.SASH,
        face_width_mm="75.00",
        welding_loss_mm="6.00",
        reinforcement_gap_mm="15.00",
    )
    mullion_v = _article(
        sku="POSTE-V",
        role=ProfileRole.MULLION_V,
        face_width_mm="80.00",
        welding_loss_mm="0.00",
        reinforcement_gap_mm="5.00",
    )
    mullion_h = _article(
        sku="POSTE-H",
        role=ProfileRole.MULLION_H,
        face_width_mm="80.00",
        welding_loss_mm="0.00",
        reinforcement_gap_mm="5.00",
    )
    bead_24 = _article(
        sku="JQ-24",
        role=ProfileRole.GLAZING_BEAD,
        face_width_mm="24.00",
        welding_loss_mm="0.00",
        reinforcement_gap_mm="15.00",
    )
    bead_14 = _article(
        sku="JQ-14",
        role=ProfileRole.GLAZING_BEAD,
        face_width_mm="14.00",
        welding_loss_mm="0.00",
        reinforcement_gap_mm="15.00",
    )
    bead_10 = _article(
        sku="JQ-10",
        role=ProfileRole.GLAZING_BEAD,
        face_width_mm="10.00",
        welding_loss_mm="0.00",
        reinforcement_gap_mm="15.00",
    )

    door_sash = _article(
        sku="HOJA-PUERTA",
        role=ProfileRole.DOOR_SASH,
        face_width_mm="90.00",
        welding_loss_mm="6.00",
        reinforcement_gap_mm="15.00",
        weight_kg_m="2.4000",
    )

    inversor = _article(
        sku="INVERSOR-60",
        role=ProfileRole.INVERSOR,
        face_width_mm="85.00",
        welding_loss_mm="6.00",
        reinforcement_gap_mm="15.00",
        weight_kg_m="2.4000",
    )

    return SystemParams(
        system_code="DEMO_60",
        finishes=("WHITE", "FOILED"),
        depth_mm=d("60.00"),
        material=MaterialType.PVC,
        system_family=SystemFamily.CASEMENT,
        effective_profile_articles={
            ProfileRole.FRAME: frame,
            ProfileRole.SASH: sash,
            ProfileRole.DOOR_SASH: door_sash,
            ProfileRole.INVERSOR: inversor,
            ProfileRole.MULLION_V: mullion_v,
            ProfileRole.MULLION_H: mullion_h,
            ProfileRole.THRESHOLD: EffectiveProfileArticle(
                sku="UMBRAL-ALU",
                role=ProfileRole.THRESHOLD,
                material=MaterialType.ALUMINIUM,
                face_width_mm=d("30.00"),
                commercial_length_mm=d("6000.00"),
                welding_loss_mm=d("0.00"),
                reinforcement_gap_mm=d("0.00"),
                weight_kg_m=d("1.2000"),
                steel_weight_kg_m=d("1.7000"),
            ),
        },
        glazing_bead_rules={
            d("4.00"): GlazingBeadRule(
                glass_thickness_mm=d("4.00"),
                bead_article=bead_24,
                bead_width_mm=d("24.00"),
                gasket_interior_mm=d("3.00"),
                gasket_exterior_mm=d("3.00"),
                cut_add_mm=d("9.00"),
            ),
            d("5.00"): GlazingBeadRule(
                glass_thickness_mm=d("5.00"),
                bead_article=bead_24,
                bead_width_mm=d("24.00"),
                gasket_interior_mm=d("2.50"),
                gasket_exterior_mm=d("2.50"),
                cut_add_mm=d("9.00"),
            ),
            d("6.00"): GlazingBeadRule(
                glass_thickness_mm=d("6.00"),
                bead_article=bead_24,
                bead_width_mm=d("24.00"),
                gasket_interior_mm=d("2.00"),
                gasket_exterior_mm=d("2.00"),
                cut_add_mm=d("9.00"),
            ),
            d("6.38"): GlazingBeadRule(
                glass_thickness_mm=d("6.38"),
                bead_article=bead_24,
                bead_width_mm=d("24.00"),
                gasket_interior_mm=d("3.00"),
                gasket_exterior_mm=d("3.00"),
                cut_add_mm=d("9.00"),
            ),
            d("20.00"): GlazingBeadRule(
                glass_thickness_mm=d("20.00"),
                bead_article=bead_14,
                bead_width_mm=d("14.00"),
                gasket_interior_mm=d("3.00"),
                gasket_exterior_mm=d("3.00"),
                cut_add_mm=d("9.00"),
            ),
            d("24.00"): GlazingBeadRule(
                glass_thickness_mm=d("24.00"),
                bead_article=bead_10,
                bead_width_mm=d("10.00"),
                gasket_interior_mm=d("3.00"),
                gasket_exterior_mm=d("3.00"),
                cut_add_mm=d("9.00"),
            ),
        },
        rebate_depth_mm=d("20.00"),
        end_milling_overlap_mm=d("0.00"),
        sash_overlap_mm=d("8.00"),
        glass_clearance_white_mm=d("5.00"),
        glass_clearance_foil_mm=d("5.00"),
        pulley_height_mm=d("12.00"),
        central_overlap_mm=d("40.00"),
        sliding_lateral_clearance_mm=d("0.00"),
        sliding_end_add_mm=d("6.00"),
        corner_bracket_loss_mm=d("0.00"),
        hook_depth_mm=d("0.00"),
        door_threshold_mm=d("30.00"),
        door_bottom_clearance_mm=d("20.00"),
        rail_type=RailType.DUAL,
        sliding_glazing_deduction_width_mm=d("20.00"),
        sliding_glazing_deduction_height_mm=d("20.00"),
        door_leaf_side_clearance_mm=d("7.00"),
        available_hardware_kits=[
            kit for kit in demo_hardware_kits() if not kit.sku.startswith("KIT-SLIDING")
        ],
        available_panel_rules={
            "PANEL-SANDWICH-DEMO-24": PanelRule(
                sku="PANEL-SANDWICH-DEMO-24",
                name="Panel Sándwich Demo 24mm",
                kind="SANDWICH_PANEL",
                thickness_mm=d("24.00"),
                weight_kg_m2=d("10.0000"),
            ),
        },
        cut_rules={
            ProfileRole.FRAME: ProfileCutRule(
                role=ProfileRole.FRAME, cut_angle_deg=d("45.0"), welded_ends=2
            ),
            ProfileRole.SASH: ProfileCutRule(
                role=ProfileRole.SASH, cut_angle_deg=d("45.0"), welded_ends=2
            ),
            ProfileRole.DOOR_SASH: ProfileCutRule(
                role=ProfileRole.DOOR_SASH, cut_angle_deg=d("45.0"), welded_ends=2
            ),
            ProfileRole.INVERSOR: ProfileCutRule(
                role=ProfileRole.INVERSOR, cut_angle_deg=d("45.0"), welded_ends=2
            ),
            ProfileRole.MULLION_V: ProfileCutRule(
                role=ProfileRole.MULLION_V, cut_angle_deg=d("90.0"), welded_ends=0
            ),
            ProfileRole.MULLION_H: ProfileCutRule(
                role=ProfileRole.MULLION_H, cut_angle_deg=d("90.0"), welded_ends=0
            ),
            ProfileRole.GLAZING_BEAD: ProfileCutRule(
                role=ProfileRole.GLAZING_BEAD, cut_angle_deg=d("45.0")
            ),
            ProfileRole.THRESHOLD: ProfileCutRule(
                role=ProfileRole.THRESHOLD, cut_angle_deg=d("90.0")
            ),
        },
        reinforcement_rules=[
            # White members need steel only from one metre up; foiled/dark
            # members are reinforced unconditionally (thermal expansion).
            ReinforcementRule(
                role=role,
                finish_class="WHITE",
                min_length_mm=d("1000.00"),
                screws_per_m=d("4.00"),
                screw_sku="TORNILLO-4X16",
            )
            for role in (
                ProfileRole.FRAME,
                ProfileRole.SASH,
                ProfileRole.DOOR_SASH,
                ProfileRole.INVERSOR,
                ProfileRole.MULLION_V,
                ProfileRole.MULLION_H,
            )
        ]
        + [
            ReinforcementRule(
                role=role,
                finish_class="NON_WHITE",
                min_length_mm=d("0.00"),
                screws_per_m=d("4.00"),
                screw_sku="TORNILLO-4X16",
            )
            for role in (
                ProfileRole.FRAME,
                ProfileRole.SASH,
                ProfileRole.DOOR_SASH,
                ProfileRole.INVERSOR,
                ProfileRole.MULLION_V,
                ProfileRole.MULLION_H,
            )
        ],
        typology_limits={
            "TURN_LEFT": TypologyLimit(
                opening_type="TURN_LEFT",
                min_leaf_width_mm=d("350.00"),
                max_leaf_width_mm=d("1400.00"),
                min_leaf_height_mm=d("400.00"),
                max_leaf_height_mm=d("2500.00"),
                max_leaf_weight_kg=d("100.00"),
                max_aspect_ratio=d("2.80"),
            ),
            "TILT_TURN_RIGHT": TypologyLimit(
                opening_type="TILT_TURN_RIGHT",
                min_leaf_width_mm=d("450.00"),
                max_leaf_width_mm=d("1600.00"),
                min_leaf_height_mm=d("450.00"),
                max_leaf_height_mm=d("2500.00"),
                max_leaf_weight_kg=d("130.00"),
            ),
            "AWNING": TypologyLimit(
                opening_type="AWNING",
                min_leaf_width_mm=d("400.00"),
                max_leaf_width_mm=d("1800.00"),
                min_leaf_height_mm=d("350.00"),
                max_leaf_height_mm=d("1200.00"),
                max_leaf_weight_kg=d("45.00"),
            ),
            "DOOR_ENTRY": TypologyLimit(
                opening_type="DOOR_ENTRY",
                min_leaf_width_mm=d("600.00"),
                max_leaf_width_mm=d("1100.00"),
                min_leaf_height_mm=d("1700.00"),
                max_leaf_height_mm=d("2500.00"),
                max_leaf_weight_kg=d("120.00"),
            ),
            # Spec-key rows (D03): the seed declares envelopes per
            # canonical axis — the engine resolves emitted keys against
            # these, not against the legacy names.
            "TURN": TypologyLimit(
                opening_type="TURN",
                min_leaf_width_mm=d("350.00"),
                max_leaf_width_mm=d("1400.00"),
                min_leaf_height_mm=d("400.00"),
                max_leaf_height_mm=d("2500.00"),
                max_leaf_weight_kg=d("100.00"),
                max_aspect_ratio=d("2.80"),
            ),
            "TILT_TURN": TypologyLimit(
                opening_type="TILT_TURN",
                min_leaf_width_mm=d("450.00"),
                max_leaf_width_mm=d("1600.00"),
                min_leaf_height_mm=d("450.00"),
                max_leaf_height_mm=d("2500.00"),
                max_leaf_weight_kg=d("130.00"),
            ),
            "TILT": TypologyLimit(
                opening_type="TILT",
                min_leaf_width_mm=d("400.00"),
                max_leaf_width_mm=d("1600.00"),
                min_leaf_height_mm=d("400.00"),
                max_leaf_height_mm=d("1200.00"),
                max_leaf_weight_kg=d("60.00"),
            ),
            "TOP_HUNG": TypologyLimit(
                opening_type="TOP_HUNG",
                min_leaf_width_mm=d("400.00"),
                max_leaf_width_mm=d("1800.00"),
                min_leaf_height_mm=d("350.00"),
                max_leaf_height_mm=d("1200.00"),
                max_leaf_weight_kg=d("45.00"),
            ),
            "BOTTOM_HUNG": TypologyLimit(
                opening_type="BOTTOM_HUNG",
                min_leaf_width_mm=d("400.00"),
                max_leaf_width_mm=d("1400.00"),
                min_leaf_height_mm=d("500.00"),
                max_leaf_height_mm=d("1600.00"),
                max_leaf_weight_kg=d("80.00"),
            ),
            "DOOR:TURN": TypologyLimit(
                opening_type="DOOR:TURN",
                min_leaf_width_mm=d("600.00"),
                max_leaf_width_mm=d("1100.00"),
                min_leaf_height_mm=d("1700.00"),
                max_leaf_height_mm=d("2500.00"),
                max_leaf_weight_kg=d("120.00"),
            ),
            "DOOR_DOUBLE": TypologyLimit(
                opening_type="DOOR_DOUBLE",
                min_leaf_width_mm=d("500.00"),
                max_leaf_width_mm=d("900.00"),
                min_leaf_height_mm=d("1700.00"),
                max_leaf_height_mm=d("2500.00"),
                max_leaf_weight_kg=d("120.00"),
            ),
        },
        glass_products=_demo_60_glass_products(),
        glass_safety_rules=_demo_glass_safety_rules(),
        glass_type_limits=_demo_glass_type_limits(),
        # Declared opening repertoire the seed carries for DEMO_60 (D03):
        # repository ORDER BY movement.
        opening_capabilities=(
            OpeningCapability(
                movement=OpeningMovement.BOTTOM_HUNG,
                directions=(OpeningDirection.INWARD, OpeningDirection.OUTWARD),
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW,),
                max_leaves=1,
            ),
            OpeningCapability(
                movement=OpeningMovement.FIXED,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                max_leaves=2,
                fixed_in_sash=True,
            ),
            OpeningCapability(
                movement=OpeningMovement.TILT,
                directions=(OpeningDirection.INWARD,),
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW,),
                max_leaves=1,
            ),
            OpeningCapability(
                movement=OpeningMovement.TILT_TURN,
                directions=(OpeningDirection.INWARD,),
                leaf_roles=(LeafRole.SINGLE, LeafRole.ACTIVE, LeafRole.PASSIVE),
                unit_kinds=(UnitKind.WINDOW,),
                max_leaves=2,
            ),
            OpeningCapability(
                movement=OpeningMovement.TOP_HUNG,
                directions=(OpeningDirection.OUTWARD,),
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW,),
                max_leaves=1,
            ),
            OpeningCapability(
                movement=OpeningMovement.TURN,
                directions=(OpeningDirection.INWARD, OpeningDirection.OUTWARD),
                leaf_roles=(LeafRole.SINGLE, LeafRole.ACTIVE, LeafRole.PASSIVE),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                max_leaves=2,
            ),
        ),
    )


def _demo_60_glass_products() -> dict[str, GlassProduct]:
    """DEMO_60 glass catalog — parity with `supabase/seed.sql` D02 rows
    (compositions built by the same engine parser)."""

    def product(
        sku: str,
        name: str,
        notation: str,
        *,
        safety_class: str | None = None,
        ug_w_m2k: str | None = None,
        g_value: str | None = None,
        light_transmission_pct: str | None = None,
        weight_kg_m2: str,
        price_tier: int,
        review_pending: bool,
        surcharges: list[GlassSurchargeRate] | None = None,
    ) -> GlassProduct:
        return GlassProduct(
            sku=sku,
            name=name,
            composition=parse_glass_notation(notation),
            safety_class=safety_class,
            ug_w_m2k=d(ug_w_m2k) if ug_w_m2k is not None else None,
            g_value=d(g_value) if g_value is not None else None,
            light_transmission_pct=(
                d(light_transmission_pct) if light_transmission_pct is not None else None
            ),
            weight_kg_m2=d(weight_kg_m2),
            min_area_m2=d("0.3000"),
            price_tier=price_tier,
            review_pending=review_pending,
            surcharges=list(surcharges or []),
        )

    def rate(
        kind: Literal["TEMPERED", "EDGE_POLISH", "DRILL", "PALILLAJE"],
        unit: Literal["M2", "M", "EA", "CROSS"],
        amount: str,
        label: str,
    ) -> GlassSurchargeRate:
        return GlassSurchargeRate(
            kind=kind, unit=unit, amount=d(amount), label=label, currency="CLP"
        )

    return {
        "VIDRIO-BASE": product(
            "VIDRIO-BASE",
            "Termopanel incoloro 4·16·4",
            "4-16-4 Float Incoloro",
            weight_kg_m2="20.000",
            price_tier=2,
            review_pending=False,
            surcharges=[
                rate("DRILL", "EA", "3500.0000", "Perforación"),
                rate("PALILLAJE", "CROSS", "1500.0000", "Palillaje interior — por cruce"),
            ],
        ),
        "DVH-20": product(
            "DVH-20",
            "Termopanel incoloro 4·12·4",
            "4-12-4 Float Incoloro",
            weight_kg_m2="20.000",
            price_tier=2,
            review_pending=False,
            surcharges=[
                rate("PALILLAJE", "CROSS", "1500.0000", "Palillaje interior — por cruce"),
            ],
        ),
        "VIDRIO-LOWE-24": product(
            "VIDRIO-LOWE-24",
            "Termopanel Low-E 4·16·4",
            "4 / 16 Ar / 4 Low-E (c3)",
            ug_w_m2k="1.400",
            g_value="0.630",
            light_transmission_pct="80.00",
            weight_kg_m2="20.000",
            price_tier=4,
            review_pending=True,
            surcharges=[
                rate("DRILL", "EA", "3500.0000", "Perforación"),
                rate("PALILLAJE", "CROSS", "1500.0000", "Palillaje interior — por cruce"),
            ],
        ),
        "VIDRIO-TEMP-6": product(
            "VIDRIO-TEMP-6",
            "Templado incoloro 6 mm",
            "6 templado",
            safety_class="B",
            weight_kg_m2="15.000",
            price_tier=3,
            review_pending=True,
            surcharges=[
                rate("EDGE_POLISH", "M", "1200.0000", "Canto pulido"),
                rate("TEMPERED", "M2", "5500.0000", "Recargo templado"),
            ],
        ),
        "VIDRIO-LAM-638": product(
            "VIDRIO-LAM-638",
            "Laminado seguridad 3+3",
            "3+3 PVB 0,38",
            safety_class="A",
            weight_kg_m2="15.407",
            price_tier=4,
            review_pending=True,
            surcharges=[
                rate("EDGE_POLISH", "M", "1200.0000", "Canto pulido"),
            ],
        ),
    }


def _demo_glass_safety_rules() -> list[GlassSafetyRule]:
    """Seeded NCh 135-family WARNING rules (synthetic pending official
    text) — parity with `supabase/seed.sql`. No floor-distance rule is
    seeded: the model knows the pane's offset to the unit base, never the
    floor height of the installation."""
    return [
        GlassSafetyRule(
            code="GLASS-SAFETY-ADJ-DOOR",
            title="Paño lateral junto a puerta",
            message="El paño lateral de una puerta debería llevar vidrio de seguridad.",
            requires_adjacent_door=True,
            required_safety="SAFETY_GLASS",
            severity="WARNING",
            source_ref="NCh 135/2 — referencia sintética pendiente de norma oficial",
            review_pending=True,
        ),
        GlassSafetyRule(
            code="GLASS-SAFETY-DOOR",
            title="Paño vidriado en puerta",
            message=(
                "El paño de una puerta vidriada debería llevar vidrio de "
                "seguridad (templado o laminado)."
            ),
            requires_door=True,
            required_safety="SAFETY_GLASS",
            severity="WARNING",
            source_ref="NCh 135/2 — referencia sintética pendiente de norma oficial",
            review_pending=True,
        ),
        GlassSafetyRule(
            code="GLASS-SAFETY-LARGE-PANE",
            title="Gran paño vidriado",
            message=(
                "Un paño de 4 m² o más expone una superficie grande: se "
                "recomienda vidrio de seguridad."
            ),
            min_area_m2=d("4.0000"),
            required_safety="SAFETY_GLASS",
            severity="WARNING",
            source_ref="NCh 135/2 — referencia sintética pendiente de norma oficial",
            review_pending=True,
        ),
    ]


def _demo_glass_type_limits() -> list[GlassTypeLimit]:
    """Seeded manufacturing bounds (synthetic) — parity with
    `supabase/seed.sql`."""
    return [
        GlassTypeLimit(
            code="GLASS-LIMIT-FLOAT-4",
            lamina_kind="FLOAT",
            thickness_min_mm=d("4.00"),
            thickness_max_mm=d("4.00"),
            max_area_m2=d("4.5000"),
            source_ref="Referencia sintética — revisar con proveedor",
            review_pending=True,
        ),
        GlassTypeLimit(
            code="GLASS-LIMIT-MONO-SIDE",
            lamina_kind="FLOAT",
            min_side_mm=d("250.00"),
            max_aspect_ratio=d("12.000"),
            source_ref="Referencia sintética — relación de aspecto ≤ 12",
            review_pending=True,
        ),
        GlassTypeLimit(
            code="GLASS-LIMIT-TEMPERED-EXACT-CUT",
            lamina_kind="TEMPERED",
            requires_exact_cut=True,
            source_ref="Práctica vidriera — el templado no se recorta",
            review_pending=True,
        ),
        GlassTypeLimit(
            code="GLASS-LIMIT-TEMPERED-SIDE",
            lamina_kind="TEMPERED",
            max_side_mm=d("3200.00"),
            source_ref="Referencia sintética — revisar con proveedor",
            review_pending=True,
        ),
    ]


def demo_hardware_kits() -> list[HardwareKitRule]:
    """Approved synthetic fixtures. New ranges are not manufacturer specifications."""
    rows = [
        ("KIT-TURN", "Kit Practicable Demo 60", "TURN", "400", "1200", "500", "2400", "80", 0, 0),
        (
            "KIT-TILT-TURN",
            "Kit Vorne OB 100kg",
            "TILT_TURN",
            "450",
            "1400",
            "600",
            "2400",
            "100",
            0,
            1,
        ),
        (
            "KIT-SLIDING",
            "Kit Corredera Demo 60",
            "SLIDING",
            "400",
            "1500",
            "500",
            "2500",
            "120",
            2,
            0,
        ),
        (
            "KIT-AWNING-16",
            'Kit Proyectante Compás 16" 45kg',
            "AWNING",
            "400",
            "1200",
            "400",
            "1000",
            "45",
            0,
            2,
        ),
        (
            "KIT-DOOR-MULTIPOINT",
            "Kit Puerta Entrada Multipunto Demo 60",
            "DOOR",
            "700",
            "1200",
            "1800",
            "2400",
            "120",
            0,
            0,
        ),
        (
            "KIT-TILT",
            "Kit Solo Abatimiento Demo 60",
            "TILT",
            "400",
            "1600",
            "400",
            "1200",
            "60",
            0,
            0,
        ),
        (
            "KIT-BOTTOM-HUNG",
            "Kit Abatimiento Bisagra Inferior Demo 60",
            "BOTTOM_HUNG",
            "400",
            "1400",
            "500",
            "1600",
            "80",
            0,
            0,
        ),
        (
            "KIT-FALLEBA",
            "Kit Falleba Hoja Pasiva Demo 60",
            "FALLEBA",
            "300",
            "1200",
            "600",
            "2400",
            "100",
            0,
            0,
        ),
    ]
    contents = {
        "KIT-AWNING-16": [
            HardwareComponent(
                sku="DEMO-STAY-16",
                name='Compás a fricción 16"',
                qty=d("2"),
                unit="unit",
            )
        ],
        "KIT-DOOR-MULTIPOINT": [
            HardwareComponent(
                sku="DEMO-LOCK-MULTIPOINT",
                name="Cerradura multipunto Demo",
                qty=d("1"),
                unit="unit",
            )
        ],
        "KIT-TILT": [
            HardwareComponent(
                sku="DEMO-SCISSOR-TILT",
                name="Compás de abatimiento Demo",
                qty=d("2"),
                unit="unit",
            )
        ],
        "KIT-BOTTOM-HUNG": [
            HardwareComponent(
                sku="DEMO-HINGE-BOTTOM",
                name="Bisagra inferior Demo",
                qty=d("2"),
                unit="unit",
            ),
            HardwareComponent(
                sku="DEMO-SCISSOR-BH",
                name="Brazo limitador Demo",
                qty=d("2"),
                unit="unit",
            ),
        ],
        "KIT-FALLEBA": [
            HardwareComponent(
                sku="DEMO-FALLEBA-ROD",
                name="Falleba de cierre Demo",
                qty=d("1"),
                unit="unit",
            ),
            HardwareComponent(
                sku="DEMO-FALLEBA-BOLT",
                name="Pasador de falleba Demo",
                qty=d("2"),
                unit="unit",
            ),
        ],
    }
    kits = [
        HardwareKitRule(
            sku=sku,
            name=name,
            opening_type=opening,
            min_leaf_width_mm=d(min_w),
            max_leaf_width_mm=d(max_w),
            min_leaf_height_mm=d(min_h),
            max_leaf_height_mm=d(max_h),
            max_leaf_weight_kg=d(max_kg),
            rail_type=RailType.DUAL,
            carriages_qty=carriages,
            stay_arms_qty=stays,
            weight_kg=d("2.50"),
            contents=contents.get(sku, []),
        )
        for sku, name, opening, min_w, max_w, min_h, max_h, max_kg, carriages, stays in rows
    ]
    kits.append(
        HardwareKitRule(
            sku="KIT-SLIDING-MONO",
            name="Kit Corredera Mono Demo 60",
            opening_type="SLIDING",
            min_leaf_width_mm=d("400"),
            max_leaf_width_mm=d("1500"),
            min_leaf_height_mm=d("500"),
            max_leaf_height_mm=d("2500"),
            max_leaf_weight_kg=d("120"),
            rail_type=RailType.MONO,
            carriages_qty=1,
            stay_arms_qty=0,
            weight_kg=d("2.10"),
            contents=[],
        )
    )
    return kits


def alu_65_params() -> SystemParams:
    """ALU_65 test catalog — mechanically jointed aluminium. Synthetic fixtures."""

    def _alu(
        *,
        sku: str,
        role: ProfileRole,
        face_width_mm: str,
        weight_kg_m: str = "1.4000",
    ) -> EffectiveProfileArticle:
        return EffectiveProfileArticle(
            sku=sku,
            role=role,
            material=MaterialType.ALUMINIUM,
            face_width_mm=d(face_width_mm),
            welding_loss_mm=d("0.00"),
            reinforcement_gap_mm=d("0.00"),
            weight_kg_m=d(weight_kg_m),
            steel_weight_kg_m=d("0.0000"),
        )

    kits = [
        (
            "KIT-A-TURN",
            "Kit practicable Aluminio 65",
            "TURN",
            "400",
            "1100",
            "500",
            "2200",
            "60",
            0,
            0,
        ),
        (
            "KIT-A-TILT-TURN",
            "Kit oscilobatiente Aluminio 65",
            "TILT_TURN",
            "450",
            "1300",
            "600",
            "2200",
            "90",
            0,
            1,
        ),
        (
            "KIT-A-SLIDING",
            "Kit corredera Aluminio 65",
            "SLIDING",
            "500",
            "1800",
            "600",
            "2400",
            "100",
            2,
            0,
        ),
        (
            "KIT-A-AWNING",
            "Kit proyectante Aluminio 65",
            "AWNING",
            "450",
            "1400",
            "400",
            "1200",
            "50",
            0,
            2,
        ),
        (
            "KIT-A-DOOR",
            "Kit puerta multipunto Aluminio 65",
            "DOOR",
            "750",
            "1200",
            "1900",
            "2400",
            "90",
            0,
            0,
        ),
    ]
    return SystemParams(
        system_code="ALU_65",
        depth_mm=d("65.00"),
        material=MaterialType.ALUMINIUM,
        system_family=SystemFamily.CASEMENT,
        effective_profile_articles={
            ProfileRole.FRAME: _alu(sku="MARCO-A", role=ProfileRole.FRAME, face_width_mm="55.00"),
            ProfileRole.SASH: _alu(
                sku="HOJA-A", role=ProfileRole.SASH, face_width_mm="62.00", weight_kg_m="1.5500"
            ),
            ProfileRole.MULLION_V: _alu(
                sku="POSTE-A-V",
                role=ProfileRole.MULLION_V,
                face_width_mm="70.00",
                weight_kg_m="1.7000",
            ),
            ProfileRole.MULLION_H: _alu(
                sku="POSTE-A-H",
                role=ProfileRole.MULLION_H,
                face_width_mm="70.00",
                weight_kg_m="1.7000",
            ),
            ProfileRole.THRESHOLD: _alu(
                sku="UMBRAL-A",
                role=ProfileRole.THRESHOLD,
                face_width_mm="28.00",
                weight_kg_m="0.9000",
            ),
        },
        glazing_bead_rules={
            d("24.00"): GlazingBeadRule(
                glass_thickness_mm=d("24.00"),
                bead_article=_alu(
                    sku="JQ-A-8",
                    role=ProfileRole.GLAZING_BEAD,
                    face_width_mm="8.00",
                    weight_kg_m="0.2000",
                ),
                bead_width_mm=d("8.00"),
                gasket_interior_mm=d("3.50"),
                gasket_exterior_mm=d("3.50"),
                cut_add_mm=d("7.00"),
            ),
        },
        rebate_depth_mm=d("20.00"),
        end_milling_overlap_mm=d("0.00"),
        sash_overlap_mm=d("6.00"),
        glass_clearance_white_mm=d("4.00"),
        glass_clearance_foil_mm=d("4.00"),
        pulley_height_mm=d("10.00"),
        central_overlap_mm=d("25.00"),
        sliding_lateral_clearance_mm=d("3.00"),
        sliding_end_add_mm=d("5.00"),
        corner_bracket_loss_mm=d("2.00"),
        hook_depth_mm=d("8.00"),
        door_threshold_mm=d("25.00"),
        door_bottom_clearance_mm=d("18.00"),
        rail_type=RailType.DUAL,
        sliding_glazing_deduction_width_mm=d("15.00"),
        sliding_glazing_deduction_height_mm=d("15.00"),
        door_leaf_side_clearance_mm=d("5.00"),
        # Aluminium cuts are sawn square with mechanical (non-welded) joints.
        cut_rules={
            role: ProfileCutRule(role=role, cut_angle_deg=d("45.0"), welded_ends=None)
            for role in (
                ProfileRole.FRAME,
                ProfileRole.SASH,
                ProfileRole.DOOR_SASH,
                ProfileRole.MULLION_V,
                ProfileRole.MULLION_H,
                ProfileRole.GLAZING_BEAD,
                ProfileRole.THRESHOLD,
            )
        },
        typology_limits={
            "TURN_LEFT": TypologyLimit(
                opening_type="TURN_LEFT",
                min_leaf_width_mm=d("350.00"),
                max_leaf_width_mm=d("1000.00"),
                min_leaf_height_mm=d("400.00"),
                max_leaf_height_mm=d("2200.00"),
                max_leaf_weight_kg=d("60.00"),
            ),
            "TILT_TURN_RIGHT": TypologyLimit(
                opening_type="TILT_TURN_RIGHT",
                min_leaf_width_mm=d("450.00"),
                max_leaf_width_mm=d("1200.00"),
                min_leaf_height_mm=d("450.00"),
                max_leaf_height_mm=d("2200.00"),
                max_leaf_weight_kg=d("90.00"),
            ),
            "DOOR_ENTRY": TypologyLimit(
                opening_type="DOOR_ENTRY",
                min_leaf_width_mm=d("600.00"),
                max_leaf_width_mm=d("1100.00"),
                min_leaf_height_mm=d("1700.00"),
                max_leaf_height_mm=d("2500.00"),
                max_leaf_weight_kg=d("100.00"),
            ),
        },
        available_hardware_kits=[
            HardwareKitRule(
                sku=sku,
                name=name,
                opening_type=opening,
                min_leaf_width_mm=d(min_w),
                max_leaf_width_mm=d(max_w),
                min_leaf_height_mm=d(min_h),
                max_leaf_height_mm=d(max_h),
                max_leaf_weight_kg=d(max_kg),
                rail_type=RailType.DUAL,
                carriages_qty=carriages,
                stay_arms_qty=stays,
                weight_kg=d("2.50"),
            )
            for sku, name, opening, min_w, max_w, min_h, max_h, max_kg, carriages, stays in kits
        ],
    )


def _sliding_kits(dual_sku: str, mono_sku: str, label: str) -> list[HardwareKitRule]:
    """Sliding-series hardware: dual-rail kit plus its monorail sibling."""
    return [
        HardwareKitRule(
            sku=dual_sku,
            name=f"Kit Corredera {label}",
            opening_type="SLIDING",
            min_leaf_width_mm=d("400"),
            max_leaf_width_mm=d("1500"),
            min_leaf_height_mm=d("500"),
            max_leaf_height_mm=d("2500"),
            max_leaf_weight_kg=d("120"),
            rail_type=RailType.DUAL,
            carriages_qty=2,
            stay_arms_qty=0,
            weight_kg=d("2.50"),
            contents=[],
        ),
        HardwareKitRule(
            sku=mono_sku,
            name=f"Kit Corredera Mono {label}",
            opening_type="SLIDING",
            min_leaf_width_mm=d("400"),
            max_leaf_width_mm=d("1500"),
            min_leaf_height_mm=d("500"),
            max_leaf_height_mm=d("2500"),
            max_leaf_weight_kg=d("120"),
            rail_type=RailType.MONO,
            carriages_qty=1,
            stay_arms_qty=0,
            weight_kg=d("2.10"),
            contents=[],
        ),
    ]


def _sliding_limits() -> dict[str, TypologyLimit]:
    opening_types = ("SLIDING_2L", "SLIDING_3L", "SLIDING_4L", "SLIDING")
    return {
        opening: TypologyLimit(
            opening_type=opening,
            min_leaf_width_mm=d("400.00"),
            max_leaf_width_mm=d("1500.00"),
            min_leaf_height_mm=d("500.00"),
            max_leaf_height_mm=d("2500.00"),
            max_leaf_weight_kg=d("120.00"),
        )
        for opening in opening_types
    }


def _sliding_cut_rules(bead_rounding: str = "0.01") -> dict[ProfileRole, ProfileCutRule]:
    return {
        ProfileRole.FRAME: ProfileCutRule(
            role=ProfileRole.FRAME, cut_angle_deg=d("45.0"), welded_ends=2
        ),
        ProfileRole.RAIL: ProfileCutRule(
            role=ProfileRole.RAIL, cut_angle_deg=d("45.0"), welded_ends=2
        ),
        ProfileRole.SLIDING_SASH: ProfileCutRule(
            role=ProfileRole.SLIDING_SASH, cut_angle_deg=d("45.0"), welded_ends=2
        ),
        ProfileRole.INTERLOCK: ProfileCutRule(
            role=ProfileRole.INTERLOCK,
            cut_angle_deg=d("45.0"),
            welded_ends=2,
            # The encuentro lap where two moving leaves meet.
            interlock_deduction_mm=d("18.00"),
        ),
        ProfileRole.MULLION_V: ProfileCutRule(
            role=ProfileRole.MULLION_V, cut_angle_deg=d("90.0"), welded_ends=0
        ),
        ProfileRole.MULLION_H: ProfileCutRule(
            role=ProfileRole.MULLION_H, cut_angle_deg=d("90.0"), welded_ends=0
        ),
        ProfileRole.GLAZING_BEAD: ProfileCutRule(
            role=ProfileRole.GLAZING_BEAD,
            cut_angle_deg=d("45.0"),
            rounding_mm=d(bead_rounding),
        ),
    }


def _sliding_reinforcement_rules() -> list[ReinforcementRule]:
    roles = (
        ProfileRole.FRAME,
        ProfileRole.RAIL,
        ProfileRole.SLIDING_SASH,
        ProfileRole.INTERLOCK,
        ProfileRole.MULLION_V,
        ProfileRole.MULLION_H,
    )
    return [
        ReinforcementRule(
            role=role,
            finish_class="WHITE",
            min_length_mm=d("1000.00"),
            screws_per_m=d("4.00"),
            screw_sku="TORNILLO-4X16",
        )
        for role in roles
    ] + [
        ReinforcementRule(
            role=role,
            finish_class="NON_WHITE",
            min_length_mm=d("0.00"),
            screws_per_m=d("4.00"),
            screw_sku="TORNILLO-4X16",
        )
        for role in roles
    ]


def demo_corredera_60_params() -> SystemParams:
    """DEMO_CORREDERA_60 — PVC sliding sibling of DEMO_60. Synthetic fixture."""
    return SystemParams(
        system_code="DEMO_CORREDERA_60",
        finishes=("WHITE", "FOILED"),
        depth_mm=d("60.00"),
        material=MaterialType.PVC,
        system_family=SystemFamily.SLIDING,
        effective_profile_articles={
            ProfileRole.FRAME: _article(
                sku="MARCO-CORR",
                role=ProfileRole.FRAME,
                face_width_mm="50.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.RAIL: _article(
                sku="RIEL-CORR",
                role=ProfileRole.RAIL,
                face_width_mm="52.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.SLIDING_SASH: _article(
                sku="HOJA-CORR",
                role=ProfileRole.SLIDING_SASH,
                face_width_mm="42.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.INTERLOCK: _article(
                sku="ENCUENTRO-CORR",
                role=ProfileRole.INTERLOCK,
                face_width_mm="38.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.MULLION_V: _article(
                sku="POSTE-CORR-V",
                role=ProfileRole.MULLION_V,
                face_width_mm="60.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
            ProfileRole.MULLION_H: _article(
                sku="POSTE-CORR-H",
                role=ProfileRole.MULLION_H,
                face_width_mm="60.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
        },
        glazing_bead_rules={
            d("4.00"): GlazingBeadRule(
                glass_thickness_mm=d("4.00"),
                bead_article=_article(
                    sku="JQ-CORR-24",
                    role=ProfileRole.GLAZING_BEAD,
                    face_width_mm="24.00",
                    welding_loss_mm="0.00",
                    reinforcement_gap_mm="15.00",
                ),
                bead_width_mm=d("24.00"),
                gasket_interior_mm=d("3.00"),
                gasket_exterior_mm=d("3.00"),
                cut_add_mm=d("9.00"),
            ),
            d("20.00"): GlazingBeadRule(
                glass_thickness_mm=d("20.00"),
                bead_article=_article(
                    sku="JQ-CORR-14",
                    role=ProfileRole.GLAZING_BEAD,
                    face_width_mm="14.00",
                    welding_loss_mm="0.00",
                    reinforcement_gap_mm="15.00",
                ),
                bead_width_mm=d("14.00"),
                gasket_interior_mm=d("3.00"),
                gasket_exterior_mm=d("3.00"),
                cut_add_mm=d("9.00"),
            ),
        },
        rebate_depth_mm=d("20.00"),
        end_milling_overlap_mm=d("0.00"),
        sash_overlap_mm=d("8.00"),
        glass_clearance_white_mm=d("5.00"),
        glass_clearance_foil_mm=d("5.00"),
        pulley_height_mm=d("14.00"),
        central_overlap_mm=d("45.00"),
        sliding_lateral_clearance_mm=d("0.00"),
        sliding_end_add_mm=d("6.00"),
        corner_bracket_loss_mm=d("0.00"),
        hook_depth_mm=d("0.00"),
        door_threshold_mm=d("0.00"),
        door_bottom_clearance_mm=d("0.00"),
        rail_type=RailType.DUAL,
        sliding_glazing_deduction_width_mm=d("25.00"),
        sliding_glazing_deduction_height_mm=d("25.00"),
        door_leaf_side_clearance_mm=d("0.00"),
        available_hardware_kits=_sliding_kits(
            "KIT-SLIDING-CORR", "KIT-SLIDING-CORR-MONO", "Demo Corredera 60"
        ),
        cut_rules=_sliding_cut_rules(),
        reinforcement_rules=_sliding_reinforcement_rules(),
        typology_limits=_sliding_limits(),
    )


def alu_corredera_params() -> SystemParams:
    """ALU_CORREDERA_70 — mechanically jointed aluminium slider. Synthetic."""

    def _alu(
        *,
        sku: str,
        role: ProfileRole,
        face_width_mm: str,
        weight_kg_m: str = "1.4000",
    ) -> EffectiveProfileArticle:
        return EffectiveProfileArticle(
            sku=sku,
            role=role,
            material=MaterialType.ALUMINIUM,
            face_width_mm=d(face_width_mm),
            welding_loss_mm=d("0.00"),
            reinforcement_gap_mm=d("0.00"),
            weight_kg_m=d(weight_kg_m),
            steel_weight_kg_m=d("0.0000"),
        )

    return SystemParams(
        system_code="ALU_CORREDERA_70",
        depth_mm=d("70.00"),
        material=MaterialType.ALUMINIUM,
        system_family=SystemFamily.SLIDING,
        effective_profile_articles={
            ProfileRole.FRAME: _alu(
                sku="MARCO-AC", role=ProfileRole.FRAME, face_width_mm="45.00", weight_kg_m="1.2500"
            ),
            ProfileRole.RAIL: _alu(
                sku="RIEL-AC", role=ProfileRole.RAIL, face_width_mm="50.00", weight_kg_m="1.4500"
            ),
            ProfileRole.SLIDING_SASH: _alu(
                sku="HOJA-AC",
                role=ProfileRole.SLIDING_SASH,
                face_width_mm="35.00",
                weight_kg_m="1.1000",
            ),
            ProfileRole.INTERLOCK: _alu(
                sku="ENCUENTRO-AC",
                role=ProfileRole.INTERLOCK,
                face_width_mm="30.00",
                weight_kg_m="0.9500",
            ),
            ProfileRole.MULLION_V: _alu(
                sku="POSTE-AC-V",
                role=ProfileRole.MULLION_V,
                face_width_mm="55.00",
                weight_kg_m="1.3000",
            ),
            ProfileRole.MULLION_H: _alu(
                sku="POSTE-AC-H",
                role=ProfileRole.MULLION_H,
                face_width_mm="55.00",
                weight_kg_m="1.3000",
            ),
        },
        glazing_bead_rules={
            d("20.00"): GlazingBeadRule(
                glass_thickness_mm=d("20.00"),
                bead_article=_alu(
                    sku="JQ-AC-10",
                    role=ProfileRole.GLAZING_BEAD,
                    face_width_mm="10.00",
                    weight_kg_m="0.2000",
                ),
                bead_width_mm=d("10.00"),
                gasket_interior_mm=d("3.00"),
                gasket_exterior_mm=d("3.00"),
                cut_add_mm=d("7.00"),
            ),
        },
        rebate_depth_mm=d("20.00"),
        end_milling_overlap_mm=d("0.00"),
        sash_overlap_mm=d("6.00"),
        glass_clearance_white_mm=d("4.00"),
        glass_clearance_foil_mm=d("4.00"),
        pulley_height_mm=d("10.00"),
        central_overlap_mm=d("25.00"),
        sliding_lateral_clearance_mm=d("3.00"),
        sliding_end_add_mm=d("5.00"),
        corner_bracket_loss_mm=d("2.00"),
        hook_depth_mm=d("8.00"),
        door_threshold_mm=d("0.00"),
        door_bottom_clearance_mm=d("0.00"),
        rail_type=RailType.DUAL,
        sliding_glazing_deduction_width_mm=d("18.00"),
        sliding_glazing_deduction_height_mm=d("18.00"),
        door_leaf_side_clearance_mm=d("0.00"),
        available_hardware_kits=_sliding_kits(
            "KIT-AC-SLIDING", "KIT-AC-SLIDING-MONO", "Aluminio Corredera 70"
        ),
        cut_rules=_sliding_cut_rules(),
        reinforcement_rules=[],
        typology_limits=_sliding_limits(),
    )


# ---------------------------------------------------------------------------
# D08 — tipologías avanzadas: synthetic DEMO systems per fabrication family.
# Every fixture below is SEED_SYNTHETIC-grade data: plausible catalog values,
# never certified. The golden tests freeze what the engine computes from them.
# ---------------------------------------------------------------------------


def _d08_beads(prefix: str) -> dict[Decimal, GlazingBeadRule]:
    return {
        d("4.00"): GlazingBeadRule(
            glass_thickness_mm=d("4.00"),
            bead_article=_article(
                sku=f"JQ-{prefix}-24",
                role=ProfileRole.GLAZING_BEAD,
                face_width_mm="24.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="15.00",
            ),
            bead_width_mm=d("24.00"),
            gasket_interior_mm=d("3.00"),
            gasket_exterior_mm=d("3.00"),
            cut_add_mm=d("9.00"),
        ),
        d("24.00"): GlazingBeadRule(
            glass_thickness_mm=d("24.00"),
            bead_article=_article(
                sku=f"JQ-{prefix}-10",
                role=ProfileRole.GLAZING_BEAD,
                face_width_mm="10.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="15.00",
            ),
            bead_width_mm=d("10.00"),
            gasket_interior_mm=d("3.00"),
            gasket_exterior_mm=d("3.00"),
            cut_add_mm=d("9.00"),
        ),
    }


def _limit(
    opening: str,
    min_w: str,
    max_w: str,
    min_h: str,
    max_h: str,
    max_kg: str,
) -> TypologyLimit:
    return TypologyLimit(
        opening_type=opening,
        min_leaf_width_mm=d(min_w),
        max_leaf_width_mm=d(max_w),
        min_leaf_height_mm=d(min_h),
        max_leaf_height_mm=d(max_h),
        max_leaf_weight_kg=d(max_kg),
    )


def _d08_panel_rule() -> dict[str, PanelRule]:
    return {
        "PANEL-SANDWICH-DEMO-24": PanelRule(
            sku="PANEL-SANDWICH-DEMO-24",
            name="Panel Sándwich Demo 24mm",
            kind="SANDWICH_PANEL",
            thickness_mm=d("24.00"),
            weight_kg_m2=d("10.0000"),
        ),
    }


def demo_elevacion_90_params() -> SystemParams:
    """DEMO_ELEVACION_90 — PVC lift-slide (HST). Synthetic DEMO fixture.

    Carretillas escalonadas por peso (≤200 kg dobles, ≤400 kg reforzadas),
    umbral elevador RAIL, y puerta corredera en la misma serie."""
    return SystemParams(
        system_code="DEMO_ELEVACION_90",
        finishes=("WHITE", "FOILED"),
        depth_mm=d("90.00"),
        material=MaterialType.PVC,
        system_family=SystemFamily.LIFT_SLIDE,
        effective_profile_articles={
            ProfileRole.FRAME: _article(
                sku="MARCO-ELEV",
                role=ProfileRole.FRAME,
                face_width_mm="58.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.RAIL: _article(
                sku="RIEL-ELEV",
                role=ProfileRole.RAIL,
                face_width_mm="42.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.SLIDING_SASH: _article(
                sku="HOJA-ELEV",
                role=ProfileRole.SLIDING_SASH,
                face_width_mm="52.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.INTERLOCK: _article(
                sku="ENC-ELEV",
                role=ProfileRole.INTERLOCK,
                face_width_mm="40.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            # Umbral de aluminio para la unidad de puerta (HST y corredera).
            ProfileRole.THRESHOLD: _article(
                sku="UMBRAL-ELEV",
                role=ProfileRole.THRESHOLD,
                face_width_mm="25.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="0.00",
            ),
            ProfileRole.MULLION_V: _article(
                sku="POSTE-ELEV-V",
                role=ProfileRole.MULLION_V,
                face_width_mm="70.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
            ProfileRole.MULLION_H: _article(
                sku="POSTE-ELEV-H",
                role=ProfileRole.MULLION_H,
                face_width_mm="70.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
        },
        glazing_bead_rules=_d08_beads("ELEV"),
        rebate_depth_mm=d("20.00"),
        end_milling_overlap_mm=d("0.00"),
        sash_overlap_mm=d("8.00"),
        glass_clearance_white_mm=d("5.00"),
        glass_clearance_foil_mm=d("5.00"),
        pulley_height_mm=d("20.00"),
        central_overlap_mm=d("55.00"),
        sliding_lateral_clearance_mm=d("0.00"),
        sliding_end_add_mm=d("8.00"),
        corner_bracket_loss_mm=d("0.00"),
        hook_depth_mm=d("0.00"),
        door_threshold_mm=d("25.00"),
        door_bottom_clearance_mm=d("10.00"),
        rail_type=RailType.DUAL,
        sliding_glazing_deduction_width_mm=d("28.00"),
        sliding_glazing_deduction_height_mm=d("28.00"),
        door_leaf_side_clearance_mm=d("6.00"),
        available_panel_rules=_d08_panel_rule(),
        available_hardware_kits=[
            # HST carriages are weight-classed — a 350 kg leaf takes the
            # reinforced set, a 150 kg leaf the standard one.
            HardwareKitRule(
                sku="KIT-HST-200",
                name="Kit Elevable HST 200kg Demo",
                opening_type="LIFT_SLIDE",
                min_leaf_width_mm=d("700"),
                max_leaf_width_mm=d("3200"),
                min_leaf_height_mm=d("800"),
                max_leaf_height_mm=d("2800"),
                max_leaf_weight_kg=d("200"),
                rail_type=RailType.DUAL,
                carriages_qty=2,
                stay_arms_qty=0,
                weight_kg=d("4.80"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-CAR-HST-200",
                        name="Carretilla elevadora 200kg Demo",
                        qty=d("2"),
                        unit="unit",
                        category="ROLLER",
                    ),
                    HardwareComponent(
                        sku="DEMO-MANILLA-ELEV",
                        name="Manilla de elevación Demo",
                        qty=d("1"),
                        unit="unit",
                        category="HANDLE",
                    ),
                    HardwareComponent(
                        sku="DEMO-CIERRE-ELEV",
                        name="Cierre elevable Demo",
                        qty=d("1"),
                        unit="unit",
                        category="LOCK",
                    ),
                ],
            ),
            HardwareKitRule(
                sku="KIT-HST-400",
                name="Kit Elevable HST 400kg Reforzado Demo",
                opening_type="LIFT_SLIDE",
                min_leaf_width_mm=d("700"),
                max_leaf_width_mm=d("3200"),
                min_leaf_height_mm=d("800"),
                max_leaf_height_mm=d("2800"),
                max_leaf_weight_kg=d("400"),
                rail_type=RailType.DUAL,
                carriages_qty=4,
                stay_arms_qty=0,
                weight_kg=d("7.20"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-CAR-HST-400",
                        name="Carretilla elevadora reforzada 400kg Demo",
                        qty=d("4"),
                        unit="unit",
                        category="ROLLER",
                    ),
                    HardwareComponent(
                        sku="DEMO-MANILLA-ELEV",
                        name="Manilla de elevación Demo",
                        qty=d("1"),
                        unit="unit",
                        category="HANDLE",
                    ),
                    HardwareComponent(
                        sku="DEMO-CIERRE-ELEV",
                        name="Cierre elevable Demo",
                        qty=d("1"),
                        unit="unit",
                        category="LOCK",
                    ),
                ],
            ),
            HardwareKitRule(
                sku="KIT-SLIDING-ELEV",
                name="Kit Corredera estándar Elevación 90",
                opening_type="SLIDING",
                min_leaf_width_mm=d("400"),
                max_leaf_width_mm=d("1500"),
                min_leaf_height_mm=d("500"),
                max_leaf_height_mm=d("2500"),
                max_leaf_weight_kg=d("120"),
                rail_type=RailType.DUAL,
                carriages_qty=2,
                stay_arms_qty=0,
                weight_kg=d("2.50"),
                contents=[],
            ),
            # Puerta corredera: carretillas de puerta + cerradura de patio.
            HardwareKitRule(
                sku="KIT-PTA-CORR-ELEV",
                name="Kit Puerta Corredera Elevación 90 Demo",
                opening_type="DOOR_SLIDING",
                min_leaf_width_mm=d("700"),
                max_leaf_width_mm=d("1800"),
                min_leaf_height_mm=d("1700"),
                max_leaf_height_mm=d("2600"),
                max_leaf_weight_kg=d("160"),
                rail_type=RailType.DUAL,
                carriages_qty=2,
                stay_arms_qty=0,
                weight_kg=d("3.40"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-CAR-PTA-ELEV",
                        name="Carretilla puerta corredera Demo",
                        qty=d("2"),
                        unit="unit",
                        category="ROLLER",
                    ),
                    HardwareComponent(
                        sku="DEMO-CERR-PATIO",
                        name="Cerradura patio corredera Demo",
                        qty=d("1"),
                        unit="unit",
                        category="LOCK",
                    ),
                ],
            ),
        ],
        cut_rules=_sliding_cut_rules(),
        reinforcement_rules=_sliding_reinforcement_rules(),
        typology_limits={
            **_sliding_limits(),
            "LIFT_SLIDE": _limit(
                "LIFT_SLIDE", "700.00", "3200.00", "800.00", "2800.00", "400.00"
            ),
            "DOOR:LIFT_SLIDE": _limit(
                "DOOR:LIFT_SLIDE", "700.00", "1800.00", "1700.00", "2600.00", "400.00"
            ),
            "SLIDE": _limit(
                "SLIDE", "400.00", "1500.00", "500.00", "2500.00", "160.00"
            ),
            "DOOR:SLIDE": _limit(
                "DOOR:SLIDE", "700.00", "1800.00", "1700.00", "2600.00", "160.00"
            ),
        },
        opening_capabilities=(
            OpeningCapability(
                movement=OpeningMovement.FIXED,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                max_leaves=2,
            ),
            OpeningCapability(
                movement=OpeningMovement.SLIDE,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
            ),
            OpeningCapability(
                movement=OpeningMovement.LIFT_SLIDE,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
            ),
        ),
    )


def demo_osciloparalela_params() -> SystemParams:
    """DEMO_PSK_90 — PVC osciloparalela (tilt-slide). Synthetic DEMO fixture.

    El kit basculante+paralelo escala por peso de hoja (≤130 kg / ≤200 kg)."""
    return SystemParams(
        system_code="DEMO_PSK_90",
        finishes=("WHITE", "FOILED"),
        depth_mm=d("90.00"),
        material=MaterialType.PVC,
        system_family=SystemFamily.PARALLEL_SLIDE,
        effective_profile_articles={
            ProfileRole.FRAME: _article(
                sku="MARCO-PSK",
                role=ProfileRole.FRAME,
                face_width_mm="52.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.RAIL: _article(
                sku="RIEL-PSK",
                role=ProfileRole.RAIL,
                face_width_mm="45.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.SLIDING_SASH: _article(
                sku="HOJA-PSK",
                role=ProfileRole.SLIDING_SASH,
                face_width_mm="46.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.INTERLOCK: _article(
                sku="ENC-PSK",
                role=ProfileRole.INTERLOCK,
                face_width_mm="36.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.MULLION_V: _article(
                sku="POSTE-PSK-V",
                role=ProfileRole.MULLION_V,
                face_width_mm="66.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
            ProfileRole.MULLION_H: _article(
                sku="POSTE-PSK-H",
                role=ProfileRole.MULLION_H,
                face_width_mm="66.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
        },
        glazing_bead_rules=_d08_beads("PSK"),
        rebate_depth_mm=d("20.00"),
        end_milling_overlap_mm=d("0.00"),
        sash_overlap_mm=d("8.00"),
        glass_clearance_white_mm=d("5.00"),
        glass_clearance_foil_mm=d("5.00"),
        pulley_height_mm=d("16.00"),
        central_overlap_mm=d("42.00"),
        sliding_lateral_clearance_mm=d("0.00"),
        sliding_end_add_mm=d("6.00"),
        corner_bracket_loss_mm=d("0.00"),
        hook_depth_mm=d("0.00"),
        door_threshold_mm=d("22.00"),
        door_bottom_clearance_mm=d("10.00"),
        rail_type=RailType.DUAL,
        sliding_glazing_deduction_width_mm=d("26.00"),
        sliding_glazing_deduction_height_mm=d("26.00"),
        door_leaf_side_clearance_mm=d("6.00"),
        available_hardware_kits=[
            HardwareKitRule(
                sku="KIT-PSK-130",
                name="Kit Osciloparalela PSK 130kg Demo",
                opening_type="PARALLEL_SLIDE",
                min_leaf_width_mm=d("650"),
                max_leaf_width_mm=d("1600"),
                min_leaf_height_mm=d("600"),
                max_leaf_height_mm=d("2400"),
                max_leaf_weight_kg=d("130"),
                rail_type=RailType.DUAL,
                carriages_qty=2,
                stay_arms_qty=0,
                weight_kg=d("3.60"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-BOGIE-PSK",
                        name="Bogie osciloparalelo Demo",
                        qty=d("2"),
                        unit="unit",
                        category="ROLLER",
                    ),
                    HardwareComponent(
                        sku="DEMO-BASC-PSK",
                        name="Brazo basculante PSK Demo",
                        qty=d("2"),
                        unit="unit",
                        category="FITTING",
                    ),
                    HardwareComponent(
                        sku="DEMO-MANILLA-PSK",
                        name="Manilla PSK Demo",
                        qty=d("1"),
                        unit="unit",
                        category="HANDLE",
                    ),
                ],
            ),
            HardwareKitRule(
                sku="KIT-PSK-200",
                name="Kit Osciloparalela PSK 200kg Reforzado Demo",
                opening_type="PARALLEL_SLIDE",
                min_leaf_width_mm=d("650"),
                max_leaf_width_mm=d("2000"),
                min_leaf_height_mm=d("600"),
                max_leaf_height_mm=d("2400"),
                max_leaf_weight_kg=d("200"),
                rail_type=RailType.DUAL,
                carriages_qty=2,
                stay_arms_qty=0,
                weight_kg=d("4.40"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-BOGIE-PSK-R",
                        name="Bogie osciloparalelo reforzado Demo",
                        qty=d("2"),
                        unit="unit",
                        category="ROLLER",
                    ),
                    HardwareComponent(
                        sku="DEMO-BASC-PSK",
                        name="Brazo basculante PSK Demo",
                        qty=d("2"),
                        unit="unit",
                        category="FITTING",
                    ),
                    HardwareComponent(
                        sku="DEMO-MANILLA-PSK",
                        name="Manilla PSK Demo",
                        qty=d("1"),
                        unit="unit",
                        category="HANDLE",
                    ),
                ],
            ),
        ],
        cut_rules=_sliding_cut_rules(),
        reinforcement_rules=_sliding_reinforcement_rules(),
        typology_limits={
            "PARALLEL_SLIDE": _limit(
                "PARALLEL_SLIDE", "650.00", "2000.00", "600.00", "2400.00", "200.00"
            ),
            "DOOR:PARALLEL_SLIDE": _limit(
                "DOOR:PARALLEL_SLIDE",
                "700.00",
                "1400.00",
                "1700.00",
                "2400.00",
                "200.00",
            ),
        },
        opening_capabilities=(
            OpeningCapability(
                movement=OpeningMovement.FIXED,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW,),
                max_leaves=2,
            ),
            OpeningCapability(
                movement=OpeningMovement.PARALLEL_SLIDE,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
            ),
        ),
    )


def demo_plegable_70_params() -> SystemParams:
    """DEMO_PLEGABLE_70 — PVC folding wall. Synthetic DEMO fixture.

    Paquetes de hasta 4 hojas (3+0, 2+1, 2+2…), hoja de paso opcional,
    guía RAIL arriba y abajo, kit de carretillas+bisagras por peso."""
    return SystemParams(
        system_code="DEMO_PLEGABLE_70",
        finishes=("WHITE", "FOILED"),
        depth_mm=d("70.00"),
        material=MaterialType.PVC,
        system_family=SystemFamily.FOLDING,
        effective_profile_articles={
            ProfileRole.FRAME: _article(
                sku="MARCO-FOLD",
                role=ProfileRole.FRAME,
                face_width_mm="60.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.RAIL: _article(
                sku="GUIA-FOLD",
                role=ProfileRole.RAIL,
                face_width_mm="45.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.SASH: _article(
                sku="HOJA-FOLD",
                role=ProfileRole.SASH,
                face_width_mm="55.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.MULLION_V: _article(
                sku="POSTE-FOLD-V",
                role=ProfileRole.MULLION_V,
                face_width_mm="70.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
            ProfileRole.MULLION_H: _article(
                sku="POSTE-FOLD-H",
                role=ProfileRole.MULLION_H,
                face_width_mm="70.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
        },
        glazing_bead_rules=_d08_beads("FOLD"),
        rebate_depth_mm=d("20.00"),
        end_milling_overlap_mm=d("0.00"),
        sash_overlap_mm=d("8.00"),
        glass_clearance_white_mm=d("5.00"),
        glass_clearance_foil_mm=d("5.00"),
        pulley_height_mm=d("12.00"),
        central_overlap_mm=d("40.00"),
        sliding_lateral_clearance_mm=d("0.00"),
        sliding_end_add_mm=d("6.00"),
        corner_bracket_loss_mm=d("0.00"),
        hook_depth_mm=d("0.00"),
        door_threshold_mm=d("20.00"),
        door_bottom_clearance_mm=d("12.00"),
        rail_type=RailType.DUAL,
        sliding_glazing_deduction_width_mm=d("22.00"),
        sliding_glazing_deduction_height_mm=d("22.00"),
        door_leaf_side_clearance_mm=d("6.00"),
        fold_guide_clearance_mm=d("50.00"),
        fold_leaf_clearance_mm=d("6.00"),
        available_panel_rules=_d08_panel_rule(),
        available_hardware_kits=[
            # The pack kit covers the folding leaves — carriages, guides,
            # intermediate hinges; the pack stays inside its declared
            # weight envelope.
            HardwareKitRule(
                sku="KIT-FOLD-80",
                name="Kit Plegable 80kg Demo",
                opening_type="FOLD",
                min_leaf_width_mm=d("400"),
                max_leaf_width_mm=d("1000"),
                min_leaf_height_mm=d("800"),
                max_leaf_height_mm=d("2600"),
                max_leaf_weight_kg=d("80"),
                rail_type=RailType.DUAL,
                carriages_qty=2,
                stay_arms_qty=0,
                weight_kg=d("3.10"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-CAR-FOLD",
                        name="Carretilla de guía plegable Demo",
                        qty=d("2"),
                        unit="unit",
                        category="ROLLER",
                    ),
                    HardwareComponent(
                        sku="DEMO-BISAGRA-FOLD",
                        name="Bisagra intermedia plegable Demo",
                        qty=d("3"),
                        unit="unit",
                        category="HINGE",
                    ),
                ],
            ),
            HardwareKitRule(
                sku="KIT-FOLD-100",
                name="Kit Plegable 100kg Reforzado Demo",
                opening_type="FOLD",
                min_leaf_width_mm=d("400"),
                max_leaf_width_mm=d("1000"),
                min_leaf_height_mm=d("800"),
                max_leaf_height_mm=d("2600"),
                max_leaf_weight_kg=d("100"),
                rail_type=RailType.DUAL,
                carriages_qty=2,
                stay_arms_qty=0,
                weight_kg=d("3.60"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-CAR-FOLD-R",
                        name="Carretilla de guía plegable reforzada Demo",
                        qty=d("2"),
                        unit="unit",
                        category="ROLLER",
                    ),
                    HardwareComponent(
                        sku="DEMO-BISAGRA-FOLD",
                        name="Bisagra intermedia plegable Demo",
                        qty=d("3"),
                        unit="unit",
                        category="HINGE",
                    ),
                ],
            ),
            # La hoja de paso es una hoja practicable con cierre y manilla.
            HardwareKitRule(
                sku="KIT-FOLD-PASO",
                name="Kit Hoja de Paso Plegable Demo",
                opening_type="TURN",
                min_leaf_width_mm=d("400"),
                max_leaf_width_mm=d("1000"),
                min_leaf_height_mm=d("800"),
                max_leaf_height_mm=d("2600"),
                max_leaf_weight_kg=d("100"),
                rail_type=RailType.DUAL,
                carriages_qty=0,
                stay_arms_qty=0,
                weight_kg=d("1.80"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-CIERRE-PASO",
                        name="Cierre hoja de paso Demo",
                        qty=d("1"),
                        unit="unit",
                        category="LOCK",
                    ),
                    HardwareComponent(
                        sku="DEMO-MANILLA-PASO",
                        name="Manilla hoja de paso Demo",
                        qty=d("1"),
                        unit="unit",
                        category="HANDLE",
                    ),
                ],
            ),
            HardwareKitRule(
                sku="KIT-FOLD-PASO-DOOR",
                name="Kit Hoja de Paso Plegable Puerta Demo",
                opening_type="DOOR",
                min_leaf_width_mm=d("600"),
                max_leaf_width_mm=d("1000"),
                min_leaf_height_mm=d("1700"),
                max_leaf_height_mm=d("2600"),
                max_leaf_weight_kg=d("120"),
                rail_type=RailType.DUAL,
                carriages_qty=0,
                stay_arms_qty=0,
                weight_kg=d("2.20"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-CERR-PASO-PTA",
                        name="Cerradura hoja de paso puerta Demo",
                        qty=d("1"),
                        unit="unit",
                        category="LOCK",
                    ),
                    HardwareComponent(
                        sku="DEMO-MANILLA-PASO",
                        name="Manilla hoja de paso Demo",
                        qty=d("1"),
                        unit="unit",
                        category="HANDLE",
                    ),
                ],
            ),
        ],
        cut_rules=_sliding_cut_rules(),
        reinforcement_rules=_sliding_reinforcement_rules(),
        typology_limits={
            "FOLD": _limit(
                "FOLD", "400.00", "1000.00", "800.00", "2600.00", "100.00"
            ),
            "DOOR:FOLD": _limit(
                "DOOR:FOLD", "600.00", "1000.00", "1700.00", "2600.00", "120.00"
            ),
            # The hoja de paso resolves DOOR/TURN kits — its envelope is
            # the pass-door row, not the pack row.
            "DOOR:FOLD:LEFT:OUTWARD:ACTIVE": _limit(
                "DOOR:FOLD:LEFT:OUTWARD:ACTIVE",
                "600.00",
                "1000.00",
                "1700.00",
                "2600.00",
                "120.00",
            ),
        },
        opening_capabilities=(
            OpeningCapability(
                movement=OpeningMovement.FIXED,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                max_leaves=2,
            ),
            OpeningCapability(
                movement=OpeningMovement.FOLD,
                directions=(OpeningDirection.INWARD, OpeningDirection.OUTWARD),
                leaf_roles=(LeafRole.ACTIVE, LeafRole.PASSIVE),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                max_leaves=4,
            ),
        ),
    )


def demo_pivotante_120_params() -> SystemParams:
    """DEMO_PIVOTANTE_120 — pivot door/window. Synthetic DEMO fixture.

    Eje desplazado declarado (`axis_offset_mm`), kits de pivote por peso,
    puerta con panel sándwich."""
    return SystemParams(
        system_code="DEMO_PIVOTANTE_120",
        finishes=("WHITE", "FOILED"),
        depth_mm=d("120.00"),
        material=MaterialType.PVC,
        system_family=SystemFamily.PIVOT,
        effective_profile_articles={
            ProfileRole.FRAME: _article(
                sku="MARCO-PIV",
                role=ProfileRole.FRAME,
                face_width_mm="75.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.SASH: _article(
                sku="HOJA-PIV-V",
                role=ProfileRole.SASH,
                face_width_mm="70.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.DOOR_SASH: _article(
                sku="HOJA-PIV",
                role=ProfileRole.DOOR_SASH,
                face_width_mm="95.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.THRESHOLD: _article(
                sku="UMBRAL-PIV",
                role=ProfileRole.THRESHOLD,
                face_width_mm="25.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="0.00",
            ),
            ProfileRole.MULLION_V: _article(
                sku="POSTE-PIV-V",
                role=ProfileRole.MULLION_V,
                face_width_mm="80.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
            ProfileRole.MULLION_H: _article(
                sku="POSTE-PIV-H",
                role=ProfileRole.MULLION_H,
                face_width_mm="80.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
        },
        glazing_bead_rules=_d08_beads("PIV"),
        rebate_depth_mm=d("20.00"),
        end_milling_overlap_mm=d("0.00"),
        sash_overlap_mm=d("8.00"),
        glass_clearance_white_mm=d("5.00"),
        glass_clearance_foil_mm=d("5.00"),
        pulley_height_mm=d("12.00"),
        central_overlap_mm=d("40.00"),
        sliding_lateral_clearance_mm=d("0.00"),
        sliding_end_add_mm=d("6.00"),
        corner_bracket_loss_mm=d("0.00"),
        hook_depth_mm=d("0.00"),
        door_threshold_mm=d("25.00"),
        door_bottom_clearance_mm=d("8.00"),
        door_leaf_side_clearance_mm=d("6.00"),
        pivot_clearance_mm=d("10.00"),
        rail_type=RailType.DUAL,
        sliding_glazing_deduction_width_mm=d("24.00"),
        sliding_glazing_deduction_height_mm=d("24.00"),
        available_panel_rules=_d08_panel_rule(),
        available_hardware_kits=[
            HardwareKitRule(
                sku="KIT-PIV-300",
                name="Kit Pivotante Puerta 300kg Demo",
                opening_type="PIVOT",
                min_leaf_width_mm=d("900"),
                max_leaf_width_mm=d("2000"),
                min_leaf_height_mm=d("1900"),
                max_leaf_height_mm=d("3000"),
                max_leaf_weight_kg=d("300"),
                rail_type=RailType.DUAL,
                carriages_qty=0,
                stay_arms_qty=0,
                weight_kg=d("6.50"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-PIVOT-INF",
                        name="Pivote inferior 300kg Demo",
                        qty=d("1"),
                        unit="unit",
                        category="FITTING",
                    ),
                    HardwareComponent(
                        sku="DEMO-PIVOT-SUP",
                        name="Pivote superior guía Demo",
                        qty=d("1"),
                        unit="unit",
                        category="FITTING",
                    ),
                    HardwareComponent(
                        sku="DEMO-TIRADOR-PIV",
                        name="Tirador pivotante Demo",
                        qty=d("1"),
                        unit="unit",
                        category="HANDLE",
                    ),
                ],
            ),
            HardwareKitRule(
                sku="KIT-PIV-80",
                name="Kit Pivotante Ventana 80kg Demo",
                opening_type="PIVOT",
                min_leaf_width_mm=d("500"),
                max_leaf_width_mm=d("1400"),
                min_leaf_height_mm=d("500"),
                max_leaf_height_mm=d("1900"),
                max_leaf_weight_kg=d("80"),
                rail_type=RailType.DUAL,
                carriages_qty=0,
                stay_arms_qty=0,
                weight_kg=d("2.10"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-PIVOT-V-80",
                        name="Pivote ventana 80kg Demo",
                        qty=d("2"),
                        unit="unit",
                        category="FITTING",
                    ),
                ],
            ),
        ],
        cut_rules=_sliding_cut_rules(),
        reinforcement_rules=_sliding_reinforcement_rules(),
        typology_limits={
            "PIVOT_V": _limit(
                "PIVOT_V", "500.00", "1400.00", "500.00", "1900.00", "80.00"
            ),
            "PIVOT_H": _limit(
                "PIVOT_H", "500.00", "1400.00", "500.00", "1900.00", "80.00"
            ),
            "DOOR:PIVOT_V": _limit(
                "DOOR:PIVOT_V", "900.00", "2000.00", "1900.00", "3000.00", "300.00"
            ),
        },
        opening_capabilities=(
            OpeningCapability(
                movement=OpeningMovement.FIXED,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                max_leaves=2,
            ),
            OpeningCapability(
                movement=OpeningMovement.PIVOT_V,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.DOOR,),
            ),
            OpeningCapability(
                movement=OpeningMovement.PIVOT_H,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
            ),
        ),
    )


def demo_guillotina_60_params() -> SystemParams:
    """DEMO_GUILLOTINA_60 — PVC vertical slider. Synthetic DEMO fixture.

    Hojas apiladas TOP/BOTTOM en canal lateral; contrapesos o muelles
    según clase de peso declarada."""
    return SystemParams(
        system_code="DEMO_GUILLOTINA_60",
        finishes=("WHITE", "FOILED"),
        depth_mm=d("60.00"),
        material=MaterialType.PVC,
        system_family=SystemFamily.VERTICAL_SLIDE,
        effective_profile_articles={
            ProfileRole.FRAME: _article(
                sku="MARCO-GUI",
                role=ProfileRole.FRAME,
                face_width_mm="50.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.SLIDING_SASH: _article(
                sku="HOJA-GUI",
                role=ProfileRole.SLIDING_SASH,
                face_width_mm="38.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.INTERLOCK: _article(
                sku="TRAVES-GUI",
                role=ProfileRole.INTERLOCK,
                face_width_mm="34.00",
                welding_loss_mm="6.00",
                reinforcement_gap_mm="15.00",
            ),
            ProfileRole.MULLION_V: _article(
                sku="POSTE-GUI-V",
                role=ProfileRole.MULLION_V,
                face_width_mm="60.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
            ProfileRole.MULLION_H: _article(
                sku="POSTE-GUI-H",
                role=ProfileRole.MULLION_H,
                face_width_mm="60.00",
                welding_loss_mm="0.00",
                reinforcement_gap_mm="5.00",
            ),
        },
        glazing_bead_rules=_d08_beads("GUI"),
        rebate_depth_mm=d("20.00"),
        end_milling_overlap_mm=d("0.00"),
        sash_overlap_mm=d("8.00"),
        glass_clearance_white_mm=d("5.00"),
        glass_clearance_foil_mm=d("5.00"),
        # Canal lateral = la autoridad sliding del sistema: pulley_height
        # declara la profundidad del canal por lado.
        pulley_height_mm=d("14.00"),
        central_overlap_mm=d("30.00"),
        sliding_lateral_clearance_mm=d("4.00"),
        sliding_end_add_mm=d("6.00"),
        corner_bracket_loss_mm=d("0.00"),
        hook_depth_mm=d("0.00"),
        door_threshold_mm=d("0.00"),
        door_bottom_clearance_mm=d("0.00"),
        rail_type=RailType.DUAL,
        sliding_glazing_deduction_width_mm=d("20.00"),
        sliding_glazing_deduction_height_mm=d("20.00"),
        door_leaf_side_clearance_mm=d("0.00"),
        available_hardware_kits=[
            # Dos clases de balance: contrapeso hasta 60 kg, muelles
            # (espiral) hasta 40 kg — el kit ganador se elige por peso.
            HardwareKitRule(
                sku="KIT-GUI-CONTRAPESO",
                name="Kit Guillotina Contrapeso 60kg Demo",
                opening_type="VERTICAL_SLIDE",
                min_leaf_width_mm=d("400"),
                max_leaf_width_mm=d("1400"),
                min_leaf_height_mm=d("300"),
                max_leaf_height_mm=d("1400"),
                max_leaf_weight_kg=d("60"),
                rail_type=RailType.DUAL,
                carriages_qty=0,
                stay_arms_qty=0,
                weight_kg=d("5.80"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-CONTRAPESO-GUI",
                        name="Contrapeso guillotina Demo",
                        qty=d("2"),
                        unit="unit",
                        category="FITTING",
                    ),
                    HardwareComponent(
                        sku="DEMO-CORDON-GUI",
                        name="Cordón/polea guillotina Demo",
                        qty=d("2"),
                        unit="unit",
                        category="FITTING",
                    ),
                ],
            ),
            HardwareKitRule(
                sku="KIT-GUI-MUELLES",
                name="Kit Guillotina Muelles 40kg Demo",
                opening_type="VERTICAL_SLIDE",
                min_leaf_width_mm=d("400"),
                max_leaf_width_mm=d("1200"),
                min_leaf_height_mm=d("300"),
                max_leaf_height_mm=d("1200"),
                max_leaf_weight_kg=d("40"),
                rail_type=RailType.DUAL,
                carriages_qty=0,
                stay_arms_qty=0,
                weight_kg=d("2.40"),
                contents=[
                    HardwareComponent(
                        sku="DEMO-ESPIRAL-GUI",
                        name="Balance espiral guillotina Demo",
                        qty=d("2"),
                        unit="unit",
                        category="FITTING",
                    ),
                ],
            ),
        ],
        cut_rules=_sliding_cut_rules(),
        reinforcement_rules=_sliding_reinforcement_rules(),
        typology_limits={
            "VERTICAL_SLIDE": _limit(
                "VERTICAL_SLIDE", "400.00", "1400.00", "300.00", "1400.00", "60.00"
            ),
        },
        opening_capabilities=(
            OpeningCapability(
                movement=OpeningMovement.FIXED,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW,),
                max_leaves=2,
            ),
            OpeningCapability(
                movement=OpeningMovement.VERTICAL_SLIDE,
                leaf_roles=(LeafRole.SINGLE,),
                unit_kinds=(UnitKind.WINDOW,),
                max_leaves=2,
            ),
        ),
    )


def demo_puerta_corredera_params() -> SystemParams:
    """DEMO_PUERTA_CORREDERA_70 — sliding patio door. Synthetic DEMO fixture.

    Una serie corredera que además declara la hoja corredera de puerta:
    unidad DOOR con umbral, kit DOOR_SLIDING y cerradura de patio."""
    params = demo_elevacion_90_params().model_copy(
        update={
            "system_code": "DEMO_PUERTA_CORREDERA_70",
            "system_family": SystemFamily.SLIDING,
            "opening_capabilities": (
                OpeningCapability(
                    movement=OpeningMovement.FIXED,
                    leaf_roles=(LeafRole.SINGLE,),
                    unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                    max_leaves=2,
                ),
                OpeningCapability(
                    movement=OpeningMovement.SLIDE,
                    leaf_roles=(LeafRole.SINGLE,),
                    unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                ),
            ),
        }
    )
    return params
