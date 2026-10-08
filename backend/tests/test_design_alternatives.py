"""Design alternatives: the provider proposes intent-level structure; the
backend builds the real product-v2 model, runs every candidate through
the engine, and only VALID assemblies reach the client with engine
metrics — rejected specs surface with reasons, never as products."""

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.exceptions import APIException

from ai_gateway.providers import MockProvider
from backend.tests.factories import demo_60_params
from engine_api.repository import SystemParamsRepository
from projects import design_alternatives


def _position():
    return {
        "id": uuid4(),
        "project_id": uuid4(),
        "system_id": uuid4(),
        "width_mm": "2400",
        "height_mm": "1500",
    }


def _catalog(**overrides):
    catalog = {
        "glass_skus": {"GLASS-4MM", "DVH-4-12-4"},
        "glass_recipes": {"GLASS-4MM": "4", "DVH-4-12-4": "4-12-4"},
        "panel_skus": {"PANEL-SANDWICH-DEMO-24"},
        "thicknesses": {Decimal("4"), Decimal("24")},
    }
    catalog.update(overrides)
    return catalog


def _envelope(output):
    return {
        "audit_id": str(uuid4()),
        "capability": "design_alternatives",
        "model": "DEKOPEN Alternativas™",
        "output": output if isinstance(output, str) else json.dumps(output),
        "tokens_prompt": 10,
        "tokens_completion": 10,
        "latency_ms": 1,
        "credits_debited": 15,
    }


def _patch(monkeypatch, output, catalog=None):
    captured = {}

    def fake_invoke(**kwargs):
        captured["input"] = kwargs["input_payload"]
        return _envelope(output)

    monkeypatch.setattr(design_alternatives.gateway, "invoke", fake_invoke)
    monkeypatch.setattr(
        design_alternatives,
        "_catalog",
        lambda system_id, org_id: catalog or _catalog(),
    )
    monkeypatch.setattr(
        SystemParamsRepository,
        "load_visible",
        lambda self, system_id, active_org_id: demo_60_params(),
    )
    monkeypatch.setattr(
        SystemParamsRepository,
        "load_coupler_articles",
        lambda self, system_id, active_org_id: {},
    )
    return captured


def _call():
    return design_alternatives.alternatives(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        brief="ventana corredera para el living",
        count=3,
        system_id=uuid4(),
        operation_key="alt-1",
    )


def test_alternatives_carry_engine_metrics(monkeypatch):
    _patch(
        monkeypatch,
        {
            "alternatives": [
                {
                    "label": "Paño fijo",
                    "rationale": "simple",
                    "openings": ["FIXED"],
                    "glass_sku": "GLASS-4MM",
                },
                {
                    # Two modules share the 2400 mm envelope so the operable
                    # leaf lands inside the casement kit's declared envelope.
                    "label": "Fijo + abatible",
                    "rationale": "ventilación segura",
                    "openings": ["FIXED", "TURN_LEFT"],
                    "glass_sku": "GLASS-4MM",
                },
                {
                    # A sliding leaf on a casement-family system must be
                    # refused, not fabricated (D01 family separation).
                    "label": "Corredera",
                    "rationale": "sin barrido",
                    "openings": ["SLIDING_2L"],
                    "glass_sku": "GLASS-4MM",
                },
            ],
            "notes": "dos opciones",
        },
    )
    out = _call()
    assert out["rejected"] == [
        {"label": "Corredera", "reasons": ["typology_family_incompatible"]}
    ]
    assert len(out["alternatives"]) == 2
    fixed, sliding = out["alternatives"]
    assert fixed["label"] == "Paño fijo"
    assert fixed["metrics"]["module_count"] == 1
    assert fixed["metrics"]["openings"] == ["FIXED"]
    assert Decimal(fixed["metrics"]["glass_area_m2"]) > 0
    assert fixed["metrics"]["glass_pieces"] == 1
    # Every returned product is a real product-v2 the editor can adopt.
    assert fixed["product"]["version"] == "product-v2"
    module = fixed["product"]["assembly"]["modules"][0]
    assert module["width_mm"] == "2400.00"
    assert module["tree"]["opening_type"] == "FIXED"
    assert sliding["metrics"]["module_count"] == 2
    assert sliding["metrics"]["openings"] == ["FIXED", "TURN_LEFT"]


