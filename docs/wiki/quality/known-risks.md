---
type: risk
status: active
updated: 2026-09-28
volatility: medium
sources:
  - owner conversations through 2026-09-28
  - recent DEKOPEN audit notes
---

# Known risks and audit targets

This page records recurring failure modes. It does **not** assert that every item is still broken. Re-test against the current ref.

## Editor/domain semantics

- sliders rendered as opening outward;
- slider/casement categories insufficiently separated;
- opening symbols difficult to understand;
- handle side/orientation/3D transform errors;
- bow/bay coupling and angle semantics;
- invalid typology/system combinations;
- visual geometry diverging from engine/product model.

## Direct manipulation/history

- dirty state failing to reset after undo-to-saved;
- unsaved navigation guard behavior;
- pending divider state not clearing;
- divider placement overly center-biased;
- touch divider targeting wrong bay;
- stale listeners after canceled drag;
- top-level/divider limits;
- seam snap outside legal bounds;
- duplicated/unstable positions;
- tree responsiveness;
- coupling target too small;
- handles/controls overlapping dimensions.

## Catalog/authority

- duplicate or conflicting visible role mappings;
- global-vs-tenant authorization mistakes;
- demo data accidentally treated as certified;
- AI import without durable provenance;
- unsupported PDF/image/XLSX claims;
- technical UNKNOWN silently converted into default values;
- imported profile sections with unverified scale/origin/orientation.

## Pricing/quotation

- preview mutating persisted state;
- missing cost becoming zero;
- cost and selling price conflated;
- issued revision changing under new catalog/prices;
- unclear successor/reset behavior;
- customer documents exposing internal/confidential cost detail;
- quote UI technically correct but commercially unreadable.

## API/state consistency

- OpenAPI/generated client drift;
- component-local state not persisted;
- background jobs not reflected/refetched;
- retry races;
- confirmation behavior bypassing intended product flow.

## Security

- cross-org onboarding leakage;
- guessed-ID access;
- catalog visibility holes;
- file/document access beyond tenant authority;
- UI-only permission checks.

## Manufacturing

- released product with incomplete authority;
- BOM and visual product diverging;
- inventory shortage not blocking/flagging correctly;
- remnant/offcut state inconsistency;
- cutting optimization using wrong allowance/stock assumptions;
- remake losing traceability.

## CNC

Treat all CNC capability as high-risk until validated against known machine fixtures.

Audit:

- coordinate frame;
- units;
- face/orientation;
- handedness;
- tool mapping;
- depth;
- clamp collision;
- unsupported operation blocking;
- profile-section orientation;
- deterministic postprocessor output.

Never “best guess” machine data.

## UI/product quality

Audit for features that appear to exist only because they were implemented.

For every control ask:

- Why does it exist?
- What real task does it serve?
- What happens before and after?
- Could the system derive this instead?
- Is the terminology human?
- Is this the right density/hierarchy?

A coherent product matters more than feature count.
