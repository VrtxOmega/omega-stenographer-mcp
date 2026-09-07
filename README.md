# Omega Stenographer MCP

Stenographer preserves conversation turns, extracts decisions and blockers, and builds searchable briefs without deleting the original exchanges.

Version 2.0 requires explicit session scope. Use the same `session_id` across ingest, brief, compaction, milestone and history calls. A global history search requires `cross_session=true`. Marking a milestone changes priority; it does not establish that a statement is true.

Install with `python -m pip install .`. Run `omega-stenographer-mcp` for explicit MCP ingestion, or `python codex_capture.py` to run the server with automatic visible-message capture from local Codex transcript files. The compatibility standalone entry point uses the same maintained implementation. No model API key is required for extraction or search.

Data defaults to `~/.omega-stenographer`. `OMEGA_CODEX_SESSIONS` overrides the transcript directory; otherwise capture uses `$CODEX_HOME/sessions` or `~/.codex/sessions`. The initial cutoff defaults to September 7, 2026 and can be set with `OMEGA_CAPTURE_SINCE=YYYY-MM-DD`. Older files are indexed at their current end, and new appended messages are subsequently captured. One OS lock permits a single observer across multiple MCP processes.

The observer excludes tool results, reasoning and configuration messages; persists source receipts and SQLite file offsets; retries partial lines; and delivers committed exchanges to [Omega Brain](https://github.com/VrtxOmega/omega-brain-mcp) through a durable local event bus. The two projects carry the same versioned runtime module so Stenographer also installs independently.

`stenographer_capture_status` reports progress and delivery errors. Start a helper with `StenographerClient(session_id="example-task")` and use `ingest`, `get_brief`, `compact_guard`, `search` or `mark_milestone` within that scope.

See [current operating contract](docs/CURRENT_STATE.md) for migration, task isolation and backups. Older examples need explicit session IDs. Run `python -m unittest discover -s tests -p "test_contracts.py"` for standalone contract tests. [SSWP](https://github.com/VrtxOmega/sswp-mcp) software evidence uses the same task IDs and event bus.
