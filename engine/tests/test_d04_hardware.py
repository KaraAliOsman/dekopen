"""D04 — herrajes de verdad: clases por sistema × apertura, expansión de
componentes con reglas declaradas, restricciones con mensaje real,
manillas/opciones vendibles y lista de picking.
"""

from decimal import Decimal as D

import pytest

from dekopen_engine.hardware import (
    AmbiguousHardwareKit,
    HardwareSelectionError,
    NoCompatibleHardwareKit,
    build_hardware_item,
    evaluate_hardware_candidates,
    expand_components,
    hardware_picking_list,
    kit_cost_clp,
    normalize_opening_type,
    resolve_hardware_evaluations,
)
from dekopen_engine.models import (
    BayOpeningType,
    ComponentCutRule,
    ComponentQtyRule,
    HardwareComponent,
    HardwareFamily,
    HardwareItem,
    HardwareKitRule,
    HardwareOption,
    HardwareOptionKind,
    HandleColorOption,
    HandleModelOption,
    MachiningDeclaration,
    RailType,
    SystemParams,
)
from dekopen_engine.weight import ExactLeafWeight, with_hardware_weight
from engine.tests.catalog import demo_60_params


BASE = ExactLeafWeight(D("5"), D("7"), D("18"))  # 30 kg de hoja base


def _kit(
    sku: str,
    name: str,
    *,
    opening: str = "TILT_TURN",
    min_w: str = "450",
    max_w: str = "1200",
    min_h: str = "600",
    max_h: str = "2000",
    max_kg: str = "80",
    class_label: str | None = None,
    ratio: str | None = None,
    stay_min: str | None = None,
    stays: int = 0,
    contents: list[HardwareComponent] | None = None,
    weight_kg: str | None = "2.50",
) -> HardwareKitRule:
    return HardwareKitRule(
        sku=sku,
        name=name,
        opening_type=opening,
        min_leaf_width_mm=D(min_w),
        max_leaf_width_mm=D(max_w),
        min_leaf_height_mm=D(min_h),
        max_leaf_height_mm=D(max_h),
        max_leaf_weight_kg=D(max_kg),
        rail_type=RailType.DUAL,
        carriages_qty=0,
        stay_arms_qty=stays,
        weight_kg=D(weight_kg) if weight_kg else None,
        contents=contents or [],
        class_label=class_label,
        max_aspect_ratio=D(ratio) if ratio else None,
        min_stay_height_mm=D(stay_min) if stay_min else None,
    )


def _cierres() -> HardwareComponent:
    """Puntos de cierre: uno cada 500 mm de alto, mínimo 2, máximo 4."""
    return HardwareComponent(
        sku="CIERRE-MULTI",
        name="Punto de cierre",
        qty_rule=ComponentQtyRule(
            kind="PER_HEIGHT", per_mm=D("500"), min_qty=2, max_qty=4
        ),
        unit="unit",
        weight_kg=D("0.080"),
        cost_clp=D("3200"),
    )


def _transmision() -> HardwareComponent:
    """Transmisión cortable: alto de hoja − 60 mm."""
    return HardwareComponent(
        sku="TRANS-OB",
        name="Transmisión cremona",
        qty=D("1"),
        unit="unit",
        cut_rule=ComponentCutRule(axis="HEIGHT", minus_mm=D("60")),
        weight_kg=D("1.200"),
        cost_clp=D("8900"),
        machining=[
            MachiningDeclaration(kind="LOCK_PREP", side="B"),
            MachiningDeclaration(
                kind="ESPAG_HOUSING", side="A", u_mm=D("55"), y_mm=D("80")
            ),
        ],
    )


def _bisagras() -> HardwareComponent:
    return HardwareComponent(
        sku="BIS-OB",
        name="Bisagra",
        qty=D("3"),
        unit="unit",
        weight_kg=D("0.350"),
        cost_clp=D("4100"),
        machining=[MachiningDeclaration(kind="HINGE_PREP", side="B")],
    )


