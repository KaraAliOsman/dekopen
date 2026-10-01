"""Design assist: provider output is validated against the live product before
it becomes an op — index bounds, enums, ranges; rejected ops are reported,
never silently applied."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.exceptions import APIException

from ai_gateway.providers import MockProvider
from projects import design_assist


def _product(modules=2, couplings=1):
    return {
        "modules": [{"width_mm": "1200", "height_mm": "1500"} for _ in range(modules)],
        "couplings": [{"angle_deg": "22.5"} for _ in range(couplings)],
    }


def _position():
    return {"id": uuid4(), "project_id": uuid4(), "system_id": uuid4()}


def _catalog(**overrides):
    catalog = {
        "glass_skus": {"GLASS-4MM", "DVH-4-12-4"},
        "panel_skus": {"PANEL-SANDWICH-24"},
        "thicknesses": {Decimal("4"), Decimal("24")},
    }
    catalog.update(overrides)
    return catalog


def _envelope(output):
    return {
        "audit_id": str(uuid4()),
        "capability": "design_assist",
        "model": "DEKOPEN Diseñador™",
        "output": output if isinstance(output, str) else json.dumps(output),
        "tokens_prompt": 10,
        "tokens_completion": 10,
        "latency_ms": 1,
        "credits_debited": 10,
    }


def _patch_invoke(monkeypatch, output, catalog=None):
    captured = {}

    def fake_invoke(**kwargs):
        captured["input"] = kwargs["input_payload"]
        return _envelope(output)

    monkeypatch.setattr(design_assist.gateway, "invoke", fake_invoke)
    monkeypatch.setattr(design_assist, "_catalog", lambda system_id, org_id: catalog or _catalog())
    return captured


def test_assist_returns_validated_ops(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_module_count", "count": 3},
                {"op": "equalize_widths"},
                {"op": "set_opening", "module": 1, "opening": "SLIDING_2L"},
            ],
            "notes": "3 módulos correderas",
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=3, couplings=2),
        prompt="3 módulos correderas",
        system_id=uuid4(),
        operation_key="assist-1",
    )
    assert len(out["ops"]) == 3
    assert out["rejected"] == []
    assert out["model"] == "DEKOPEN Diseñador™"
    assert out["notes"] == "3 módulos correderas"


def test_assist_audits_the_submitted_product(monkeypatch):
    captured = _patch_invoke(monkeypatch, {"ops": [], "notes": "nada"})
    design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(),
        prompt="iguala anchos",
        system_id=uuid4(),
        operation_key="assist-2",
    )
    assert captured["input"]["product"]["modules"][0]["width_mm"] == "1200"
    assert captured["input"]["product"]["modules"][1]["index"] == 1
    assert "set_module_count" in captured["input"]["ops_contract"]


def test_out_of_bounds_module_is_rejected(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {"ops": [{"op": "set_opening", "module": 5, "opening": "FIXED"}], "notes": ""},
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=2),
        prompt="fijo en el quinto",
        system_id=uuid4(),
        operation_key="assist-3",
    )
    assert out["ops"] == []
    assert out["rejected"][0]["reason"] == "apertura_invalida"


def test_unknown_op_is_rejected_not_applied(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {"ops": [{"op": "delete_project"}, {"op": "set_height", "height_mm": 1600}]},
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(),
        prompt="borra todo y alto 1600",
        system_id=uuid4(),
        operation_key="assist-4",
    )
    assert [op["op"] for op in out["ops"]] == ["set_height"]
    assert out["rejected"][0]["reason"] == "operacion_desconocida"


def test_ranges_and_enums_enforced(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_module_count", "count": 99},
                {"op": "set_coupling_angle", "coupling": 0, "angle_deg": 120},
                {"op": "set_opening", "module": 0, "opening": "ROTATE"},
                {"op": "set_module_width", "module": 0, "width_mm": 1200},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(),
        prompt="todo al límite: 99 módulos de 1200 mm y ángulo 120",
        system_id=uuid4(),
        operation_key="assist-5",
    )
    assert [op["op"] for op in out["ops"]] == ["set_module_width"]
    assert out["ops"][0]["width_mm"] == "1200"
    assert len(out["rejected"]) == 3


def test_last_module_cannot_be_removed(monkeypatch):
    _patch_invoke(monkeypatch, {"ops": [{"op": "remove_unit", "module": 0}]})
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=1, couplings=0),
        prompt="quita el módulo",
        system_id=uuid4(),
        operation_key="assist-6",
    )
    assert out["ops"] == []
    assert out["rejected"][0]["reason"] == "modulo_invalido"


def test_bad_provider_document_is_a_502(monkeypatch):
    _patch_invoke(monkeypatch, "no es json {")
    with pytest.raises(APIException) as error:
        design_assist.assist(
            org_id=uuid4(),
            user_id=uuid4(),
            position=_position(),
            product=_product(),
            prompt="x",
            system_id=uuid4(),
            operation_key="assist-7",
        )
    assert error.value.get_codes() == "design_assist_bad_output"


def test_invalid_product_summary_is_a_400(monkeypatch):
    _patch_invoke(monkeypatch, {"ops": []})
    with pytest.raises(APIException) as error:
        design_assist.assist(
            org_id=uuid4(),
            user_id=uuid4(),
            position=_position(),
            product={"modules": []},
            prompt="x",
            system_id=uuid4(),
            operation_key="assist-8",
        )
    assert error.value.get_codes() == "design_assist_product_invalid"


def test_structural_ops_validate_against_the_evolving_assembly(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_module_count", "count": 12},
                {"op": "add_unit", "side": "right"},
                {"op": "set_opening", "module": 11, "opening": "FIXED"},
                {"op": "set_opening", "module": 12, "opening": "FIXED"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=11, couplings=10),
        prompt="doce más uno",
        system_id=uuid4(),
        operation_key="assist-9",
    )
    # Positional addresses name the original 11 modules — `module: 11` and
    # `module: 12` are out of bounds even though sim pads added refs to 12;
    # the client resolves numerics against its saved product, never the
    # mutated list.
    assert [op["op"] for op in out["ops"]] == [
        "set_module_count",
    ]
    assert [item["reason"] for item in out["rejected"]] == [
        "lado_invalido",
        "apertura_invalida",
        "apertura_invalida",
    ]


def test_remove_unit_shifts_the_validation_surface(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "remove_unit", "module": 0},
                {"op": "set_opening", "module": 1, "opening": "AWNING"},
                {"op": "set_opening", "module": 2, "opening": "AWNING"},
                {"op": "add_unit", "side": "left"},
                {"op": "set_opening", "module": 2, "opening": "FIXED"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=3, couplings=2),
        prompt="reacomoda",
        system_id=uuid4(),
        operation_key="assist-10",
    )
    # Positional addresses keep naming the original order after remove_unit:
    # index 1 → m2 and index 2 → m3 (both still live). The second set_opening
    # on m3 simply overwrites the earlier one.
    assert [op["op"] for op in out["ops"]] == [
        "remove_unit",
        "set_opening",
        "set_opening",
        "add_unit",
        "set_opening",
    ]
    assert out["ops"][4]["module"] == "m3"
    assert out["rejected"] == []


def test_catalog_skus_are_enforced(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_glass", "module": 0, "sku": "GLASS-4MM"},
                {"op": "set_glass", "module": 0, "sku": "PANEL-MADE-UP"},
                {"op": "set_panel", "module": 1, "sku": "PANEL-SANDWICH-24"},
                {"op": "set_panel", "module": 1, "sku": "NO-EXISTE"},
                {"op": "set_panel", "module": 1, "sku": None},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(),
        prompt="vidrios y panel",
        system_id=uuid4(),
        operation_key="assist-11",
    )
    assert [op["op"] for op in out["ops"]] == ["set_glass", "set_panel", "set_panel"]
    assert [item["reason"] for item in out["rejected"]] == [
        "vidrio_invalido",
        "panel_invalido",
    ]


def test_total_width_floor_tracks_the_simulated_module_count(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_total_width", "width_mm": "300"},
                {"op": "set_module_count", "count": 1},
                {"op": "set_total_width", "width_mm": "300"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=3, couplings=2),
        system_id=uuid4(),
        prompt="deja 1 módulo de 300 mm",
        operation_key="assist-13",
    )
    # 300 mm is below the 150×3 floor first; after shrinking to one module the
    # same total clears the floor — the simulated count decides, not the
    # submitted summary's count.
    assert [op["op"] for op in out["ops"]] == ["set_module_count", "set_total_width"]
    assert [item["reason"] for item in out["rejected"]] == ["ancho_invalido"]


def test_thickness_must_match_a_glazing_bead_rule(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_glass_thickness", "module": 0, "mm": "24"},
                {"op": "set_glass_thickness", "module": 0, "mm": "9"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(),
        prompt="vidrios de 24 mm y de 9 mm",
        system_id=uuid4(),
        operation_key="assist-12",
    )
    assert [op["op"] for op in out["ops"]] == ["set_glass_thickness"]
    assert [item["reason"] for item in out["rejected"]] == ["espesor_invalido"]


def test_mock_provider_emits_ops_for_spanish_intent():
    provider = MockProvider()
    out = provider.invoke(
        route={"public_name": "DEKOPEN Diseñador™", "provider_model": "mock-design-1"},
        capability="design_assist",
        input_payload={
            "prompt": "3 módulos corredera, ancho total de 2400, iguales",
            "product": _product(modules=3, couplings=2),
        },
    )
    document = json.loads(out["output"])
    ops = [op["op"] for op in document["ops"]]
    assert "set_module_count" in ops
    assert "set_total_width" in ops
    assert "equalize_widths" in ops
    assert ops.count("set_opening") == 3


def test_mock_provider_bows_angles_and_empty_notes():
    provider = MockProvider()
    out = provider.invoke(
        route={"public_name": "DEKOPEN Diseñador™", "provider_model": "mock-design-1"},
        capability="design_assist",
        input_payload={
            "prompt": "convierte en arco",
            "product": _product(modules=5, couplings=4),
        },
    )
    document = json.loads(out["output"])
    assert document["ops"] == [
        {"op": "set_coupling_angle", "coupling": i, "angle_deg": 22.5} for i in range(4)
    ]


def test_undeclared_dimensions_are_rejected_not_invented(monkeypatch):
    """Trust boundary: the model may only cite numbers the user wrote. A
    prompt like 'más ancha' declares no width — a model-invented 2400 must be
    rejected, never applied."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_total_width", "width_mm": 2400},
                {"op": "set_height", "height_mm": 1500},
                {"op": "set_module_count", "count": 5},
                {"op": "set_coupling_angle", "coupling": 0, "angle_deg": 30},
                {"op": "set_glass_thickness", "module": 0, "mm": "4"},
                {"op": "equalize_widths"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=3, couplings=2),
        prompt="hazla más ancha y pareja",
        system_id=uuid4(),
        operation_key="assist-g1",
    )
    assert [op["op"] for op in out["ops"]] == ["equalize_widths"]
    assert [item["reason"] for item in out["rejected"]] == [
        "ancho_no_declarado",
        "alto_no_declarado",
        "cantidad_no_declarada",
        "angulo_no_declarado",
        "espesor_no_declarado",
    ]


