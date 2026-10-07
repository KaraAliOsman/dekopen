"""P18 — golden Uw ISO 10077-1, UNKNOWN y cumplimiento OGUC 4.1.10."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from dekopen_engine.glass_composition import parse_glass_notation
from dekopen_engine.models import (
    EngineResult,
    GlassPiece,
    GlassProduct,
    MaterialType,
    PanelPiece,
    PlanPoint,
    ProfileCut,
    ProfileRole,
    SystemParams,
)
from dekopen_engine.thermal import (
    FrameUfInput,
    PerformanceTestInput,
    SpacerPsiInput,
    ThermalCatalogInput,
    ThermalModuleInput,
    UwComputation,
    compute_uw,
    orientation_compliance,
    position_compliance,
    resolve_classes,
)


def d(value: str) -> Decimal:
    return Decimal(value)


def _params_with_glass(
    sku: str = "DVH-1",
    ug: str | None = "1.1",
    *,
    provenance: str = "MANUAL",
    verified: bool = True,
) -> SystemParams:
    product = GlassProduct(
        sku=sku,
        name="DVH 4-12-4",
        composition=parse_glass_notation("4-12-4"),
        ug_w_m2k=d(ug) if ug is not None else None,
        weight_kg_m2=d("20.00"),
        data_provenance=provenance,
        verified=verified,
    )
    return SystemParams.model_construct(
        base_color_price=[],
        effective_profile_articles={},
        glass_products={sku: product},
    )


def _fixed_result() -> EngineResult:
    """Ventana fija 1200×800: paño vidrio 1040×640, marco 45mm cara."""
    return EngineResult(
        profile_cuts=[
            ProfileCut(
                sku="MARCO-1", role=ProfileRole.FRAME,
                material=MaterialType.PVC,
                length_mm=d("1200"), angle_left=d("45"), angle_right=d("45"),
                qty=2,
            ),
            ProfileCut(
                sku="MARCO-1", role=ProfileRole.FRAME,
                material=MaterialType.PVC,
                length_mm=d("800"), angle_left=d("45"), angle_right=d("45"),
                qty=2,
            ),
            ProfileCut(
                sku="BEAD-1", role=ProfileRole.GLAZING_BEAD,
                material=MaterialType.PVC,
                length_mm=d("1040"), angle_left=d("45"), angle_right=d("45"),
                qty=2, bay_id="b1",
            ),
            ProfileCut(
                sku="BEAD-1", role=ProfileRole.GLAZING_BEAD,
                material=MaterialType.PVC,
                length_mm=d("640"), angle_left=d("45"), angle_right=d("45"),
                qty=2, bay_id="b1",
            ),
        ],
        reinforcements=[],
        glasses=[
            GlassPiece(
                bay_id="b1",
                width_mm=d("1040"),
                height_mm=d("640"),
                area_m2=d("0.6656"),
                weight_kg=d("13.312"),
                thickness_net_mm=d("4"),
                glass_spec="4-12-4",
                article_sku="DVH-1",
                composition=parse_glass_notation("4-12-4"),
            ),
        ],
    )


def _catalog(*, verified: bool = True, provenance: str = "MANUAL") -> ThermalCatalogInput:
    return ThermalCatalogInput(
        frame_uf={
            "ALL": FrameUfInput(
                member_group="ALL", uf_w_m2k=d("1.4"),
                provenance=provenance, verified=verified,
                source="Ficha técnica fabricante",
            ),
        },
        spacers={
            "ALUMINIUM": SpacerPsiInput(
                code="ALUMINIUM", name="Separador aluminio",
                psi_w_m_k=d("0.06"), provenance=provenance, verified=verified,
            ),
        },
    )


def _module() -> ThermalModuleInput:
    return ThermalModuleInput(result=_fixed_result(), area_m2=d("0.96"))


# ─── Golden ISO 10077-1 ─────────────────────────────────────────────────────

def test_uw_golden_fixed_window() -> None:
    """Caso calculado a mano (verificación numérica del encargo):

    Aw = 1,20 × 0,80 = 0,96 m²
    Ag = 1,04 × 0,64 = 0,6656 m² · Ug = 1,1
    Af = 0,96 − 0,6656 = 0,2944 m² · Uf = 1,4
    lg = 2 × (1,04 + 0,64) = 3,36 m · Ψg = 0,06

    Uw = (0,6656×1,1 + 0,2944×1,4 + 3,36×0,06) / 0,96
       = (0,73216 + 0,41216 + 0,2016) / 0,96
       = 1,34592 / 0,96 = 1,402 → 1,40 W/m²K
    """
    params = _params_with_glass()
    uw = compute_uw(
        modules=[_module()],
        params=params,
        catalog=_catalog(),
        face_widths={"MARCO-1": d("45"), "BEAD-1": d("15")},
    )
    assert uw.status == "OK"
    assert uw.uw_w_m2k == d("1.40")
    assert uw.ag_m2 == d("0.6656")
    assert uw.af_m2 == d("0.2944")
    assert uw.lg_m == d("3.3600")
    assert uw.authority == "VERIFIED"
    assert uw.panes[0].ug_authority == "VERIFIED"
    assert uw.frame[0].uf_w_m2k == d("1.4")


def test_uw_unknown_without_ug() -> None:
    params = _params_with_glass(ug=None)
    uw = compute_uw(
        modules=[_module()], params=params, catalog=_catalog(),
        face_widths={"MARCO-1": d("45")},
    )
    assert uw.status == "UNKNOWN"
    assert uw.uw_w_m2k is None
    assert any(m.code == "UG" for m in uw.missing)


def test_uw_unknown_without_spacer_psi() -> None:
    catalog = ThermalCatalogInput(
        frame_uf={"ALL": FrameUfInput(member_group="ALL", uf_w_m2k=d("1.4"))},
        spacers={},
    )
    uw = compute_uw(
        modules=[_module()], params=_params_with_glass(), catalog=catalog,
        face_widths={"MARCO-1": d("45")},
    )
    assert uw.status == "UNKNOWN"
    assert any(m.code == "PSI" for m in uw.missing)


def test_uw_unknown_with_opaque_panel() -> None:
    result = _fixed_result()
    result.panels.append(PanelPiece(
        sku="PANEL-1", name="Panel sandwich", bay_id="b1",
        width_mm=d("1040"), height_mm=d("640"), area_m2=d("0.6656"),
        weight_kg=None,
    ))
    uw = compute_uw(
        modules=[ThermalModuleInput(result=result, area_m2=d("0.96"))],
        params=_params_with_glass(), catalog=_catalog(),
        face_widths={"MARCO-1": d("45")},
    )
    assert uw.status == "UNKNOWN"
    assert any(m.code == "PANEL_U" for m in uw.missing)


def test_uw_demo_authority_marks_worst() -> None:
    uw = compute_uw(
        modules=[_module()],
        params=_params_with_glass(provenance="SEED_SYNTHETIC", verified=False),
        catalog=_catalog(),
        face_widths={"MARCO-1": d("45")},
    )
    assert uw.status == "OK"
    assert uw.authority == "DEMO"


def test_uw_shape_piece_uses_polygon_perimeter() -> None:
    """Pieza con forma: el perímetro sale del polígono, no del bounding box."""
    shape = [
        PlanPoint(x_mm=d("0"), y_mm=d("0")),
        PlanPoint(x_mm=d("1000"), y_mm=d("0")),
        PlanPoint(x_mm=d("1000"), y_mm=d("600")),
        PlanPoint(x_mm=d("0"), y_mm=d("600")),
    ]
    result = EngineResult(
        profile_cuts=[
            ProfileCut(
                sku="MARCO-1", role=ProfileRole.FRAME,
                material=MaterialType.PVC,
                length_mm=d("1000"), angle_left=d("45"), angle_right=d("45"),
                qty=4,
            ),
        ],
        reinforcements=[],
        glasses=[
            GlassPiece(
                bay_id="b1",
                width_mm=d("1000"), height_mm=d("600"),
                shape=shape, area_m2=d("0.60"),
                weight_kg=d("12"), thickness_net_mm=d("4"),
                glass_spec="4-12-4", article_sku="DVH-1",
                composition=parse_glass_notation("4-12-4"),
            ),
        ],
    )
    uw = compute_uw(
        modules=[ThermalModuleInput(result=result, area_m2=d("0.72"))],
        params=_params_with_glass(), catalog=_catalog(),
        face_widths={"MARCO-1": d("50")},
    )
    assert uw.status == "OK"
    assert uw.lg_m == d("3.2000")


# ─── Clases de ensayo ───────────────────────────────────────────────────────

def _test_row(**over: object) -> PerformanceTestInput:
    base: dict[str, Any] = dict(
        air_class=3, water_class="7A", wind_class="C3",
        report_ref="INF-2024-118", laboratory="DICTUC",
        tested_on="2024-03-12",
        tested_width_mm=d("2400"), tested_height_mm=d("1800"),
        verified=True, provenance="MANUAL",
    )
    base.update(over)
    return PerformanceTestInput(**base)


def test_resolve_classes_prefers_typology_scope() -> None:
    catalog = ThermalCatalogInput(tests=[
        _test_row(air_class=2),
        _test_row(air_class=4, typology_scope="ABATIBLE"),
    ])
    resolved = resolve_classes(
        catalog, typology="ABATIBLE", width_mm=d("1200"), height_mm=d("1200"))
    assert resolved is not None and resolved.air_class == 4
    assert not resolved.scope_exceeded


def test_resolve_classes_flags_scope_exceeded() -> None:
    catalog = ThermalCatalogInput(tests=[_test_row()])
    resolved = resolve_classes(
        catalog, typology=None, width_mm=d("3000"), height_mm=d("1200"))
    assert resolved is not None and resolved.scope_exceeded


# ─── Cumplimiento por posición ─────────────────────────────────────────────

def _ok_uw(*, verified: bool = True) -> UwComputation:
    params = _params_with_glass(verified=verified)
    return compute_uw(
        modules=[_module()], params=params, catalog=_catalog(verified=verified),
        face_widths={"MARCO-1": d("45")},
    )


def test_compliance_zone_i_verified_class3_complies() -> None:
    catalog = ThermalCatalogInput(tests=[_test_row(air_class=3)])
    classes = resolve_classes(
        catalog, typology=None, width_mm=d("1200"), height_mm=d("1200"))
    result = position_compliance(
        uw=_ok_uw(), classes=classes, zone="I",
        use="RESIDENTIAL", orientation="N",
    )
    assert result.air_class_required == 3
    # Uw 1,40 ≤ 5,8 → la columna existe; veredicto COMPLIES (todo verificado)
    assert result.verdict == "COMPLIES"
    assert result.window_pct_max == 67  # Tabla 3, zona I / Norte / U≤1,6


def test_compliance_declared_only_gives_insufficient() -> None:
    catalog = ThermalCatalogInput(tests=[
        _test_row(air_class=3, verified=False)])
    classes = resolve_classes(
        catalog, typology=None, width_mm=d("1200"), height_mm=d("1200"))
    uw_declared = _ok_uw(verified=False)
    result = position_compliance(
        uw=uw_declared, classes=classes, zone="I",
        use="RESIDENTIAL", orientation="N",
    )
    assert result.verdict == "INSUFFICIENT_DATA"
    assert any(c.code == "UW_UNVERIFIED" for c in result.causes)
    assert any(c.code == "AIR_CLASS_UNVERIFIED" for c in result.causes)


def test_compliance_declared_below_requirement_fails() -> None:
    """La declaración misma incumple: clase 1 donde la zona exige 3."""
    catalog = ThermalCatalogInput(tests=[
        _test_row(air_class=1, verified=False)])
    classes = resolve_classes(
        catalog, typology=None, width_mm=d("1200"), height_mm=d("1200"))
    result = position_compliance(
        uw=_ok_uw(verified=False), classes=classes, zone="I",
        use="RESIDENTIAL", orientation="N",
    )
    assert result.verdict == "FAILS"


def test_compliance_demo_never_verdicts() -> None:
    params = _params_with_glass(provenance="SEED_SYNTHETIC", verified=False)
    uw = compute_uw(
        modules=[_module()], params=params,
        catalog=ThermalCatalogInput(
            frame_uf={"ALL": FrameUfInput(
                member_group="ALL", uf_w_m2k=d("1.4"),
                provenance="SEED_SYNTHETIC")},
            spacers={"ALUMINIUM": SpacerPsiInput(
                code="ALUMINIUM", psi_w_m_k=d("0.06"),
                provenance="SEED_SYNTHETIC")},
        ),
        face_widths={"MARCO-1": d("45")},
    )
    assert uw.authority == "DEMO"
    result = position_compliance(
        uw=uw, classes=None, zone="I",
        use="RESIDENTIAL", orientation="N",
    )
    assert result.verdict == "INSUFFICIENT_DATA"
    assert any(c.code == "DEMO_DATA" for c in result.causes)


def test_compliance_roof_window_zone_f() -> None:
    """Techumbre ≤60° zona B–I: U ≤ 3,6. Uw 1,40 verificado cumple."""
    result = position_compliance(
        uw=_ok_uw(), classes=None, zone="F",
        use="RESIDENTIAL", orientation="ROOF",
    )
    assert result.roof_u_max == d("3.6")
    assert result.verdict == "INSUFFICIENT_DATA"  # clase de aire F=2 falta
    assert any(c.code == "AIR_CLASS_MISSING" for c in result.causes)


def test_compliance_equipment_zone_h_limit() -> None:
    """Equipamiento H: U máx 2,40 — Uw 1,40 verificado cumple."""
    catalog = ThermalCatalogInput(tests=[_test_row(air_class=3)])
    classes = resolve_classes(
        catalog, typology=None, width_mm=d("1200"), height_mm=d("1200"))
    result = position_compliance(
        uw=_ok_uw(), classes=classes, zone="H",
        use="EQUIPMENT", orientation=None,
    )
    assert result.u_max == d("2.40")
    assert result.verdict == "COMPLIES"


def test_compliance_zone_a_no_requirement() -> None:
    result = position_compliance(
        uw=_ok_uw(), classes=None, zone="A",
        use="RESIDENTIAL", orientation="N",
    )
    # Zona A no exige clase de aire; el % de la Tabla 3 sí calza → COMPLIES.
    assert result.verdict == "COMPLIES"


def test_compliance_zone_missing() -> None:
    result = position_compliance(
        uw=_ok_uw(), classes=None, zone=None,
        use="RESIDENTIAL", orientation="N",
    )
    assert result.verdict == "INSUFFICIENT_DATA"
    assert any(c.code == "ZONE_MISSING" for c in result.causes)


# ─── % de ventanas por orientación (proyecto) ──────────────────────────────

def test_orientation_pct_fails_over_allowed() -> None:
    out = orientation_compliance(
        zone="I", orientation="S",
        window_area_m2=d("4.0"), wall_area_m2=d("10.0"),
        max_uw=d("1.40"), max_uw_authority="VERIFIED",
    )
    # I/Sur/U≤1,6 permite 23 %; hay 40 % → no cumple.
    assert out.allowed_pct == 23
    assert out.actual_pct == d("40.0")
    assert out.verdict == "FAILS"


def test_orientation_pct_wall_area_missing() -> None:
    out = orientation_compliance(
        zone="I", orientation="S",
        window_area_m2=d("4.0"), wall_area_m2=None,
        max_uw=d("1.40"), max_uw_authority="VERIFIED",
    )
    assert out.verdict == "INSUFFICIENT_DATA"
    assert any(c.code == "WALL_AREA_MISSING" for c in out.causes)


def test_orientation_pct_u_beyond_table_fails() -> None:
    out = orientation_compliance(
        zone="I", orientation="S",
        window_area_m2=d("4.0"), wall_area_m2=d("10.0"),
        max_uw=d("6.0"), max_uw_authority="DECLARED",
    )
    assert out.verdict == "FAILS"
    assert any(c.code == "U_BEYOND_TABLE" for c in out.causes)