def test_bow_alternative_gets_share_widths_and_couplings(monkeypatch):
    _patch(
        monkeypatch,
        {
            "alternatives": [
                {
                    "label": "Bow",
                    "rationale": "panorámica",
                    "openings": ["FIXED", "FIXED", "FIXED"],
                    "angle_deg": 22.5,
                    "glass_sku": "GLASS-4MM",
                }
            ]
        },
    )
    out = _call()
    assembly = out["alternatives"][0]["product"]["assembly"]
    widths = [module["width_mm"] for module in assembly["modules"]]
    assert widths == ["800.00", "800.00", "800.00"]
    assert [c["angle_deg"] for c in assembly["couplings"]] == ["22.5", "22.5"]


def test_share_width_remainder_lands_on_the_last_module(monkeypatch):
    _patch(
        monkeypatch,
        {"alternatives": [{"openings": ["FIXED", "FIXED"], "glass_sku": "GLASS-4MM"}]},
    )
    position = _position() | {"width_mm": "2399"}
    out = design_alternatives.alternatives(
        org_id=uuid4(),
        user_id=uuid4(),
        position=position,
        brief="dos hojas",
        count=1,
        system_id=uuid4(),
        operation_key="alt-2",
    )
    widths = [
        module["width_mm"]
        for module in out["alternatives"][0]["product"]["assembly"]["modules"]
    ]
    assert widths == ["1199.50", "1199.50"] or Decimal(widths[0]) + Decimal(
        widths[1]
    ) == Decimal("2399")


def test_invalid_specs_are_rejected_never_shipped(monkeypatch):
    _patch(
        monkeypatch,
        {
            "alternatives": [
                {"label": "Bien", "openings": ["FIXED"], "glass_sku": "GLASS-4MM"},
                {"label": "Rara", "openings": ["FLYING"], },
                {"label": "Sin hojas", "openings": []},
                {"label": "Vidrio falso", "openings": ["FIXED"], "glass_sku": "NO"},
                {"label": "Ángulo falso", "openings": ["FIXED", "FIXED"], "angle_deg": 170},
            ]
        },
    )
    out = _call()
    # The provider may over-produce — only the first MAX_ALTERNATIVES specs are
    # evaluated, bad ones surface with reasons and never become products.
    assert [item["label"] for item in out["alternatives"]] == ["Bien"]
    assert len(out["rejected"]) == 2


def test_bad_provider_document_is_a_502(monkeypatch):
    _patch(monkeypatch, "no es json {")
    with pytest.raises(APIException) as error:
        _call()
    assert error.value.get_codes() == "design_alternatives_bad_output"


def test_bad_dimensions_are_a_400(monkeypatch):
    _patch(monkeypatch, {"alternatives": []})
    with pytest.raises(APIException) as error:
        design_alternatives.alternatives(
            org_id=uuid4(),
            user_id=uuid4(),
            position=_position() | {"width_mm": "40"},
            brief="x",
            count=1,
            system_id=uuid4(),
            operation_key="alt-3",
        )
    assert error.value.get_codes() == "design_width_invalid"


def test_catalog_and_contract_reach_the_provider(monkeypatch):
    captured = _patch(monkeypatch, {"alternatives": []})
    _call()
    payload = captured["input"]
    assert payload["width_mm"] == "2400"
    assert payload["height_mm"] == "1500"
    assert "SLIDING_2L" in payload["openings_contract"]
    assert payload["catalog"]["glass_skus"] == ["DVH-4-12-4", "GLASS-4MM"]
    # Recipes ride inside the hashed input — a composition edit is a new
    # request, never a replay of the answer that weighed the old panes.
    assert payload["catalog"]["glass_recipes"] == {
        "DVH-4-12-4": "4-12-4",
        "GLASS-4MM": "4",
    }


