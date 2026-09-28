# Phase-11 — CNC / machining acceptance — live verification report

**HEAD:** `c004218` (incl. migration `20261228000010_step_event_cnc_program` fixing the CHECK that dropped `WO_CNC_PROGRAM` — defect found + fixed mid-run).
**Stack:** Vite `localhost:5173`, Django `127.0.0.1:8000` (`--noreload`), Supabase `:25321/:25322`, CDP Chrome. Roles: OWNER (aal2), WORKSHOP_MANAGER, OPERATOR.
**Evidence note:** session X server is dead — evidence is PNG captures via `Page.captureScreenshot` + API text, no video.

## Fixture deltas created this run
- Machine **CNC-01** `7dc69b60` "Centro mecanizado demo" — tools `saw`,`drill`,`end_mill`; systems `MEMBER_PLAN`; pp `neutral-ops-v1@1.0.0`.
- Machine **CNC-NOTOOL** — only `saw` (no `drill`/`end_mill`).
- Machine **CNC-SAW** — `SAW_CUT`-only kinds, `BAR_AXIS`.
- Fresh emissions: P-000006 REV-A → OT-…-01/02/03 (FIXED×3, TILT_TURN RIGHT); P-000004 REV-B → OT-…-01..04 (FIXED×3, TILT_TURN_LEFT, SLIDING_2L, qty11).

---

## Mandate checklist — results

