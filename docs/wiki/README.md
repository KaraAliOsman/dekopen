# DEKOPEN LLM Wiki

Persistent project knowledge for DEKOPEN.

This directory implements the LLM Wiki pattern described by Andrej Karpathy: raw evidence remains separate, while agents maintain an interlinked Markdown knowledge layer that compounds across sessions instead of reconstructing project context from scratch.

## Purpose

Use this wiki for durable knowledge that does not belong only in chat history:

- owner decisions and product intent;
- domain rules and UX principles;
- architectural synthesis across code/docs/PRs;
- competitor research;
- known product risks and recurring defects;
- current-state maps with explicit verification dates;
- useful conclusions produced during investigation.

This wiki is **not** a replacement for the repository as source of truth.

For current implementation claims, inspect the current ref, tests and running product. The wiki may tell you where to look and why something exists, but it must not override newer code evidence.

## Layers

1. **Evidence / raw sources** — repository refs, PRs, issue threads, user-provided notes, external research, screenshots and documents. Immutable where stored locally; otherwise referenced by durable URL/identifier.
2. **Wiki** — maintained Markdown synthesis in this directory.
3. **Schema** — `SCHEMA.md`, plus the repository-level `AGENTS.md`, defines how agents ingest, query and maintain the wiki.

## Start here

1. Read `index.md`.
2. Read `state/current-reality.md` for the latest verified product-state map.
3. Read `decisions/owner-decisions.md` before making product-direction decisions.
4. Read `quality/known-risks.md` before touching editor, pricing, catalog, factory or CNC.
5. For any volatile/current claim, inspect the repository before acting.

See `SCHEMA.md` for the maintenance protocol.