def test_declared_units_ground_numeric_ops(monkeypatch):
    """'2,4 metros' declares 2400 mm; 'tres módulos' declares count 3 —
    Chilean-locale parsing must recognize both as user-entered values."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_total_width", "width_mm": "2400"},
                {"op": "set_module_count", "count": 3},
                {"op": "set_height", "height_mm": "1500"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=2, couplings=1),
        prompt="tres módulos de 2,4 metros de ancho y 1500 mm de alto",
        system_id=uuid4(),
        operation_key="assist-g2",
    )
    assert [op["op"] for op in out["ops"]] == [
        "set_total_width",
        "set_module_count",
        "set_height",
    ]
    assert out["rejected"] == []


def test_unit_suffixed_literal_does_not_declare_its_raw_value(monkeypatch):
    """'240 cm' declares 2400 mm only — a provider proposing width 240 must
    not pass grounding on the token's unconverted literal."""
    _patch_invoke(
        monkeypatch,
        {"ops": [{"op": "set_total_width", "width_mm": "240"}]},
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=1, couplings=0),
        prompt="ancho total 240 cm",
        system_id=uuid4(),
        operation_key="assist-g3",
    )
    assert out["ops"] == []
    assert out["rejected"][0]["reason"] == "ancho_no_declarado"


def test_signed_angle_declares_the_signed_value(monkeypatch):
    """'ángulo -30 grados' must declare -30 — the sign binds to the number,
    while range punctuation like '2400-1500' keeps both endpoints positive."""
    _patch_invoke(
        monkeypatch,
        {"ops": [{"op": "set_coupling_angle", "coupling": 0, "angle_deg": "-30"}]},
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=2, couplings=1),
        prompt="ángulo -30 grados",
        system_id=uuid4(),
        operation_key="assist-g4",
    )
    assert out["ops"] == [{"op": "set_coupling_angle", "coupling": "c1", "angle_deg": "-30"}]
    assert out["rejected"] == []


