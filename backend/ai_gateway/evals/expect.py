"""Aserciones de los casos IA1 — cada check es una comparación estructural
sobre el resultado (producto aplicado en sandbox, ops, pasos, artefactos,
preguntas, texto citable), no una lectura subjetiva del texto del modelo.

Formato por caso (YAML):

    expect:
      expects_no_change: true        # metadatos para la taxonomía
      expects_clarification: true
      expects_prepared_only: true
      op_gap: split_bay              # el vocabulario no puede expresarlo
      context_gap: peso_hoja         # el contexto no trae el dato
      any:                           # grupos alternativos de checks: pasa
        - product: {...}             #   el caso si UN grupo entero pasa
          behavior: {...}
        - behavior: {asks_clarification: true}

`expect` sin `any` es un solo grupo. `product` se evalúa sobre la proyección
del producto resultante en el sandbox; `behavior` sobre el outcome de la ruta.
"""

from __future__ import annotations

import re
from typing import Any

from .projection import dec, project_product

# Señales de "pide aclaración" / "declara sin dato" en español del taller.
_CLARIFY_RE = re.compile(
    r"\?|cu[aá]l|c[oó]mo|qu[eé]\s+\w+|ind[ií]c|especif|precisa|confirma|"
    r"falta|necesito|necesitamos|no\s+queda\s+claro",
    re.IGNORECASE,
)
_NO_DATA_RE = re.compile(
    r"sin\s+dato|no\s+tengo|no\s+dispone|no\s+est[aá]\s+(disponible|registrado|en)|"
    r"no\s+hay\s+dato|falta(n)?\s+(el|los|la|las)\s+dato|no\s+puedo\s+saber|"
    r"no\s+es\s+posible\s+(determinar|saber)|no\s+consta|sin\s+informaci[oó]n",
    re.IGNORECASE,
)


def _text_corpus(outcome: dict, prompt: str | None = None) -> str:
    parts = [
        outcome.get("reply"),
        outcome.get("answer"),
        outcome.get("notes"),
        outcome.get("result_text"),
        " ".join(outcome.get("questions") or []),
        " ".join(str(w) for w in outcome.get("warnings") or []),
        " ".join(str(a.get("title") or "") for a in outcome.get("artifacts") or []),
    ]
    text = "\n".join(str(p) for p in parts if p)
    if prompt:
        # El eco del prompt no es contenido nuevo: un "¿...?" citado no es
        # pedir aclaración y "corredera" citado no es explicar la corredera.
        text = re.sub(re.escape(prompt), " ", text, flags=re.IGNORECASE)
        text = re.sub(r"[“”\"'«»]\s*[“”\"'«»]", " ", text)
    return text


def _eq_mm(actual: Any, expected: Any) -> bool:
    """Igualdad exacta: ENGINEERING.md fija tolerancia 0,00 mm — una vara con
    holgura dejaría pasar medidas incorrectas como correctas."""
    a, e = dec(actual), dec(expected)
    if a is None or e is None:
        return False
    return a == e


def _bay_match(bay: dict, spec: dict) -> bool:
    for key, expected in spec.items():
        if key == "glass_article_sku_in":
            if bay.get("glass_article_sku") not in expected:
                return False
        elif key in ("glass_thickness_mm",):
            if not _eq_mm(bay.get(key), expected):
                return False
        else:
            if bay.get(key) != expected:
                return False
    return True


