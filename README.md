<div align="center">
  <img src="https://raw.githubusercontent.com/VrtxOmega/Gravity-Omega/master/omega_icon.png" width="120" alt="VERITAS Omega" />
  <h1>OMEGA STENOGRAPHER MCP</h1>
  <p><strong>Passive Session Observer — Turn Ingestion · Decision Extraction · Context Compression · Searchable Briefs</strong></p>
</div>

<div align="center">

[![CI](https://github.com/VrtxOmega/omega-stenographer-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/VrtxOmega/omega-stenographer-mcp/actions/workflows/ci.yml)
![Status](https://img.shields.io/badge/Status-ACTIVE-success?style=flat-square&labelColor=000000&color=d4af37)
![Version](https://img.shields.io/badge/Version-v1.0.0-blue?style=flat-square&labelColor=000000)
![Python](https://img.shields.io/badge/Python-3.11%2B-informational?style=flat-square&labelColor=000000)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square&labelColor=000000)

[![omega-stenographer-mcp MCP server](https://glama.ai/mcp/servers/VrtxOmega/omega-stenographer-mcp/badges/card.svg)](https://glama.ai/mcp/servers/VrtxOmega/omega-stenographer-mcp)

</div>

---

## Ecosystem Canon

Omega Stenographer MCP is the **passive observation layer** of the VERITAS & Sovereign Ecosystem (Omega Universe). Where Omega Brain enforces governance and VERITAS gates evaluate artifact integrity, Stenographer observes: it ingests every conversation turn, extracts decisions and blockers from agent reasoning, builds live running notes, and compresses stale context into searchable briefs before it can be lost to context window eviction. It does not govern — it remembers. In the Omega Universe, Omega Stenographer MCP is the institutional memory: the layer that ensures no decision, no blocker, and no hard-won insight evaporates when the context window scrolls past.

> **SYSTEM INVARIANT:** Stenographer does not interpret. It extracts, indexes, and compresses. Every brief is traceable to its source turns. Every search result cites its provenance. No synthesized narrative substitutes for the original record.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [Integrations](#integrations)
- [Usage Examples](#usage-examples)
- [Tools Reference (5 Tools)](#tools-reference-5-tools)
- [Resources (2)](#resources-2)
- [Compression Model](#compression-model)
- [Troubleshooting](#troubleshooting)
- [Security & Sovereignty](#security--sovereignty)
- [Threat Model](#threat-model)
- [Roadmap](#roadmap)
- [Omega Universe](#omega-universe)
- [License](#license)

---

## Overview

### What It Is

Omega Stenographer MCP is a self-contained **Model Context Protocol (MCP) server** that runs as a local process alongside any MCP-compatible AI client. It exposes 5 tools and 2 resources covering three observation domains:

- **Turn ingestion** — every user and assistant message is captured with structured metadata (role, session ID, extracted decisions, extracted blockers)
- **Context compression** — when unprocessed turns exceed `STENO_TURN_LIMIT`, they are compressed into a tiered brief fragment and indexed for later retrieval
- **Searchable memory** — full-text search (FTS5) over all exchanges; semantic similarity search over compressed briefs; live running notes document

One Python file. One pip dependency. Zero external services.

Compatible clients: Claude Desktop, VS Code Copilot, Cursor, Windsurf, AutoGen, LangChain, CrewAI, LlamaIndex, and any MCP-compliant host.

### What It Is Not

- **Not a governance layer.** Stenographer does not approve, block, or steer agent tool calls. It observes and records.
- **Not a cloud service.** No network egress, no API keys, no telemetry. All data remains on the operator's machine under `~/.omega-stenographer/` (or `OMEGA_STENOGRAPHER_DIR`).
- **Not a language model.** Stenographer does not generate text. It ingests, extracts, indexes, and compresses agent conversation.
- **Not a policy authority.** Stenographer tags decisions and blockers heuristically; it does not determine correctness or enforce constraints.

---

## Features

### Turn Ingestion

- **Every turn captured** — role, content, session ID, timestamp
- **Automatic decision extraction** — regex-based patterns detect decision-like statements (decided, chose, settled on, key finding, →)
- **Automatic blocker extraction** — detects stuck states, errors, crashes, timeouts
- **FTS5 full-text indexing** — every exchange is immediately searchable by content, decisions, and blockers

### Context Compression

- **Configurable turn limit** — defaults to 8 turns (`STENO_TURN_LIMIT`); when exceeded, unprocessed turns are compressed
- **Tiered briefs** — tier-A briefs contain extracted decisions; tier-B briefs preserve raw context excerpts
- **Traceable provenance** — every brief records its source turn IDs; no synthesized narrative replaces the original record
- **Automatic FTS indexing** — compressed briefs are immediately searchable

### Searchable Memory

- **FTS5 keyword search** — `stenographer_query_history` searches all exchanges by content, decisions, and blockers
- **Semantic similarity search** — `stenographer_compact_guard` uses TF-IDF cosine similarity to rank compressed briefs against a query
- **Live running notes** — `stenographer_get_brief` returns a formatted document with milestones, compressed briefs, and recent exchanges
- **Milestone marking** — `stenographer_mark_milestone` elevates critical exchanges to tier-A priority

### Operational Characteristics

- **Two transports** — stdio (default, MCP standard) and SSE (HTTP streaming for web clients)
- **Docker-ready** — single `Dockerfile`, non-root user, unbuffered I/O
- **Single dependency** — `mcp>=1.0.0`
- **Fully local** — no cloud, no API keys, no external server required
- **Venv auto-activation shim** — the standalone script re-execs itself with the venv Python if deps are isolated

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP CLIENT                               │
│   (Claude Desktop / VS Code Copilot / Cursor / AutoGen / ...)   │
└───────────────────────────┬─────────────────────────────────────┘
                            │  MCP stdio / SSE (JSON-RPC 2.0)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              OMEGA STENOGRAPHER MCP SERVER                       │
│           omega_stenographer_mcp_standalone.py                   │
│                                                                 │
│  ┌──────────────────────────┐  ┌──────────────────────────────┐ │
│  │    INGESTION ENGINE      │  │     COMPRESSION ENGINE       │ │
│  │                          │  │                              │ │
│  │  Turn Capture            │  │  Turn Counting               │ │
│  │  (role, content, SID)    │  │  (unprocessed tally)         │ │
│  │                          │  │                              │ │
│  │  Decision Extraction     │  │  Fragment Generation         │ │
│  │  (regex patterns)        │  │  (combined context +         │ │
│  │                          │  │   decision summary)          │ │
│  │  Blocker Extraction      │  │                              │ │
│  │  (problem detection)     │  │  Tier Assignment             │ │
│  │                          │  │  (A: decisions, B: context)  │ │
│  │  FTS5 Indexing           │  │                              │ │
│  │  (content, decisions,    │  │  Source Turn Tracking        │ │
│  │   blockers)              │  │  (brief → turns mapping)     │ │
│  └──────────┬───────────────┘  └────────────────┬─────────────┘ │
│             │                                   │               │
│  ┌──────────┴───────────────────────────────────┴─────────────┐ │
│  │                    SEARCH & RETRIEVAL                      │ │
│  │                                                            │ │
│  │  FTS5 Search (exchanges)    TF-IDF Similarity (briefs)     │ │
│  │  Running Notes Builder      Milestone Manager              │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────│───────────────────────────────────────────────────┘
              │
              ▼  SQLite
    ┌───────────────────────────┐
    │  ~/.omega-stenographer/   │
    │  steno.db                 │
    │  (exchanges + briefs +    │
    │   FTS5 indexes)           │
    └───────────────────────────┘
```

### Component Roles

| Layer | Component | Role |
|-------|-----------|------|
| **Ingestion** | Turn Capture | Records every user/assistant message with structured metadata |
| **Ingestion** | Decision Extraction | Regex-based detection of decision-like statements in agent reasoning |
| **Ingestion** | Blocker Extraction | Regex-based detection of stuck states, errors, and problems |
| **Ingestion** | FTS5 Indexing | Full-text search index across content, decisions, and blockers |
| **Compression** | Turn Counting | Tracks unprocessed exchanges; triggers compression at `STENO_TURN_LIMIT` |
| **Compression** | Fragment Generation | Condenses multiple turns into a single brief with decision summaries |
| **Compression** | Tier Assignment | Tier-A for decision-bearing context; tier-B for raw context excerpts |
| **Compression** | Source Tracking | Every brief records its constituent turn IDs for traceability |
| **Retrieval** | FTS5 Search | Keyword search over all exchanges |
| **Retrieval** | TF-IDF Similarity | Cosine similarity ranking of compressed briefs |
| **Retrieval** | Running Notes | Formatted document builder: milestones → briefs → recent exchanges |

> 🏛️ **Protocol Standard:** The `omega-stenographer-mcp` is the passive observation counterpart to Omega Brain MCP. Where Omega Brain enforces the VERITAS Ω-CODE v2.0 governance gates, Stenographer captures the institutional memory those gates operate on — preserving decisions, blockers, and context that would otherwise be lost to context window pressure.

---

## Requirements

| Requirement | Details |
|-------------|---------|
| Python | 3.11 or 3.12 |
| Core dependency | `mcp >= 1.0.0` |
| OS | Linux, macOS, Windows (WSL2 recommended on Windows) |
| Disk | ~5 MB for source + SQLite data dir (default `~/.omega-stenographer/`) |

> **No external embedding service required.** Stenographer uses built-in TF-IDF n-gram (128-dim) for semantic similarity — no GPU, no model download, always available.

---

## Installation

### From PyPI

```bash
pip install omega-stenographer-mcp
```

### From Source

```bash
git clone https://github.com/VrtxOmega/omega-stenographer-mcp.git
cd omega-stenographer-mcp
pip install mcp
```

### Docker

```bash
docker build -t omega-stenographer-mcp .
docker run --rm -i omega-stenographer-mcp                              # stdio mode (MCP standard)
docker run --rm -p 8056:8056 omega-stenographer-mcp --sse --port 8056  # SSE mode
```

### Run Tests

```bash
pip install pytest pytest-asyncio pytest-cov
PYTHONUTF8=1 OMEGA_STENOGRAPHER_DIR=/tmp/steno-test pytest tests/ -v --tb=short
```

---

## Quickstart

### 1 — Verify the server starts

```bash
python omega_stenographer_mcp_standalone.py --help
```

### 2 — Run in stdio mode (default)

The server reads JSON-RPC 2.0 messages from stdin and writes responses to stdout. MCP clients manage this process automatically via the config below.

```bash
python omega_stenographer_mcp_standalone.py
```

### 3 — Run in SSE mode (HTTP streaming)

```bash
python omega_stenographer_mcp_standalone.py --sse --port 8056
# GET  http://localhost:8056/sse      — event stream
# POST http://localhost:8056/messages — send tool calls
```

### 4 — Test a tool call manually (stdio)

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"stenographer_ingest_exchange","arguments":{"role":"user","content":"Hello, world!"}}}' \
  | python omega_stenographer_mcp_standalone.py
```

### 5 — Configure your MCP client (see [Configuration](#configuration))

---

## Configuration

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "omega-stenographer": {
      "command": "python",
      "args": ["/absolute/path/to/omega_stenographer_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### VS Code / GitHub Copilot

Add to `.vscode/mcp.json` in your workspace (or user settings):

```json
{
  "servers": {
    "omega-stenographer": {
      "type": "stdio",
      "command": "python",
      "args": ["/absolute/path/to/omega_stenographer_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### Cursor

In **Cursor Settings → MCP → Add Server**:

```json
{
  "mcpServers": {
    "omega-stenographer": {
      "command": "python",
      "args": ["/absolute/path/to/omega_stenographer_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### Windsurf / Cascade

In `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "omega-stenographer": {
      "command": "python",
      "args": ["/absolute/path/to/omega_stenographer_mcp_standalone.py"],
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

### SSE / HTTP Client

```json
{
  "mcpServers": {
    "omega-stenographer": {
      "type": "sse",
      "url": "http://localhost:8056/sse"
    }
  }
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHONUTF8` | `0` | Set to `1` on Windows to avoid encoding errors |
| `OMEGA_STENOGRAPHER_DIR` | `~/.omega-stenographer/` | Override the data directory for the SQLite database |
| `STENO_TURN_LIMIT` | `8` | Number of unprocessed turns before compression triggers |
| `STENO_TOP_K` | `5` | Number of briefs returned by `stenographer_compact_guard` |

---

## Integrations

Omega Stenographer MCP integrates with any MCP-compatible client using standard JSON-RPC 2.0 over stdio or SSE. For framework-specific integration patterns (LangChain, CrewAI, AutoGen, LlamaIndex) see [`INTEGRATIONS.md`](INTEGRATIONS.md) and the [`examples/`](examples/) directory.

### Recommended Integration Pattern

For production use, keep one persistent server process across all calls.

```python
import subprocess, json

class StenoClient:
    def __init__(self, server_path):
        self.proc = subprocess.Popen(
            ["python", server_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True
        )

    def call(self, tool_name, args):
        msg = {
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args}
        }
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

client = StenoClient("/path/to/omega_stenographer_mcp_standalone.py")

# Ingest a turn
client.call("stenographer_ingest_exchange", {
    "role": "user",
    "content": "Fix the authentication bug",
    "session_id": "session-001"
})

# Get running notes
notes = client.call("stenographer_get_brief", {})

# Search history
results = client.call("stenographer_query_history", {"query": "authentication"})

client.close()
```

### Quick-Reference Pattern Table

| Goal | Tool | Notes |
|---|---|---|
| Capture a turn | `stenographer_ingest_exchange` | Call after every user/assistant message |
| View live notes | `stenographer_get_brief` | Returns milestones + compressed briefs + recent exchanges |
| Context window rescue | `stenographer_compact_guard` | Returns compressed briefing + top-K relevant briefs |
| Flag critical decision | `stenographer_mark_milestone` | Elevates to tier-A |
| Keyword search history | `stenographer_query_history` | FTS5 search across all exchanges |

---

## Usage Examples

All examples use JSON-RPC 2.0. In practice, your MCP client sends these automatically when you invoke a tool. The shell one-liner form is useful for testing.

### Ingest a turn

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"stenographer_ingest_exchange","arguments":{"role":"assistant","content":"I found the bug in the auth module — the JWT validation was using the wrong secret key. Fix applied to auth.py line 42.","session_id":"debug-session"}}}' \
  | python omega_stenographer_mcp_standalone.py
```

**Response (abbreviated):**

```json
{
  "result": {
    "content": [{
      "type": "text",
      "text": "Ingested [assistant] #1 (119 chars; decisions: 1; blockers: 0)"
    }]
  }
}
```

### Get running notes

```json
{
  "jsonrpc": "2.0", "id": 2,
  "method": "tools/call",
  "params": {
    "name": "stenographer_get_brief",
    "arguments": {}
  }
}
```

**Response:**

```
# Running Session Notes

## 📝 Recent Exchanges

### [1] ASSISTANT (💡 1 decisions)
I found the bug in the auth module — the JWT validation was using the wrong secret key...

### [2] USER
Deploy to staging and monitor for 24 hours.
```

### Search history by keyword

```json
{
  "jsonrpc": "2.0", "id": 3,
  "method": "tools/call",
  "params": {
    "name": "stenographer_query_history",
    "arguments": {
      "query": "JWT OR auth",
      "limit": 5
    }
  }
}
```

### Compact guard — rescue from context pressure

```json
{
  "jsonrpc": "2.0", "id": 4,
  "method": "tools/call",
  "params": {
    "name": "stenographer_compact_guard",
    "arguments": {
      "query": "authentication deployment"
    }
  }
}
```

**Response:**

```
# Compaction Guard Briefing

Query: authentication deployment

## 🔴 Live (Uncompressed)
- [assistant] I found the bug in the auth module... [Decisions: JWT validation fix applied]

## 📦 Compressed Briefs (Top-K)
- [A] Batch 1-5: Decisions: Switched to setuptools for build; Fixed JWT secret key rotation
```

### Mark a milestone

```json
{
  "jsonrpc": "2.0", "id": 5,
  "method": "tools/call",
  "params": {
    "name": "stenographer_mark_milestone",
    "arguments": {
      "exchange_id": 1,
      "label": "Auth bug root cause identified"
    }
  }
}
```

---

## Tools Reference (5 Tools)

| Tool | Purpose |
|------|---------|
| `stenographer_ingest_exchange` | Capture a conversation turn with role, content, and session ID. Auto-extracts decisions and blockers. |
| `stenographer_get_brief` | Build and return the live running notes document: milestones, compressed briefs, recent exchanges. |
| `stenographer_compact_guard` | Get compressed briefing + top-K relevant briefs. Call when context window pressure hits or before compaction. |
| `stenographer_mark_milestone` | Flag a critical exchange for tier-A priority — survives compression and appears in running notes. |
| `stenographer_query_history` | FTS5 keyword search over all ingested exchanges by content, decisions, and blockers. |

---

## Resources (2)

| URI | Description |
|-----|-------------|
| `omega-stenographer://session/notes` | Live running notes document — formatted markdown |
| `omega-stenographer://session/guard` | Auto-compressed briefing + relevant RAG fragments |

---

## Compression Model

Stenographer's compression is designed to solve a specific problem: **context window eviction.** When an agent session runs long, early turns scroll out of the context window. Those early turns may contain critical decisions, blocker discoveries, or architectural choices that the agent needs later.

### How It Works

1. **Turn counting:** Every ingested turn increments the unprocessed counter. Stenographer tracks this via `SELECT COUNT(*) FROM exchanges WHERE compressed=0`.

2. **Threshold trigger:** When unprocessed turns ≥ `STENO_TURN_LIMIT` (default: 8), `compress_unprocessed()` fires automatically.

3. **Fragment generation:** All unprocessed turns are combined. If decisions were extracted, the brief summarizes them. If no decisions, raw context (first 300 chars) is preserved.

4. **Tier assignment:**
   - **Tier A** — brief contains extracted decisions (highest signal)
   - **Tier B** — brief contains raw context excerpts (medium signal)

5. **Source tracking:** Every brief records its `source_turns` as a JSON array of exchange IDs. No record is lost — the brief is always traceable back to the original turns.

6. **Compaction marking:** Source turns are marked `compressed=1` so they won't appear in running notes (they're summarized in the brief), but they remain in the database for FTS5 search.

### Configuration Tuning

| Scenario | STENO_TURN_LIMIT | Rationale |
|----------|-----------------|-----------|
| Short sessions (10-20 turns) | 12 | Less aggressive compression; more detail in running notes |
| Long sessions (50+ turns) | 6 | Aggressive compression; prevent context window overflow |
| Default | 8 | Balanced — compresses before most context windows evict |

---

## File Structure

```
omega-stenographer-mcp/
├── omega_stenographer_mcp_standalone.py  # MCP server — Ingestion + Compression + Retrieval (~374 lines)
├── requirements.txt                      # mcp>=1.0.0
├── pyproject.toml                        # Package config
├── Dockerfile                            # Non-root, unbuffered, stdio + SSE
├── INTEGRATIONS.md                       # LangChain, CrewAI, AutoGen, LlamaIndex guides
├── SECURITY.md                           # Vulnerability reporting policy
├── CHANGELOG.md                          # Release history
├── docs/
│   └── integration.md                    # Detailed integration reference
├── examples/
│   ├── langchain_quickstart.py
│   ├── crewai_quickstart.py
│   ├── autogen_quickstart.py
│   └── llamaindex_quickstart.py
└── tests/
    ├── test_ingest.py                    # Turn ingestion + decision/blocker extraction tests
    ├── test_compression.py               # Compression threshold + tier assignment tests
    ├── test_search.py                    # FTS5 search + TF-IDF similarity tests
    └── test_brief.py                     # Running notes + milestone tests
```

---

## Troubleshooting

### Server does not start / `ModuleNotFoundError: mcp`

```bash
pip install mcp
```

### `UnicodeDecodeError` on Windows

Set the environment variable before running:

```bash
set PYTHONUTF8=1
python omega_stenographer_mcp_standalone.py
```

Or add `"env": { "PYTHONUTF8": "1" }` to your MCP client config.

### Client shows "Server disconnected" immediately

1. Confirm the path in your client config is **absolute** (e.g., `C:\Users\you\omega-stenographer-mcp\omega_stenographer_mcp_standalone.py`), not relative.
2. Run the server manually in a terminal to see startup errors: `python /path/to/omega_stenographer_mcp_standalone.py`
3. Check Python version: `python --version` must be 3.11+.

### Compression not firing

1. Check unprocessed count: the database should show `SELECT COUNT(*) FROM exchanges WHERE compressed=0` ≥ `STENO_TURN_LIMIT`.
2. Verify `STENO_TURN_LIMIT` is set (default: 8).
3. Check stderr for traceback — the `compress_unprocessed` function logs errors to the server's stderr.

### Briefs return empty or truncated

1. Verify the `briefs` table exists: `sqlite3 ~/.omega-stenographer/steno.db ".tables"`
2. Check that source turns had decisions extracted (non-empty `decisions` field).
3. Tier-B briefs preserve raw context; if content is short, the brief will be short.

### Database corruption

Delete the data directory and restart to rebuild from scratch (all persisted memory will be lost):

```bash
rm -rf ~/.omega-stenographer/
python omega_stenographer_mcp_standalone.py
```

To use a separate data directory per project:

```bash
OMEGA_STENOGRAPHER_DIR=/path/to/project-steno python omega_stenographer_mcp_standalone.py
```

### SSE mode: `Connection refused` on port 8056

Ensure the server is running with `--sse --port 8056` and that the port is not blocked by a firewall. Check with:

```bash
curl -N http://localhost:8056/sse
```

---

## Security & Sovereignty

- **All data is local.** The SQLite database is stored in `~/.omega-stenographer/` (or `OMEGA_STENOGRAPHER_DIR`). No data is transmitted to any external service.
- **No API keys required.** The server requires only a local Python installation and the `mcp` package.
- **Passive observation only.** Stenographer does not approve, block, or steer agent actions. It cannot modify agent behavior.
- **Non-root Docker.** The provided `Dockerfile` runs as a non-root `steno` user.
- **Sensitive data handling.** Do not ingest secrets, credentials, or PII into Stenographer. The database is unencrypted SQLite on disk; protect it with OS-level file permissions.
- **Venv isolation.** The standalone script includes a venv auto-activation shim — if dependencies are in a `.venv` directory, the script re-execs itself with the venv Python, ensuring no system Python pollution.

For vulnerability reporting, see [`SECURITY.md`](SECURITY.md).

---

## Threat Model

### In Scope

| Threat | Mitigation |
|--------|-----------|
| Loss of critical agent decisions to context window eviction | Automatic compression at `STENO_TURN_LIMIT`; tier-A briefs preserve decisions |
| Inability to search past conversation | FTS5 full-text index on all exchanges; persistent across restarts |
| Compressed briefs losing provenance | Every brief records source turn IDs; traceable back to original records |
| Compression producing synthesized narrative | Briefs preserve verbatim context excerpts; no LLM-generated summary |
| Server crash on malformed input | Input validation on role enum + required fields; `compress_unprocessed` is exception-safe |

### Out of Scope

The following threats are **not** addressed by Omega Stenographer MCP:

- **Compromised host or operating system** — if the process environment is controlled by an adversary, no application-layer protection is sufficient
- **Unauthorized database access** — the database is unencrypted SQLite; OS-level access controls are the operator's responsibility
- **Malicious administrator** — an operator with filesystem access can modify or delete the data directory directly
- **Supply-chain compromise of `mcp` or Python itself** — dependency integrity verification is the operator's responsibility
- **Network-level attacks** — SSE mode exposes an HTTP endpoint; TLS termination and network access control are the operator's responsibility
- **Decision extraction accuracy** — regex-based extraction is heuristic; false negatives and false positives are expected

### Trust Boundaries

```
  [ MCP Client / AI Agent ]
           │
           │  Trust: MCP client provides truthful turn content.
           │         Stenographer does not verify accuracy.
           ▼
  [ Omega Stenographer MCP Server ]  ← Observation boundary
           │
           │  Trust: Local filesystem is operator-controlled.
           │         No external services are contacted.
           ▼
  [ ~/.omega-stenographer/steno.db ]
```

Stenographer operates at the observation boundary — it records what it sees. It does not enforce policy, verify claims, or approve actions. If a turn contains false information, Stenographer will faithfully record, index, and compress that false information.

---

## Roadmap

| Milestone | Status | Description |
|-----------|--------|-------------|
| v1.0 — Core observation stack | Released | Turn ingestion, decision/blocker extraction, FTS5 search, compression, milestones |
| v1.1 — Enhanced extraction | Planned | LLM-assisted decision extraction for higher recall; configurable extraction patterns |
| v1.2 — Embedding upgrades | Planned | Optional `fastembed` ONNX or `sentence-transformers` for higher-quality similarity search |
| v1.3 — Multi-session merge | Planned | Cross-session brief merging for long-running projects across multiple sessions |
| v2.0 — Omega Brain bridge | Planned | Native Stenographer → Omega Brain ingestion bridge; briefs auto-ingested as RAG fragments |

Community contributions are welcome. See [`CONTRIBUTING.md`](.github/CONTRIBUTING.md) for invariants that must not be broken.

---

## Omega Universe

Omega Stenographer MCP is the passive observation layer of the **VERITAS & Sovereign Ecosystem**. The following repositories form the broader Omega Universe:

| Repository | Role |
|------------|------|
| [VrtxOmega/omega-stenographer-mcp](https://github.com/VrtxOmega/omega-stenographer-mcp) | **This repo** — Passive session observer: turn ingestion, decision extraction, context compression |
| [VrtxOmega/omega-brain-mcp](https://github.com/VrtxOmega/omega-brain-mcp) | Governance control plane: Cortex gate, VERITAS pipeline, S.E.A.L. ledger |
| [VrtxOmega/sswp-mcp](https://github.com/VrtxOmega/sswp-mcp) | Deterministic build attestation protocol |
| [VrtxOmega/veritas-vault](https://github.com/VrtxOmega/veritas-vault) | Retention substrate — deterministic storage under VERITAS constraints |
| [VrtxOmega/Aegis](https://github.com/VrtxOmega/Aegis) | Policy enforcement engine — sovereign access control layer |
| [VrtxOmega/SovereignMedia](https://github.com/VrtxOmega/SovereignMedia) | Sovereign desktop media application |
| [VrtxOmega/Ollama-Omega](https://github.com/VrtxOmega/Ollama-Omega) | Local LLM bridge — Ollama integration with Omega governance layer |

---

> 📖 Read the master narrative: [Why Sovereign AI?](https://github.com/VrtxOmega/veritas-portfolio/blob/main/content/SOVEREIGN_AI.md)

## 🌐 VERITAS Omega Ecosystem

This project is part of the [VERITAS Omega Universe](https://github.com/VrtxOmega/veritas-portfolio) — a sovereign AI infrastructure stack.

- [VERITAS-Omega-CODE](https://github.com/VrtxOmega/VERITAS-Omega-CODE) — Deterministic verification spec (10-gate pipeline)
- [Gravity-Omega](https://github.com/VrtxOmega/Gravity-Omega) — Desktop AI operator platform
- [Omega-Brain-MCP](https://github.com/VrtxOmega/omega-brain-mcp) — Governance-first MCP server
- [Ollama-Omega](https://github.com/VrtxOmega/Ollama-Omega) — Ollama MCP bridge for any IDE
- [OmegaWallet](https://github.com/VrtxOmega/OmegaWallet) — Desktop Ethereum wallet (renderer-cannot-sign)
- [veritas-vault](https://github.com/VrtxOmega/veritas-vault) — Local-first AI knowledge engine
- [sovereign-arcade](https://github.com/VrtxOmega/sovereign-arcade) — 8-game arcade with VERITAS design system
- [SSWP](https://github.com/VrtxOmega/sswp-mcp) — Deterministic build attestation protocol

## License

MIT — see [`LICENSE`](LICENSE) for full text.

---

<div align="center">
  <sub>Built by <a href="https://github.com/VrtxOmega">RJ Lopez</a> · <strong>VERITAS Omega Framework</strong></sub><br/>
  <sub>
    <a href="https://github.com/VrtxOmega/omega-stenographer-mcp/issues">Report Issue</a> ·
    <a href="CHANGELOG.md">Changelog</a> ·
    <a href="INTEGRATIONS.md">Integrations</a> ·
    <a href="SECURITY.md">Security Policy</a> ·
    <a href="https://glama.ai/mcp/servers/VrtxOmega/omega-stenographer-mcp">Glama MCP Registry</a>
  </sub>
</div>