def test_sign_binding_is_lexical_not_spacing_based(monkeypatch):
    """A '-' subtracting from a preceding number is range punctuation however
    it is spaced; only a non-subtraction '-' signs the value."""
    _patch_invoke(monkeypatch, {"ops": []})
    values = design_assist._declared_values
    assert Decimal("-30") in values("ángulo -30 grados")
    for prompt in (
        "ángulo entre 30 -20 grados",
        "ángulo entre 30 - 20 grados",
        "ángulo 30-20 grados",
        "ángulo entre 30° - 20°",
        "ángulo 30 grados - 20 grados",
        "30 mm - 20 mm",
    ):
        declared = values(prompt)
        assert Decimal("-20") not in declared
        assert Decimal("20") in declared and Decimal("30") in declared
    for prompt in ("ángulos 30°; -20°", "+30°/-20°", "30, -20", "30 y -20"):
        declared = values(prompt)
        assert Decimal("-20") in declared and Decimal("30") in declared


def test_stable_refs_address_modules_and_survive_structural_ops(monkeypatch):
    """§2: domain ids drive the wire — a ref names the entity, not its slot.
    Removing m2 mid-sequence keeps m3's ref honest where an index would have
    silently shifted, and a unit the sequence itself adds is addressable as
    added_m{n}."""
    captured = _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "remove_unit", "module": "mod-b"},
                {"op": "set_opening", "module": "mod-c", "opening": "AWNING"},
                {"op": "add_unit", "side": "right"},
                {"op": "set_opening", "module": "added_m1", "opening": "FIXED"},
                {"op": "set_coupling_angle", "coupling": "added_c1", "angle_deg": "-15"},
            ],
            "notes": "",
        },
    )
    product = {
        "modules": [
            {"id": "mod-a", "width_mm": "1200", "height_mm": "1500"},
            {"id": "mod-b", "width_mm": "900", "height_mm": "1500"},
            {"id": "mod-c", "width_mm": "900", "height_mm": "1500", "contour": {}},
        ],
        "couplings": [
            {"id": "cpl-1", "angle_deg": "20", "modules": ["mod-a", "mod-b"]},
            {"id": "cpl-2", "angle_deg": "20", "modules": ["mod-b", "mod-c"]},
        ],
    }
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=product,
        prompt="ángulo -15 en una unión",
        system_id=uuid4(),
        operation_key="assist-r1",
    )
    assert out["ops"] == [
        {"op": "remove_unit", "module": "mod-b"},
        {"op": "set_opening", "module": "mod-c", "opening": "AWNING"},
        {"op": "add_unit", "side": "right", "ref": "added_m1"},
        {"op": "set_opening", "module": "added_m1", "opening": "FIXED"},
        {"op": "set_coupling_angle", "coupling": "added_c1", "angle_deg": "-15"},
    ]
    assert out["rejected"] == []
    summary = captured["input"]["product"]
    assert summary["modules"][0]["ref"] == "mod-a"
    assert summary["modules"][2]["shape"] == "CONTOUR"
    assert summary["couplings"][0]["modules"] == ["mod-a", "mod-b"]
    assert summary["couplings"][1]["ref"] == "cpl-2"