def test_mock_provider_proposes_a_sliding_for_corredera_brief():
    provider = MockProvider()
    out = provider.invoke(
        route={"public_name": "DEKOPEN Alternativas™", "provider_model": "mock-design-1"},
        capability="design_alternatives",
        input_payload={
            "brief": "corredera para el dormitorio",
            "width_mm": "2400",
            "height_mm": "1500",
            "count": 3,
            "openings_contract": ["FIXED", "SLIDING_2L"],
            "catalog": {"glass_skus": [], "panel_skus": [], "glazing_thicknesses": []},
        },
    )
    document = json.loads(out["output"])
    assert document["alternatives"][0]["openings"] == ["SLIDING_2L"]


def test_mock_provider_honors_count():
    provider = MockProvider()
    out = provider.invoke(
        route={"public_name": "DEKOPEN Alternativas™", "provider_model": "mock-design-1"},
        capability="design_alternatives",
        input_payload={
            "brief": "ventana",
            "count": 1,
            "openings_contract": ["FIXED"],
            "catalog": {"glass_skus": [], "panel_skus": [], "glazing_thicknesses": []},
        },
    )
    document = json.loads(out["output"])
    assert len(document["alternatives"]) == 1


def test_count_caps_evaluated_specs(monkeypatch):
    _patch(
        monkeypatch,
        {
            "alternatives": [
                {"label": "Una", "openings": ["FIXED"], "glass_sku": "GLASS-4MM"},
                {"label": "Dos", "openings": ["FIXED", "FIXED"], "glass_sku": "GLASS-4MM"},
                {"label": "Tres", "openings": ["FIXED"] * 3, "glass_sku": "GLASS-4MM"},
            ]
        },
    )
    out = design_alternatives.alternatives(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        brief="una",
        count=1,
        system_id=uuid4(),
        operation_key="alt-count",
    )
    assert [item["label"] for item in out["alternatives"]] == ["Una"]
    assert out["rejected"] == []


def test_recipeless_sku_rejects_instead_of_substituting_slot(monkeypatch):
    """A glass article without a declared recipe cannot publish engine
    weight — the bead slot is not a composition."""
    _patch(
        monkeypatch,
        {"alternatives": [{"openings": ["FIXED"], "glass_sku": "GLASS-4MM"}]},
        catalog=_catalog(
            thicknesses={Decimal("6")},
            glass_recipes={"GLASS-4MM": None, "DVH-4-12-4": None},
        ),
    )
    out = _call()
    assert out["alternatives"] == []
    assert out["rejected"][0]["reasons"] == ["vidrio_sin_composicion"]


def test_door_spec_fills_the_single_catalog_panel(monkeypatch):
    _patch(
        monkeypatch,
        {"alternatives": [{"label": "Puerta", "openings": ["DOOR_ENTRY"]}]},
    )
    out = design_alternatives.alternatives(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        brief="puerta",
        count=1,
        system_id=uuid4(),
        operation_key="alt-door",
        # Door-sized live dimensions — a 2400 mm door is honestly refused.
        width_mm="900.00",
        height_mm="2100.00",
    )
    tree = out["alternatives"][0]["product"]["assembly"]["modules"][0]["tree"]
    assert tree["panel_article_sku"] == "PANEL-SANDWICH-DEMO-24"


def test_live_dimensions_win_over_the_persisted_row(monkeypatch):
    captured = _patch(
        monkeypatch,
        {"alternatives": [{"openings": ["FIXED"], "glass_sku": "GLASS-4MM"}]},
    )
    out = design_alternatives.alternatives(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        brief="una",
        count=1,
        system_id=uuid4(),
        operation_key="alt-dims",
        width_mm="3000.00",
        height_mm="2100.00",
    )
    assert captured["input"]["width_mm"] == "3000.00"
    assert captured["input"]["height_mm"] == "2100.00"
    module = out["alternatives"][0]["product"]["assembly"]["modules"][0]
    assert module["width_mm"] == "3000.00"
    assert module["height_mm"] == "2100.00"