def _roldanas() -> HardwareComponent:
    return HardwareComponent(
        sku="ROLD-150",
        name="Carro rodante 150kg",
        qty=D("2"),
        unit="unit",
        weight_kg=D("0.900"),
        cost_clp=D("7800"),
    )


def _multipunto() -> HardwareComponent:
    return HardwareComponent(
        sku="CIERRE-PUERTA",
        name="Cerradura multipunto",
        qty=D("1"),
        unit="unit",
        weight_kg=D("1.600"),
        cost_clp=D("24000"),
        machining=[MachiningDeclaration(kind="LOCK_PREP", side="B")],
    )


def _d04_params() -> SystemParams:
    """DEMO_60 con una familia OB de dos clases reales, una corredera
    pesada con roldanas, una puerta multipunto y opciones vendibles."""
    base = demo_60_params()
    kits = [
        _kit(
            "KIT-OB-ESTANDAR",
            "Kit OB clase estándar",
            max_kg="80",
            class_label="estándar",
            contents=[_cierres(), _transmision(), _bisagras()],
        ),
        _kit(
            "KIT-OB-PESADA",
            "Kit OB clase pesada",
            max_w="1400",
            max_h="2400",
            max_kg="160",
            class_label="pesada",
            contents=[_cierres(), _transmision(), _bisagras()],
            weight_kg="3.10",
        ),
        _kit(
            "KIT-CORR-PESADA",
            "Kit corredera clase pesada",
            opening="SLIDING",
            min_w="600",
            max_w="1800",
            min_h="800",
            max_h="2600",
            max_kg="150",
            class_label="pesada",
            contents=[_roldanas()],
            weight_kg="2.80",
        ),
        _kit(
            "KIT-DOOR-MULTI",
            "Kit puerta multipunto",
            opening="DOOR",
            min_w="700",
            max_w="1200",
            min_h="1800",
            max_h="2400",
            max_kg="120",
            class_label="estándar",
            contents=[_multipunto()],
            weight_kg="2.10",
        ),
        _kit(
            "KIT-AWN-COMPAS",
            "Kit proyectante compás",
            opening="AWNING",
            min_w="400",
            max_w="1600",
            min_h="400",
            max_h="1600",
            max_kg="45",
            stays=2,
            stay_min="500",
            ratio="3.00",
            contents=[],
        ),
    ]
    families = {
        "TILT_TURN": HardwareFamily(
            opening_type="TILT_TURN",
            handle_models=[
                HandleModelOption(sku="MAN-EST", name="Manilla estándar",
                                  kind="STANDARD", price_delta_clp=D("0")),
                HandleModelOption(sku="MAN-LLAVE", name="Manilla con llave",
                                  kind="LOCKABLE", price_delta_clp=D("7500")),
            ],
            handle_colors=[
                HandleColorOption(sku="COL-BL", name="Blanco", price_delta_clp=D("0")),
                HandleColorOption(sku="COL-NE", name="Negro", price_delta_clp=D("1200")),
            ],
            handle_height_rule="RANGE",
            handle_height_min_mm=D("900"),
            handle_height_max_mm=D("1300"),
            handle_height_default_mm=D("1000"),
        ),
        "DOOR": HardwareFamily(
            opening_type="DOOR",
            handle_models=[
                HandleModelOption(sku="MAN-PUERTA", name="Manilla de puerta con escudo",
                                  kind="DOOR_ESCUTCHEON", price_delta_clp=D("18000")),
            ],
            handle_colors=[
                HandleColorOption(sku="COL-BL", name="Blanco", price_delta_clp=D("0")),
            ],
            handle_height_rule="FIXED_FROM_BASE",
            handle_height_default_mm=D("1050"),
        ),
    }
    options = {
        "OPT-MICROVENT": HardwareOption(
            sku="OPT-MICROVENT",
            name="Microventilación",
            kind=HardwareOptionKind.MICROVENTILATION,
            opening_type="TILT_TURN",
            price_delta_clp=D("15000"),
            components=[
                HardwareComponent(
                    sku="KIT-MICROVENT",
                    name="Conjunto microventilación",
                    qty=D("1"),
                    unit="unit",
                    weight_kg=D("0.250"),
                    cost_clp=D("6200"),
                )
            ],
        ),
        "OPT-ANTIPAL": HardwareOption(
            sku="OPT-ANTIPAL",
            name="Puntos antipalanca",
            kind=HardwareOptionKind.SECURITY,
            opening_type="TILT_TURN",
            price_delta_clp=D("9500"),
            components=[
                HardwareComponent(
                    sku="CIERRE-ANTIPAL",
                    name="Punto antipalanca",
                    qty=D("2"),
                    unit="unit",
                    weight_kg=D("0.120"),
                    cost_clp=D("2900"),
                )
            ],
        ),
        "OPT-LIMITADOR": HardwareOption(
            sku="OPT-LIMITADOR",
            name="Limitador de apertura",
            kind=HardwareOptionKind.OPENING_LIMITER,
            opening_type="TILT_TURN",
            price_delta_clp=D("11000"),
            components=[
                HardwareComponent(
                    sku="BRAZO-LIMITADOR",
                    name="Brazo limitador",
                    qty=D("1"),
                    unit="unit",
                    weight_kg=D("0.400"),
                    cost_clp=D("5300"),
                )
            ],
        ),
    }
    return base.model_copy(
        update={
            "available_hardware_kits": kits,
            "hardware_families": families,
            "hardware_options": options,
        }
    )


