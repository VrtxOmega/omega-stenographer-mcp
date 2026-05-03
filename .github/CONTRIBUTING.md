# Contributing to Omega Stenographer MCP

## How to Add a New Tool

1. **Define the tool** in `list_tools()`:
   ```python
   Tool(name="stenographer_my_tool",
        description="What it does.",
        inputSchema={"type": "object", "properties": {...}, "required": [...]})
   ```

2. **Implement the dispatch** in `call_tool()`:
   ```python
   elif name == "stenographer_my_tool":
       result = _my_tool_logic(arguments.get("param", ""))
       return [TextContent(type="text", text=json.dumps(result, indent=2))]
   ```

3. **Add a test** in `tests/` covering expected output + edge cases + database state.

4. **Open a PR** — CI runs pytest on 3.11 + 3.12 automatically.

## Invariants That Must Not Break

| Invariant | Test file | What it guards |
|---|---|---|
| Compression preserves source turn IDs | `test_compression.py` | Brief provenance traceability |
| FTS5 index populated on ingest | `test_ingest.py` | Search completeness |
| `STENO_TURN_LIMIT` threshold honored | `test_compression.py` | Compression timing |
| Tier assignment logic (A vs B) | `test_compression.py` | Decision signal preservation |

Do not change `STENO_TURN_LIMIT` (8) or `STENO_TOP_K` (5) without filing an issue first.

## Dev Setup

```bash
git clone https://github.com/VrtxOmega/omega-stenographer-mcp
cd omega-stenographer-mcp
pip install mcp pytest pytest-asyncio
pytest tests/ -v
```
