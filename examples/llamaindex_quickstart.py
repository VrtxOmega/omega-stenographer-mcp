"""LlamaIndex Quickstart — Omega Stenographer MCP integration.

pip install llama-index llama-index-tools-mcp
"""

from llama_index.tools.mcp import MCPToolSpec

tool_spec = MCPToolSpec(
    command="python",
    args=["omega_stenographer_mcp_standalone.py"]
)

# All 5 stenographer tools available as LlamaIndex tools
tools = tool_spec.to_tool_list()
print(f"Loaded {len(tools)} tools:")
for t in tools:
    print(f"  - {t.metadata.name}: {t.metadata.description}")

# Use with a LlamaIndex agent:
# from llama_index.core.agent import ReActAgent
# from llama_index.llms.openai import OpenAI
#
# agent = ReActAgent.from_tools(tools, llm=OpenAI(), verbose=True)
# agent.chat("Debug the authentication module and document every step.")