def _resolve(
    params: SystemParams,
    *,
    width: str,
    height: str,
    opening: BayOpeningType = BayOpeningType.TILT_TURN_LEFT,
    sku: str | None = None,
    options: list[str] | None = None,
) -> "tuple[HardwareKitRule, ExactLeafWeight]":
    components = []
    for option_sku in options or []:
        option = params.hardware_options.get(option_sku)
        if option is not None:
            components.extend(option.components)
    return resolve_hardware_evaluations(
        evaluate_hardware_candidates(
            opening_group=normalize_opening_type(opening),
            width_mm=D(width),
            height_mm=D(height),
            base_weight=BASE,
            params=params,
            explicit_sku=sku,
            option_components=components,
        ),
        opening_group=normalize_opening_type(opening),
        explicit_sku=sku,
        leaf_width_mm=D(width),
        leaf_height_mm=D(height),
    )


# ---------------------------------------------------------------- expansión


def test_expansion_oscilobatiente_both_sizes() -> None:
    params = _d04_params()
    for height, expected_cierres, expected_transmision in (
        (D("1300"), D("3"), D("1240")),
        (D("1900"), D("4"), D("1840")),
    ):
        expanded = expand_components(
            next(k.contents for k in params.available_hardware_kits
                 if k.sku == "KIT-OB-ESTANDAR"),
            leaf_width_mm=D("900"),
            leaf_height_mm=height,
        )
        cierres = next(c for c in expanded if c.sku == "CIERRE-MULTI")
        transmision = next(c for c in expanded if c.sku == "TRANS-OB")
        assert cierres.qty == expected_cierres
        assert transmision.length_mm == expected_transmision


def test_expansion_corredera_pesada() -> None:
    params = _d04_params()
    kit, _ = _resolve(
        params, width="1400", height="2200", opening=BayOpeningType.SLIDING_2L
    )
    assert kit.sku == "KIT-CORR-PESADA"
    expanded = expand_components(
        kit.contents, leaf_width_mm=D("1400"), leaf_height_mm=D("2200")
    )
    assert expanded[0].sku == "ROLD-150" and expanded[0].qty == D("2")


