---
type: source
status: active
updated: 2026-09-28
volatility: low
sources:
  - https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
---

# Andrej Karpathy — LLM Wiki

Canonical source: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

## Why it matters to DEKOPEN

The pattern addresses a recurring project problem: an agent entering a new session otherwise has to reconstruct decisions, relationships and research from raw chats/docs every time.

Karpathy's pattern uses three layers:

1. immutable raw sources;
2. an LLM-maintained interlinked Markdown wiki;
3. a schema file that tells agents how to ingest/query/lint it.

Key operations:

- **ingest**: integrate a source into all relevant pages, not only one summary;
- **query**: answer from accumulated synthesis and file durable new insights back;
- **lint**: find contradictions, staleness, orphans, missing concepts and evidence gaps;
- **index**: content-oriented navigation;
- **log**: chronological append-only history.

At moderate scale, a well-maintained index can be sufficient before adding dedicated search infrastructure.

## DEKOPEN adaptation

DEKOPEN adds an important constraint:

> the wiki preserves understanding, but the repository remains authoritative for current implementation state.

Therefore high-volatility claims require a ref/date and must be revalidated before code decisions.

This protects the project from replacing “lost chat memory” with a different failure mode: stale documentation memory.
