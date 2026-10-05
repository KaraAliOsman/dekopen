"""D02 — structured glass composition: notation round-trip, derived
quantities and rule evaluation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from dekopen_engine import (
    ChamberGas,
    GlassChamber,
    GlassCoating,
    GlassComposition,
    GlassLamina,
    GlassPieceContext,
    GlassSafetyRule,
    GlassTypeLimit,
    InterlayerKind,
    SpacerKind,
    billable_area_m2,
    build_glass_piece,
    composition_from_dict,
    composition_to_dict,
    evaluate_glass_limits,
    evaluate_glass_safety,
    format_glass_notation,
    glass_price_lines,
    GlassSurchargeRate,
    GlassSurchargeSelection,
    parse_glass_notation,
    requires_exact_cut,
)


# -- Notation ida-vuelta: 30 real workshop spellings -------------------------

ROUND_TRIP_CASES = [
    "4 / 12 aire / 4",
    "5 / 12 Ar / 4 Low-E (c3)",
    "3+3 PVB 0,38",
    "4+4 / 16 / 6 templado",
    "DVH 5-12-5",
    "4-16-4",
    "6",
    "4-12-4",
    "DVH 4-16-4 argon",
    "4+4 / 12 / 4 templado",
    "3+3.1",
    "44.2",
    "5 bronce / 12 / 4",
    "4 low-e (c2) / 16 Ar / 4",
    "6+6 PVB acústico",
    "4-12-3+3",
    "4-16-4-16-4",
    "5 / 12 borde caliente / 4 low-e (c3)",
    "termopanel 4-16-4",
    "vidrio hermético 5-14-5",
    "8",
    "10",
    "4 espejo",
    "5 satinado / 12 / 4",
    "4+4 pvb 0,76 / 12 / 4",
    "6 laminado",
    "4 reflectivo / 16 / 4",
    "5 gris",
    "3+3 / 9 / 3+3",
    "H. 4-16-4",
]


@pytest.mark.parametrize("notation", ROUND_TRIP_CASES)
def test_notation_round_trip(notation: str) -> None:
    composition = parse_glass_notation(notation)
    assert composition is not None, notation
    formatted = format_glass_notation(composition)
    reparsed = parse_glass_notation(formatted)
    assert reparsed == composition, f"{notation!r} -> {formatted!r}"


def test_case_and_decimal_variants() -> None:
    assert parse_glass_notation("dvh 5-12-5") == parse_glass_notation("DVH 5-12-5")
    assert parse_glass_notation("3+3 PVB 0.38") == parse_glass_notation(
        "3+3 PVB 0,38"
    )
    assert parse_glass_notation(" 4/12/4 ") == parse_glass_notation("4 / 12 / 4")


def test_unreadable_notations_stay_unknown() -> None:
    for raw in (
        "", "DVH", "x-16-4", "hermetico doble", "4-16-4-16", "vidrio",
        "4 / doce / 4", "abc", "4-0-4", "7 laminado",
    ):
        assert parse_glass_notation(raw) is None, raw


# -- Structured model semantics ----------------------------------------------

def test_lamina_semantics() -> None:
    composition = parse_glass_notation("3+3 PVB 0,38")
    assert composition is not None
    lamina = composition.laminae[0]
    assert lamina.is_laminate
    assert lamina.panes == [Decimal("3"), Decimal("3")]
    assert lamina.interlayer is InterlayerKind.PVB_038
    assert lamina.glass_thickness_mm == Decimal("6")
    assert lamina.total_thickness_mm == Decimal("6.38")


def test_composition_totals_and_weight() -> None:
    dvh = parse_glass_notation("4-16-4")
    assert dvh is not None
    assert dvh.is_igu and not dvh.has_laminate
    assert dvh.net_thickness_mm() == Decimal("8")
    assert dvh.total_thickness_mm() == Decimal("24")
    assert dvh.weight_kg_m2() == Decimal("20")

    laminated = parse_glass_notation("4 / 12 / 3+3 PVB 0,38")
    assert laminated is not None
    assert laminated.net_thickness_mm() == Decimal("10")
    assert laminated.total_thickness_mm() == Decimal("22.38")
    # Glass 10 mm x 2.50 + PVB 0.38 x 1.07 = 25.4066 kg/m2.
    assert laminated.weight_kg_m2() == Decimal("25.4066")


def test_tempered_and_coating_flags() -> None:
    composition = parse_glass_notation("5 / 12 Ar / 4 Low-E (c3) templado")
    assert composition is not None
    assert composition.has_tempered
    inner = composition.laminae[1]
    assert inner.coating is GlassCoating.LOW_E
    assert inner.coating_face == 3
    assert composition.chambers[0].gas is ChamberGas.ARGON


def test_warm_edge_spacer() -> None:
    composition = parse_glass_notation("5 / 12 borde caliente / 4")
    assert composition is not None
    assert composition.chambers[0].spacer is SpacerKind.WARM_EDGE


def test_dict_round_trip() -> None:
    composition = parse_glass_notation("5 / 12 Ar / 4 Low-E (c3)")
    assert composition is not None
    restored = composition_from_dict(composition_to_dict(composition))
    assert restored == composition


def test_malformed_composition_rejected() -> None:
    with pytest.raises(ValueError):
        GlassComposition(
            layers=[
                GlassLamina(panes=[Decimal("4")]),
                GlassLamina(panes=[Decimal("4")]),
            ]
        )
    with pytest.raises(ValueError):
        GlassComposition(
            layers=[
                GlassLamina(panes=[Decimal("4")]),
                GlassChamber(width_mm=Decimal("12")),
            ]
        )


def test_coating_face_must_belong_to_its_lamina() -> None:
    # Face 3 belongs to the inner lamina of a DVH — declaring it on the
    # outer one is a data error, rejected at construction.
    with pytest.raises(ValueError):
        GlassComposition(
            layers=[
                GlassLamina(
                    panes=[Decimal("4")],
                    coating=GlassCoating.LOW_E,
                    coating_face=3,
                ),
                GlassChamber(width_mm=Decimal("12")),
                GlassLamina(panes=[Decimal("4")]),
            ]
        )
    # …while the same face on the inner lamina is legitimate.
    assert (
        GlassComposition(
            layers=[
                GlassLamina(panes=[Decimal("5")]),
                GlassChamber(width_mm=Decimal("12")),
                GlassLamina(
                    panes=[Decimal("4")],
                    coating=GlassCoating.LOW_E,
                    coating_face=3,
                ),
            ]
        )
        .laminae[1]
        .coating_face
        == 3
    )


# -- Derived quantities on the piece ------------------------------------------

def test_piece_carries_package_and_pvb_weight() -> None:
    glass = build_glass_piece(
        bay_id="lam",
        width_mm=Decimal("1000"),
        height_mm=Decimal("1000"),
        glass_spec="4 / 12 / 3+3 PVB 0,38",
    )
    assert glass.thickness_net_mm == Decimal("10.00")
    assert glass.thickness_total_mm == Decimal("22.38")
    # 1 m2 x 25.4066 kg/m2 — the PVB film mass is inside.
    assert glass.weight_kg == Decimal("25.41")
    assert glass.composition is not None and glass.composition.has_laminate


def test_piece_without_pvb_keeps_canonical_weight() -> None:
    glass = build_glass_piece(
        bay_id="dvh",
        width_mm=Decimal("1000"),
        height_mm=Decimal("1000"),
        glass_spec="4-12-4",
    )
    assert glass.weight_kg == Decimal("20.00")
    assert glass.thickness_total_mm == Decimal("20.00")


def test_weight_uses_exact_area_against_published_area() -> None:
    glass = build_glass_piece(
        bay_id="anti_double_rounding",
        width_mm=Decimal("100.00"),
        height_mm=Decimal("76.50"),
        glass_spec="6",
    )
    naive = (
        glass.area_m2 * Decimal("6") * Decimal("2.50")
    ).quantize(Decimal("0.01"))
    assert glass.area_m2 == Decimal("0.0077")
    assert glass.weight_kg == Decimal("0.11")
    assert naive == Decimal("0.12")
    assert glass.weight_kg != naive


# -- Safety rules --------------------------------------------------------------

def _ctx(**kwargs: object) -> GlassPieceContext:
    base: dict[str, object] = dict(
        bay_id="bay",
        width_mm=Decimal("1000"),
        height_mm=Decimal("1000"),
        area_m2=Decimal("1.0"),
    )
    base.update(kwargs)
    return GlassPieceContext.model_validate(base)


def test_door_rule_warns_on_ordinary_glass() -> None:
    rules = [
        GlassSafetyRule(
            code="NCH135-DOOR",
            title="Puertas vidriadas requieren vidrio de seguridad",
            requires_door=True,
            required_safety="TEMPERED",
            source_ref="NCh 135/2",
        )
    ]
    ordinary = parse_glass_notation("4")
    findings = evaluate_glass_safety(
        _ctx(opening_type="DOOR_ENTRY"), ordinary, rules
    )
    assert len(findings) == 1
    assert findings[0].rule_code == "NCH135-DOOR"
    assert findings[0].severity == "WARNING"
    assert findings[0].source_ref == "NCh 135/2"
    assert findings[0].required_safety == "TEMPERED"


def test_tempered_composition_satisfies_door_rule() -> None:
    rules = [
        GlassSafetyRule(
            code="NCH135-DOOR",
            title="Puertas vidriadas requieren vidrio de seguridad",
            requires_door=True,
            required_safety="TEMPERED",
            source_ref="NCh 135/2",
        )
    ]
    tempered = parse_glass_notation("4 templado")
    assert evaluate_glass_safety(
        _ctx(opening_type="DOOR_ENTRY"), tempered, rules
    ) == []


def test_low_pane_rule_fires_under_800mm() -> None:
    rules = [
        GlassSafetyRule(
            code="NCH135-LOW",
            title="Paño vidriado bajo 800 mm del nivel de piso",
            sill_below_mm=Decimal("800"),
            required_safety="LAMINATED",
            source_ref="NCh 135/2",
        )
    ]
    low = evaluate_glass_safety(
        _ctx(sill_mm=Decimal("300")), parse_glass_notation("4"), rules
    )
    assert len(low) == 1
    assert (
        evaluate_glass_safety(
            _ctx(sill_mm=Decimal("1200")), parse_glass_notation("4"), rules
        )
        == []
    )
    laminate = parse_glass_notation("3+3 PVB 0,38")
    assert evaluate_glass_safety(
        _ctx(sill_mm=Decimal("300")), laminate, rules
    ) == []


def test_adjacent_door_rule() -> None:
    rules = [
        GlassSafetyRule(
            code="NCH135-SIDELIGHT",
            title="Panel lateral adyacente a puerta",
            requires_adjacent_door=True,
            required_safety="LAMINATED",
            source_ref="NCh 135/2",
        )
    ]
    assert evaluate_glass_safety(
        _ctx(adjacent_door=True), parse_glass_notation("4"), rules
    ) != []
    assert evaluate_glass_safety(
        _ctx(adjacent_door=False), parse_glass_notation("4"), rules
    ) == []


def test_safety_class_only_by_declaration() -> None:
    rules = [
        GlassSafetyRule(
            code="NCH135-CLASS-A",
            title="Gran ventanal exige clase A",
            min_area_m2=Decimal("2.0"),
            required_safety="SAFETY_CLASS_A",
            source_ref="NCh 135/2",
        )
    ]
    ctx = _ctx(area_m2=Decimal("3.0"))
    # The engine never infers the class — only a declared product passes.
    assert evaluate_glass_safety(
        ctx, parse_glass_notation("4 templado"), rules
    ) != []
    assert evaluate_glass_safety(
        ctx, parse_glass_notation("4"), rules,
        declared_safety_class="A",
    ) == []


def test_mandatory_rule_is_error_severity() -> None:
    rules = [
        GlassSafetyRule(
            code="NCH135-DOOR",
            title="Puerta",
            requires_door=True,
            required_safety="TEMPERED",
            severity="MANDATORY",
        )
    ]
    findings = evaluate_glass_safety(
        _ctx(opening_type="DOOR_ENTRY"), parse_glass_notation("4"), rules
    )
    assert findings[0].severity == "MANDATORY"


# -- Type limits ----------------------------------------------------------------

def test_type_limit_breach_warns() -> None:
    limits = [
        GlassTypeLimit(
            code="LIM-FLOAT-4",
            lamina_kind="FLOAT",
            thickness_max_mm=Decimal("4"),
            max_area_m2=Decimal("2.0"),
            source_ref="proveedor",
        )
    ]
    big = evaluate_glass_limits(
        _ctx(area_m2=Decimal("2.5")), parse_glass_notation("4"), limits
    )
    assert len(big) == 1 and "max_area" in big[0].message
    assert (
        evaluate_glass_limits(
            _ctx(area_m2=Decimal("1.5")), parse_glass_notation("4"), limits
        )
        == []
    )


def test_exact_cut_on_tempered() -> None:
    assert requires_exact_cut(parse_glass_notation("4 templado"), [])
    assert not requires_exact_cut(parse_glass_notation("4"), [])


def test_aspect_ratio_limit() -> None:
    limits = [
        GlassTypeLimit(
            code="LIM-ASPECT",
            lamina_kind="ANY",
            max_aspect_ratio=Decimal("5"),
        )
    ]
    skinny = GlassPieceContext(
        bay_id="b", width_mm=Decimal("300"), height_mm=Decimal("2000"),
        area_m2=Decimal("0.6"),
    )
    findings = evaluate_glass_limits(
        skinny, parse_glass_notation("4"), limits
    )
    assert len(findings) == 1 and "aspect" in findings[0].message


# -- Pricing --------------------------------------------------------------------

def test_billable_area_respects_product_minimum() -> None:
    assert billable_area_m2(Decimal("0.20"), Decimal("0.30")) == Decimal("0.30")
    assert billable_area_m2(Decimal("0.50"), Decimal("0.30")) == Decimal("0.50")
    assert billable_area_m2(Decimal("0.20"), None) == Decimal("0.20")


def test_price_lines_base_and_tempered_surcharge() -> None:
    tempered_product = [
        GlassSurchargeRate(kind="TEMPERED", unit="M2", amount=Decimal("1500"))
    ]
    lines = glass_price_lines(
        sku="DVH-24-T",
        cost_per_m2=Decimal("25000"),
        exact_area_m2=Decimal("0.10"),
        min_area_m2=Decimal("0.30"),
        surcharges=tempered_product,
        selections=None,
        composition=parse_glass_notation("4-16-4 templado"),
        width_mm=Decimal("400"),
        height_mm=Decimal("250"),
    )
    assert lines[0].kind == "GLASS"
    assert lines[0].quantity == Decimal("0.3000")
    assert lines[0].cost == Decimal("7500.0000")
    assert lines[1].kind == "GLASS_TEMPERED"
    assert lines[1].cost == Decimal("450.0000")


def test_price_lines_polish_drill_palillaje() -> None:
    rates = [
        GlassSurchargeRate(
            kind="EDGE_POLISH", unit="M", amount=Decimal("3000")
        ),
        GlassSurchargeRate(kind="DRILL", unit="EA", amount=Decimal("2000")),
        GlassSurchargeRate(
            kind="PALILLAJE", unit="CROSS", amount=Decimal("1200")
        ),
    ]
    selections = [
        GlassSurchargeSelection(
            kind="EDGE_POLISH", edges=["top", "bottom"]
        ),
        GlassSurchargeSelection(kind="DRILL", count=4),
        GlassSurchargeSelection(kind="PALILLAJE", columns=3, rows=1),
    ]
    lines = glass_price_lines(
        sku="MONO-4",
        cost_per_m2=Decimal("10000"),
        exact_area_m2=Decimal("0.75"),
        min_area_m2=None,
        surcharges=rates,
        selections=selections,
        composition=parse_glass_notation("4"),
        width_mm=Decimal("500"),
        height_mm=Decimal("1500"),
    )
    kinds = [line.kind for line in lines]
    assert kinds == [
        "GLASS", "GLASS_EDGE_POLISH", "GLASS_DRILL", "GLASS_PALILLAJE"
    ]
    polish = lines[1]
    assert polish.quantity == Decimal("1.0000")  # 2 x 500 mm
    assert polish.cost == Decimal("3000.0000")
    assert lines[2].quantity == Decimal("4.0000")
    assert lines[2].cost == Decimal("8000.0000")
    assert lines[3].quantity == Decimal("3.0000")  # 3 columns x 1 row
    assert lines[3].cost == Decimal("3600.0000")