def test_expansion_puerta() -> None:
    params = _d04_params()
    kit, _ = _resolve(
        params, width="950", height="2150", opening=BayOpeningType.DOOR_ENTRY
    )
    assert kit.sku == "KIT-DOOR-MULTI"
    expanded = expand_components(
        kit.contents, leaf_width_mm=D("950"), leaf_height_mm=D("2150")
    )
    assert expanded[0].qty == D("1")
    assert expanded[0].machining[0].kind == "LOCK_PREP"


def test_component_requires_qty_or_rule() -> None:
    with pytest.raises(Exception):
        HardwareComponent(sku="X", name="x", unit="unit")


# ------------------------------------------------- resolución de clase


def test_tightest_class_wins_when_both_fit() -> None:
    params = _d04_params()
    kit, weight = _resolve(params, width="900", height="1400")
    assert kit.sku == "KIT-OB-ESTANDAR" and kit.class_label == "estándar"
    assert weight.hardware_weight_kg == D("2.50")


def test_heavier_leaf_picks_heavy_class() -> None:
    params = _d04_params()
    heavy = ExactLeafWeight(D("20"), D("25"), D("60"))  # 105 kg + kit
    kit, _ = resolve_hardware_evaluations(
        evaluate_hardware_candidates(
            opening_group=normalize_opening_type(BayOpeningType.TILT_TURN_LEFT),
            width_mm=D("1200"), height_mm=D("2100"),
            base_weight=heavy, params=params,
        ),
        opening_group=normalize_opening_type(BayOpeningType.TILT_TURN_LEFT),
        leaf_width_mm=D("1200"), leaf_height_mm=D("2100"),
    )
    assert kit.sku == "KIT-OB-PESADA" and kit.class_label == "pesada"


def test_identical_envelopes_stay_ambiguous() -> None:
    params = _d04_params()
    twin = params.available_hardware_kits[0].model_copy(
        update={"sku": "KIT-OB-GEMELO"}
    )
    params = params.model_copy(
        update={"available_hardware_kits": params.available_hardware_kits + [twin]}
    )
    with pytest.raises(AmbiguousHardwareKit):
        _resolve(params, width="900", height="1400")


# ------------------------------------------------------ restricciones


def test_weight_restriction_names_class_and_suggests_next() -> None:
    params = _d04_params()
    heavy = ExactLeafWeight(D("20"), D("25"), D("55"))  # 100 kg + 2.5 kit
    with pytest.raises(NoCompatibleHardwareKit) as error:
        resolve_hardware_evaluations(
            evaluate_hardware_candidates(
                opening_group=normalize_opening_type(BayOpeningType.TILT_TURN_LEFT),
                width_mm=D("900"), height_mm=D("1400"),
                base_weight=heavy, params=params,
                explicit_sku="KIT-OB-ESTANDAR",
            ),
            opening_group=normalize_opening_type(BayOpeningType.TILT_TURN_LEFT),
            explicit_sku="KIT-OB-ESTANDAR",
            leaf_width_mm=D("900"), leaf_height_mm=D("1400"),
        )
    context = error.value.context
    assert context["axis"] == "weight"
    assert context["leaf_weight_kg"] == "102.50"
    assert context["kit_max_weight_kg"] == "80"
    assert context["suggestion"] == "heavier_class"
    assert context["suggested_sku"] == "KIT-OB-PESADA"
    assert context["suggested_class_label"] == "pesada"
    assert context["suggested_max_weight_kg"] == "160"


def test_size_restriction_suggests_split_bay() -> None:
    params = _d04_params()
    huge = ExactLeafWeight(D("50"), D("40"), D("80"))
    with pytest.raises(NoCompatibleHardwareKit) as error:
        resolve_hardware_evaluations(
            evaluate_hardware_candidates(
                opening_group=normalize_opening_type(BayOpeningType.TILT_TURN_LEFT),
                width_mm=D("1450"), height_mm=D("2300"),
                base_weight=huge, params=params,
            ),
            opening_group=normalize_opening_type(BayOpeningType.TILT_TURN_LEFT),
            leaf_width_mm=D("1450"), leaf_height_mm=D("2300"),
        )
    context = error.value.context
    assert context["leaf_width_mm"] == "1450" and context["leaf_height_mm"] == "2300"
    assert context["suggestion"] == "split_bay"
    assert context["heaviest_sku"] == "KIT-OB-PESADA"
    assert context["heaviest_class_label"] == "pesada"


