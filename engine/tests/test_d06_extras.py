"""D06 — accesorios y extras de verdad: golden coverage of the extras engine.

A real quote line is never "ventana × precio": vierteaguas, ensanches,
tapajuntas, mosquiteros and project services are catalogued articles the
engine measures off the product and derives into sublines (cantidad ×
precio = total), BOM pieces and cuts. These tests pin that contract.
"""

from __future__ import annotations

from decimal import Decimal

from dekopen_engine.extras import (
    evaluate_service_lines,
    merge_extra_templates,
)
from dekopen_engine.models import (
    BayOpeningType,
    EdgeSide,
    ExtraArticle,
    ExtraKind,
    ExtraLine,
    ExtraPricingUnit,
    ExtraSelection,
    ExtraTemplate,
    MaterialType,
    PieceOrigin,
    ServiceArticle,
    ServiceKind,
    ServicePositionMeasure,
    ServiceQtyRule,
    SystemFamily,
    SystemParams,
    UnitKind,
)
from dekopen_engine.product import (
    ProductModel,
    evaluate_product,
    make_bow_assembly,
    make_single_unit,
)

GLASS_4_MM = Decimal("4.00")
GLASS_4_SPEC = "4"

VIERTEAGUAS = ExtraArticle(
    sku="EXT-VIERT-60",
    name="Vierteaguas exterior",
    kind=ExtraKind.SILL,
    pricing_unit=ExtraPricingUnit.METER,
    unit_price=Decimal("11000"),
    unit_price_currency="CLP",
    unit_cost=Decimal("5500"),
    unit_cost_currency="CLP",
    cut_profile_sku="VIERT-ALU-60",
    cut_material=MaterialType.ALUMINIUM,
    vuelo_default_mm=Decimal("30"),
    unit_kinds=(UnitKind.WINDOW,),
    suggestion_reason="El vierteaguas suele acompañar a las ventanas de fachada",
)

ENSANCHE = ExtraArticle(
    sku="EXT-ENS-60",
    name="Ensanche de marco",
    kind=ExtraKind.FRAME_EXTENSION,
    pricing_unit=ExtraPricingUnit.METER,
    unit_price=Decimal("8500"),
    unit_price_currency="CLP",
    unit_cost=Decimal("4200"),
    unit_cost_currency="CLP",
    cut_profile_sku="ENS-PVC-60",
    cut_material=MaterialType.PVC,
)

TAPAJUNTA = ExtraArticle(
    sku="EXT-TPJ-60",
    name="Tapajunta de encuentro",
    kind=ExtraKind.COVER_TRIM,
    pricing_unit=ExtraPricingUnit.METER,
    unit_price=Decimal("4900"),
    unit_price_currency="CLP",
    cut_profile_sku="TPJ-PVC-60",
    cut_material=MaterialType.PVC,
)

MOSQUITERO_CORREDERA = ExtraArticle(
    sku="EXT-MOSQ-CORR",
    name="Mosquitero corredera",
    kind=ExtraKind.MOSQUITO_SCREEN,
    pricing_unit=ExtraPricingUnit.EACH,
    unit_price=Decimal("28500"),
    unit_price_currency="CLP",
    unit_cost=Decimal("16000"),
    unit_cost_currency="CLP",
    families=(SystemFamily.SLIDING,),
    unit_kinds=(UnitKind.WINDOW,),
    suggestion_reason="Las correderas suelen llevar mosquitero corredera",
)

MOSQUITERO = ExtraArticle(
    sku="EXT-MOSQ-ENR",
    name="Mosquitero enrollable",
    kind=ExtraKind.MOSQUITO_SCREEN,
    pricing_unit=ExtraPricingUnit.EACH,
    unit_price=Decimal("32000"),
    unit_price_currency="CLP",
)

AIREADOR_SIN_PRECIO = ExtraArticle(
    sku="EXT-AIREADOR",
    name="Aireador de lama",
    kind=ExtraKind.VENTILATOR,
    pricing_unit=ExtraPricingUnit.EACH,
)


def _params(demo_60_params: SystemParams, *articles: ExtraArticle) -> SystemParams:
    return demo_60_params.model_copy(
        update={"extra_articles": {a.sku: a for a in articles}}
    )


def _product_with_extras(
    product: ProductModel, *skus: ExtraSelection
) -> ProductModel:
    return product.model_copy(update={"extras": list(skus)})


