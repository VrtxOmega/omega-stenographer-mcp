# Integrations

Omega Stenographer MCP integrates with any MCP-compatible client using standard JSON-RPC 2.0 over stdio or SSE.

## Integration Patterns

### LangChain

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "stenographer": {
        "command": "python",
        "args": ["/path/to/omega_stenographer_mcp_standalone.py"],
        "transport": "stdio",
    }
})

# Ingest a turn
await client.call_tool("stenographer_ingest_exchange", {
    "role": "user",
    "content": "Fix the authentication bug",
    "session_id": "langchain-session"
})

# Get running notes
notes = await client.call_tool("stenographer_get_brief", {})
```

### CrewAI

```python
from crewai import Agent, Task, Crew
from crewai.tools import MCPTool

steno_tool = MCPTool(
    server_command=["python", "/path/to/omega_stenographer_mcp_standalone.py"],
    tool_name="stenographer_ingest_exchange"
)

agent = Agent(
    role="Debugger",
    goal="Find and fix bugs",
    tools=[steno_tool],
    backstory="You capture every debugging decision."
)
```

### AutoGen

```python
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools

server_params = StdioServerParams(
    command="python",
    args=["/path/to/omega_stenographer_mcp_standalone.py"]
)

tools = await mcp_server_tools(server_params)
```

### LlamaIndex

```python
from llama_index.tools.mcp import MCPToolSpec

tool_spec = MCPToolSpec(
    command="python",
    args=["/path/to/omega_stenographer_mcp_standalone.py"]
)

tools = tool_spec.to_tool_list()
```

## SSE Mode Integration

```bash
python omega_stenographer_mcp_standalone.py --sse --port 8056
```

Connect to `http://localhost:8056/sse` for event stream, POST to `http://localhost:8056/messages` for tool calls.

## See examples/ directory for full runnable quickstarts.
