# Integration Reference

## MCP Protocol

Omega Stenographer MCP implements the Model Context Protocol (MCP) specification. All communication occurs via JSON-RPC 2.0 over stdio or SSE transport.

### Server Info

```
Name: omega-stenographer
Version: 1.0.0
```

### Capabilities

- **Tools** — 5 tools for turn ingestion, brief construction, compaction, milestone marking, and history search
- **Resources** — 2 resources for running notes and compaction guard

### Transport Modes

**stdio (default):**
- Reads JSON-RPC 2.0 messages from stdin
- Writes responses to stdout
- Standard MCP transport — most clients use this

**SSE (HTTP streaming):**
- `GET /sse` — Server-Sent Events endpoint for streaming responses
- `POST /messages` — Endpoint for sending tool calls
- Port configurable via `--port` flag

### Tool Schema

All tools return `TextContent` with structured text (JSON or markdown).

## Configuration Reference

### Required Permissions

The server needs:
- Read/write access to `~/.omega-stenographer/` (or `OMEGA_STENOGRAPHER_DIR`)
- Python 3.11+ with `mcp` package installed

### Port Mapping

| Service | Default Port | Configurable |
|---------|-------------|--------------|
| stdio transport | N/A | N/A |
| SSE transport | 8056 | `--port` flag |

## Client Integration

See [`INTEGRATIONS.md`](../INTEGRATIONS.md) for framework-specific examples (LangChain, CrewAI, AutoGen, LlamaIndex).