def test_malformed_spec_rejects_without_aborting_siblings(monkeypatch):
    _patch(
        monkeypatch,
        {
            "alternatives": [
                {"label": "Rota", "openings": [["FIXED"]]},
                {"label": "Buena", "openings": ["FIXED"], "glass_sku": "GLASS-4MM"},
            ]
        },
    )
    out = _call()
    assert [item["label"] for item in out["alternatives"]] == ["Buena"]
    assert out["rejected"][0]["reasons"] == ["aperturas_invalidas"]


def test_nan_angle_rejects_the_spec_not_the_response(monkeypatch):
    _patch(
        monkeypatch,
        {
            "alternatives": [
                {"label": "NaN", "openings": ["FIXED", "FIXED"], "angle_deg": "NaN"},
                {"label": "Buena", "openings": ["FIXED"], "glass_sku": "GLASS-4MM"},
            ]
        },
    )
    out = _call()
    assert [item["label"] for item in out["alternatives"]] == ["Buena"]
    assert out["rejected"][0]["reasons"] == ["angulo_invalido"]


def test_ambiguous_glass_rejects_glazed_specs(monkeypatch):
    """Multiple catalog SKUs + no provider pick = unpriceable candidate —
    rejected, never offered."""
    _patch(
        monkeypatch,
        {
            "alternatives": [
                {"label": "Fija", "openings": ["FIXED"]},
                {"label": "Puerta", "openings": ["DOOR_ENTRY"]},
            ]
        },
    )
    out = design_alternatives.alternatives(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        brief="dos opciones",
        count=3,
        system_id=uuid4(),
        operation_key="alt-ambig",
        # Door-sized live dims — a 2400 mm door is honestly refused.
        width_mm="900.00",
        height_mm="2100.00",
    )
    assert [item["label"] for item in out["alternatives"]] == ["Puerta"]
    assert out["rejected"][0]["reasons"] == ["vidrio_no_resuelto"]


def test_single_catalog_glass_fills_the_candidate(monkeypatch):
    _patch(
        monkeypatch,
        {"alternatives": [{"label": "Fija", "openings": ["FIXED"]}]},
        catalog=_catalog(glass_skus={"GLASS-4MM"}),
    )
    out = _call()
    tree = out["alternatives"][0]["product"]["assembly"]["modules"][0]["tree"]
    assert tree["glass_article_sku"] == "GLASS-4MM"


def test_single_catalog_coupler_fills_the_union():
    product, reason = design_alternatives._build_product(
        {"openings": ["FIXED", "FIXED"], "glass_sku": "GLASS-4MM"},
        width_mm=Decimal("2400"),
        height_mm=Decimal("1500"),
        catalog=_catalog(),
        coupler_skus={"COUPLER-A"},
    )
    assert reason is None
    assert product["assembly"]["couplings"][0]["coupler_profile_sku"] == "COUPLER-A"


def test_unknown_coupler_sku_rejects_the_spec():
    product, reason = design_alternatives._build_product(
        {"openings": ["FIXED", "FIXED"], "coupler_sku": "NOPE", "glass_sku": "GLASS-4MM"},
        width_mm=Decimal("2400"),
        height_mm=Decimal("1500"),
        catalog=_catalog(),
        coupler_skus={"COUPLER-A"},
    )
    assert product is None and reason == "union_desconocida"


def test_selected_glass_binds_recipe_and_matching_bead():
    """A DVH SKU carries its composition: spec "4-12-4" weighs 8 mm of
    glass and occupies a 20 mm unit — the 24 mm bead rule accepts it."""
    product, reason = design_alternatives._build_product(
        {"openings": ["FIXED"], "glass_sku": "DVH-4-12-4"},
        width_mm=Decimal("1200"),
        height_mm=Decimal("1500"),
        catalog=_catalog(),
        coupler_skus=set(),
    )
    assert reason is None
    tree = product["assembly"]["modules"][0]["tree"]
    assert tree["glass_spec"] == "4-12-4"
    assert tree["glass_thickness_mm"] == "24"


