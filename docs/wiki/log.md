# DEKOPEN Wiki Log

Append-only chronology. Keep newest entries at the bottom.

## [2026-09-28] bootstrap | LLM Wiki instantiated

- Read Andrej Karpathy's canonical `llm-wiki.md` idea file.
- Adapted the pattern to DEKOPEN's stronger requirement that current implementation claims must be revalidated against the repository.
- Seeded schema, index, product direction, owner decisions, current-state page, known-risk page, competitor map and source pages.
- Established separation between current repo fact, owner intent, historical context and external research.
- No attempt was made to turn the wiki into an alternative source of engineering numeric truth.

## [2026-10-05] P00 | foundation branch, constitution and visual evidence harness

- Created the v1 foundation changes for `integracion/v1`: design constitution in-repo, defaults/activation records, queue state, route hygiene and `ux:capture`.
- Added a realistic DEMO fixture direction for Ventanas del Sur SpA while keeping `DEMO_60` explicitly synthetic and non-certified.
- Verified local focused tests, engine/backend/frontend unit suites, frontend typecheck and build. Local generated-API drift check was blocked by Windows application control on the `rpds` DLL.
- Captured a smoke baseline for `/login`; full-route capture remains a follow-up once every portal/token fixture state exists.

## [2026-10-05] P00 | merge status reconciled

- Confirmed PR #114 is merged into `integracion/v1` at `a096f85b2e56e21eda024c1ec92a456ed9d30b03`.
- Confirmed the four required GitHub checks passed: Lint & Typecheck, Test Suite, Frontend Build and Database Gate.
- Updated the queue state and current-reality verification ref so the next session can advance from P00.

## [2026-10-05] P00 | evidence harness completed end-to-end

- Replaced the login-only smoke baseline with the full authenticated harness: per-role Mailpit magic-link logins, org selection and TOTP aal2 for the OWNER, declarative route table over all App.tsx routes (41 capture jobs), and report.json + index.html output.
- Baseline `docs/redesign/captures/baseline-2026-10-05/` now covers 270 captures (38 routes with findings, 2276 findings) with committed 1440×900 light shots.
- Realistic fixture: two tenant orgs, 12 lifecycle projects, 5 portal token states and `.fixture-state.json` for route interpolation; idempotency proven by `frontend/tests/e2e/fixture.spec.ts` under `make test-db`.
- Fixed a real dead-end found by the harness: `/select-organization` did not redirect `mfa_required` sessions to `/auth/mfa`, stranding multi-org OWNER logins.
- Local jammy VM needed a self-built `libharfbuzz-subset.so.0` (harfbuzz 2.7.4) for WeasyPrint PDF tests; CI already installs `libharfbuzz-subset0`.