def test_ratio_restriction_names_real_values() -> None:
    params = _d04_params()
    with pytest.raises(NoCompatibleHardwareKit) as error:
        resolve_hardware_evaluations(
            evaluate_hardware_candidates(
                opening_group=normalize_opening_type(BayOpeningType.AWNING),
                width_mm=D("400"), height_mm=D("1500"),  # ratio 3.75 > 3.00
                base_weight=BASE, params=params,
            ),
            opening_group=normalize_opening_type(BayOpeningType.AWNING),
            leaf_width_mm=D("400"), leaf_height_mm=D("1500"),
        )
    context = error.value.context
    assert context["axis"] == "ratio"
    assert context["leaf_aspect_ratio"] == "3.750"
    assert context["kit_max_aspect_ratio"] == "3.00"


def test_stay_height_restriction_names_minimum() -> None:
    params = _d04_params()
    with pytest.raises(NoCompatibleHardwareKit) as error:
        resolve_hardware_evaluations(
            evaluate_hardware_candidates(
                opening_group=normalize_opening_type(BayOpeningType.AWNING),
                width_mm=D("800"), height_mm=D("450"),  # < 500 mm min compás
                base_weight=BASE, params=params,
            ),
            opening_group=normalize_opening_type(BayOpeningType.AWNING),
            leaf_width_mm=D("800"), leaf_height_mm=D("450"),
        )
    context = error.value.context
    assert context["axis"] == "stay_height"
    assert context["stay_min_height_mm"] == "500"


# -------------------------------------------------- manillas / opciones


def _item(
    params: SystemParams,
    *,
    width: str = "900",
    height: str = "1400",
    opening: BayOpeningType = BayOpeningType.TILT_TURN_LEFT,
    handle_model_sku: str | None = None,
    handle_color_sku: str | None = None,
    handle_height_mm: D | None = None,
    option_skus: list[str] | None = None,
) -> HardwareItem:
    kit, weight = _resolve(
        params,
        width=width,
        height=height,
        opening=opening,
        options=option_skus,
    )
    return build_hardware_item(
        kit=kit,
        exact_weight=weight,
        opening=opening,
        bay_id="bay_1",
        leaf_id="leaf_1",
        leaf_width_mm=D(width),
        leaf_height_mm=D(height),
        params=params,
        handle_model_sku=handle_model_sku,
        handle_color_sku=handle_color_sku,
        handle_height_mm=handle_height_mm,
        option_skus=option_skus,
    )


def test_handle_selection_and_height_resolution() -> None:
    params = _d04_params()
    item = _item(
        params, handle_model_sku="MAN-LLAVE", handle_color_sku="COL-NE",
    )
    assert item.handle_model_name == "Manilla con llave"
    assert item.handle_color_name == "Negro"
    # Regla RANGE con default declarado.
    assert item.handle_height_mm == D("1000")
    # Δprecio = manilla con llave + color negro.
    assert item.price_delta_clp == D("8700")


def test_handle_height_out_of_declared_range() -> None:
    params = _d04_params()
    with pytest.raises(HardwareSelectionError) as error:
        _item(params, handle_height_mm=D("1500"))
    assert error.value.code == "handle_height_out_of_range"
    assert error.value.params["min_mm"] == "900"
    assert error.value.params["max_mm"] == "1300"


