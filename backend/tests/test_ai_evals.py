"""Arnés de evaluación IA1: casos cargables, proyección estructural del
producto, aserciones por resultado y taxonomía de fallos — sin DB ni red."""

from decimal import Decimal
from pathlib import Path

import pytest

from ai_gateway.evals import fixtures, taxonomy
from ai_gateway.evals.expect import evaluate
from ai_gateway.evals.projection import project_product
from ai_gateway.evals.run import load_cases
from ai_gateway.evals.sandbox import OpsSandbox, SandboxUnavailable

CASES_DIR = Path(fixtures.__file__).resolve().parent / "cases"


def test_cases_load_and_validate():
    cases = load_cases(CASES_DIR)
    assert len(cases) == 26
    ids = [case["id"] for case in cases]
    assert len(set(ids)) == 26
    for case in cases:
        assert case["via"] in ("design_assist", "agent", "ask"), case["id"]
        assert case["prompt"], case["id"]
        assert case["expected"], case["id"]
        assert case.get("fixture"), case["id"]
        assert isinstance(case.get("expect"), dict), case["id"]
        groups = case["expect"].get("any")
        assert isinstance(groups, list) and groups, case["id"]


def test_projection_single_module():
    given = fixtures.given("editor", product_variant="vacia")
    proj = project_product(given["product"])
    assert proj["module_count"] == 1
    assert proj["total_width_mm"] == Decimal("1500.00")
    assert proj["height_mm"] == Decimal("1200.00")
    assert proj["modules"][0]["bays"][0]["opening_type"] == "FIXED"


def test_projection_divided_module():
    given = fixtures.given("editor", product_variant="dividida")
    proj = project_product(given["product"])
    assert proj["module_count"] == 1
    openings = [bay["opening_type"] for bay in proj["modules"][0]["bays"]]
    assert openings == ["FIXED", "TILT_TURN_LEFT"]
    assert proj["modules"][0]["splits"][0]["type"] == "SPLIT_V"
    assert proj["modules"][0]["splits"][0]["offset_mm"] == Decimal("750.00")


def test_evaluate_result_not_text():
    """La evaluación es por resultado: el ancho aplicado en sandbox decide,
    no el texto del modelo."""
    case = next(c for c in load_cases(CASES_DIR) if c["id"] == "E03")
    product = fixtures.given("editor")["product"]
    product["assembly"]["modules"][0]["width_mm"] = Decimal("1800.00")
    product["assembly"]["modules"][0]["height_mm"] = Decimal("1350.00")
    run = {
        "outcome": {"ops_accepted": [{"op": "set_total_width"}]},
        "sandbox": {"product_after": product, "product_changed": True},
        "error": None,
        "metrics": {},
    }
    verdict = evaluate(case, run, fixtures.given("editor"))
    assert verdict["pass"] is True


def test_evaluate_rejects_prompt_echo_as_clarification():
    """Un proveedor que repite el prompt no está pidiendo aclaración."""
    case = {
        "id": "X",
        "prompt": "¿cuánto pesa la hoja derecha?",
        "expect": {"any": [{"behavior": {"asks_clarification": True}}]},
    }
    run = {
        "outcome": {
            "reply": "Revisé el contexto para “¿cuánto pesa la hoja derecha?”. "
            "Respuesta determinista del proveedor MOCK.",
            "questions": [],
        },
        "sandbox": {},
        "error": None,
    }
    assert evaluate(case, run, {})["pass"] is False
    run["outcome"]["questions"] = ["¿qué hoja?"]
    assert evaluate(case, run, {})["pass"] is True


def test_taxonomy_provider_error():
    case = {"id": "X", "expect": {}}
    run = {"error": {"code": "ai_provider_quota"}, "outcome": {}}
    assert taxonomy.classify(case, run)[0] == taxonomy.PROVEEDOR_ERROR


def test_taxonomy_op_gap_and_validator():
    case = {"id": "X", "expect": {"op_gap": "split_bay", "any": []}}
    run = {"error": None, "outcome": {"ops_accepted": [], "rejected": []}}
    assert taxonomy.classify(case, run)[0] == taxonomy.OP_NO_SOPORTADA
    case2 = {"id": "Y", "expect": {"any": []}}
    run2 = {
        "error": None,
        "outcome": {
            "ops_accepted": [],
            "rejected": [{"op": "set_glass", "reason": "vidrio_invalido"}],
        },
    }
    assert taxonomy.classify(case2, run2)[0] == taxonomy.OP_RECHAZADA_VALIDADOR


def test_sandbox_applies_real_reducer():
    """El sandbox usa el mismo applyDesignOps del canvas (Node + esbuild)."""
    sandbox = OpsSandbox()
    try:
        after = sandbox.apply(
            fixtures.given("editor")["product"],
            [{"op": "set_total_width", "width_mm": "1800"}],
        )
    except SandboxUnavailable as error:
        pytest.skip(f"sandbox no disponible: {error}")
    proj = project_product(after)
    assert proj["total_width_mm"] == Decimal("1800")
