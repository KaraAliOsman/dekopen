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


def test_evaluate_exact_mm_no_tolerance():
    """La vara es 0,00 mm: 1800,4 no puede aprobar una expectativa de 1800."""
    case = next(c for c in load_cases(CASES_DIR) if c["id"] == "E03")
    product = fixtures.given("editor")["product"]
    product["assembly"]["modules"][0]["width_mm"] = Decimal("1800.4")
    product["assembly"]["modules"][0]["height_mm"] = Decimal("1350.00")
    run = {
        "outcome": {"ops_accepted": [{"op": "set_total_width"}]},
        "sandbox": {"product_after": product, "product_changed": True},
        "error": None,
        "metrics": {},
    }
    verdict = evaluate(case, run, fixtures.given("editor"))
    assert verdict["pass"] is False


def test_evaluate_sandbox_error_fails_case():
    """Un sandbox caído invalida el caso — no pasa por omisión aunque el
    comportamiento textual parezca correcto."""
    case = {
        "id": "X",
        "expect": {"any": [{"behavior": {"no_ops_accepted": True}}]},
    }
    run = {
        "outcome": {"ops_accepted": [{"op": "set_glass"}]},
        "sandbox": {"sandbox_error": "node no está en el PATH", "product_changed": None},
        "error": None,
    }
    assert evaluate(case, run, {})["pass"] is False
    assert taxonomy.classify(case, run)[0] == taxonomy.ERROR_ARNES


def test_evaluate_batch_verifies_ops_and_product():
    """Un lote al segundo piso con la op equivocada no satisface J01: el
    check compara la op y el vidrio resultante por posición."""
    case = next(c for c in load_cases(CASES_DIR) if c["id"] == "J01")
    segundo_piso = next(
        row for row in fixtures.project_positions_rows() if "segundo piso" in row["location_tag"]
    )
    outcome = {
        "steps": [
            {
                "kind": "batch_ops",
                "items": [
                    {
                        "position_id": segundo_piso["id"],
                        "ops": [{"op": "set_total_width", "width_mm": "1500"}],
                    }
                ],
            }
        ],
        "ops_proposed": [],
        "ops_accepted": [],
    }
    run = {"outcome": outcome, "sandbox": {}, "error": None}
    # La op es set_total_width, no set_glass → el lote correcto en cobertura
    # pero equivocado en contenido debe fallar.
    assert evaluate(case, run, fixtures.given("proyecto"))["pass"] is False

    outcome["steps"][0]["items"][0]["ops"] = [{"op": "set_glass"}]
    run["sandbox"] = {"batch_results": {}}
    # Op correcta pero sin resultado aplicado → product_each falla igual.
    assert evaluate(case, run, fixtures.given("proyecto"))["pass"] is False

    product_after = fixtures.product(
        [fixtures.module(fixtures.bay("SLIDING_2L"), "1800.00", "1200.00")]
    )
    product_after["assembly"]["modules"][0]["tree"]["glass_article_sku"] = "VIDRIO-BASE"
    run["sandbox"] = {
        "batch_results": {
            str(segundo_piso["id"]): {"product_after": product_after, "changed": True}
        }
    }
    assert evaluate(case, run, fixtures.given("proyecto"))["pass"] is True


def test_taxonomy_clarification_missing_beats_op_gap():
    """E08 exige aclaración: no preguntar nada es no_pidio_aclaracion, no
    op_no_soportada, aunque el caso también declare op_gap."""
    case = next(c for c in load_cases(CASES_DIR) if c["id"] == "E08")
    run = {
        "error": None,
        "outcome": {"ops_accepted": [], "ops_proposed": [], "rejected": [], "questions": []},
        "sandbox": {"product_changed": False},
    }
    assert taxonomy.classify(case, run)[0] == taxonomy.NO_PIDIO_ACLARACION


def test_broker_metrics_per_case():
    """metrics(start) recorta el tramo: cada caso reporta SUS llamadas."""
    from ai_gateway.evals.harness import ProviderBroker

    broker = ProviderBroker("MOCK")
    broker.calls.append({"capability": "design_assist", "operation_key": "a", "latency_ms": 10})
    broker.calls.append({"capability": "agent", "operation_key": "b", "latency_ms": 20})
    assert broker.metrics(1)["provider_calls"] == 1
    assert broker.metrics(1)["latency_ms"] == 20
    assert broker.metrics(0)["provider_calls"] == 2


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
            "Respuesta determinista del proveedor de prueba.",
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