def test_unknown_ref_is_rejected_not_floored_to_an_index(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {"ops": [{"op": "set_opening", "module": "mod-z", "opening": "FIXED"}]},
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=2),
        prompt="fijo en módulo z",
        system_id=uuid4(),
        operation_key="assist-r2",
    )
    assert out["ops"] == []
    assert out["rejected"][0]["reason"] == "apertura_invalida"


def _graph_product():
    """Two-unit assembly with explicit coupling endpoints — the wire surface
    the canvas client already sends (stable ids, edge topology)."""
    return {
        "modules": [
            {"id": "m1", "width_mm": "900", "height_mm": "1500"},
            {"id": "m2", "width_mm": "900", "height_mm": "1500"},
        ],
        "couplings": [
            {
                "id": "c1",
                "angle_deg": "0",
                "kind": "INLINE",
                "modules": ["m1", "m2"],
                "edges": ["right", "left"],
            }
        ],
    }


def test_duplicate_module_lands_on_the_free_edge(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "duplicate_module", "module": "m2"},
                {"op": "set_opening", "module": "added_m1", "opening": "TURN_LEFT"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_graph_product(),
        prompt="duplica la segunda con apertura",
        system_id=uuid4(),
        operation_key="assist-d1",
    )
    assert out["ops"] == [
        {"op": "duplicate_module", "module": "m2"},
        {"op": "set_opening", "module": "added_m1", "opening": "TURN_LEFT"},
    ]
    assert out["rejected"] == []


