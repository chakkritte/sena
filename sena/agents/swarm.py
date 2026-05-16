"""Multi-agent swarm / debate mode for consensus-based problem solving."""

from __future__ import annotations

from typing import Any

from sena.agents.base import ReactAgent
from sena.core.events import Event, EventBus
from sena.core.models import Message


class SwarmAgent:
    """Coordinate multiple agents to debate and reach consensus.

    Usage::

        swarm = SwarmAgent([agent_a, agent_b, agent_c], rounds=2)
        result = await swarm.run("Should we use Redis or Postgres for caching?")
    """

    def __init__(
        self,
        agents: list[ReactAgent],
        rounds: int = 2,
        event_bus: EventBus | None = None,
    ) -> None:
        """Initialize the swarm.

        Args:
            agents: List of ReactAgent instances with different specialisations.
            rounds: Number of debate rounds before final consensus.
            event_bus: Optional shared event bus for cross-agent communication.
        """
        self.agents = agents
        self.rounds = rounds
        self.event_bus = event_bus or EventBus()

    async def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        """Run the swarm debate and return the consensus response."""
        # Initial responses from all agents
        responses: list[str] = []
        for i, agent in enumerate(self.agents):
            response = await agent.run(task, context)
            responses.append(response)
            await self.event_bus.publish(Event(
                type="swarm.response",
                payload={"agent": i, "response": response},
            ))

        # Debate rounds
        for round_num in range(self.rounds):
            new_responses: list[str] = []
            for i, agent in enumerate(self.agents):
                other_responses = [
                    r for j, r in enumerate(responses) if j != i
                ]
                debate_prompt = (
                    f"Original task: {task}\n\n"
                    f"Other agents responded:\n"
                    + "\n---\n".join(
                        f"Agent {j}: {r}" for j, r in enumerate(other_responses)
                    )
                    + "\n\nPlease refine your answer considering the above perspectives."
                )
                refined = await agent.run(debate_prompt, context)
                new_responses.append(refined)
                await self.event_bus.publish(Event(
                    type="swarm.refinement",
                    payload={"round": round_num + 1, "agent": i, "response": refined},
                ))
            responses = new_responses

        # Final consensus synthesis by the first agent
        consensus_prompt = (
            f"Original task: {task}\n\n"
            f"After {self.rounds} rounds of debate, the agents converged on:\n"
            + "\n---\n".join(f"Agent {i}: {r}" for i, r in enumerate(responses))
            + "\n\nSynthesise a final consensus answer that best incorporates all views."
        )
        consensus = await self.agents[0].run(consensus_prompt, context)
        await self.event_bus.publish(Event(
            type="swarm.consensus",
            payload={"consensus": consensus},
        ))
        return consensus