def _check_product(checks: dict, product_after: dict | None, product_changed: bool) -> list[dict]:
    results = []
    proj = project_product(product_after) if product_after else None
    for name, want in checks.items():
        ok = False
        detail = ""
        if name == "unchanged":
            ok = bool(want) == (not product_changed)
            detail = "producto sin cambios" if not product_changed else "producto cambió"
        elif proj is None:
            ok = False
            detail = "no hay producto resultante"
        elif name == "module_count":
            ok = proj["module_count"] == int(want)
            detail = f"modules={proj['module_count']}"
        elif name == "module_count_min":
            ok = proj["module_count"] >= int(want)
            detail = f"modules={proj['module_count']}"
        elif name == "total_width_mm":
            ok = _eq_mm(proj["total_width_mm"], want)
            detail = f"total={proj['total_width_mm']}"
        elif name == "height_mm":
            ok = _eq_mm(proj["height_mm"], want)
            detail = f"height={proj['height_mm']}"
        elif name == "bays":
            got = [bay["opening_type"] for m in proj["modules"] for bay in m["bays"]]
            ok = got == list(want)
            detail = f"openings={got}"
        elif name == "bays_count":
            got = sum(len(m["bays"]) for m in proj["modules"])
            ok = got == int(want)
            detail = f"bays={got}"
        elif name == "every_bay":
            bays = [bay for m in proj["modules"] for bay in m["bays"]]
            ok = bool(bays) and all(_bay_match(bay, want or {}) for bay in bays)
            detail = f"bays={bays}"
        elif name == "some_bay":
            bays = [bay for m in proj["modules"] for bay in m["bays"]]
            ok = any(_bay_match(bay, want or {}) for bay in bays)
            detail = f"bays={bays}"
        elif name == "splits":
            expected = want if isinstance(want, list) else [want]
            got_splits = [split for m in proj["modules"] for split in m["splits"]]
            ok = bool(expected) and all(
                any(
                    split["type"] == spec.get("type")
                    and _eq_mm(split["offset_mm"], spec.get("offset_mm"))
                    for split in got_splits
                )
                for spec in expected
            )
            detail = f"splits={got_splits}"
        elif name == "couplings":
            expected = want if isinstance(want, list) else [want]
            ok = all(
                any(
                    all(
                        _eq_mm(c.get(key), value) if key == "angle_deg" else c.get(key) == value
                        for key, value in spec.items()
                    )
                    for c in proj["couplings"]
                )
                for spec in expected
            )
            detail = f"couplings={proj['couplings']}"
        else:
            detail = f"check de producto desconocido: {name}"
        results.append({"check": f"product.{name}", "ok": ok, "detail": detail})
    return results