def test_duplicate_module_refused_when_both_edges_claimed(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {"ops": [{"op": "duplicate_module", "module": "m1"}]},
    )
    product = _graph_product()
    product["modules"].append({"id": "m0", "width_mm": "700", "height_mm": "1500"})
    product["couplings"].insert(
        0,
        {
            "id": "c0",
            "angle_deg": "0",
            "kind": "INLINE",
            "modules": ["m0", "m1"],
            "edges": ["right", "left"],
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=product,
        prompt="duplica la del medio",
        system_id=uuid4(),
        operation_key="assist-d2",
    )
    assert out["ops"] == []
    assert out["rejected"][0]["reason"] == "sin_borde_libre"


def test_insert_module_splits_the_inline_seam(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "insert_module", "coupling": "c1"},
                {"op": "set_coupling_angle", "coupling": "added_c1", "angle_deg": "12"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_graph_product(),
        prompt="inserta una unidad en la unión con ángulo 12",
        system_id=uuid4(),
        operation_key="assist-d3",
    )
    assert out["ops"] == [
        {"op": "insert_module", "coupling": "c1"},
        {"op": "set_coupling_angle", "coupling": "added_c1", "angle_deg": "12"},
    ]
    assert out["rejected"] == []


def test_insert_module_refuses_non_inline_joints(monkeypatch):
    _patch_invoke(monkeypatch, {"ops": [{"op": "insert_module", "coupling": "c1"}]})
    product = _graph_product()
    product["couplings"][0]["kind"] = "STACKED"
    product["couplings"][0]["edges"] = ["top", "bottom"]
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=product,
        prompt="inserta en la unión",
        system_id=uuid4(),
        operation_key="assist-d4",
    )
    assert out["ops"] == []
    assert out["rejected"][0]["reason"] == "union_invalida"


def test_remove_coupling_frees_the_edges(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "remove_coupling", "coupling": "c1"},
                {"op": "duplicate_module", "module": "m1"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_graph_product(),
        prompt="desconecta la unión y duplica la primera",
        system_id=uuid4(),
        operation_key="assist-d5",
    )
    assert [op["op"] for op in out["ops"]] == ["remove_coupling", "duplicate_module"]
    assert out["rejected"] == []


def test_set_coupling_kind_follows_the_joint_edges(monkeypatch):
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_coupling_kind", "coupling": "c1", "kind": "STACKED"},
                {"op": "set_coupling_kind", "coupling": "c1", "kind": "INLINE"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_graph_product(),
        prompt="cambia el tipo de unión",
        system_id=uuid4(),
        operation_key="assist-d6",
    )
    # A left/right seam can only stay INLINE — the stacked kind is refused.
    assert out["ops"] == [{"op": "set_coupling_kind", "coupling": "c1", "kind": "INLINE"}]
    assert out["rejected"][0]["reason"] == "tipo_invalido"


