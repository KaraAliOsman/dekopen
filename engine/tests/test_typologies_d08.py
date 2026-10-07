"""D08 — tipologías avanzadas: goldens por familia sintética DEMO.

Cada caso congela cortes + BOM + herrajes del fixture DEMO de su familia
(`engine/tests/catalog.py` — SEED_SYNTHETIC, nunca certificado) y un test
de capacidad: un sistema que no declara la tipología la rechaza con causa,
nunca la fabrica por defecto.
"""

from __future__ import annotations

from decimal import Decimal

import pytest


from dekopen_engine import (
    BayLeaf,
    EngineResult,
    HingeSide,
    LeafRole,
    Opening,
    OpeningDirection,
    OpeningMovement,
    OpeningSpec,
    ProfileRole,
    SystemParams,
    UnitKind,
    calculate_geometry,
)
from dekopen_engine.geometry import IncompatibleTypologyError
from dekopen_engine.weight import MissingFabricationAuthority
from dekopen_engine.models import (
    SlidingLayout,
    SlidingPanel,
    SlidingPanelKind,
)
from engine.tests.test_openings_d03 import _bay, _leaf


def d(value: str) -> Decimal:
    return Decimal(value)


def _bom(result: EngineResult) -> dict[str, list[tuple[object, ...]]]:
    return {
        "profile_cuts": sorted(
            (c.sku, c.role.value, str(c.length_mm), c.qty)
            for c in result.profile_cuts
        ),
        "glasses": sorted(
            (str(g.width_mm), str(g.height_mm)) for g in result.glasses
        ),
        "hardware": sorted(
            (h.kit_sku, str(h.qty), h.leaf_id or "")
            for h in result.hardware_items
        ),
        "leaf_weights": sorted(
            (w.leaf_id or "", str(w.total_weight_kg)) for w in result.leaf_weights
        ),
    }


def _pivot_leaf(movement: OpeningMovement, axis: str) -> BayLeaf:
    return BayLeaf(
        slot="PRIMARY",
        axis_offset_mm=d(axis),
        opening=Opening(movement=movement),
    )


def _layout(*panels: SlidingPanel, tracks: int = 2) -> SlidingLayout:
    return SlidingLayout(tracks=tracks, panels=list(panels))


# --- Corredera elevable (HST) -------------------------------------------


def test_hst_scheme_a_fixed_plus_moving_golden(
    demo_elevacion_90_params: SystemParams,
) -> None:
    """Esquema A — fijo izquierda + hoja elevable derecha.

    El marco monta RIEL-ELEV abajo; la hoja lleva el kit elevable de su
    clase de peso (KIT-HST-200 bajo 200 kg) y el vidrio del dominio
    corredera (deducciones 28 mm)."""
    node = _bay(
        "hst-a",
        width="2400",
        height="2200",
        opening=Opening(movement=OpeningMovement.LIFT_SLIDE),
        sliding_layout=_layout(
            SlidingPanel(slot="left", kind=SlidingPanelKind.FIXED),
            SlidingPanel(slot="right", kind=SlidingPanelKind.MOVING, track=1),
        ),
    )
    result = calculate_geometry(node, demo_elevacion_90_params)
    cuts = _bom(result)["profile_cuts"]
    # Riel inferior HST + marco de tres lados.
    assert ("RIEL-ELEV", "RAIL", "2406.00", 1) in cuts
    frame_qty = sum(
        int(str(cut[3])) for cut in cuts if cut[0] == "MARCO-ELEV"
    )
    assert frame_qty == 3
    # Hoja elevable sobre el riel — el kit es la clase de peso declarada.
    leaf_cuts = [cut for cut in cuts if cut[0] == "HOJA-ELEV"]
    assert leaf_cuts
    assert _bom(result)["hardware"] == [
        ("KIT-HST-200", "1", "hst-a:L2"),
    ]
    # El paño fijo izquierdo acristala en marco; la hoja lleva su vidrio.
    assert len(result.glasses) == 2
    weight = result.leaf_weights[0].total_weight_kg
    assert weight is not None and weight > d("0")


