# DEKOPEN — engineering invariants

Short list of guarantees that protect real damage. Everything else is ordinary
engineering judgment — component structure, naming, CSS, internal APIs, reversible
architecture. Don't escalate those.

## Numbers and determinism

- `/engine` is pure: no I/O, no Django, no HTTP, no `float`. Test it with
  `pytest engine/`.
- Every computed dimension/weight/price comes from the engine or from an explicit
  human-entered field — never from free text, templates, or an LLM.
- `Decimal` for millimetres and money everywhere: engine, backend serializers, SQL
  (`NUMERIC`, never `REAL`/`FLOAT`/`DOUBLE PRECISION`). Tolerance is `0.00 mm`.
- Formula changes ship with a golden-case test (`engine/tests/test_gold_cases_*`).
  Regenerate goldens only via `make goldgen` and review the diff.
- The deterministic golden cases (G1–G7 and successors) describe proven
  manufacturing behavior — keep them passing at `0.00 mm`.

## Data and tenancy

- Schema of record: `supabase/migrations/`. The canonical demo catalog `DEMO_60`
  lives in `supabase/seed.sql` — synthetic, never a certified catalog.
- Every tenant table: `org_id` + `ENABLE ROW LEVEL SECURITY` + policies through
  `private.current_user_org_ids()`. A cross-tenant read is a release blocker.
- Global catalogs are world-readable; tenant data never is.
- Issued artifacts are immutable: project revisions, emitted documents, price and
  audit history, BOM snapshots. Corrections happen in a new revision.
- Migrations must apply cleanly on populated data and reject invalid upgrades
  atomically (`make test-db` exercises both on real Postgres).

## Money and externally consequential actions

- Payments are idempotent: replays, out-of-order callbacks, and retries never
  double-charge or double-grant.
- Sending to a customer, releasing to the factory, and purchasing material each
  require an explicit human action. No silent irreversibility.
- AI writes are audited before they are applied (`ai_audit_logs`).

## Human identifiers and number format (§3.3)

Every entity a person names aloud carries a stable org-scoped human code, and
every visible number follows the closed format table in
`docs/design/CONSTITUCION.md` §3.3.

| Magnitude | Format | Example |
|---|---|---|
| mm (cotas, cortes, vanos) | integer, thin space U+2009 thousands separator | `2 400 × 1 800 mm` |
| mm with declared precision | decimal comma per the authority | `1 249,5 mm` |
| CLP | `$` + dot thousands, no decimals | `$1.435.471` |
| USD / UF | 2 decimals / 4 decimals | `US$ 1.234,50` · `UF 38,4521` |
| Percentage | 1 decimal, comma | `32,5 %` |
| Area | 2 decimals | `2,16 m²` |
| Weight | 1 decimal | `38,4 kg` |
| Uw / Ug | 2 decimals | `1,40 W/m²K` |
| Date | `dd-mm-aaaa` America/Santiago | `04-10-2026` |

Rules that hold across surfaces:

- Human codes are allocated by `private.next_human_code(org_id, kind)` under a
  per-org advisory lock and sealed by `private.guard_human_code` triggers:
  `OC-######` (purchase orders; pre-seal rows keep `PO-`), `RT-######`
  (remnants), `REC-######` (receipts), plus the existing `OT-…` work-order and
  `P##` position codes. The code is the address: global search resolves `OC-000012`,
  `RT-000003`, `REC-000004` and OT/position codes.
- A roll-back leaves a hole in the sequence — acceptable and documented; a code
  that was never issued is never recycled into another row.
- Frontend display formatting lives in `frontend/src/format.ts` (`fmtMm`,
  `fmtMoney`, `fmtArea`, `fmtWeight`, `fmtUvalue`, `fmtPct`, `fmtDate`,
  `shortTechnicalId`); `<EntityCode>` in `ui/format.tsx` is the only component
  allowed to show technical IDs.
- **Input boundary:** editable or persisted values stay canonical machine
  decimal — dot separator, no grouping (`fmtMmCanonical`, never `fmtMm`).
  Machine exports (CSV cells, DXF labels) also stay canonical/ASCII so they
  round-trip.
- No raw UUID or hash ≥ 10 hex chars on client or workshop surfaces; fingerprints
  appear only abbreviated (8 hex) in document footers/titleblocks. QR payloads
  keep the full technical data.

## Product judgment

- Users see workshop language: what is wrong, why it matters, what it affects,
  how to fix it — never enum names, hashes, IDs, or stack traces.
- Distinguish "geometry valid" from "manufacturing definition incomplete"; never
  pretend missing catalog authority is exact output.
