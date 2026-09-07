# Current operating contract — September 2026

This release addresses reproduced correctness and recovery failures in the standalone MCP deployment. It changes tool contracts; older unscoped calls must be updated.

| Component | Responsibility | Verified boundary |
|---|---|---|
| Stenographer | Preserve visible conversation turns and extracted briefs | Task/session isolation, source receipts, replayable outbox |
| Omega Brain | Retrieve context, evaluate supplied claims, record audit events | Indexed lexical retrieval and local operator-policy receipts |
| SSWP | Execute configured software checks and preserve evidence | Receipt validation at the witness entry point, bounded processes, persistent records |

Use the same task identifier as Brain `task_id` and Steno `session_id`. Use `conversation_id` when saving a handoff. Cross-task retrieval requires an explicit opt-in. Default shared state lives in `~/.veritas-shared`; set `VERITAS_SHARED_DIR` identically in all three processes to override it. Also configure `OMEGA_BRAIN_DATA_DIR`, `OMEGA_STENOGRAPHER_DIR` and `SSWP_DB` when placing the databases elsewhere.

Retrieval uses FTS5 to select at most 256 candidates, then a stable 512-feature lexical representation. Scores measure textual relevance; they are not semantic understanding, evidence confidence, or authorization. Old text remains preserved and searchable with explicit cross-task access. New fragments record their task and representation version, and may supersede an earlier fragment in the same task.

Cortex returns advisory alignment and preserves arguments. `omega_execute` validates and dispatches internal Brain tools. Neither intercepts other applications. SSWP witness operations verify a locally authenticated receipt covering the exact tool, canonical path, arguments, task, source digest, policy digest, expiry and one-use nonce. Only explicitly registered projects and configured commands are eligible. The host, installed dependencies and local policy/key files remain trusted. This is not an OS sandbox or protection against the host administrator.

Create `operator-policy.json` in the shared directory with `witness_roots` (exact canonical project paths) and `projects` keyed by those paths. Each optional `build`, `test` or `lint` entry has an `argv` array and `timeoutMs`. Create a private 32-byte `approval.key` locally; never commit it. `omega_authorize_action(tool="sswp_witness", args={"repoPath":canonical_path}, task_id=task_id)` issues the receipt. Pass it to `sswp_witness` with the same path and task. Any source or policy change requires another receipt.

Missing checks are INCONCLUSIVE, execution errors are ERROR, failed checks are FAIL, and inapplicable checks are labeled separately. BUILD_SUCCESS establishes one successful run. An optional `reproducible` profile supplies `argv`, `outputs`, and optional `setup` commands; two fresh source copies must independently produce identical nonempty output manifests. Dependencies and tools are host-trusted, so this is same-host reproducibility evidence, not hermetic or cross-host assurance. Output files from the original source tree are removed before each independent build.

Dependency and security claim gates evaluate supplied evidence. They do not secretly run scanners or fetch vulnerability databases. Missing coverage is INCONCLUSIVE; supplied crash and exploit results are evaluated. SSWP npm/pnpm inventories cover lockfile package entries, including transitive entries, and distinguish declared integrity from independently checked bytes.

Historical ledger rows remain unchanged and unverified. New canonical v2 chains begin with a fingerprinted legacy boundary and serialize writes. Event type, task, nested payload, sequence and timestamp are covered. Appending to an invalid v2 chain is refused. Hashes establish local consistency, not authorship, truth, or resistance to complete rewriting by an administrator. Preserve external backup receipts to compare historical heads.

Steno keeps complete source exchanges. Brief extraction is heuristic and retains source IDs, decisions, blockers and continuation signals. Priority does not promote a claim to verified evidence. Capturing Codex transcripts is opt-in through the `codex_capture.py` entry point. It observes visible user/assistant messages, not tool results or private reasoning. SQLite capture offsets, idempotent source receipts and outboxes support restart/replay. Recovery reconciles independently timed database snapshots by replaying missing event copies.

Back up SQLite databases with the online backup API, plus source, policy and configuration. Exclude keys, credentials and transient WAL/SHM files. Restore to a separate directory first, then start the observer so delivery receipts reconcile. A locally queued sync file is not proof of a verified cloud backup. The restored Linux/network deployment and old network helper are outside this standalone release's validation scope.

Validation uses synthetic fixtures, actual stdio MCP calls, cross-language receipt verification, concurrent writers, invalid/tampered evidence, timeouts, task overlap, old brief retrieval and snapshot/replay recovery. Passing these checks is regression evidence, not an independent security certification or a market-wide performance benchmark.