def test_undeclared_handle_model_refused() -> None:
    params = _d04_params()
    with pytest.raises(HardwareSelectionError) as error:
        _item(params, handle_model_sku="MAN-INEXISTENTE")
    assert error.value.code == "hardware_selection_unknown"
    assert error.value.params["field"] == "handle_model_sku"


def test_undeclared_option_refused() -> None:
    params = _d04_params()
    with pytest.raises(HardwareSelectionError) as error:
        _item(params, option_skus=["OPT-FALSA"])
    assert error.value.code == "hardware_selection_unknown"


def test_option_for_other_opening_refused() -> None:
    params = _d04_params()
    door_option = HardwareOption(
        sku="OPT-DOOR-ONLY",
        name="Opción de puerta",
        kind=HardwareOptionKind.CONCEALED_HINGES,
        opening_type="DOOR",
        price_delta_clp=D("5000"),
        components=[],
    )
    params = params.model_copy(
        update={"hardware_options": {**params.hardware_options, "OPT-DOOR-ONLY": door_option}}
    )
    with pytest.raises(HardwareSelectionError):
        _item(params, option_skus=["OPT-DOOR-ONLY"])


def test_options_expand_into_bom_with_provenance() -> None:
    params = _d04_params()
    item = _item(
        params,
        option_skus=["OPT-MICROVENT", "OPT-ANTIPAL"],
        handle_model_sku="MAN-EST",
        handle_color_sku="COL-BL",
    )
    assert item.option_names == ["Microventilación", "Puntos antipalanca"]
    option_lines = [c for c in item.contents if c.option_sku]
    assert {c.sku: c.option_sku for c in option_lines} == {
        "KIT-MICROVENT": "OPT-MICROVENT",
        "CIERRE-ANTIPAL": "OPT-ANTIPAL",
    }
    # Δprecio = microvent + antipalanca (+ manilla/color a 0).
    assert item.price_delta_clp == D("24500")
    # Costo = clase estándar expandida + opciones.
    # cierres 3×3200 + transmisión 8900 + bisagras 3×4100 + 6200 + 2×2900
    assert item.cost_clp == D("42800")


def test_door_fixed_from_base_height() -> None:
    params = _d04_params()
    item = _item(
        params,
        width="950",
        height="2150",
        opening=BayOpeningType.DOOR_ENTRY,
        handle_model_sku="MAN-PUERTA",
        handle_color_sku="COL-BL",
    )
    assert item.handle_height_mm == D("1050")
    assert item.kit_sku == "KIT-DOOR-MULTI"


# ------------------------------------------------------------ picking


def test_machining_declared_vs_emitted() -> None:
    params = _d04_params()
    item = _item(params)
    machining = {(m.kind, m.status) for m in item.machining}
    assert ("ESPAG_HOUSING", "EMITTED") in machining
    assert ("LOCK_PREP", "DECLARED_NOT_EMITTED") in machining
    assert ("HINGE_PREP", "DECLARED_NOT_EMITTED") in machining


def test_picking_list_twelve_positions_matches_engine_sum() -> None:
    """La OT de 12 posiciones: el picking agregado es exactamente la suma
    por-hoja que emite el motor — transmisión cortada incluida."""
    params = _d04_params()
    items = []
    for index in range(12):
        kit, weight = _resolve(params, width="900", height="1400")
        items.append(
            build_hardware_item(
                kit=kit,
                exact_weight=weight,
                opening=BayOpeningType.TILT_TURN_LEFT,
                bay_id=f"bay_{index}",
                leaf_id=f"leaf_{index}",
                leaf_width_mm=D("900"),
                leaf_height_mm=D("1400"),
                params=params,
            )
        )
    picking = hardware_picking_list(items, quantity=1)
    by_sku = {line.sku: line for line in picking}
    # 3 puntos por hoja × 12 hojas.
    assert by_sku["CIERRE-MULTI"].qty == D("36")
    # Transmisión: 1 por hoja con largo de corte 1340.
    assert by_sku["TRANS-OB"].qty == D("12")
    assert by_sku["TRANS-OB"].length_mm == D("1340")
    assert by_sku["BIS-OB"].qty == D("36")
    for line in picking:
        assert line.sources == ["KIT-OB-ESTANDAR"]


