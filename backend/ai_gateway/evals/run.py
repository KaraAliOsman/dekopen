"""Runner del diagnóstico IA1 — un comando corre los 26 casos de punta a
punta y emite el informe JSON por resultado.

    cd backend
    python -m ai_gateway.evals.run --provider MOCK \
        --out ../docs/ai/evals/2026-10-05-mock.json

`--provider` acepta MOCK (determinista, sin red) o el nombre de un proveedor
real configurado por entorno (`AI_GATEWAY_{P}_API_KEY` + `_BASE_URL` —
p.ej. `--provider MIMO`); `auto` corre ambos. La evaluación es por RESULTADO:
las ops propuestas se aplican en el sandbox Node con el reducer real del
frontend y se compara la estructura resultante, no el texto.

El comando nunca rompe el build: fallos de casos se reportan; un error del
propio arnés sale 1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# El módulo vive dentro de backend/; al correr como `python -m` desde otro
# cwd, `ai_gateway` aún no es importable — agregar el directorio backend.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# El arnés corre fuera del servidor: MOCK sólo está habilitado con DEBUG o la
# bandera explícita — el runner la fija para la corrida.
os.environ.setdefault("AI_GATEWAY_MOCK_ENABLED", "1")

import django  # noqa: E402

django.setup()

import yaml  # noqa: E402

from ai_gateway.evals import taxonomy  # noqa: E402
from ai_gateway.evals.expect import evaluate  # noqa: E402
from ai_gateway.evals.fixtures import given as given_for  # noqa: E402
from ai_gateway.evals.harness import ProviderBroker, run_case, configured_provider_names  # noqa: E402
from ai_gateway.evals.sandbox import OpsSandbox, SandboxUnavailable  # noqa: E402

CASES_DIR = Path(__file__).resolve().parent / "cases"


def load_cases(cases_dir: Path) -> list[dict]:
    cases = []
    for path in sorted(cases_dir.glob("*.yaml")):
        with path.open(encoding="utf-8") as handle:
            case = yaml.safe_load(handle)
        case["_source"] = path.name
        cases.append(case)
    return cases


def apply_sandbox(case: dict, run: dict, given: dict, sandbox: OpsSandbox) -> None:
    """Aplica las ops aceptadas sobre una copia del producto fixture y deja
    en run["sandbox"] la proyección resultante (o la razón de no aplicar)."""
    ops = list((run.get("outcome") or {}).get("ops_accepted") or [])
    product_json = given.get("product")
    if not ops or not isinstance(product_json, dict):
        run["sandbox"] = {
            "applied": 0,
            "product_after": product_json,
            "product_changed": False,
            "note": "sin ops aceptadas" if not ops else "sin producto fixture",
        }
        return
    try:
        after = sandbox.apply(product_json, ops)
    except SandboxUnavailable as error:
        run["sandbox"] = {"applied": 0, "sandbox_error": str(error), "product_changed": None}
        return
    run["sandbox"] = {
        "applied": len(ops),
        "product_after": after,
        "product_changed": after != product_json,
    }


def run_suite(provider: str, cases: list[dict]) -> dict:
    """Corre los casos con un broker por suite (métricas agregadas limpias)."""
    results = []
    sandbox = OpsSandbox()
    try:
        broker = ProviderBroker(provider)
        broker_error = None
    except Exception as error:  # proveedor sin configurar: se reporta por caso
        broker = None
        broker_error = error
    for case in cases:
        given = given_for(
            case.get("fixture") or "editor",
            product_variant=case.get("product_variant") or "vacia",
        )
        if broker is None:
            run = {
                "id": case["id"],
                "via": case["via"],
                "surface": case.get("surface"),
                "outcome": {},
                "error": {
                    "code": getattr(broker_error, "code", "ai_provider_unavailable"),
                    "kind": "provider",
                },
                "sandbox": {},
                "metrics": {},
            }
        else:
            run = run_case(case, broker=broker)
        # El sandbox corre aunque la ruta haya fallado parcialmente: si hay
        # ops aceptadas en el outcome parcial, se evalúan igual.
        if run.get("error") is None:
            apply_sandbox(case, run, given, sandbox)
        verdict = evaluate(case, run, given)
        failure, detail = (None, None)
        if not verdict["pass"]:
            failure, detail = taxonomy.classify(case, run)
        results.append(
            {
                "id": case["id"],
                "view": case.get("view"),
                "via": case["via"],
                "surface": case.get("surface"),
                "prompt": case["prompt"],
                "expected": case.get("expected"),
                "metrics": run.get("metrics"),
                "outcome": run.get("outcome"),
                "error": run.get("error"),
                "sandbox": run.get("sandbox"),
                "verdict": {
                    "pass": verdict["pass"],
                    "failure": failure,
                    "failure_detail": detail,
                    "checks": verdict["checks"],
                },
            }
        )
    return {
        "provider": provider,
        "cases": results,
        "total": len(results),
        "passed": sum(1 for r in results if r["verdict"]["pass"]),
    }


def summarize(report: dict) -> dict:
    """Resumen por vista y taxonomía — el contenido del README del diagnóstico."""
    by_view: dict[str, dict[str, int]] = {}
    by_failure: dict[str, int] = {}
    for case in report["cases"]:
        view = case.get("view") or "sin-vista"
        by_view.setdefault(view, {"total": 0, "passed": 0})
        by_view[view]["total"] += 1
        if case["verdict"]["pass"]:
            by_view[view]["passed"] += 1
        else:
            cause = case["verdict"]["failure"] or "resultado_incorrecto"
            by_failure[cause] = by_failure.get(cause, 0) + 1
    return {
        "total": report["total"],
        "passed": report["passed"],
        "rate": round(report["passed"] / report["total"], 4) if report["total"] else 0,
        "by_view": by_view,
        "by_failure": dict(sorted(by_failure.items(), key=lambda kv: -kv[1])),
    }


def _serializable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_serializable(v) for v in value)
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return str(value)
    except ImportError:  # pragma: no cover
        pass
    from uuid import UUID

    if isinstance(value, UUID):
        return str(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Arnés de evaluación IA1")
    parser.add_argument(
        "--provider",
        default="MOCK",
        help="MOCK | <nombre de proveedor configurado, p.ej. MIMO> | auto",
    )
    parser.add_argument("--cases-dir", default=str(CASES_DIR))
    parser.add_argument("--out", default=None, help="JSON de salida (uno por proveedor)")
    parser.add_argument("--tag", default=None, help="etiqueta de la corrida")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases_dir))
    if not cases:
        print(f"sin casos en {args.cases_dir}", file=sys.stderr)
        return 1

    providers = (
        ["MOCK", *configured_provider_names()] if args.provider == "auto" else [args.provider]
    )
    stamp = args.tag or ""
    exit_code = 0
    for provider in providers:
        report = run_suite(provider, cases)
        report["meta"] = {
            "harness": "ai_gateway.evals",
            "tag": stamp,
            "provider": provider,
            "model": next(
                (r["outcome"].get("model") for r in report["cases"] if r.get("outcome")),
                None,
            ),
        }
        report["summary"] = summarize(report)
        out_path = Path(args.out) if args.out else None
        if out_path and len(providers) > 1:
            out_path = out_path.with_name(f"{out_path.stem}-{provider.lower()}{out_path.suffix}")
        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(_serializable(report), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print(
            f"[{provider}] {report['passed']}/{report['total']} casos pasan; "
            f"fallos: {report['summary']['by_failure']}"
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
