---
type: decision
status: active
updated: 2026-09-28
volatility: low
sources:
  - owner conversations through 2026-09-28
  - docs/PRODUCT.md
  - docs/ENGINEERING.md
---

# Owner decisions

Durable decisions that should survive chat/session boundaries.

## Product identity

DEKOPEN is an **AI-native operating system for window and door companies**, not a quotation app with a decorative editor.

The target system connects:

customer → project → product design → deterministic engineering → BOM → costing/pricing → quotation/revision → purchasing/inventory → cutting/production → machining/CNC → QC/packing/dispatch → optional installation/service → analytics.

The configured product is the center of the system.

## UX rule

> If DEKOPEN can derive a value deterministically, the user must not be asked for it.

The default sales/design flow should feel close to:

**Diseño → Medidas → Aperturas → Vidrio → Color → Precio**

A normal professional should become productive quickly; advanced manufacturing complexity should appear progressively.

## Product-model direction

- Composition beats hardcoded typology branches.
- Bow/bay should arise from assemblies/modules/couplings, not exist only as a special enum.
- V1 customer/product data must not be casually destroyed as V2 evolves.
- Stable object identity matters for selection, history, undo, AI actions and diffs.

## Domain correctness over cosmetic completion

A tiny-looking domain error can invalidate user trust.

Examples previously called out by the owner:

- a sliding sash represented as opening outward;
- sliding and casement treated as if directly interchangeable;
- confusing opening symbols;
- impossible compatibility;
- handles in nonsensical positions;
- features present merely because they were implemented, without a domain reason.

Every feature needs a clear why.

## UI direction

The product should feel:

- human;
- deliberate;
- professional;
- high-density where useful;
- canvas/work-object first;
- closer to excellent pro tools than generic SaaS.

Avoid:

- generic AI-startup gradients;
- endless cards;
- fake dashboards;
- decorative metrics;
- robot/developer language exposed to workshop users;
- visually polished but logically meaningless controls.

Design references include high-quality Adobe/Figma/Linear/Raycast/Duolingo interaction principles and Pentagram-level identity discipline, without copying brand styling.

## Agent workflow

Preferred agent behavior:

- autonomous;
- long-horizon when task requires it;
- investigate → execute → exercise → correct;
- use the real browser/app, not JSX inspection alone;
- find missing problems rather than implementing only the literal checklist;
- continue past the first PR when the mandate is not complete.

Avoid excessive maker/checker/Gauntlet ceremony.

Prefer one primary writer/integrator plus specialist read-only reviewers when parallelism helps.

## Engineering trust

Never trade correctness for apparent progress:

- no invented technical data;
- no silent fallbacks that change geometry, money, security or manufacturing;
- no fake-green tests;
- no demo authority becoming production authority;
- no LLM-generated engineering numeric truth.

Unknown production-critical facts remain UNKNOWN until authoritative.

## AI direction

AI is a core operating layer, not a side-chat.

All AI mutations should converge on the same typed domain operations used by the UI:

propose → validate → diff → confirm where risk requires it → apply → undo/audit.

Target surfaces:

- inline contextual AI;
- persistent AI dock;
- full AI workspace for substantial jobs.

Long AI work should expose jobs, steps, tools, artifacts, evidence, warnings and approvals rather than hiding work in chat scroll.

## Renderer direction

One authoritative ProductModel/evaluated geometry should feed:

- technical 2D;
- commercial 2D/2.5D;
- 3D;
- quotation imagery;
- customer portal;
- drawings/sections.

Do not create a separate decorative 3D product truth.

Use real ProfileSection geometry when available; fallback representations must be honest about their schematic nature.

## Catalog direction

Catalog is the technical knowledge center, not database administration.

Critical attributes include:

manufacturer, system/family, material, applications, sections, articles, beads, reinforcement, hardware, glazing, finishes, compatibility, readiness and provenance.

AI may assist ingestion/reconciliation but cannot self-certify missing manufacturing authority.

## Commercial direction

Issued quote revisions are immutable. Corrections create successor revisions.

Cost, selling price, discount, margin and tax must not collapse into one mutable number.

Price should be explainable.

## Factory/CNC direction

Manufacturing, inventory, cut optimization and CNC are first-class product capabilities.

CNC requires an explicit machine-neutral machining model, coordinate authority, tools, faces/orientation, clamps, machine capabilities, validation, preview and deterministic postprocessors.

Never output plausible CNC garbage to make a feature look finished.

## QA direction

Before market-readiness, perform a real professional test campaign:

- fresh organization;
- realistic catalogs/data;
- sales-to-production workflow;
- manual-vs-engine math comparisons;
- cross-tenant attacks;
- opening-family visual/domain checks;
- bow/bay editing;
- price revision immutability;
- factory exceptions/remakes;
- CNC fixtures;
- visual QA at realistic resolutions;
- recorded usage reviewed like a product designer.

Automated tests alone are not acceptance.
