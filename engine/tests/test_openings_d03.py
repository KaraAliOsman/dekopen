"""D03 — Aperturas y tipologías de verdad.

Cubre el contrato del encargo:
- Mapeo total enum ↔ `OpeningSpec` y paridad de fabricación: un producto
  guardado (enum) fabrica idéntico a su `OpeningSpec` migrado.
- Golden tests por tipología: cortes, herrajes y peso por hoja.
- Capacidades por sistema: un sistema sin "hacia afuera" rechaza la
  dirección nombrando las familias que sí la admiten.
- Nombres humanos en español (`spec_display_name_es`).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from dekopen_engine import (
    BayLeaf,
    BayOpeningType,
    EngineResult,
    HingeSide,
    LeafRole,
    NodeType,
    Opening,
    OpeningCapability,
    OpeningDirection,
    OpeningMovement,
    OpeningSpec,
    ParametricNode,
    ProfileRole,
    SystemParams,
    UnitKind,
    calculate_geometry,
    families_admitting_spec,
    legacy_openings_for_spec,
    resolve_opening_spec,
    spec_display_name_es,
    spec_for_legacy,
)
from dekopen_engine.geometry import IncompatibleTypologyError


def d(value: str) -> Decimal:
    return Decimal(value)


def _bay(
    case_id: str, width: str = "1200", height: str = "1400", **kw: object
) -> ParametricNode:
    base = dict(
        id=case_id,
        type=NodeType.BAY,
        width_mm=d(width),
        height_mm=d(height),
        glass_thickness_mm=d("24"),
        glass_spec="4/16/4",
    )
    base.update(kw)
    return ParametricNode.model_validate(base)


def _leaf(
    movement: OpeningMovement,
    *,
    slot: str = "PRIMARY",
    hinge: HingeSide = HingeSide.NONE,
    direction: OpeningDirection | None = None,
    role: LeafRole = LeafRole.SINGLE,
    fixed_in_sash: bool = False,
) -> BayLeaf:
    return BayLeaf(
        slot=slot,
        opening=Opening(
            movement=movement,
            hinge_side=hinge,
            direction=direction,
            leaf_role=role,
            fixed_in_sash=fixed_in_sash,
        ),
    )


def _bom(result: EngineResult) -> dict[str, object]:
    """The fabrication identity the migration must preserve: every cut,
    glass, panel, kit, fitting, reinforcement and leaf weight."""
    def nn(value: object) -> str:
        return "" if value is None else str(value)
    return {
        "profile_cuts": sorted(
            (
                c.sku,
                c.role.value,
                str(c.length_mm),
                nn(c.qty),
                str(c.angle_left),
                str(c.angle_right),
                nn(c.bay_id),
                nn(c.leaf_id),
            )
            for c in result.profile_cuts
        ),
        "glasses": sorted(
            (str(g.width_mm), str(g.height_mm), nn(g.bay_id))
            for g in result.glasses
        ),
        "panels": sorted(
            (p.sku, str(p.width_mm), str(p.height_mm), nn(p.bay_id))
            for p in result.panels
        ),
        "hardware": sorted(
            (h.kit_sku, nn(h.qty), nn(h.bay_id), nn(h.leaf_id))
            for h in result.hardware_items
        ),
        "fittings": sorted(
            (f.sku, nn(f.qty), nn(f.bay_id)) for f in result.fittings
        ),
        "reinforcements": sorted(
            (
                s.parent_profile_sku,
                s.role.value,
                str(s.length_mm),
                nn(s.qty),
                nn(s.leaf_id),
            )
            for s in result.reinforcements
        ),
        "leaf_weights": sorted(
            (
                nn(w.bay_id),
                nn(w.leaf_id),
                str(w.total_weight_kg),
            )
            for w in result.leaf_weights
        ),
    }


def _profile_lengths(result: EngineResult, role: ProfileRole) -> list[str]:
    return [
        str(cut.length_mm)
        for cut in sorted(
            (c for c in result.profile_cuts if c.role is role),
            key=lambda c: c.length_mm,
        )
    ]


def _kit_skus(result: EngineResult) -> list[str]:
    return sorted(item.kit_sku for item in result.hardware_items)


# --- Total map enum ↔ spec ---------------------------------------------


@pytest.mark.parametrize("opening_type", list(BayOpeningType))
def test_every_enum_value_maps_to_one_spec(
    opening_type: BayOpeningType,
) -> None:
    spec = spec_for_legacy(opening_type, "LEFT")
    assert spec.leaves, f"{opening_type} produced an empty spec"
    # The map is total and the enum survives the round trip.
    assert opening_type in legacy_openings_for_spec(spec)


def test_unknown_composition_maps_back_to_canonical_key() -> None:
    spec = OpeningSpec(
        unit_kind=UnitKind.DOOR,
        leaves=[
            _leaf(
                OpeningMovement.TURN,
                hinge=HingeSide.RIGHT,
                direction=OpeningDirection.OUTWARD,
            )
        ],
    )
    assert legacy_openings_for_spec(spec) == frozenset()


# --- Migration parity: enum product fabricates identically -------------


def _legacy_node(opening_type: BayOpeningType, **extra: object) -> ParametricNode:
    base = dict(
        id="legacy",
        type=NodeType.BAY,
        width_mm=d("1200"),
        height_mm=d("1400"),
        glass_thickness_mm=d("24"),
        glass_spec="4/16/4",
        opening_type=opening_type,
    )
    base.update(extra)
    return ParametricNode.model_validate(base)


@pytest.mark.parametrize(
    "opening_type,extra",
    [
        (BayOpeningType.FIXED, {}),
        (BayOpeningType.TURN_LEFT, {}),
        (BayOpeningType.TURN_RIGHT, {}),
        (BayOpeningType.TILT_TURN_LEFT, {}),
        (BayOpeningType.TILT_TURN_RIGHT, {}),
        (BayOpeningType.AWNING, {"height_mm": d("900")}),
        (
            BayOpeningType.DOOR_ENTRY,
            {
                "width_mm": d("900"),
                "height_mm": d("2100"),
                "panel_article_sku": "PANEL-SANDWICH-DEMO-24",
                "door_handedness": "RIGHT",
            },
        ),
        (
            BayOpeningType.DOOR_DOUBLE,
            {
                "width_mm": d("1600"),
                "height_mm": d("2100"),
                "panel_article_sku": "PANEL-SANDWICH-DEMO-24",
                "door_handedness": "RIGHT",
            },
        ),
    ],
)
def test_enum_declared_and_spec_declared_fabricate_identically(
    demo_60_params: SystemParams,
    opening_type: BayOpeningType,
    extra: dict[str, object],
) -> None:
    """Golden de migración: el BOM del producto guardado (enum) es idéntico
    al del OpeningSpec equivalente — misma geometría, mismos herrajes,
    mismo precio de materiales."""
    legacy_node = _legacy_node(opening_type, **extra)
    spec = spec_for_legacy(
        opening_type, str(extra.get("door_handedness") or "LEFT")
    )
    spec_node = legacy_node.model_copy(
        update={
            "opening_type": None,
            "leaves": spec.leaves,
            "unit_kind": spec.unit_kind,
        }
    )
    legacy_result = calculate_geometry(legacy_node, demo_60_params)
    spec_result = calculate_geometry(spec_node, demo_60_params)
    assert _bom(legacy_result) == _bom(spec_result)


def test_sliding_enum_and_spec_fabricate_identically(
    demo_corredera_60_params: SystemParams,
) -> None:
    from dekopen_engine import SlidingLayout, SlidingPanel, SlidingPanelKind

    layout = SlidingLayout(
        tracks=2,
        panels=[
            SlidingPanel(slot="L1", kind=SlidingPanelKind.MOVING, track=0),
            SlidingPanel(slot="L2", kind=SlidingPanelKind.MOVING, track=1),
        ],
    )
    legacy_node = ParametricNode(
        id="sl",
        type=NodeType.BAY,
        width_mm=d("2000"),
        height_mm=d("2100"),
        opening_type=BayOpeningType.SLIDING_2L,
        glass_thickness_mm=d("20"),
        glass_spec="4-12-4 Float Incoloro",
        sliding_layout=layout,
    )
    spec_node = legacy_node.model_copy(
        update={
            "opening_type": None,
            "opening": spec_for_legacy(BayOpeningType.SLIDING_2L).leaves[0].opening,
        }
    )
    assert _bom(calculate_geometry(legacy_node, demo_corredera_60_params)) == _bom(
        calculate_geometry(spec_node, demo_corredera_60_params)
    )


# --- Golden tests por tipología (Diseño 3) ------------------------------


def test_turn_outward_golden(demo_60_params: SystemParams) -> None:
    """Abatible hacia afuera — bisagras a la derecha: misma envolvente de
    hoja que el abatible hacia adentro (la dirección cambia la simbología
    y el plano de herraje, no el encaje del cerco)."""
    result = calculate_geometry(
        _bay(
            "out1",
            opening=Opening(
                movement=OpeningMovement.TURN,
                hinge_side=HingeSide.RIGHT,
                direction=OpeningDirection.OUTWARD,
            ),
        ),
        demo_60_params,
    )
    assert _profile_lengths(result, ProfileRole.FRAME) == [
        "1206.00",
        "1406.00",
    ]
    assert _profile_lengths(result, ProfileRole.SASH) == [
        "1102.00",
        "1302.00",
    ]
    assert _kit_skus(result) == ["KIT-TURN"]
    glass = result.glasses[0]
    assert (str(glass.width_mm), str(glass.height_mm)) == ("976.00", "1176.00")


def test_tilt_only_golden(demo_60_params: SystemParams) -> None:
    """Solo abatimiento (banderola): bisagras abajo, abre hacia adentro."""
    result = calculate_geometry(
        _bay(
            "til1",
            height="900",
            opening=Opening(
                movement=OpeningMovement.TILT,
                hinge_side=HingeSide.BOTTOM,
                direction=OpeningDirection.INWARD,
            ),
        ),
        demo_60_params,
    )
    assert _profile_lengths(result, ProfileRole.SASH) == [
        "802.00",
        "1102.00",
    ]
    assert _kit_skus(result) == ["KIT-TILT"]
    glass = result.glasses[0]
    assert (str(glass.width_mm), str(glass.height_mm)) == ("976.00", "676.00")


def test_top_hung_awning_golden(demo_60_params: SystemParams) -> None:
    """Proyectante: bisagras arriba, abre hacia afuera (kit compás)."""
    result = calculate_geometry(
        _bay(
            "awn1",
            height="900",
            opening=Opening(
                movement=OpeningMovement.TOP_HUNG,
                hinge_side=HingeSide.TOP,
                direction=OpeningDirection.OUTWARD,
            ),
        ),
        demo_60_params,
    )
    assert _profile_lengths(result, ProfileRole.SASH) == [
        "802.00",
        "1102.00",
    ]
    assert _kit_skus(result) == ["KIT-AWNING-16"]


def test_bottom_hung_golden(demo_60_params: SystemParams) -> None:
    """Abatimiento hacia adentro — bisagras abajo."""
    result = calculate_geometry(
        _bay(
            "bh1",
            opening=Opening(
                movement=OpeningMovement.BOTTOM_HUNG,
                hinge_side=HingeSide.BOTTOM,
                direction=OpeningDirection.INWARD,
            ),
        ),
        demo_60_params,
    )
    assert _profile_lengths(result, ProfileRole.SASH) == [
        "1102.00",
        "1302.00",
    ]
    assert _kit_skus(result) == ["KIT-BOTTOM-HUNG"]


def test_fixed_in_sash_golden(demo_60_params: SystemParams) -> None:
    """Fijo en hoja: corta hoja y junquillo pero no evalúa herraje ni
    manilla — vidrio igual que una hoja practicable."""
    result = calculate_geometry(
        _bay(
            "fs1",
            opening=Opening(
                movement=OpeningMovement.FIXED, fixed_in_sash=True
            ),
        ),
        demo_60_params,
    )
    assert _profile_lengths(result, ProfileRole.SASH) == [
        "1102.00",
        "1302.00",
    ]
    assert result.hardware_items == []
    glass = result.glasses[0]
    assert (str(glass.width_mm), str(glass.height_mm)) == ("976.00", "1176.00")


def test_french_window_active_right_golden(demo_60_params: SystemParams) -> None:
    """Francesa 2 hojas — activa derecha: la pasiva corta su lado de
    encuentro como inversor y recibe la falleba; la activa cubre el
    encuentro por el solape declarado."""
    result = calculate_geometry(
        _bay(
            "fr1",
            leaves=[
                _leaf(
                    OpeningMovement.TURN,
                    slot="L1",
                    hinge=HingeSide.LEFT,
                    direction=OpeningDirection.INWARD,
                    role=LeafRole.PASSIVE,
                ),
                _leaf(
                    OpeningMovement.TURN,
                    slot="L2",
                    hinge=HingeSide.RIGHT,
                    direction=OpeningDirection.INWARD,
                    role=LeafRole.ACTIVE,
                ),
            ],
        ),
        demo_60_params,
    )
    # Passive (L1): horizontals 554 mm; active (L2): 562 mm — the active
    # leaf is wider by the declared interlock overlap on the meeting edge.
    widths = [
        str(c.length_mm)
        for c in sorted(
            (
                c
                for c in result.profile_cuts
                if c.role is ProfileRole.SASH and c.length_mm < d("1000")
            ),
            key=lambda c: c.length_mm,
        )
    ]
    assert widths == ["554.00", "562.00"]
    assert _kit_skus(result) == ["KIT-FALLEBA", "KIT-TURN"]
    kits_by_leaf = {item.leaf_id: item.kit_sku for item in result.hardware_items}
    assert kits_by_leaf == {"fr1:L1": "KIT-FALLEBA", "fr1:L2": "KIT-TURN"}
    assert len(result.glasses) == 2


def test_french_window_active_left_symmetric(demo_60_params: SystemParams) -> None:
    """Francesa — activa izquierda: espejo exacto de la activa derecha."""
    left = calculate_geometry(
        _bay(
            "frL",
            leaves=[
                _leaf(
                    OpeningMovement.TURN,
                    slot="L1",
                    hinge=HingeSide.LEFT,
                    direction=OpeningDirection.INWARD,
                    role=LeafRole.ACTIVE,
                ),
                _leaf(
                    OpeningMovement.TURN,
                    slot="L2",
                    hinge=HingeSide.RIGHT,
                    direction=OpeningDirection.INWARD,
                    role=LeafRole.PASSIVE,
                ),
            ],
        ),
        demo_60_params,
    )
    kits_by_leaf = {item.leaf_id: item.kit_sku for item in left.hardware_items}
    assert kits_by_leaf == {"frL:L1": "KIT-TURN", "frL:L2": "KIT-FALLEBA"}
    # The active leaf (now L1) is the wider one.
    active = [
        str(c.length_mm)
        for c in left.profile_cuts
        if c.leaf_id == "frL:L1"
        and c.role is ProfileRole.SASH
        and c.length_mm < d("1000")
    ]
    passive = [
        str(c.length_mm)
        for c in left.profile_cuts
        if c.leaf_id == "frL:L2"
        and c.role is ProfileRole.SASH
        and c.length_mm < d("1000")
    ]
    assert active == ["562.00"]
    assert passive == ["554.00"]


def test_single_door_golden(demo_60_params: SystemParams) -> None:
    """Puerta simple derecha hacia adentro: cerco de tres lados + umbral,
    hoja DOOR_SASH con panel sándwich y kit multipunto."""
    result = calculate_geometry(
        _bay(
            "d1",
            width="900",
            height="2100",
            unit_kind=UnitKind.DOOR,
            panel_article_sku="PANEL-SANDWICH-DEMO-24",
            glass_thickness_mm=None,
            glass_spec=None,
            opening=Opening(
                movement=OpeningMovement.TURN,
                hinge_side=HingeSide.RIGHT,
                direction=OpeningDirection.INWARD,
            ),
        ),
        demo_60_params,
    )
    assert _profile_lengths(result, ProfileRole.FRAME) == [
        "906.00",
        "2103.00",
    ]
    assert _profile_lengths(result, ProfileRole.THRESHOLD) == ["780.00"]
    assert _profile_lengths(result, ProfileRole.DOOR_SASH) == [
        "772.00",
        "2004.00",
    ]
    assert _kit_skus(result) == ["KIT-DOOR-MULTIPOINT"]
    assert len(result.panels) == 1
    panel = result.panels[0]
    assert (str(panel.width_mm), str(panel.height_mm)) == ("616.00", "1848.00")


def test_double_door_golden(demo_60_params: SystemParams) -> None:
    """Puerta doble — activa izquierda: sin mullion, encuentro con
    inversor en la pasiva (falleba), ambas hojas DOOR_SASH con panel."""
    result = calculate_geometry(
        _bay(
            "d2",
            width="1600",
            height="2100",
            unit_kind=UnitKind.DOOR,
            panel_article_sku="PANEL-SANDWICH-DEMO-24",
            glass_thickness_mm=None,
            glass_spec=None,
            leaves=[
                _leaf(
                    OpeningMovement.TURN,
                    slot="L1",
                    hinge=HingeSide.LEFT,
                    direction=OpeningDirection.INWARD,
                    role=LeafRole.ACTIVE,
                ),
                _leaf(
                    OpeningMovement.TURN,
                    slot="L2",
                    hinge=HingeSide.RIGHT,
                    direction=OpeningDirection.INWARD,
                    role=LeafRole.PASSIVE,
                ),
            ],
        ),
        demo_60_params,
    )
    assert _profile_lengths(result, ProfileRole.FRAME) == [
        "1606.00",
        "2103.00",
    ]
    assert _profile_lengths(result, ProfileRole.THRESHOLD) == ["1480.00"]
    kits_by_leaf = {item.leaf_id: item.kit_sku for item in result.hardware_items}
    assert kits_by_leaf == {
        "d2:L1": "KIT-DOOR-MULTIPOINT",
        "d2:L2": "KIT-FALLEBA",
    }
    assert len(result.panels) == 2
    weights = {w.leaf_id: str(w.total_weight_kg) for w in result.leaf_weights}
    assert weights == {"d2:L1": "33.48", "d2:L2": "33.06"}
    # No mullion: the pair meets leaf-to-leaf.
    assert not [
        c for c in result.profile_cuts if c.role is ProfileRole.MULLION_V
    ]


def test_door_with_sidelight_golden(demo_60_params: SystemParams) -> None:
    """Puerta + lateral fijo: la unidad DOOR declara umbral continuo bajo
    el mullion; la hoja vive dentro y el lateral vidriado fijo."""
    node = ParametricNode(
        id="s1",
        type=NodeType.SPLIT_V,
        width_mm=d("1600"),
        height_mm=d("2150"),
        unit_kind=UnitKind.DOOR,
        split_offset_mm=d("950"),
        mullion_profile_sku="POSTE-V",
        children=[
            ParametricNode(
                id="door",
                type=NodeType.BAY,
                panel_article_sku="PANEL-SANDWICH-DEMO-24",
                opening=Opening(
                    movement=OpeningMovement.TURN,
                    hinge_side=HingeSide.LEFT,
                    direction=OpeningDirection.INWARD,
                ),
            ),
            ParametricNode(
                id="side",
                type=NodeType.BAY,
                glass_thickness_mm=d("24"),
                glass_spec="4/16/4",
                opening=Opening(movement=OpeningMovement.FIXED),
            ),
        ],
    )
    result = calculate_geometry(node, demo_60_params)
    assert _profile_lengths(result, ProfileRole.THRESHOLD) == ["1480.00"]
    assert _profile_lengths(result, ProfileRole.MULLION_V) == ["2060.00"]
    assert _profile_lengths(result, ProfileRole.DOOR_SASH) == [
        "842.00",
        "2054.00",
    ]
    assert _kit_skus(result) == ["KIT-DOOR-MULTIPOINT"]
    assert len(result.glasses) == 1  # el lateral
    assert len(result.panels) == 1  # el panel de la puerta


# --- Capacidades por sistema (Diseño 2) ---------------------------------


def test_capability_rejection_names_admitting_families() -> None:
    """Un sistema CASEMENT sin 'hacia afuera' rechaza la dirección y el
    mensaje nombra las familias que sí la admiten (el catálogo concreto en
    la API nombra sistemas)."""
    params = demo_60_params_for_capability_test()
    node = _bay(
        "rejected",
        opening=Opening(
            movement=OpeningMovement.TURN,
            hinge_side=HingeSide.LEFT,
            direction=OpeningDirection.OUTWARD,
        ),
    )
    with pytest.raises(IncompatibleTypologyError) as error:
        calculate_geometry(node, params)
    assert error.value.code == "opening_capability_incompatible"
    message = str(error.value)
    assert "OUTWARD" in message
    assert "familias que sí la admiten" in message
    assert "CASEMENT" in message


def test_capability_rejection_on_sliding_family_names_casement(
    demo_corredera_60_params: SystemParams,
) -> None:
    """Un sistema corredera no fabrica hojas abatibles: el rechazo apunta
    a las familias abisagradas."""
    node = _bay(
        "rej",
        opening=Opening(
            movement=OpeningMovement.TURN,
            hinge_side=HingeSide.LEFT,
            direction=OpeningDirection.INWARD,
        ),
        sliding_layout=None,
    )
    with pytest.raises(IncompatibleTypologyError) as error:
        calculate_geometry(node, demo_corredera_60_params)
    assert error.value.code == "typology_family_incompatible"
    assert "CASEMENT" in str(error.value)


def test_system_without_max_leaves_2_rejects_french_window() -> None:
    params = demo_60_params_for_capability_test().model_copy(
        update={
            "opening_capabilities": (
                OpeningCapability(
                    movement=OpeningMovement.TURN,
                    directions=(OpeningDirection.INWARD,),
                    unit_kinds=(UnitKind.WINDOW,),
                ),
            )
        }
    )
    node = _bay(
        "rejected",
        leaves=[
            _leaf(
                OpeningMovement.TURN,
                slot="L1",
                hinge=HingeSide.LEFT,
                direction=OpeningDirection.INWARD,
                role=LeafRole.ACTIVE,
            ),
            _leaf(
                OpeningMovement.TURN,
                slot="L2",
                hinge=HingeSide.RIGHT,
                direction=OpeningDirection.INWARD,
                role=LeafRole.PASSIVE,
            ),
        ],
    )
    with pytest.raises(IncompatibleTypologyError, match="rol"):
        calculate_geometry(node, params)


def demo_60_params_for_capability_test() -> SystemParams:
    """A casement system whose catalog declares INWARD-only TURN — the
    capability rows, not the family fallback, decide."""
    from engine.tests.catalog import demo_60_params as build

    return build().model_copy(
        update={
            "opening_capabilities": (
                OpeningCapability(
                    movement=OpeningMovement.FIXED,
                    unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                    fixed_in_sash=True,
                ),
                OpeningCapability(
                    movement=OpeningMovement.TURN,
                    directions=(OpeningDirection.INWARD,),
                    leaf_roles=(
                        LeafRole.SINGLE,
                        LeafRole.ACTIVE,
                        LeafRole.PASSIVE,
                    ),
                    unit_kinds=(UnitKind.WINDOW, UnitKind.DOOR),
                    max_leaves=2,
                ),
            )
        }
    )


# --- Nombres humanos (Diseño 5) -----------------------------------------


@pytest.mark.parametrize(
    "spec,expected",
    [
        (
            OpeningSpec(
                leaves=[
                    _leaf(
                        OpeningMovement.TURN,
                        hinge=HingeSide.LEFT,
                        direction=OpeningDirection.OUTWARD,
                    )
                ]
            ),
            "Abatible hacia afuera — bisagras a la izquierda",
        ),
        (
            OpeningSpec(
                leaves=[
                    _leaf(
                        OpeningMovement.TURN,
                        slot="L1",
                        hinge=HingeSide.LEFT,
                        direction=OpeningDirection.INWARD,
                        role=LeafRole.PASSIVE,
                    ),
                    _leaf(
                        OpeningMovement.TURN,
                        slot="L2",
                        hinge=HingeSide.RIGHT,
                        direction=OpeningDirection.INWARD,
                        role=LeafRole.ACTIVE,
                    ),
                ]
            ),
            "Francesa 2 hojas — activa derecha",
        ),
        (
            OpeningSpec(
                leaves=[
                    _leaf(
                        OpeningMovement.TILT,
                        hinge=HingeSide.BOTTOM,
                        direction=OpeningDirection.INWARD,
                    )
                ]
            ),
            "Solo abatimiento (banderola)",
        ),
        (
            OpeningSpec(
                leaves=[
                    _leaf(
                        OpeningMovement.TOP_HUNG,
                        hinge=HingeSide.TOP,
                        direction=OpeningDirection.OUTWARD,
                    )
                ]
            ),
            "Proyectante",
        ),
        (
            OpeningSpec(
                unit_kind=UnitKind.DOOR,
                leaves=[
                    _leaf(
                        OpeningMovement.TURN,
                        slot="L1",
                        hinge=HingeSide.LEFT,
                        direction=OpeningDirection.INWARD,
                        role=LeafRole.ACTIVE,
                    ),
                    _leaf(
                        OpeningMovement.TURN,
                        slot="L2",
                        hinge=HingeSide.RIGHT,
                        direction=OpeningDirection.INWARD,
                        role=LeafRole.PASSIVE,
                    ),
                ],
            ),
            "Puerta doble — activa izquierda",
        ),
        (
            OpeningSpec(leaves=[_leaf(OpeningMovement.FIXED)]),
            "Fijo",
        ),
    ],
)
def test_spec_display_name_es(spec: OpeningSpec, expected: str) -> None:
    assert spec_display_name_es(spec) == expected


# --- Validación del modelo (Diseño 1) ------------------------------------


def test_opening_and_leaves_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="Declare `opening` or `leaves`"):
        ParametricNode(
            id="bad",
            type=NodeType.BAY,
            width_mm=d("1000"),
            height_mm=d("1000"),
            opening=Opening(movement=OpeningMovement.FIXED),
            leaves=[_leaf(OpeningMovement.FIXED)],
        )


def test_fixed_in_sash_requires_fixed_movement() -> None:
    with pytest.raises(ValueError, match="fixed_in_sash"):
        Opening(
            movement=OpeningMovement.TURN,
            hinge_side=HingeSide.LEFT,
            direction=OpeningDirection.INWARD,
            fixed_in_sash=True,
        )


def test_turn_needs_direction() -> None:
    with pytest.raises(ValueError):
        Opening(movement=OpeningMovement.TURN, hinge_side=HingeSide.LEFT)


def test_tilt_turn_is_inward_only() -> None:
    with pytest.raises(ValueError):
        Opening(
            movement=OpeningMovement.TILT_TURN,
            hinge_side=HingeSide.LEFT,
            direction=OpeningDirection.OUTWARD,
        )


def test_french_pair_requires_one_active() -> None:
    with pytest.raises(ValueError, match="exactly one ACTIVE leaf"):
        OpeningSpec(
            leaves=[
                _leaf(
                    OpeningMovement.TURN,
                    slot="L1",
                    hinge=HingeSide.LEFT,
                    direction=OpeningDirection.INWARD,
                ),
                _leaf(
                    OpeningMovement.TURN,
                    slot="L2",
                    hinge=HingeSide.RIGHT,
                    direction=OpeningDirection.INWARD,
                ),
            ]
        )


def test_french_pair_hinges_must_be_outer() -> None:
    """La hoja izquierda abisagra a la izquierda y la derecha a la
    derecha — cualquier otra composición no puede cerrar."""
    with pytest.raises(ValueError, match="hinges (LEFT|RIGHT)|left leaf.*hinges"):
        OpeningSpec(
            leaves=[
                _leaf(
                    OpeningMovement.TURN,
                    slot="L1",
                    hinge=HingeSide.RIGHT,
                    direction=OpeningDirection.INWARD,
                    role=LeafRole.ACTIVE,
                ),
                _leaf(
                    OpeningMovement.TURN,
                    slot="L2",
                    hinge=HingeSide.LEFT,
                    direction=OpeningDirection.INWARD,
                    role=LeafRole.PASSIVE,
                ),
            ]
        )


def test_opening_spec_resolve_prefers_new_fields() -> None:
    node = _bay(
        "n1",
        opening=Opening(
            movement=OpeningMovement.TILT,
            hinge_side=HingeSide.BOTTOM,
            direction=OpeningDirection.INWARD,
        ),
    )
    spec = resolve_opening_spec(node)
    assert spec.leaves[0].opening.movement is OpeningMovement.TILT


def test_opening_spec_conflict_fails_closed() -> None:
    node = _bay(
        "n1",
        opening_type=BayOpeningType.TURN_LEFT,
        opening=Opening(
            movement=OpeningMovement.TILT,
            hinge_side=HingeSide.BOTTOM,
            direction=OpeningDirection.INWARD,
        ),
    )
    with pytest.raises(ValueError, match="declares.*but also"):
        resolve_opening_spec(node)


def test_families_admitting_spec_for_french_window() -> None:
    spec = spec_for_legacy(BayOpeningType.DOOR_DOUBLE, "LEFT")
    assert families_admitting_spec(spec) == ["CASEMENT", "DOOR"]