def test_hst_scheme_c_two_moving_meeting_golden(
    demo_elevacion_90_params: SystemParams,
) -> None:
    """Esquema C — dos hojas elevables que se encuentran al centro."""
    node = _bay(
        "hst-c",
        width="3000",
        height="2200",
        opening=Opening(movement=OpeningMovement.LIFT_SLIDE),
        sliding_layout=_layout(
            SlidingPanel(slot="left", kind=SlidingPanelKind.MOVING, track=0),
            SlidingPanel(slot="right", kind=SlidingPanelKind.MOVING, track=1),
        ),
    )
    result = calculate_geometry(node, demo_elevacion_90_params)
    assert sorted(
        (item.kit_sku, item.leaf_id) for item in result.hardware_items
    ) == [
        ("KIT-HST-200", "hst-c:L1"),
        ("KIT-HST-200", "hst-c:L2"),
    ]
    # Encuentro: cada hoja lleva perfil de encuentro en su canto de cierre.
    encounter = [
        cut for cut in result.profile_cuts if cut.role is ProfileRole.INTERLOCK
    ]
    assert len(encounter) == 2
    assert len(result.glasses) == 2


def test_hst_window_corredera_also_fabricates(
    demo_elevacion_90_params: SystemParams,
) -> None:
    """La serie HST declara también corredera estándar (kit SLIDING)."""
    node = _bay(
        "hst-std",
        opening=Opening(movement=OpeningMovement.SLIDE),
        sliding_layout=_layout(
            SlidingPanel(slot="a", kind=SlidingPanelKind.MOVING, track=0),
            SlidingPanel(slot="b", kind=SlidingPanelKind.MOVING, track=1),
        ),
    )
    result = calculate_geometry(node, demo_elevacion_90_params)
    assert {item.kit_sku for item in result.hardware_items} == {
        "KIT-SLIDING-ELEV"
    }


# --- Osciloparalela (PSK) -------------------------------------------------


def test_psk_sliding_plus_tilt_golden(
    demo_osciloparalela_params: SystemParams,
) -> None:
    """PSK — hoja que bascula para ventilar y desliza en paralelo."""
    node = _bay(
        "psk-1",
        width="1400",
        height="1600",
        opening=Opening(movement=OpeningMovement.PARALLEL_SLIDE),
        sliding_layout=_layout(
            SlidingPanel(slot="sola", kind=SlidingPanelKind.MOVING, track=0),
            tracks=1,
        ),
    )
    result = calculate_geometry(node, demo_osciloparalela_params)
    # Herraje específico PSK por peso — la hoja ~40 kg toma el kit base.
    assert _bom(result)["hardware"] == [
        ("KIT-PSK-130", "1", "psk-1:L1"),
    ]
    assert any(
        cut.sku == "RIEL-PSK" and cut.role is ProfileRole.RAIL
        for cut in result.profile_cuts
    )


# --- Plegable -------------------------------------------------------------


def _fold_leaf(
    slot: str,
    hinge: HingeSide,
    role: LeafRole = LeafRole.PASSIVE,
) -> BayLeaf:
    return _leaf(
        OpeningMovement.FOLD,
        slot=slot,
        hinge=hinge,
        direction=OpeningDirection.OUTWARD,
        role=role,
    )


def test_fold_3_0_pack_golden(demo_plegable_70_params: SystemParams) -> None:
    """Plegable 3+0 — paquete completo a la izquierda, sin hoja de paso."""
    node = _bay(
        "fold-3",
        width="2400",
        height="2200",
        leaves=[
            _fold_leaf("L1", HingeSide.LEFT),
            _fold_leaf("L2", HingeSide.LEFT),
            _fold_leaf("L3", HingeSide.LEFT),
        ],
    )
    result = calculate_geometry(node, demo_plegable_70_params)
    cuts = _bom(result)["profile_cuts"]
    # Guía plegable arriba y abajo.
    rails = sorted(cut for cut in cuts if cut[0] == "GUIA-FOLD")
    assert rails == [
        ("GUIA-FOLD", "RAIL", "2406.00", 1),
        ("GUIA-FOLD", "RAIL", "2406.00", 1),
    ]
    # Tres hojas: kit de carretillas/bisagras por hoja.
    assert _bom(result)["hardware"] == [
        ("KIT-FOLD-80", "1", "fold-3:L1"),
        ("KIT-FOLD-80", "1", "fold-3:L2"),
        ("KIT-FOLD-80", "1", "fold-3:L3"),
    ]
    leaf_heights = {
        str(cut.length_mm)
        for cut in result.profile_cuts
        if cut.sku == "HOJA-FOLD" and cut.leaf_id
    }
    assert "2036.00" in leaf_heights  # interior 2080 − 50 de guía + soldadura


