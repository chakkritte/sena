import pytest
from unittest.mock import MagicMock, patch
from carbonclaw.agents.supervisor import SupervisorAgent
from carbonclaw.config.settings import CarbonClawConfig

@pytest.mark.asyncio
async def test_supervisor_agent_overrides():
    config = CarbonClawConfig(
        agent_overrides={
            "planner": "custom-planner-model",
            "coding": "auto"
        }
    )
    
    provider = MagicMock()
    memory = MagicMock()
    
    with patch("carbonclaw.config.settings.CarbonClawConfig", return_value=config):
        supervisor = SupervisorAgent(provider, [], memory)
        
        assert supervisor._agents["planner"].model == "custom-planner-model"
        # coding is auto, should fall back to supervisor default (None/provided)
        assert supervisor._agents["coding"].model is None or supervisor._agents["coding"].model == "auto"

@pytest.mark.asyncio
async def test_supervisor_delegation():
    from unittest.mock import AsyncMock
    provider = MagicMock()
    memory = MagicMock()
    memory.store = AsyncMock() # Mock store as async
    
    supervisor = SupervisorAgent(provider, [], memory)
    
    # Mock agent run as an async function
    supervisor._agents["coding"].run = AsyncMock(return_value="done")
    
    result = await supervisor.delegate("coding", "fix bug")
    assert result == "done"
    supervisor._agents["coding"].run.assert_called_once()
    memory.store.assert_called_once()
