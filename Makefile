.PHONY: help lint typecheck test test-engine test-backend test-frontend test-mutations test-db test-ai-evals build check goldgen runjobs

PY := python
NPM := npm --prefix frontend

help:
	@echo "DEKOPEN — development commands"
	@echo "  make lint           - ruff, ESLint, prettier, generated-API sync, source guards"
	@echo "  make typecheck      - mypy engine, Django check, tsc"
	@echo "  make test           - engine + backend (unit) + frontend unit tests"
	@echo "  make test-db        - live DB gate (Docker + Supabase CLI): pgTAP, RLS, auth e2e"
	@echo "  make test-mutations - 0.01mm formula mutation drill (engine)"
	@echo "  make test-ai-evals  - AI evals harness, 26 casos MOCK (no bloqueante)"
	@echo "  make build          - production frontend build"
	@echo "  make runjobs        - durable background-job worker (claim + execute queue)"
	@echo "  make check          - lint + typecheck + test + build"
	@echo "  make goldgen        - regenerate engine golden snapshots"

lint:
	$(PY) -m ruff check .
	$(NPM) run lint
	$(NPM) run format:check
	$(PY) scripts/check_generated_api.py
	$(PY) scripts/check_guards.py

typecheck:
	$(PY) -m mypy engine/
	$(PY) backend/manage.py check
	$(NPM) run typecheck

test: test-engine test-backend test-frontend

test-engine:
	$(PY) -m pytest engine/ -q -W error \
		-W "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning"
	$(PY) -m engine.scripts.regenerate_golden --check

test-backend:
	$(PY) -m pytest backend/ -q -W error \
		-W "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning" \
		--ignore=backend/tests/integration

test-frontend:
	$(NPM) run test

test-mutations:
	$(PY) scripts/check_core_mutations.py

test-db:
	$(PY) scripts/db_gate.py

# Diagnóstico IA1: corre los 26 casos contra MOCK (determinista, sin red ni
# credenciales) y escribe el informe en docs/ai/evals/. No bloquea: los casos
# fallidos son el diagnóstico, no un fallo de build.
test-ai-evals:
	$(PY) scripts/ai_evals.py --provider MOCK --out docs/ai/evals/ci-mock.json

build:
	$(NPM) run build

runjobs:
	$(PY) backend/manage.py runjobs

check: lint typecheck test build

goldgen:
	$(PY) -m engine.scripts.regenerate_golden