class TestVierteaguas:
    def test_sill_golden_1500_plus_vuelos(self, demo_60_params: SystemParams) -> None:
        """Golden: vierteaguas 1500 + 30 + 30 → 1 560 mm de corte, 1,56 m
        facturados al precio declarado del artículo."""
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1500"),
                height_mm=Decimal("1400"),
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(sku="EXT-VIERT-60"),
        )
        evaluation = evaluate_product(product, _params(demo_60_params, VIERTEAGUAS))
        assert evaluation.bom is not None
        cuts = [
            cut
            for cut in evaluation.bom.profile_cuts
            if cut.origin is PieceOrigin.EXTRA
        ]
        assert [(c.sku, c.length_mm, c.qty) for c in cuts] == [
            ("VIERT-ALU-60", Decimal("1560"), 1)
        ]
        line = evaluation.bom.extra_lines[0]
        assert (line.sku, line.quantity, line.unit) == (
            "EXT-VIERT-60",
            Decimal("1.56"),
            ExtraPricingUnit.METER,
        )
        assert line.unit_price == Decimal("11000")
        assert line.total_price == Decimal("17160.00")
        assert line.total_cost == Decimal("8580.00")

    def test_sill_run_merges_contiguous_modules(
        self, demo_60_params: SystemParams
    ) -> None:
        """Bow de dos módulos: el vano corrido toma el vuelo solo en los
        extremos de la tirada — dos cortes de 780 mm, no dos de 780+780."""
        product = _product_with_extras(
            make_bow_assembly(
                module_count=2,
                width_mm=Decimal("1500"),
                height_mm=Decimal("1400"),
                angle_deg=Decimal("10"),
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(sku="EXT-VIERT-60"),
        )
        evaluation = evaluate_product(product, _params(demo_60_params, VIERTEAGUAS))
        assert evaluation.bom is not None
        cuts = [
            cut
            for cut in evaluation.bom.profile_cuts
            if cut.origin is PieceOrigin.EXTRA
        ]
        assert sorted(c.length_mm for c in cuts) == [Decimal("780"), Decimal("780")]
        assert evaluation.bom.extra_lines[0].quantity == Decimal("1.56")

    def test_sill_vuelo_override(self, demo_60_params: SystemParams) -> None:
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1200"),
                height_mm=Decimal("1000"),
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(
                sku="EXT-VIERT-60",
                vuelo_left_mm=Decimal("50"),
                vuelo_right_mm=Decimal("50"),
            ),
        )
        evaluation = evaluate_product(product, _params(demo_60_params, VIERTEAGUAS))
        assert evaluation.bom is not None
        assert evaluation.bom.extra_lines[0].quantity == Decimal("1.30")


class TestEnsancheTapajunta:
    def test_ensanche_on_declared_sides(self, demo_60_params: SystemParams) -> None:
        """Ensanche LEFT+RIGHT sobre un fijo 1500×1400: dos cortes de 1,4 m
        que entran al BOM como piezas EXTRA del perfil de ensanche."""
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1500"),
                height_mm=Decimal("1400"),
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(
                sku="EXT-ENS-60", sides=(EdgeSide.LEFT, EdgeSide.RIGHT)
            ),
        )
        evaluation = evaluate_product(product, _params(demo_60_params, ENSANCHE))
        assert evaluation.bom is not None
        cuts = [
            cut
            for cut in evaluation.bom.profile_cuts
            if cut.origin is PieceOrigin.EXTRA
        ]
        assert [(c.sku, c.length_mm) for c in cuts] == [
            ("ENS-PVC-60", Decimal("1400")),
            ("ENS-PVC-60", Decimal("1400")),
        ]
        line = evaluation.bom.extra_lines[0]
        assert line.quantity == Decimal("2.80")
        assert line.total_price == Decimal("23800.00")

    def test_sided_extra_without_sides_emits_nothing(
        self, demo_60_params: SystemParams
    ) -> None:
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1500"),
                height_mm=Decimal("1400"),
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(sku="EXT-TPJ-60"),
        )
        evaluation = evaluate_product(product, _params(demo_60_params, TAPAJUNTA))
        assert evaluation.bom is not None
        assert evaluation.bom.extra_lines == []
        assert not any(
            cut.origin is PieceOrigin.EXTRA for cut in evaluation.bom.profile_cuts
        )