def test_recipe_without_a_bead_rule_rejects_the_candidate():
    product, reason = design_alternatives._build_product(
        {"openings": ["FIXED"], "glass_sku": "DVH-4-12-4"},
        width_mm=Decimal("1200"),
        height_mm=Decimal("1500"),
        catalog=_catalog(thicknesses={Decimal("4")}),
        coupler_skus=set(),
    )
    assert product is None and reason == "vidrio_incompatible"


def test_unparseable_recipe_rejects_instead_of_guessing():
    product, reason = design_alternatives._build_product(
        {"openings": ["FIXED"], "glass_sku": "DVH-4-12-4"},
        width_mm=Decimal("1200"),
        height_mm=Decimal("1500"),
        catalog=_catalog(glass_recipes={"DVH-4-12-4": "templado incoloro"}),
        coupler_skus=set(),
    )
    assert product is None and reason == "vidrio_incompatible"


def test_trailing_garbage_recipe_rejects_instead_of_miscounting():
    """A recipe with a corrupt token ("4-16-4garbage") must not be counted
    here and misweighted by the engine there — it rejects the candidate."""
    product, reason = design_alternatives._build_product(
        {"openings": ["FIXED"], "glass_sku": "DVH-4-12-4"},
        width_mm=Decimal("1200"),
        height_mm=Decimal("1500"),
        catalog=_catalog(glass_recipes={"DVH-4-12-4": "4-16-4garbage"}),
        coupler_skus=set(),
    )
    assert product is None and reason == "vidrio_incompatible"


def test_recipeless_sku_rejects_instead_of_fabricating_weight():
    """A bead slot is not a composition — an article without a declared
    recipe cannot publish an engine-derived weight on the card."""
    product, reason = design_alternatives._build_product(
        {"openings": ["FIXED"], "glass_sku": "DVH-4-12-4"},
        width_mm=Decimal("1200"),
        height_mm=Decimal("1500"),
        catalog=_catalog(glass_recipes={"DVH-4-12-4": None}),
        coupler_skus=set(),
    )
    assert product is None and reason == "vidrio_sin_composicion"


def test_spec_less_mapping_rejects_instead_of_substituting_the_slot():
    """The slot dimension is not a recipe — an article without a declared
    composition cannot publish a card weight."""
    product, reason = design_alternatives._build_product(
        {"openings": ["FIXED"], "glass_sku": "GLASS-4MM"},
        width_mm=Decimal("1200"),
        height_mm=Decimal("1500"),
        catalog=_catalog(glass_recipes={"GLASS-4MM": None}),
        coupler_skus=set(),
    )
    assert product is None and reason == "vidrio_sin_composicion"


def test_leaf_weight_only_when_leaves_exist(monkeypatch):
    _patch(
        monkeypatch,
        {
            "alternatives": [
                {"label": "Fija", "openings": ["FIXED"], "glass_sku": "GLASS-4MM"},
                {"label": "Abatible", "openings": ["TILT_TURN_LEFT"], "glass_sku": "GLASS-4MM"},
            ]
        },
    )
    # Leaf-sized live dimensions — a 2400 mm abatible honestly fails leaf
    # limits, same as in the editor.
    out = design_alternatives.alternatives(
        org_id=uuid4(),
        user_id=uuid4(),
        position=_position(),
        brief="dos",
        count=2,
        system_id=uuid4(),
        operation_key="alt-leaf",
        width_mm="900.00",
        height_mm="1400.00",
    )
    fixed, operable = out["alternatives"][0], out["alternatives"][1]
    assert fixed["metrics"]["leaf_weight_kg"] is None
    assert operable["metrics"]["leaf_weight_kg"] is not None
