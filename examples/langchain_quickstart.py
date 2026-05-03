"""LangChain Quickstart — Omega Stenographer MCP integration.

pip install langchain langchain-mcp-adapters
"""

import asyncio
import json

async def main():
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({
        "stenographer": {
            "command": "python",
            "args": ["omega_stenographer_mcp_standalone.py"],
            "transport": "stdio",
        }
    })

    # Ingest turns
    await client.call_tool("stenographer_ingest_exchange", {
        "role": "user",
        "content": "Debug the authentication module — users can't log in.",
        "session_id": "langchain-demo"
    })

    await client.call_tool("stenographer_ingest_exchange", {
        "role": "assistant",
        "content": "Found the issue: JWT secret key was rotated without updating the validation endpoint. Fix applied to auth.py line 42.",
        "session_id": "langchain-demo"
    })

    # Get running notes
    notes = await client.call_tool("stenographer_get_brief", {})
    print("Running Notes:")
    print(notes)

    # Search history
    results = await client.call_tool("stenographer_query_history", {"query": "JWT OR auth"})
    print("\nSearch Results:")
    print(results)

if __name__ == "__main__":
    asyncio.run(main())