def test_fold_2_1_with_pass_door_golden(
    demo_plegable_70_params: SystemParams,
) -> None:
    """Plegable 2+1 — dos hojas al anclaje izquierdo; la tercera, que
    cierra sobre el anclaje derecho, es la hoja de paso (kit TURN)."""
    node = _bay(
        "fold-2p1",
        width="2400",
        height="2200",
        leaves=[
            _fold_leaf("L1", HingeSide.LEFT),
            _fold_leaf("L2", HingeSide.LEFT),
            _fold_leaf("R1", HingeSide.RIGHT, role=LeafRole.ACTIVE),
        ],
    )
    result = calculate_geometry(node, demo_plegable_70_params)
    assert _bom(result)["hardware"] == [
        ("KIT-FOLD-80", "1", "fold-2p1:L1"),
        ("KIT-FOLD-80", "1", "fold-2p1:L2"),
        ("KIT-FOLD-PASO", "1", "fold-2p1:R1"),
    ]


def test_fold_pass_door_must_anchor_the_pack(
    demo_plegable_70_params: SystemParams,
) -> None:
    """Una hoja de paso en medio del paquete no toca el marco — no se
    fabrica, se rechaza con causa."""
    with pytest.raises(ValueError, match="hoja de paso"):
        OpeningSpec(
            unit_kind=UnitKind.WINDOW,
            leaves=[
                _fold_leaf("L1", HingeSide.LEFT),
                _fold_leaf("L2", HingeSide.LEFT, role=LeafRole.ACTIVE),
                _fold_leaf("L3", HingeSide.LEFT),
            ],
        )


def test_fold_requires_declared_guide_clearances(
    demo_plegable_70_params: SystemParams,
) -> None:
    """Sin juegos de guía declarados no hay fabricación — causa explícita."""
    params = demo_plegable_70_params.model_copy(
        update={"fold_guide_clearance_mm": None}
    )
    node = _bay(
        "fold-nomsg",
        width="2400",
        height="2200",
        leaves=[
            _fold_leaf("L1", HingeSide.LEFT),
            _fold_leaf("L2", HingeSide.LEFT),
        ],
    )
    with pytest.raises(MissingFabricationAuthority, match="fold_"):
        calculate_geometry(node, params)


# --- Pivotante ------------------------------------------------------------


def test_pivot_door_with_declared_axis_golden(
    demo_pivotante_120_params: SystemParams,
) -> None:
    """Puerta pivotante — eje desplazado 500 mm desde el canto izquierdo."""
    node = _bay(
        "piv-door",
        width="1400",
        height="2400",
        unit_kind=UnitKind.DOOR,
        panel_article_sku="PANEL-SANDWICH-DEMO-24",
        leaves=[_pivot_leaf(OpeningMovement.PIVOT_V, "500")],
    )
    result = calculate_geometry(node, demo_pivotante_120_params)
    assert _bom(result)["hardware"] == [("KIT-PIV-300", "1", "")]
    # La hoja descontada por el juego pivotante (10 mm por lado).
    leaf_cuts = [
        cut
        for cut in result.profile_cuts
        if cut.role is ProfileRole.DOOR_SASH
    ]
    assert leaf_cuts
    # Panel sándwich como relleno de puerta.
    assert result.panels