| # | Item | Result |
|---|------|--------|
| 1 | `depth_undeclared` / `tool_undeclared` exact BLOCKs | ✅ engine-verified — `test_drill_without_authorized_depth_is_an_exact_blocker`, `test_member_op_without_tool_is_blocked` pass; **cannot be triggered live** — derived ops always carry tool_id, no API creates manual ops. Defensive path only. |
| 2 | HANDLE_PREP stays `feature_point_only` WARN | ✅ live: readiness shows **Atención** (not Bloqueado) on CNC-01; tooltip "Posición sin patrón de perforación declarado: kind=HANDLE_PREP · reason=point-level prep…"; generate still allowed → WARN programs. |
| 3 | `input_fingerprint` binds plan+machine → SUPERSEDED | ✅ PATCH machine `postprocessor_version`/`clamp_zones` → program reads `SUPERSEDED` on list, download → 422 `cnc_program_superseded`; identity retained. |
| 4 | `manifest.json` on every export | ✅ ops-export + each program ship `manifest.json` (schema `dekopen_export_manifest_v1`, `kind` `ops_export`/`cnc_program`); sha256+bytes match real files byte-for-byte (verified by hashing downloaded content). |
| 5 | CSV `sequence_no` first column | ✅ both ops-export and program CSVs start `sequence_no`. |
| 6 | L/R hands mirror ops on right member | ✅ TT-RIGHT preps x=52 stile; TT-LEFT preps x=1148 stile (exact mirror); SLIDING leaves prep facing stiles 920/880. |
| 7 | 90° vs authorized-angle cuts keep per-face angles through trim | ✅ per-op `angle_left/right_deg` 45°/90° carried; no spurious boundary_conflict. |
| 8 | Multi-unit identical members distinct | ✅ qty-3 FIXED → 12 pieces, unit_index 1/2/3 distinct; piece ids suffixed `-01/-02/-03`. |
| 9 | Op without tool / without depth = named blockers in readiness UI | ⚠️ engine-exact (`tool_undeclared`/`depth_undeclared` BLOCK); **live readiness can only show** machine-side blockers (`no_compatible_tool`, `unsupported_kind` — both verified, i18n "Sin herramienta compatible…"/"Operación no soportada…"). `undeclared` codes unreachable on real plans — see finding F1. |
| 10 | CUSTOM/manual op valid with declared datum | ✅ engine `test_manual_custom_op_passes_with_declared_datum`; no live path (no manual-op API). |
| 11 | Incompatible machine = explicit BLOCK | ✅ CNC-SAW → `unsupported_kind` (Bloqueado), CNC-NOTOOL → `no_compatible_tool`; generate buttons hidden on BLOCK; API generate → 422 `cnc_program_blocked` with physical detail. |
| 12 | Generate → download → manifest hashes match | ✅ `OT-P-000006-REV-A-03-P03U01M06-CNC-01-01` + `OT-P-000004-REV-B-02-P02U01M07-CNC-01-01` — sha256+bytes match; identity/program_no/plan_seed correct. |
| 13 | Edit machine → SUPERSEDED + download refused | ✅ verified; regen → new `program_no` (`-02`), old stays listed SUPERSEDED. |
| 14 | Machining station card + CNC panel: op select highlights mark; station ops + unassigned ops listed | ✅ op select highlights `cnc-mark`/`cnc-diagram-op` is-selected; station card lists ops (#·Ref. montaje·u·face·depth·tool). Unassigned-ops line exists in code but **unreachable on these plans** — every op kind maps to a station. |
| 15 | Pack PDF: datum labels Ext.A/Ext.B + "Ref. montaje" | ✅ machining section caption corrected to member-local datum ("desde el extremo A — la izquierda de la tira"); "Ref. montaje: no son mecanizados ejecutables" printed; member strip draws Ext.A (u=0)/Ext.B marks. Verified on TT-03 + TT-L packs. |
| 16 | Historical-risk set fixed | ✅ `test_saw_ops_order_is_numeric`, `test_saw_boundary_conflict_is_flagged`, mirror test — 36/36 `test_operations.py` pass. |

## Findings

- **F1 (limits, not defects):** `tool_undeclared`/`depth_undeclared`/CUSTOM/unassigned-ops/`boundary_conflict`/`inverted profile` have **no live path** — ops derive only from plans; the fixture catalog produces no asymmetric-angle or inverter profiles. Engine tests cover all six; UI renders machine-side blockers correctly.
- **F2 — RESOLVED @ `8216180`+uncommitted:** `manifest.json` now in the program download list (`["operations.json","operations.csv","manifest.json"]` buttons render — `15-manifest-button.png`).
- **F3 — RESOLVED after second fix:** `.cnc-panel-body` `overflow-x:auto` contained the members×machines grid; a follow-up fix added `overflow-x:auto` to `.production-optimize`, `.production-glass`, `.operator-section` and `div:has(> table.production-plan)`. **Page now measures `scrollWidth=485` at iw=500 — no horizontal overflow** (`17-mobile-fixed.png`; verified `overflowX:auto` live on `.production-optimize`).

## Re-verification @ `8216180` (post-fix)
- ✅ `manifest.json` button renders in program list — captured (`15-manifest-button.png`); wired to the same `downloadProgram()` → `cnc/programs/<id>/file/<name>` endpoint; endpoint returns 200/1577B on the CURRENT program and correctly 422 `cnc_program_superseded` on superseded ones (UI hides file buttons on those anyway).
- ✅ `.cnc-panel-body` contains its wide table internally; sidebar `.production-orders` also inside bounds (469px).
- ✅ Page `scrollWidth=485` at iw=500 after second fix — **no horizontal overflow** (`17-mobile-fixed.png`).
- Programs on this order now run `-01 SUPERSEDED, -02 SUPERSEDED, -03 CURRENT` — seq increments and lazy-stale list both correct.

## Captures

- `01..03` readiness panel (collapsed → member×machine verdicts → expanded ops diagram + INICIO/FIN datum strip).
- `04` op-select highlight on member diagram.
- `05/06` machining station card ops list + selected op.
- `07` CNC workspace (Centros y herramientas).
- `08` mobile @iw500 (overflow evidence).
- `09` TT-LEFT readiness (mirrored member M07, per-machine verdicts).
- `10` SLIDING_2L both leaf members + per-member generated programs.
- `11` OPERATOR view — programs + downloads visible, Generate hidden (canWrite gate).
- `12` `?piece=P02-U01-M07` deep link auto-resolves to OT-…-01 (b4a59a3 fix holds).
- `13-pack-ttl.pdf` + `pack-tt03.pdf` — production packs w/ machining section; `pack-machining-page8.png` rendered page.
- `program-m06-*` / `program-ttl-*` / `ops-export-*` — real downloaded artifacts incl. manifests (hashes verified).
- `14-mobile-cnc.png` — CNC panel at iw500.
