"""Tool for delegating tasks to specialized sub-agents."""

from __future__ import annotations

from typing import Any, Optional

from sena.core.base import BaseTool, ToolResult
from sena.core.models import Message


class InvokeAgentTool(BaseTool):
    """Delegates a task to a specialized sub-agent."""

    name = "invoke_agent"
    description = (
        "Invokes a specialized sub-agent to perform a specific task or investigation. "
        "Available agents: codebase_investigator, planner, coding, review, qa, docs, generalist. "
        "Use this to delegate complex or specialized work to keep your own context clean."
    )
    parameters = {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Name of the sub-agent to invoke.",
                "enum": ["codebase_investigator", "planner", "coding", "review", "qa", "docs", "generalist"],
            },
            "prompt": {
                "type": "string",
                "description": "The complete, detailed query to send the sub-agent.",
            },
        },
        "required": ["agent_name", "prompt"],
    }

    def __init__(
        self,
        provider: Any,
        memory: Any,
        tools: list[BaseTool],
        model: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.provider = provider
        self.memory = memory
        self.tools = tools
        self.model = model

    async def execute(self, **kwargs: Any) -> ToolResult:
        agent_name = kwargs["agent_name"]
        prompt = kwargs["prompt"]

        from sena.agents.base import ReactAgent
        from sena.agents.coding import CodingAgent
        from sena.agents.docs import DocsAgent
        from sena.agents.planner import PlannerAgent
        from sena.agents.qa import QAAgent
        from sena.agents.review import ReviewAgent

        agent: Optional[ReactAgent] = None
        
        if agent_name == "planner":
            agent = PlannerAgent(self.provider, self.tools, self.memory, self.model)
        elif agent_name == "coding":
            agent = CodingAgent(self.provider, self.tools, self.memory, self.model)
        elif agent_name == "review":
            agent = ReviewAgent(self.provider, self.tools, self.memory, self.model)
        elif agent_name == "qa":
            agent = QAAgent(self.provider, self.tools, self.memory, self.model)
        elif agent_name == "docs":
            agent = DocsAgent(self.provider, self.tools, self.memory, self.model)
        elif agent_name == "codebase_investigator":
            # Codebase investigator is a coding agent with more specific instructions
            agent = CodingAgent(self.provider, self.tools, self.memory, self.model)
            agent.system_prompt += (
                "\n\nYou are a Codebase Investigator. Your goal is to map the architecture, "
                "understand system-wide dependencies, and identify root causes of complex bugs. "
                "Use grep and search tools extensively."
            )
        elif agent_name == "generalist":
            agent = ReactAgent(self.provider, self.tools, self.memory, self.model)
        else:
            agent = None

        if agent:
            result = await agent.run(prompt)
            return ToolResult(tool_call_id="", name=self.name, content=result)
        
        return ToolResult(tool_call_id="", name=self.name, content=f"Error: Agent '{agent_name}' not found.", is_error=True)
