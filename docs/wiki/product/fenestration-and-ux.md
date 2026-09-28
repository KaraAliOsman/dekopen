---
type: concept
status: active
updated: 2026-09-28
volatility: medium
sources:
  - owner decisions through 2026-09-28
  - docs/PRODUCT.md
---

# Fenestration and UX principles

## Sliding and hinged families are not interchangeable

A slider moves on a track. A casement/turn sash rotates around hinges.

Therefore:

- do not draw swing arcs for normal sliding motion;
- do not show slider arrows as casement rotation;
- handle/hinge semantics must match the family;
- do not allow a sliding sash to be dropped into a hinged system merely because both are rectangles;
- mixed assemblies may contain independent units of different families only when an explicit structural/coupling rule allows the complete units to coexist.

Compatibility belongs in domain data/rules, not visual guesswork.

## Opening graphics are semantic

Opening symbols must communicate:

- fixed vs operable;
- opening family;
- handedness/direction;
- interior/exterior viewpoint;
- active/inactive leaf where relevant.

A stylish but ambiguous symbol is a defect.

Use one coherent grammar across Studio, quotations and manufacturing documents, with deliberate simplification by audience.

## Composition

Bow/bay/corner products should emerge from modules/units joined by explicit couplings, transforms and angles.

The editor should make composition natural:

- add unit left/right;
- connect;
- set/drag angle;
- adjust module widths;
- select individual modules;
- preserve identity through undo/save/reload.

## Direct manipulation

The window must dominate Studio.

Selection should synchronize canvas, hierarchy, inspector, validation, BOM and AI context.

Manipulate physical concepts directly:

- overall dimensions;
- divider/mullion/transom;
- opening;
- unit/coupling angle;
- handles where editable.

Use exact numeric entry alongside drag interaction.

## Workshop language

Users should see actions and errors in workshop/business language, not implementation vocabulary.

Prefer:

- “Emitir cotización”
- “Enviar al taller”
- “Este herraje admite hojas hasta …”

Avoid exposing:

- enum names;
- hashes;
- internal IDs;
- raw stack traces;
- implementation flags.

## Progressive disclosure

Basic users should not be required to select obscure profile/bead/hardware codes when deterministic rules can derive them.

Advanced users need traceability and overrides where legitimate.

Power should appear when needed, not permanently crowd the primary workflow.