def test_pivot_window_horizontal_axis_golden(
    demo_pivotante_120_params: SystemParams,
) -> None:
    """Pivotante de eje horizontal — la compensación es vertical."""
    node = _bay(
        "piv-h",
        width="1200",
        height="1200",
        leaves=[_pivot_leaf(OpeningMovement.PIVOT_H, "400")],
    )
    result = calculate_geometry(node, demo_pivotante_120_params)
    assert _bom(result)["hardware"] == [("KIT-PIV-80", "1", "")]
    assert result.glasses


def test_pivot_without_axis_refuses(
    demo_pivotante_120_params: SystemParams,
) -> None:
    """El eje desplazado es dato declarado — sin él, causa, no fabricación."""
    node = _bay(
        "piv-noaxis",
        opening=Opening(movement=OpeningMovement.PIVOT_H),
    )
    with pytest.raises(ValueError, match="eje"):
        calculate_geometry(node, demo_pivotante_120_params)


def test_pivot_axis_outside_leaf_refuses(
    demo_pivotante_120_params: SystemParams,
) -> None:
    node = _bay(
        "piv-out",
        width="1200",
        height="1200",
        leaves=[_pivot_leaf(OpeningMovement.PIVOT_H, "2000")],
    )
    with pytest.raises(ValueError, match="fuera de la hoja"):
        calculate_geometry(node, demo_pivotante_120_params)


# --- Guillotina -----------------------------------------------------------


def test_guillotina_double_golden(
    demo_guillotina_60_params: SystemParams,
) -> None:
    """Guillotina doble — dos hojas TOP/BOTTOM, travesaño de encuentro."""
    node = _bay(
        "gui-2",
        width="1000",
        height="1500",
        leaves=[
            _leaf(OpeningMovement.VERTICAL_SLIDE, slot="TOP"),
            _leaf(OpeningMovement.VERTICAL_SLIDE, slot="BOTTOM"),
        ],
    )
    result = calculate_geometry(node, demo_guillotina_60_params)
    assert _bom(result)["hardware"] == [
        ("KIT-GUI-MUELLES", "1", "gui-2:BOTTOM"),
        ("KIT-GUI-MUELLES", "1", "gui-2:TOP"),
    ]
    # El travesaño de encuentro vive en la arista de solape de cada hoja.
    meeting = [
        cut for cut in result.profile_cuts if cut.role is ProfileRole.INTERLOCK
    ]
    assert len(meeting) == 2
    # Altura de corte: pitch + solape central + aditivo de extremo.
    cuts_h = [
        str(cut.length_mm)
        for cut in result.profile_cuts
        if cut.sku == "HOJA-GUI"
    ]
    assert "721.00" in cuts_h  # (1400−30)/2 + 30 + 6 de extremo


def test_guillotina_single_hung_golden(
    demo_guillotina_60_params: SystemParams,
) -> None:
    """Guillotina simple — fijo arriba (en marco) + hoja inferior."""
    node = _bay(
        "gui-1",
        width="1000",
        height="1500",
        leaves=[
            _leaf(OpeningMovement.FIXED, slot="TOP"),
            _leaf(OpeningMovement.VERTICAL_SLIDE, slot="BOTTOM"),
        ],
    )
    result = calculate_geometry(node, demo_guillotina_60_params)
    assert _bom(result)["hardware"] == [
        ("KIT-GUI-MUELLES", "1", "gui-1:BOTTOM"),
    ]
    # Un fijo acristalado en marco + el vidrio de la hoja.
    assert len(result.glasses) == 2
    leaf_cuts = [
        cut.length_mm
        for cut in result.profile_cuts
        if cut.sku == "HOJA-GUI" and cut.leaf_id
    ]
    assert leaf_cuts


def test_guillotina_slots_required(
    demo_guillotina_60_params: SystemParams,
) -> None:
    """Dos hojas sin TOP/BOTTOM declarado no son guillotina construible."""
    with pytest.raises(ValueError):
        OpeningSpec(
            unit_kind=UnitKind.WINDOW,
            leaves=[
                _leaf(OpeningMovement.VERTICAL_SLIDE, slot="A"),
                _leaf(OpeningMovement.VERTICAL_SLIDE, slot="B"),
            ],
        )


# --- Puerta corredera -----------------------------------------------------


