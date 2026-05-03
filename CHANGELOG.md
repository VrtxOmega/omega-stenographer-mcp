# Changelog

## v1.0.0 — 2026-05-02

**First public release.**

Omega Stenographer MCP is a self-contained MCP server that passively observes agent sessions — ingesting every turn, extracting decisions and blockers, building running notes, and compressing stale context into searchable briefs. No external server required. One file.

### Added

**Core systems (all built-in)**
- **Turn Ingestion** — Capture every user/assistant message with role, content, session ID, and timestamp
- **Decision Extraction** — Regex-based detection of decision-like statements (decided, chose, settled on, key finding, →)
- **Blocker Extraction** — Detection of stuck states, errors, crashes, timeouts
- **FTS5 Indexing** — Full-text search across exchanges by content, decisions, and blockers
- **Context Compression** — Automatic compression of unprocessed turns into tiered briefs when `STENO_TURN_LIMIT` is exceeded
- **Tiered Briefs** — Tier-A for decision-bearing context; Tier-B for raw context excerpts
- **Source Tracking** — Every brief records its source turn IDs for traceability
- **TF-IDF Similarity** — Built-in 128-dim TF-IDF n-gram for semantic search (no external dependencies)
- **Running Notes** — Formatted document with milestones, compressed briefs, and recent exchanges
- **Milestone Marking** — Elevate critical exchanges to tier-A priority
- **Venv Auto-Activation** — Shim that re-execs with venv Python if deps are isolated

**Tools (5)**
`stenographer_ingest_exchange`, `stenographer_get_brief`, `stenographer_compact_guard`,
`stenographer_mark_milestone`, `stenographer_query_history`

**Resources (2)**
- `omega-stenographer://session/notes` — Live running notes document
- `omega-stenographer://session/guard` — Auto-compressed briefing

### Invariants

- Compression preserves source turn IDs — every brief is traceable to its original exchanges
- No LLM-generated summaries — briefs use verbatim context excerpts and regex-extracted decisions
- `STENO_TURN_LIMIT = 8` (default)
- `STENO_TOP_K = 5` (default)
- TF-IDF n-gram: 128 dimensions
