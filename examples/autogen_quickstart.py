"""AutoGen Quickstart — Omega Stenographer MCP integration.

pip install autogen-agentchat autogen-ext[mcp]
"""

import asyncio
from autogen_ext.tools.mcp import StdioServerParams, mcp_server_tools
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken

async def main():
    server_params = StdioServerParams(
        command="python",
        args=["omega_stenographer_mcp_standalone.py"]
    )

    tools = await mcp_server_tools(server_params)
    print(f"Loaded {len(tools)} tools: {[t.name for t in tools]}")

    # Create an agent with stenographer tools
    agent = AssistantAgent(
        name="Debugger",
        system_message="You document every debugging decision using stenographer tools.",
        tools=tools,
    )

    response = await agent.on_messages(
        [TextMessage(content="The authentication module is failing. Investigate and document.", source="user")],
        cancellation_token=CancellationToken(),
    )
    print(response.chat_message.content)

if __name__ == "__main__":
    asyncio.run(main())