def _check_behavior(
    checks: dict,
    outcome: dict,
    spec_positions: list[dict],
    prompt: str | None,
    sandbox: dict | None = None,
) -> list[dict]:
    results = []
    text = _text_corpus(outcome, prompt)
    ops_proposed = outcome.get("ops_proposed") or []
    ops_accepted = outcome.get("ops_accepted") or []
    rejected = outcome.get("rejected") or []
    questions = outcome.get("questions") or []
    steps = outcome.get("steps") or []
    artifacts = outcome.get("artifacts") or []
    for name, want in checks.items():
        ok = False
        detail = ""
        if name == "ops_accepted":
            ok = len(ops_accepted) == int(want)
            detail = f"accepted={len(ops_accepted)}"
        elif name == "ops_accepted_min":
            ok = len(ops_accepted) >= int(want)
            detail = f"accepted={len(ops_accepted)}"
        elif name == "ops_accepted_max":
            ok = len(ops_accepted) <= int(want)
            detail = f"accepted={len(ops_accepted)}"
        elif name == "ops_proposed_min":
            ok = len(ops_proposed) >= int(want)
            detail = f"proposed={len(ops_proposed)}"
        elif name == "no_ops":
            ok = len(ops_proposed) == 0 and len(ops_accepted) == 0
            detail = f"proposed={len(ops_proposed)}"
        elif name == "no_ops_accepted":
            ok = len(ops_accepted) == 0
            detail = f"accepted={len(ops_accepted)}"
        elif name == "rejected":
            expected = want if isinstance(want, list) else [want]
            ok = all(
                any(
                    (spec.get("op") in (None, r.get("op")))
                    and (
                        r.get("reason") == spec.get("reason")
                        or str(r.get("reason") or "").split(":")[-1]
                        in (spec.get("reason_any") or [spec.get("reason")])
                    )
                    for r in rejected
                )
                for spec in expected
            )
            detail = f"rejected={rejected}"
        elif name == "questions_min":
            ok = len(questions) >= int(want)
            detail = f"questions={len(questions)}"
        elif name == "asks_clarification":
            ok = bool(want) == (bool(questions) or bool(_CLARIFY_RE.search(text)))
            detail = f"questions={questions}"
        elif name == "sin_dato":
            ok = bool(want) == bool(_NO_DATA_RE.search(text))
            detail = "admite sin dato" if _NO_DATA_RE.search(text) else "no lo admite"
        elif name == "text_mentions_any":
            haystack = text.lower()
            ok = any(str(w).lower() in haystack for w in want)
            detail = f"texto={text[:160]}"
        elif name == "text_mentions_all":
            haystack = text.lower()
            ok = all(str(w).lower() in haystack for w in want)
            detail = f"faltan={[w for w in want if str(w).lower() not in haystack]}"
        elif name == "text_matches_any":
            ok = any(re.search(str(w), text, re.IGNORECASE) for w in want)
            detail = f"texto={text[:160]}"
        elif name == "text_excludes":
            bad = [str(w) for w in want if re.search(str(w), text, re.IGNORECASE)]
            ok = not bad
            detail = f"aparecen={bad}"
        elif name == "state":
            ok = outcome.get("state") == want
            detail = f"state={outcome.get('state')}"
        elif name == "steps_kinds_contain":
            kinds = {s.get("kind") for s in steps if isinstance(s, dict)}
            ok = all(k in kinds for k in want)
            detail = f"kinds={sorted(kinds)}"
        elif name == "steps_kinds_absent":
            kinds = {s.get("kind") for s in steps if isinstance(s, dict)}
            ok = not any(k in kinds for k in want)
            detail = f"kinds={sorted(kinds)}"
        elif name == "prepare_action":
            ok = any(
                s.get("kind") == "prepare" and s.get("action") == want
                for s in steps
                if isinstance(s, dict)
            )
            detail = f"steps={steps}"
        elif name == "artifact":
            spec = want or {}
            ok = any(
                (spec.get("kind") in (None, a.get("kind")))
                and all(
                    key in (a.get("payload") or {})
                    for key in spec.get("payload_contains_keys") or []
                )
                for a in artifacts
                if isinstance(a, dict)
            )
            detail = f"artifacts={artifacts}"
        elif name == "artifact_absent":
            ok = not artifacts
            detail = f"artifacts={len(artifacts)}"
        elif name == "batch":
            spec = want or {}
            items: list[dict] = []
            covered: set[str] = set()
            for step in steps:
                if isinstance(step, dict) and step.get("kind") == "batch_ops":
                    for item in step.get("items") or []:
                        if isinstance(item, dict) and item.get("position_id"):
                            items.append(item)
                            covered.add(str(item["position_id"]))
            locations = spec.get("only_locations") or []
            if locations:
                allowed = {
                    str(row["id"])
                    for row in spec_positions
                    if any(
                        str(loc).lower() in str(row.get("location_tag") or "").lower()
                        for loc in locations
                    )
                }
            else:
                allowed = set(spec.get("positions_only_ids") or [])
            ok = True
            if "positions_min" in spec:
                ok = ok and len(covered) >= int(spec["positions_min"])
            if allowed:
                ok = ok and covered.issubset(allowed)
            elif spec.get("positions_only_ids") is not None or locations:
                ok = ok and not covered
            if "all_ids" in spec:
                ok = ok and set(spec["all_ids"]).issubset(covered)
            if "positions_count" in spec:
                ok = ok and len(covered) == int(spec["positions_count"])
            detail = f"covered={sorted(covered)} allowed={sorted(allowed)}"
            # ops_each: cada posición cubierta debe llevar una op que calce
            # cada patrón — un lote al segundo piso que cambia el ANCHO no
            # satisface "cambia el vidrio".
            ops_each = spec.get("ops_each") or []
            if ops_each:
                ok_ops = all(
                    all(
                        any(
                            re.search(str(rx), str(op.get("op") or ""))
                            for op in item.get("ops") or []
                            if isinstance(op, dict)
                        )
                        for rx in ops_each
                    )
                    for item in items
                )
                ok = ok and ok_ops
                detail += f" ops_each={'ok' if ok_ops else 'faltan'}"
            # product_each: aserciones de producto contra el resultado del
            # sandbox por posición cubierta (run['sandbox']['batch_results']).
            product_each = spec.get("product_each")
            if product_each:
                batch_results = (sandbox or {}).get("batch_results") or {}
                bad = []
                for pid in sorted(covered):
                    entry = batch_results.get(pid) or {}
                    sub = _check_product(
                        product_each,
                        entry.get("product_after"),
                        bool(entry.get("changed")),
                    )
                    failed = [c["detail"] for c in sub if not c["ok"]]
                    if failed:
                        bad.append(f"{pid}:{failed}")
                ok = ok and not bad
                detail += f" product_each={'ok' if not bad else bad}"
        elif name == "queries_include_surface":
            ok = any(
                q.get("surface") == want and q.get("status") == "ok"
                for q in outcome.get("queries") or []
                if isinstance(q, dict)
            )
            detail = f"queries={outcome.get('queries')}"
        elif name == "reply_nonempty":
            ok = bool((outcome.get("reply") or outcome.get("answer") or "").strip())
            detail = "reply vacío"
        elif name == "answered_ok":
            # La ruta respondió sin errores de grounding/formato.
            ok = outcome.get("_no_error", True)
            detail = ""
        else:
            detail = f"check de comportamiento desconocido: {name}"
        results.append({"check": f"behavior.{name}", "ok": ok, "detail": detail})
    return results


