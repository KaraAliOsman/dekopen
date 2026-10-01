# Phase-04 captures — parameter-evidence registry + Studio kit picker

Worktree `/home/ubuntu/wt-commercial` · branch `devin/1790335313-commercial-workspace` · **HEAD `20d8c70`**
("feat(catalogs): parameter evidence registry + PostgREST privilege hygiene + Studio kit compatibility").
Captured live against the running fixture stack (Vite :5173, Django :8000, Supabase :25321) as `demo-owner` (OWNER, aal2).

## Files

| File | Shows |
|---|---|
| `00-catalog-entry.png` | Catálogo técnico list — system cards w/ manufacturer/family/version/review chips, detail panel w/ completeness + relation map |
| `01-fuentes-pending.png` | SystemWorkspace "Fuentes" on org-owned **MB-86**: 2 PENDING rows + Revisar/Rechazar actions |
| `01b-fuentes-global-readonly.png` | Fuentes on a **global demo system** (read_only) — table renders, review buttons hidden (authorization contrast) |
| `02-fuentes-reviewed.png` | Same section after review: `depth_mm` row flipped to **Revisado** (buttons gone), `chamber_count` still Pendiente |
| `03-studio-kit-picker.png` | Studio editor on a TILT_TURN bay — "Kit de herrajes" select: *Automático* + valid kit **Kit Vorne OB 100kg** |
| `04-studio-kit-incompatible.png` | Close-up of the ranked select + `assembly-kit-incompatible` list (4 kits + reasons) |

## Two new experiences — what was verified

### (a) Catalog parameter evidence ("Fuentes")
- `POST /api/v1/catalogs/evidence/` declares a `PENDING` row (fields `authority_table`, `row_id`, `field_name`, `value_text`, `unit`, `scope`, `source_document`, `source_page`). Verified: rows land in `catalog_parameter_evidence` and appear in the Fuentes table.
- `GET /api/v1/catalogs/evidence/?system_id=<id>` lists with joined target object.
- `POST /api/v1/catalogs/evidence/<id>/review/` `{review_state: REVIEWED}` stamps the row — the UI drops the action buttons and shows "Revisado". **Real transition captured** (row 2 in `02-`).

### (b) Studio "Herrajes" kit picker
- On a TILT_TURN bay the inspector shows a `<select>` bound to `bay.hardware_set_sku`: *Automático* option first, then the single valid kit (`KIT-TILT-TURN` → "Kit Vorne OB 100kg").
- `assembly-kit-incompatible` lists the 4 non-matching kits **with reasons**: wrong opening type, leaf width out of range, leaf height out of range.

## Authorization / authority matrix (verified live)

| Actor | Action | Result |
|---|---|---|
| OWNER (aal2) | `POST /evidence/` (declare) | ✅ 201 → PENDING |
| OWNER | `POST /evidence/<id>/review/` | ✅ stamps REVIEWED |
| ESTIMATOR (read role) | `GET /evidence/` | ✅ 200 (can read) |
| ESTIMATOR | `POST /evidence/` | ✅ **403 `catalog_permission_denied`** |
| ESTIMATOR | `POST /evidence/<id>/review/` | ✅ **403 `catalog_permission_denied`** |
| no/invalid token | `GET /evidence/` | ✅ 401 `invalid_token` |
| UI, global demo system | Fuentes review buttons | hidden (`read_only`) — `01b` |

## Inventory — real data still missing & expected source

Only **1** of the catalog's authority parameters currently carries **REVIEWED** documentary evidence (`profile_systems.depth_mm` on MB-86). 3 more are declared-but-PENDING. Everything else is **unbacked**. Expected source per field:

| Authority table / field | Status | Expected source |
|---|---|---|
| `profile_systems.depth_mm` | ✅ REVIEWED | manufacturer ficha técnica (MB-86 pág. 8) |
| `profile_systems.chamber_count` | ⏳ PENDING | manufacturer ficha técnica (cross-section count) |
| `profile_articles.face_width_mm` | ⏳ PENDING | profile-supplier datasheet (visible face width) |
| `profile_articles.welding_loss_mm` | ⏳ PENDING | welder spec / supplier tolerance sheet |
| `profile_systems.sash_overlap_mm, rebate_depth_mm, glass_clearance_*, door_threshold/clearance, rail_type, finishes` | ❌ none | series technical datasheet |
| `profile_articles.commercial_length_mm, weight_kg_m, steel_weight_kg_m, section` | ❌ none | profile supplier datasheet + reinforcement-supplier spec |
| `glazing_bead_matrix.bead_width_mm, gasket_*_mm, cut_add_mm` | ❌ none | glazing-bead datasheet per glass thickness |
| `hardware_kits.min/max leaf dims, max_leaf_weight_kg, rail_type, contents` | ❌ none | hardware-manufacturer spec (e.g. Roto/Siegenia) |
| `glass_purchase_mappings`, `infill_articles.thickness_mm/weight_kg_m2` | ❌ none | glass-supplier catalog + purchasing price list |
| `manufacturing/reinforcement/handle policies` (authority JSONB) | ❌ none | machinery manuals + placement spec |

## ⚠️ Blockers / caveats (honest)

- **Seeded `handle_requirement_policies.authority` JSONB is malformed** → `GET /api/v1/projects/design-options/<system>` returns **422 `technical_authority_required`** on **every seeded system** (DEMO_60/GLASS_45/ALU_65). Consequence: the editor's `Herrajes` select cannot render on any seeded system. Verified root cause: `HandleRequirementPolicyV1.model_validate` (strict `EngineModel`, `strict=True`) rejects 161 fields where JSONB stores strings ("TURN_LEFT","-10.00") that can't satisfy `Decimal`/enum/int instance checks.
- **To reach the picker I could not use a seeded system.** I created a fresh **org-owned** catalog (`T70` "Serie Taller 70 PVC") via the real `POST /systems/`, cloned the *full* DEMO_60 catalog to it via SQL (articles, bead matrix, kits, glass map, infill, manufacturing + reinforcement policies), set `rebate_depth_mm`, then created a real position on it (`POST /projects/<proj>/positions/`). Only then did `design-options` return 200 and the picker render. **This is the path the captures show — no seeded system could reach it.**
- The MB-86 org system (used for the Fuentes review captures) is also evidence-locked now — declaring evidence sets `technical_locked`, after which its catalog rows can't be edited (intended behavior).
- The malformed seed `authority` data + immutability trigger make the picker unreachable on fixture data out of the box; **fixing the seeded `handle_requirement_policies.authority` JSONB (store numeric/enum-native values, or relax the strict parse) is the real fix.**