def test_stacked_unit_member_is_addressable_later(monkeypatch):
    """A stacked member joins the ref set like any module — capacity counts
    it and later ops address it, exactly as the client applies them."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "add_stacked_unit", "module": "m1"},
                {"op": "set_opening", "module": "added_m1", "opening": "FIXED"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_graph_product(),
        prompt="apila un fijo encima",
        system_id=uuid4(),
        operation_key="assist-d7",
    )
    assert out["ops"] == [
        {"op": "add_stacked_unit", "module": "m1"},
        {"op": "set_opening", "module": "added_m1", "opening": "FIXED"},
    ]
    assert out["rejected"] == []


def _stacked_product():
    """Two inline roots plus a transom stacked on the second — the declared
    order ends in a stacked member, so the chain end is not the list tail."""
    product = _graph_product()
    product["modules"].append({"id": "t1", "width_mm": "900", "height_mm": "400"})
    product["couplings"].append(
        {
            "id": "c2",
            "angle_deg": "0",
            "kind": "STACKED",
            "modules": ["m2", "t1"],
            "edges": ["top", "bottom"],
        }
    )
    return product


def test_add_unit_joins_the_chain_end_past_a_stacked_member(monkeypatch):
    """A trailing stacked member leaves the true chain end free — claiming
    its edge instead would let a later duplicate validate a seam the client
    refuses."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "add_unit", "side": "right"},
                {"op": "duplicate_module", "module": "m2"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_stacked_product(),
        prompt="agrega una unidad a la derecha y duplica la segunda",
        system_id=uuid4(),
        operation_key="assist-d8",
    )
    assert out["ops"] == [{"op": "add_unit", "side": "right", "ref": "added_m1"}]
    assert out["rejected"][0]["reason"] == "sin_borde_libre"


def test_remove_unit_never_invents_a_joint_in_a_stacked_graph(monkeypatch):
    """Removing m2 incident to an INLINE and a STACKED joint must not
    relink — the client drops both and invents nothing. Then the chain
    end is m1 (t1 is stacked), so append-right still joins a real seam."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "remove_unit", "module": "m2"},
                {"op": "add_unit", "side": "right"},
                {"op": "set_opening", "module": "added_m1", "opening": "AWNING"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_stacked_product(),
        prompt="saca la segunda y agrega otra a la derecha",
        system_id=uuid4(),
        operation_key="assist-d9",
    )
    assert out["ops"] == [
        {"op": "remove_unit", "module": "m2"},
        {"op": "add_unit", "side": "right", "ref": "added_m1"},
        {"op": "set_opening", "module": "added_m1", "opening": "AWNING"},
    ]
    assert out["rejected"] == []


def test_stacked_members_count_toward_module_capacity(monkeypatch):
    """A stacked member is a real module — the ceiling counts it, so
    add_stacked_unit cannot push the assembly past MAX_MODULE_COUNT."""
    product = _product(modules=12, couplings=11)
    _patch_invoke(
        monkeypatch,
        {"ops": [{"op": "add_stacked_unit", "module": 11}]},
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=product,
        prompt="apila un módulo encima",
        system_id=uuid4(),
        operation_key="assist-d10",
    )
    assert out["ops"] == []
    assert out["rejected"][0]["reason"] == "modulo_invalido"


def test_unstacking_makes_the_member_a_chain_end(monkeypatch):
    """Once the transom's STACKED coupling is removed it is a plain root —
    appending right joins it."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "remove_coupling", "coupling": "c2"},
                {"op": "add_unit", "side": "right"},
                {"op": "duplicate_module", "module": "t1"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_stacked_product(),
        prompt="desconecta el transom, agrega a la derecha y duplica el transom",
        system_id=uuid4(),
        operation_key="assist-d9",
    )
    # t1 is now the right chain end: add_unit claims t1.right, so the
    # duplicate lands on t1's free left — all three ops apply.
    assert [op["op"] for op in out["ops"]] == [
        "remove_coupling",
        "add_unit",
        "duplicate_module",
    ]
    assert out["rejected"] == []


