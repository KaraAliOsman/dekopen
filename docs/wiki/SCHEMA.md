# DEKOPEN Wiki Schema and Agent Protocol

## 1. Principle

The wiki is a **compiled knowledge layer**, not the source of executable truth.

DEKOPEN uses the rule:

> REPO = MEMORY for implementation state.

The wiki exists to preserve synthesis, decisions, relationships and context that would otherwise be lost across chats and agent sessions.

## 2. Authority order by claim type

Do not use one universal hierarchy for every claim.

### Computed engineering numbers
1. current engine code + approved catalog authority;
2. golden tests and deterministic fixtures;
3. engineering documentation;
4. wiki synthesis.

### Database schema / tenancy
1. `supabase/migrations/`;
2. live DB tests/RLS evidence;
3. backend code;
4. wiki.

### Current product behavior
1. running application on the target ref;
2. current code and tests;
3. merged PR evidence;
4. current-state wiki page.

### Product intent
1. explicit recent owner decision;
2. `docs/PRODUCT.md`;
3. durable decision pages in this wiki;
4. older historical plans.

### Engineering invariants
1. `docs/ENGINEERING.md`;
2. `AGENTS.md`;
3. current deterministic/security tests;
4. wiki explanation.

### External/domain research
1. primary manufacturer/vendor/competitor source;
2. source page in `sources/`;
3. synthesis in `research/` or domain pages.

If two sources conflict, do not silently blend them. Record the contradiction and identify which authority currently governs.

## 3. Page metadata

New substantial pages should begin with YAML frontmatter when useful:

```yaml
---
type: decision | source | concept | synthesis | state | risk | research
status: active | draft | superseded | archived
updated: YYYY-MM-DD
volatility: low | medium | high
verified_ref: optional git ref/SHA
sources:
  - source identifier
---
```

### Volatility

- **low**: enduring product principle or historical decision;
- **medium**: architecture that may evolve;
- **high**: current branch/PR/CI/product state.

High-volatility pages must state when and where they were verified.

## 4. Evidence rules

Never present inference as repository fact.

For important claims, preserve enough evidence to re-check them:

- repo path + ref/SHA;
- PR/issue number;
- commit SHA;
- test/fixture name;
- owner-decision date/context;
- external URL + access date;
- document/page/sheet/row when relevant.

Do not store private chain-of-thought. Store conclusions, evidence, assumptions and unresolved questions.

Do not paste copyrighted external documents wholesale into this public repository unless redistribution is permitted. Prefer source metadata + link + concise synthesis.

## 5. Ingest workflow

When a new durable source arrives:

1. identify source type and authority;
2. preserve or reference the raw source;
3. create/update a page in `sources/`;
4. extract claims, decisions, contradictions and open questions;
5. update every relevant concept/entity/synthesis page, not just the source summary;
6. add cross-links;
7. update `index.md`;
8. append one dated entry to `log.md`;
9. if the source changes a current implementation claim, re-verify against the relevant ref before updating `state/current-reality.md`.

One source may legitimately update many pages.

## 6. Query workflow

For project questions:

1. read `index.md`;
2. locate relevant wiki pages;
3. if the question concerns current implementation, inspect the current repository/ref;
4. read underlying source evidence where necessary;
5. answer with explicit separation between:
   - verified current fact,
   - owner intent,
   - historical context,
   - external research,
   - inference;
6. if the answer produces a durable synthesis, add it back to the wiki and append the log.

Do not force every trivial answer into the wiki. Save knowledge that will materially help later sessions.

## 7. Lint workflow

Periodically inspect for:

- stale high-volatility claims;
- contradictions;
- pages that assert current state without a verification ref/date;
- orphan pages;
- duplicate concepts;
- broken/missing links;
- superseded decisions still presented as active;
- source summaries never integrated into concept pages;
- unsupported factual claims;
- unresolved questions for which existing evidence now provides an answer.

Fix what can be fixed from evidence. Flag unresolved gaps.

## 8. Session bootstrap

An agent entering DEKOPEN with no chat context should:

1. read root `AGENTS.md`;
2. read `docs/PRODUCT.md`;
3. read `docs/ENGINEERING.md`;
4. read `docs/wiki/index.md`;
5. read `docs/wiki/decisions/owner-decisions.md`;
6. read the relevant domain wiki pages;
7. read the tail of `docs/wiki/log.md`;
8. inspect current branch, open PRs and affected code before making current-state assertions;
9. run/use the product when UX behavior matters.

The wiki should reduce rediscovery, not eliminate verification.

## 9. Update discipline

- `index.md`: content-oriented map; update when pages are created/renamed/reorganized.
- `log.md`: chronological and append-only.
- `state/current-reality.md`: intentionally replace/update as reality changes, preserving verification metadata.
- decision pages: never erase the fact that an old decision existed; mark it superseded and link to the replacement.

## 10. Search tooling

Start simple: Markdown + index + repository search.

Only add qmd/vector/hybrid search if the wiki becomes large enough that navigation degrades. Optional tools must not become a prerequisite for normal agent operation.