class TestCountedExtras:
    def test_mosquitero_corredera_counts_moving_leaves(
        self, demo_corredera_60_params: SystemParams
    ) -> None:
        """SLIDING_2L son dos hojas correderas: el mosquitero emite un
        fitting por hoja y factura dos unidades."""
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1800"),
                height_mm=Decimal("1400"),
                opening=BayOpeningType.SLIDING_2L,
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(sku="EXT-MOSQ-CORR"),
        )
        params = _params(demo_corredera_60_params, MOSQUITERO_CORREDERA)
        evaluation = evaluate_product(product, params)
        assert evaluation.bom is not None
        extra_fittings = [
            f for f in evaluation.bom.fittings if f.origin is PieceOrigin.EXTRA
        ]
        assert len(extra_fittings) == 2
        assert all(f.sku == "EXT-MOSQ-CORR" for f in extra_fittings)
        line = evaluation.bom.extra_lines[0]
        assert line.quantity == Decimal("2")
        assert line.unit is ExtraPricingUnit.EACH
        assert line.total_price == Decimal("57000.00")

    def test_qty_override_for_fixed_pane(self, demo_60_params: SystemParams) -> None:
        """Un mosquitero fijo sobre un paño fijo no deriva de hojas — el
        estimador declara la cantidad."""
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1500"),
                height_mm=Decimal("1400"),
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(sku="EXT-MOSQ-ENR", qty=1),
        )
        evaluation = evaluate_product(product, _params(demo_60_params, MOSQUITERO))
        assert evaluation.bom is not None
        assert evaluation.bom.extra_lines[0].quantity == Decimal("1")
        extra_fittings = [
            f for f in evaluation.bom.fittings if f.origin is PieceOrigin.EXTRA
        ]
        assert len(extra_fittings) == 1 and extra_fittings[0].qty == 1

    def test_counted_on_fixed_derives_zero(self, demo_60_params: SystemParams) -> None:
        """Sin hojas operables ni cantidad declarada, el contado no emite
        nada — la posición fija no finge un mosquitero."""
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1500"),
                height_mm=Decimal("1400"),
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(sku="EXT-MOSQ-ENR"),
        )
        evaluation = evaluate_product(product, _params(demo_60_params, MOSQUITERO))
        assert evaluation.bom is not None
        assert evaluation.bom.extra_lines == []
        assert not any(
            f.origin is PieceOrigin.EXTRA for f in evaluation.bom.fittings
        )

    def test_priceless_article_still_derives_quantity(
        self, demo_corredera_60_params: SystemParams
    ) -> None:
        """Sin precio declarado no hay número inventado: la sublínea llega
        con cantidad y total None — el documento lee 'Sin dato'."""
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1800"),
                height_mm=Decimal("1400"),
                opening=BayOpeningType.SLIDING_2L,
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(sku="EXT-AIREADOR"),
        )
        evaluation = evaluate_product(
            product, _params(demo_corredera_60_params, AIREADOR_SIN_PRECIO)
        )
        assert evaluation.bom is not None
        line = evaluation.bom.extra_lines[0]
        assert line.quantity == Decimal("2")
        assert line.unit_price is None and line.total_price is None


class TestSuggestions:
    def test_companion_suggested_with_reason(
        self, demo_60_params: SystemParams
    ) -> None:
        """El sistema sugiere los extras que acompañan a la tipología, con
        su causa — el usuario acepta o descarta."""
        product = make_single_unit(
            width_mm=Decimal("1500"),
            height_mm=Decimal("1400"),
            glass_thickness_mm=GLASS_4_MM,
            glass_spec=GLASS_4_SPEC,
        )
        evaluation = evaluate_product(
            product, _params(demo_60_params, VIERTEAGUAS, MOSQUITERO_CORREDERA)
        )
        reasons = {s.sku: s.reason for s in evaluation.extra_suggestions}
        # The window qualifies for the sill; the sliding mosquitero's
        # family predicate excludes a casement position.
        assert reasons == {
            "EXT-VIERT-60": "El vierteaguas suele acompañar a las ventanas de fachada"
        }

    def test_selected_extra_is_not_suggested(
        self, demo_60_params: SystemParams
    ) -> None:
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1500"),
                height_mm=Decimal("1400"),
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(sku="EXT-VIERT-60"),
        )
        evaluation = evaluate_product(
            product, _params(demo_60_params, VIERTEAGUAS)
        )
        assert evaluation.extra_suggestions == []

    def test_suggestion_needs_measurable_context(
        self, demo_60_params: SystemParams
    ) -> None:
        """A mosquitero is never suggested on a fixed pane — nothing would
        measure."""
        product = make_single_unit(
            width_mm=Decimal("1500"),
            height_mm=Decimal("1400"),
            glass_thickness_mm=GLASS_4_MM,
            glass_spec=GLASS_4_SPEC,
        )
        evaluation = evaluate_product(product, _params(demo_60_params, MOSQUITERO))
        assert evaluation.extra_suggestions == []