def evaluate(case: dict, run: dict, given: dict | None = None) -> dict:
    """Evalúa el caso sobre el registro de `harness.run_case`.

    Devuelve {pass, checks, failure_hint}: pass es verdadero cuando el run
    tuvo error distinto de None solo si el caso lo espera explícitamente —
    la mayoría de los casos esperan que la ruta responda, así que un error
    ya falla el grupo que lo requiere."""
    expect = case.get("expect") or {}
    groups = (
        expect.get("any")
        if isinstance(expect.get("any"), list)
        else [{k: v for k, v in expect.items() if k in ("product", "behavior")}]
    )
    outcome = run.get("outcome") or {}
    sandbox = run.get("sandbox") or {}
    spec_positions = (given or {}).get("positions") or []
    has_error = run.get("error") is not None
    outcome = dict(outcome)
    outcome["_no_error"] = not has_error

    all_results: list[dict] = []
    passed = False
    if has_error and not any(
        isinstance(g, dict) and (g.get("behavior") or {}).get("expects_error") for g in groups
    ):
        # Error inesperado: no hace falta evaluar checks.
        all_results.append(
            {
                "check": "route.ok",
                "ok": False,
                "detail": f"la ruta falló: {(run.get('error') or {}).get('code')}",
            }
        )
    else:
        for group in groups:
            if not isinstance(group, dict):
                continue
            results: list[dict] = []
            if "product" in group:
                results.extend(
                    _check_product(
                        group["product"],
                        sandbox.get("product_after"),
                        bool(sandbox.get("product_changed")),
                    )
                )
            if "behavior" in group:
                results.extend(
                    _check_behavior(
                        group["behavior"],
                        outcome,
                        spec_positions,
                        case.get("prompt"),
                        sandbox,
                    )
                )
            if not results:
                continue
            all_results.extend(results)
            if all(r["ok"] for r in results):
                passed = True
                break
        if not all_results:
            all_results.append(
                {"check": "expect.defined", "ok": False, "detail": "el caso no declara checks"}
            )
    # El sandbox no aplicó las ops aceptadas: el resultado quedó sin medir —
    # el caso no puede declararse exitoso aunque los checks de texto pasaran.
    if sandbox.get("sandbox_error"):
        all_results.append(
            {
                "check": "sandbox.ok",
                "ok": False,
                "detail": f"sandbox no aplicó ops: {sandbox['sandbox_error']}",
            }
        )
        passed = False
    return {"pass": passed, "checks": all_results}