def test_picking_list_tracks_option_sources() -> None:
    params = _d04_params()
    item = _item(params, option_skus=["OPT-ANTIPAL"])
    picking = hardware_picking_list([item], quantity=4)
    by_sku = {line.sku: line for line in picking}
    assert by_sku["CIERRE-ANTIPAL"].qty == D("8")
    assert by_sku["CIERRE-ANTIPAL"].sources == ["OPT-ANTIPAL"]


# ------------------------------------------------------- peso y costo


def test_weight_falls_back_to_component_masses() -> None:
    params = _d04_params()
    kit = next(k for k in params.available_hardware_kits if k.sku == "KIT-OB-ESTANDAR")
    unpacked = kit.model_copy(update={"weight_kg": None})
    weight = with_hardware_weight(
        BASE, unpacked, params, leaf_width_mm=D("900"), leaf_height_mm=D("1400")
    )
    # 3×0.080 + 1.200 + 3×0.350 = 2.49 kg — sin peso declarado de kit.
    assert weight.hardware_weight_kg == D("2.490")
    assert weight.weight_unknown_reasons == ()


def test_weight_stays_unknown_without_declared_masses() -> None:
    params = _d04_params()
    kit = next(k for k in params.available_hardware_kits if k.sku == "KIT-OB-ESTANDAR")
    bare = kit.model_copy(update={"weight_kg": None, "contents": []})
    weight = with_hardware_weight(
        BASE, bare, params, leaf_width_mm=D("900"), leaf_height_mm=D("1400")
    )
    assert weight.hardware_weight_kg is None
    assert "missing_hardware_mass:KIT-OB-ESTANDAR" in weight.weight_unknown_reasons


def test_options_add_mass_to_leaf() -> None:
    params = _d04_params()
    extras = params.hardware_options["OPT-MICROVENT"].components
    kit = next(k for k in params.available_hardware_kits if k.sku == "KIT-OB-ESTANDAR")
    weight = with_hardware_weight(
        BASE, kit, params,
        leaf_width_mm=D("900"), leaf_height_mm=D("1400"),
        extra_components=extras,
    )
    assert weight.hardware_weight_kg == D("2.50") + D("0.250")


def test_kit_cost_clp_resolves_expansion() -> None:
    params = _d04_params()
    kit = next(k for k in params.available_hardware_kits if k.sku == "KIT-OB-ESTANDAR")
    # 3×3200 + 8900 + 3×4100 = 30.800
    assert kit_cost_clp(kit, leaf_width_mm=D("900"), leaf_height_mm=D("1400")) == D("30800")


# ---------------------------------------------------- delta de precio


def test_explicit_failed_class_delta_to_suggested() -> None:
    """Sugerir la clase siguiente lleva el Δ de precio real cuando ambas
    clases declaran costo de componentes."""
    params = _d04_params()
    heavy = ExactLeafWeight(D("20"), D("25"), D("55"))
    with pytest.raises(NoCompatibleHardwareKit) as error:
        resolve_hardware_evaluations(
            evaluate_hardware_candidates(
                opening_group=normalize_opening_type(BayOpeningType.TILT_TURN_LEFT),
                width_mm=D("900"), height_mm=D("1400"),
                base_weight=heavy, params=params,
                explicit_sku="KIT-OB-ESTANDAR",
            ),
            opening_group=normalize_opening_type(BayOpeningType.TILT_TURN_LEFT),
            explicit_sku="KIT-OB-ESTANDAR",
            leaf_width_mm=D("900"), leaf_height_mm=D("1400"),
        )
    # pesada: 3×3200 + 8900 + 3×4100 = 30.800 (mismos componentes) → Δ = 0
    assert error.value.context["delta_clp"] == "0"