def test_relinked_seam_keeps_the_earlier_coupling_ref(monkeypatch):
    """§5 review: removing the middle member of a chain relinks the survivors
    under the EARLIER joint's id — the id the client reuses — not a minted
    added_c*. The repaired seam stays addressable, the dropped ref is dead."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "remove_unit", "module": "m2"},
                {"op": "set_coupling_angle", "coupling": "c1", "angle_deg": "12"},
                {"op": "set_coupling_angle", "coupling": "c2", "angle_deg": "12"},
            ],
            "notes": "",
        },
    )
    product = {
        "modules": [
            {"id": "m1", "width_mm": "900", "height_mm": "1500"},
            {"id": "m2", "width_mm": "900", "height_mm": "1500"},
            {"id": "m3", "width_mm": "900", "height_mm": "1500"},
        ],
        "couplings": [
            {"id": "c1", "angle_deg": "0", "kind": "INLINE",
             "modules": ["m1", "m2"], "edges": ["right", "left"]},
            {"id": "c2", "angle_deg": "0", "kind": "INLINE",
             "modules": ["m2", "m3"], "edges": ["right", "left"]},
        ],
    }
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=product,
        prompt="ángulo 12 en la unión",
        system_id=uuid4(),
        operation_key="assist-relink",
    )
    assert out["ops"] == [
        {"op": "remove_unit", "module": "m2"},
        {"op": "set_coupling_angle", "coupling": "c1", "angle_deg": "12"},
    ]
    assert out["rejected"] == [{"op": "set_coupling_angle", "reason": "angulo_invalido"}]


def test_added_module_ops_check_shape_and_frameless(monkeypatch):
    """§5 review: a member minted inside the sequence (added_m*) has module
    info registered — insert/stacked ops don't trip 'miembro_no_recto' on it."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "add_unit", "side": "right"},
                {"op": "add_stacked_unit", "module": "added_m1"},
            ],
            "notes": "",
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=1, couplings=0),
        prompt="otra unidad a la derecha",
        system_id=uuid4(),
        operation_key="assist-added-info",
    )
    assert [op["op"] for op in out["ops"]] == ["add_unit", "add_stacked_unit"]
    assert out["rejected"] == []


def test_module_count_growth_joins_the_chain_end_past_a_stacked_member(
    monkeypatch,
):
    """set_module_count grows through addAdjacentUnit("right") — the free
    right chain end, never the declaration tail. Joining the trailing
    stacked member instead would leave m2.right free in the sim and let a
    later duplicate claim an edge the client already took."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "set_module_count", "count": 4},
                {"op": "duplicate_module", "module": "m2"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_stacked_product(),
        prompt="cuatro módulos y duplica la segunda",
        system_id=uuid4(),
        operation_key="assist-d11",
    )
    assert out["ops"] == [{"op": "set_module_count", "count": 4}]
    assert out["rejected"][0]["reason"] == "sin_borde_libre"


def _chain3_product():
    """Three inline units — enough room to insert into one seam, then remove
    a member and see which incident joint survives (earlier ref wins)."""
    return {
        "modules": [
            {"id": "m1", "width_mm": "900", "height_mm": "1500"},
            {"id": "m2", "width_mm": "900", "height_mm": "1500"},
            {"id": "m3", "width_mm": "900", "height_mm": "1500"},
        ],
        "couplings": [
            {
                "id": "c1",
                "angle_deg": "0",
                "kind": "INLINE",
                "modules": ["m1", "m2"],
                "edges": ["right", "left"],
            },
            {
                "id": "c2",
                "angle_deg": "0",
                "kind": "INLINE",
                "modules": ["m2", "m3"],
                "edges": ["right", "left"],
            },
        ],
    }


def test_insert_then_remove_keeps_the_same_surviving_joint(monkeypatch):
    """insert_module splices the minted joint right after the seam (client
    order), so a later removal preserves the earlier incident ref — the same
    joint the client's relink keeps."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "insert_module", "coupling": "c1"},
                {"op": "remove_unit", "module": "m2"},
                {"op": "remove_coupling", "coupling": "added_c1"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_chain3_product(),
        prompt="inserta en la primera unión, quita el medio y luego la unión nueva",
        system_id=uuid4(),
        operation_key="assist-e1",
    )
    assert out["ops"] == [
        {"op": "insert_module", "coupling": "c1"},
        {"op": "remove_unit", "module": "m2"},
        {"op": "remove_coupling", "coupling": "added_c1"},
    ]
    assert out["rejected"] == []


