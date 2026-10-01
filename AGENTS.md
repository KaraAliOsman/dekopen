# DEKOPEN — repository map

DEKOPEN is a parametric engineering + quoting OS for PVC/aluminium fenestration:
a deterministic pure engine, a Django modular monolith, Supabase/Postgres with RLS,
and a Vite + React SPA.

## Layout

- `engine/src/dekopen_engine/` — pure calculation engine. No I/O, no Django, no HTTP.
  All dimensions and money are `Decimal`; tolerance is `0.00 mm`.
- `engine/tests/` — engine tests incl. golden cases (`test_gold_cases_*`) that freeze
  proven manufacturing math.
- `backend/` — Django apps by domain (`authentication`, `engine_api`, `projects`,
  `pricing`, `documents`, `purchasing`, `billing`, `catalogs`). HTTP edge only;
  numbers come from the engine.
- `frontend/` — React 18 + TypeScript + Vite. Product UI lives in `src/features/`.
  API client is generated from `backend/openapi.yaml` (orval).
- `supabase/` — migrations (source of truth for schema), `seed.sql` (canonical
  `DEMO_60` demo catalog), pgTAP tests.
- `docs/PRD/` — domain specifications. `docs/ENGINEERING.md` — hard invariants.
  `docs/PRODUCT.md` — product direction.

## Working here

The normal loop: understand → implement → exercise the affected capability →
fix what is wrong → continue. Verify the surface you touched; run the full suite
when the change is genuinely cross-cutting.

```text
make lint           # ruff, ESLint, prettier, generated-API sync, source guards
make typecheck      # mypy engine/, Django check, tsc
make test           # engine + backend unit + frontend unit tests
make test-db        # live Supabase gate (needs Docker + supabase CLI): pgTAP, RLS, auth e2e
make test-mutations # 0.01mm formula mutation drill
make build          # production frontend build
```

Frontend dev server: `npm --prefix frontend run dev`. Backend: `python backend/manage.py runserver`
(uses sqlite without `DATABASE_URL`; real RLS behavior needs `make test-db`'s stack).

## Hard invariants — see docs/ENGINEERING.md

- Engine output is the only source of computed numbers. Never let free text,
  templates, or an LLM manufacture a numeric result.
- `Decimal` for mm and money — in engine, backend, and SQL (`NUMERIC`, never float types).
- Every tenant table keeps `org_id` + RLS; cross-tenant reads are bugs, not features.
- Issued revisions/documents and price/audit history are immutable.
- Payments are idempotent; externally consequential actions require an explicit
  human click.
- Formula changes ship with a golden-case test. Regenerate goldens only via
  `make goldgen` and review the diff.

## Commits and PRs

Changes land via pull request. CI jobs (Lint & Typecheck, Test Suite, Frontend
Build, Database Gate) are the merge safety net — fix what they flag, don't weaken
the checks.

## Persistent project knowledge

DEKOPEN keeps a maintained LLM Wiki under `docs/wiki/` so project decisions,
research and cross-session synthesis do not disappear into chat history.

For tasks that depend on project history, owner intent, known risks, competitor
research or prior conclusions:

1. read `docs/wiki/index.md`;
2. read the relevant linked pages;
3. for current implementation claims, re-check the target ref/code/tests/running
   product — the wiki never overrides newer repository evidence;
4. when work produces durable knowledge, maintain the wiki according to
   `docs/wiki/SCHEMA.md` and append `docs/wiki/log.md`.

Keep four categories distinct: verified current repo fact, owner/product intent,
historical context, and external research. Never turn a wiki inference into
engineering numeric truth or production authority.