def test_sliding_door_unit_golden(
    demo_puerta_corredera_params: SystemParams,
) -> None:
    """Puerta corredera — unidad DOOR con hoja corredera: marco de tres
    lados + umbral + kit de puerta corredera (cerradura de patio), no el
    kit SLIDING de ventana ni el multipunto de puerta practicable."""
    node = _bay(
        "ptdoor-1",
        width="2000",
        height="2200",
        unit_kind=UnitKind.DOOR,
        panel_article_sku="PANEL-SANDWICH-DEMO-24",
        leaves=[_leaf(OpeningMovement.SLIDE)],
        sliding_layout=_layout(
            SlidingPanel(slot="fijo", kind=SlidingPanelKind.FIXED),
            SlidingPanel(slot="puerta", kind=SlidingPanelKind.MOVING, track=1),
        ),
    )
    result = calculate_geometry(node, demo_puerta_corredera_params)
    assert _bom(result)["hardware"] == [
        ("KIT-PTA-CORR-ELEV", "1", "ptdoor-1:L2"),
    ]
    assert any(
        cut.role is ProfileRole.THRESHOLD for cut in result.profile_cuts
    )


# --- Capacidad: sin declaración, no disponible con causa -----------------


@pytest.mark.parametrize(
    "movement,params_fixture",
    [
        (OpeningMovement.LIFT_SLIDE, "demo_corredera_60_params"),
        (OpeningMovement.PARALLEL_SLIDE, "demo_corredera_60_params"),
        (OpeningMovement.PARALLEL_SLIDE, "demo_elevacion_90_params"),
        (OpeningMovement.VERTICAL_SLIDE, "demo_elevacion_90_params"),
        (OpeningMovement.LIFT_SLIDE, "demo_plegable_70_params"),
    ],
)
def test_movement_refuses_where_the_system_does_not_declare_it(
    movement: OpeningMovement,
    params_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    params = request.getfixturevalue(params_fixture)
    node = _bay(
        "cap-neg",
        opening=Opening(movement=movement),
        sliding_layout=_layout(
            SlidingPanel(slot="a", kind=SlidingPanelKind.MOVING, track=0),
            SlidingPanel(slot="b", kind=SlidingPanelKind.MOVING, track=1),
        ),
    )
    with pytest.raises((IncompatibleTypologyError, ValueError)):
        calculate_geometry(node, params)


def test_fold_refuses_on_a_sliding_system(
    demo_corredera_60_params: SystemParams,
) -> None:
    node = _bay(
        "cap-fold",
        width="1600",
        height="2200",
        leaves=[
            _fold_leaf("L1", HingeSide.LEFT),
            _fold_leaf("L2", HingeSide.LEFT),
        ],
    )
    with pytest.raises(IncompatibleTypologyError):
        calculate_geometry(node, demo_corredera_60_params)


def test_pivot_refuses_on_a_folding_system(
    demo_plegable_70_params: SystemParams,
) -> None:
    node = _bay(
        "cap-piv",
        leaves=[_pivot_leaf(OpeningMovement.PIVOT_V, "500")],
    )
    with pytest.raises(IncompatibleTypologyError):
        calculate_geometry(node, demo_plegable_70_params)


def test_door_slide_refuses_on_window_only_system(
    demo_corredera_60_params: SystemParams,
) -> None:
    """DEMO_CORREDERA_60 no declara el umbral de puerta ni el kit de
    puerta corredera — la hoja se admite pero la fabricación falla con
    causa (artículo THRESHOLD ausente), nunca fabrica con datos inventados."""
    node = _bay(
        "cap-door",
        width="2000",
        height="2200",
        unit_kind=UnitKind.DOOR,
        leaves=[_leaf(OpeningMovement.SLIDE)],
        sliding_layout=_layout(
            SlidingPanel(slot="a", kind=SlidingPanelKind.MOVING, track=0),
            SlidingPanel(slot="b", kind=SlidingPanelKind.MOVING, track=1),
        ),
    )
    with pytest.raises((IncompatibleTypologyError, ValueError)):
        calculate_geometry(node, demo_corredera_60_params)