def test_add_unit_keeps_numeric_address_on_the_original_module(monkeypatch):
    """`module: 0` names the ORIGINAL first module — after add_unit splices a
    new member at index 0, positional addresses still resolve through the
    original ordering, exactly like the client's saved product. Aliasing the
    mutable sim list would make this resolve to `added_m1`."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "add_unit", "side": "left"},
                {"op": "set_opening", "module": 0, "opening": "AWNING"},
            ]
        },
    )
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=_product(modules=3, couplings=2),
        prompt="agrega a la izquierda y abre el primer módulo",
        system_id=uuid4(),
        operation_key="assist-e2",
    )
    assert out["ops"] == [
        {"op": "add_unit", "side": "left", "ref": "added_m1"},
        {"op": "set_opening", "module": "m1", "opening": "AWNING"},
    ]
    assert out["rejected"] == []


def test_add_unit_clone_keeps_the_end_modules_shape(monkeypatch):
    """addAdjacentUnit clones the chain-end member — a contoured end produces
    a contoured clone, so a stacked op on `added_m1` must be refused exactly
    as the client refuses it. Recording the clone as RECT would validate an
    op the UI silently drops."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "add_unit", "side": "right"},
                {"op": "add_stacked_unit", "module": "added_m1"},
            ]
        },
    )
    product = {
        "modules": [{"id": "m1", "width_mm": "1200", "height_mm": "1500", "contour": {}}],
        "couplings": [],
    }
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=product,
        prompt="agrega a la derecha y apila la nueva",
        system_id=uuid4(),
        operation_key="assist-e3",
    )
    assert [op["op"] for op in out["ops"]] == ["add_unit"]
    assert out["rejected"][0]["reason"] == "modulo_invalido"


def test_insert_module_lands_before_the_seams_right_endpoint(monkeypatch):
    """insertModuleBetween splices the new member immediately BEFORE the
    seam's second endpoint — a seam whose declarations aren't neighbors
    (m1↔m3 with m2 between) places the clone at index 2: [m1,m2,new,m3].
    Simulating after-the-left ([m1,new,m2,m3]) makes a later count
    reduction trim a different member than the client keeps."""
    _patch_invoke(
        monkeypatch,
        {
            "ops": [
                {"op": "insert_module", "coupling": "c1"},
                {"op": "set_module_count", "count": 3},
                {"op": "set_module_count", "count": 2},
                {"op": "set_opening", "module": "m2", "opening": "AWNING"},
            ]
        },
    )
    product = {
        "modules": [
            {"id": "m1", "width_mm": "1200", "height_mm": "1500"},
            {"id": "m2", "width_mm": "900", "height_mm": "1500"},
            {"id": "m3", "width_mm": "900", "height_mm": "1500"},
        ],
        "couplings": [
            {"id": "c1", "angle_deg": "0", "modules": ["m1", "m3"], "edges": ["right", "left"]},
        ],
    }
    out = design_assist.assist(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        product=product,
        prompt="inserta entre m1 y m3, recuenta a 2, abre m2",
        system_id=uuid4(),
        operation_key="assist-e4",
    )
    # The client order is [m1,m2,new,m3]; reducing to 3 then 2 leaves
    # [m1,m2] — m2 is still addressable. Under the after-left placement
    # the second reduction drops m2 instead and the opening is refused.
    assert out["rejected"] == []
    assert [op["op"] for op in out["ops"]] == [
        "insert_module",
        "set_module_count",
        "set_module_count",
        "set_opening",
    ]
    assert out["ops"][3]["module"] == "m2"
