"""Tools and agents for self-evolution and rule learning."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

import structlog

from carbonclaw.core.base import BaseAgent, BaseTool
from carbonclaw.agents.base import ReactAgent
from carbonclaw.core.models import Message, ToolResult

if TYPE_CHECKING:
    from carbonclaw.core.base import BaseMemory, BaseProvider

logger = structlog.get_logger()


class LearnRuleTool(BaseTool):
    """Tool for agents to learn and persist new rules/preferences."""

    name = "learn_rule"
    description = (
        "Permanently store a new rule, preference, or 'lesson learned' based on user feedback or self-reflection. "
        "Use this to evolve your behavior and avoid repeating mistakes."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "rule": {"type": "string", "description": "The concise rule or lesson to learn."},
            "context": {"type": "string", "description": "Short explanation of why this rule was learned."},
        },
        "required": ["rule"],
    }

    def __init__(self, memory: BaseMemory) -> None:
        self.memory = memory

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        rule = arguments.get("rule", "")
        context = arguments.get("context", "Learned from interaction.")
        
        await self.memory.store(
            content=rule,
            namespace="learned_rules",
            metadata={"source": "agent_learning", "reason": context},
        )
        
        logger.info("agent.learned_rule", rule=rule, reason=context)
        return ToolResult(
            tool_call_id="",
            name=self.name,
            content=f"Successfully learned rule: {rule}",
        )


class LearnStrategyTool(BaseTool):
    """Tool for agents to learn and persist strategic routing rules."""
    
    name = "learn_strategy"
    description = (
        "Permanently store a strategic routing adjustment based on performance analysis. "
        "Use this if a specific model or provider consistently fails at a certain task type."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "target_task_type": {"type": "string", "description": "The task type to adjust (e.g. coding, research, general)."},
            "condition": {"type": "string", "description": "Condition when this applies (e.g. complexity > 0.8)."},
            "action": {"type": "string", "description": "The routing action (e.g. prefer_cloud, force_openai)."},
            "reason": {"type": "string", "description": "Why this adjustment is needed."},
        },
        "required": ["target_task_type", "action", "reason"],
    }

    def __init__(self, memory: BaseMemory) -> None:
        self.memory = memory

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        await self.memory.store(
            content=json.dumps(arguments),
            namespace="strategic_adjustments",
            metadata={"source": "evolution_agent"},
        )
        logger.info("agent.learned_strategy", target=arguments.get("target_task_type"), action=arguments.get("action"))
        return ToolResult(tool_call_id="", name=self.name, content="Strategy learned.")


class EvolutionAgent(ReactAgent):
    """Agent that reflects on past interactions to extract lessons and evolve."""

    name = "evolution"
    description = "Reflects on task history to improve system behavior."

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool],
        memory: BaseMemory,
        model: str | None = None,
    ) -> None:
        super().__init__(
            provider=provider,
            tools=tools,
            memory=memory,
            system_prompt=(
                "You are a Self-Evolution Agent. Your goal is to analyze agent interactions and extract 'lessons learned'. "
                "1. Analyze the provided message history for inefficiencies, errors, or user corrections. "
                "2. Formulate concise, actionable rules to prevent these issues in the future. "
                "3. Use the 'learn_rule' tool to save behavioral rules. "
                "4. Use the 'learn_strategy' tool to adjust routing (e.g., if a local model fails complex tasks, tell the router to prefer cloud models for that task type). "
                "Be critical but constructive. Only learn high-value rules that improve future performance."
            ),
            model=model,
            max_iterations=5,
        )
        # Register both learning tools
        self.tools.append(LearnRuleTool(memory))
        self.tools.append(LearnStrategyTool(memory))

    async def reflect(self, history: list[Message]) -> None:
        """Analyze a conversation history and extract lessons."""
        history_text = "\n".join([f"{m.role}: {m.content}" for m in history if m.content])
        task = (
            f"Analyze the following interaction and learn any rules that would have improved performance:\n\n"
            f"{history_text}\n\n"
            "If no clear lessons are found, you don't need to do anything."
        )
        await self.run(task)