class TestServices:
    def test_installation_per_perimeter_meter(self) -> None:
        """Instalación por ml de perímetro: dos posiciones de 1500×1400
        miden 11,60 ml a su precio declarado."""
        articles = [
            ServiceArticle(
                code="INST-ML",
                name="Instalación por ml",
                kind=ServiceKind.INSTALLATION,
                qty_rule=ServiceQtyRule.PER_LINEAR_METER,
                unit_price=Decimal("4500"),
                unit_price_currency="CLP",
            ),
            ServiceArticle(
                code="FLETE",
                name="Flete a obra",
                kind=ServiceKind.FREIGHT,
                qty_rule=ServiceQtyRule.FIXED,
                unit_price=Decimal("45000"),
                unit_price_currency="CLP",
            ),
            ServiceArticle(
                code="RETIRO",
                name="Retiro de ventana existente",
                kind=ServiceKind.REMOVAL,
                qty_rule=ServiceQtyRule.PER_POSITION_UNIT,
                unit_price=Decimal("18000"),
                unit_price_currency="CLP",
            ),
        ]
        positions = [
            ServicePositionMeasure(
                width_mm=Decimal("1500"), height_mm=Decimal("1400"), quantity=2
            )
        ]
        lines = {line.code: line for line in evaluate_service_lines(articles, positions)}
        assert lines["INST-ML"].quantity == Decimal("11.60")
        assert lines["INST-ML"].unit == "ml"
        assert lines["INST-ML"].total_price == Decimal("52200.00")
        assert lines["FLETE"].quantity == Decimal("1")
        assert lines["FLETE"].total_price == Decimal("45000.00")
        assert lines["RETIRO"].quantity == Decimal("2")
        assert lines["RETIRO"].total_price == Decimal("36000.00")

    def test_installation_per_m2(self) -> None:
        articles = [
            ServiceArticle(
                code="INST-M2",
                name="Instalación por m²",
                kind=ServiceKind.INSTALLATION,
                qty_rule=ServiceQtyRule.PER_M2,
                unit_price=Decimal("12000"),
                unit_price_currency="CLP",
            )
        ]
        positions = [
            ServicePositionMeasure(
                width_mm=Decimal("1500"), height_mm=Decimal("1400"), quantity=2
            )
        ]
        (line,) = evaluate_service_lines(articles, positions)
        assert line.quantity == Decimal("4.20")
        assert line.unit == "m²"
        assert line.total_price == Decimal("50400.00")


class TestTemplates:
    def test_templates_preselect_without_overriding(self) -> None:
        """Las plantillas de la org se preseleccionan en la posición
        nueva; una declaración del estimador gana sobre la plantilla."""
        merged = merge_extra_templates(
            [ExtraSelection(sku="EXT-ENS-60", sides=(EdgeSide.LEFT,))],
            [
                ExtraTemplate(sku="EXT-ENS-60", sides=(EdgeSide.LEFT, EdgeSide.RIGHT)),
                ExtraTemplate(sku="EXT-VIERT-60"),
            ],
        )
        assert [(s.sku, tuple(s.sides)) for s in merged] == [
            ("EXT-ENS-60", (EdgeSide.LEFT,)),
            ("EXT-VIERT-60", ()),
        ]


class TestLineIntegrity:
    def test_sublines_sum_to_extra_total(self, demo_60_params: SystemParams) -> None:
        """Las sublíneas suman exactamente lo que la posición cobra por
        extras — ningún redondeo se pierde."""
        product = _product_with_extras(
            make_single_unit(
                width_mm=Decimal("1500"),
                height_mm=Decimal("1400"),
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
            ExtraSelection(sku="EXT-VIERT-60"),
            ExtraSelection(
                sku="EXT-ENS-60", sides=(EdgeSide.LEFT, EdgeSide.RIGHT)
            ),
        )
        evaluation = evaluate_product(
            product, _params(demo_60_params, VIERTEAGUAS, ENSANCHE)
        )
        assert evaluation.bom is not None
        lines: list[ExtraLine] = evaluation.bom.extra_lines
        assert len(lines) == 2
        subtotal = sum(line.total_price for line in lines if line.total_price)
        assert subtotal == Decimal("17160.00") + Decimal("23800.00")
