"""CrewAI Quickstart — Omega Stenographer MCP integration.

pip install crewai crewai-tools
"""

from crewai import Agent, Task, Crew
from crewai.tools import MCPTool

steno_tool = MCPTool(
    server_command=["python", "omega_stenographer_mcp_standalone.py"],
    tool_name="stenographer_ingest_exchange"
)

# Agent that documents every debugging step
debugger = Agent(
    role="Senior Debugger",
    goal="Find and fix bugs while documenting every decision",
    backstory="You are a meticulous debugger who records every insight.",
    tools=[steno_tool],
    verbose=True
)

task = Task(
    description="The authentication module is failing. Investigate and fix the root cause. Record every decision you make.",
    expected_output="A fixed authentication module with documented debugging steps.",
    agent=debugger
)

crew = Crew(
    agents=[debugger],
    tasks=[task],
    verbose=True
)

result = crew.kickoff()
print(result)
