import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from carbonclaw.agents.healer import HealerAgent
from carbonclaw.core.models import ToolResult

@pytest.mark.asyncio
async def test_healer_initialization() -> None:
    supervisor = MagicMock()
    healer = HealerAgent(supervisor, test_command="echo 'success'")
    assert healer.test_command == "echo 'success'"
    assert healer.supervisor == supervisor

@pytest.mark.asyncio
async def test_healer_loop_immediate_success() -> None:
    supervisor = MagicMock()
    healer = HealerAgent(supervisor, test_command="echo 'success'")
    
    mock_shell_instance = AsyncMock()
    mock_shell_instance.execute.return_value = ToolResult(
        tool_call_id="1",
        name="shell",
        content="All tests passed!",
        is_error=False
    )
    
    with patch("carbonclaw.agents.healer.ShellTool", return_value=mock_shell_instance):
        res = await healer.heal_loop(max_attempts=3)
        assert res is True
        assert mock_shell_instance.execute.call_count == 1
        supervisor.swarm_debate.assert_not_called()

@pytest.mark.asyncio
async def test_healer_loop_fix_success() -> None:
    supervisor = MagicMock()
    supervisor.swarm_debate = AsyncMock(return_value="Fixed.")
    healer = HealerAgent(supervisor, test_command="pytest")
    
    mock_shell_instance = AsyncMock()
    mock_shell_instance.execute.side_effect = [
        ToolResult(tool_call_id="1", name="shell", content="AssertionError", is_error=True),
        ToolResult(tool_call_id="2", name="shell", content="Success!", is_error=False)
    ]
    
    with patch("carbonclaw.agents.healer.ShellTool", return_value=mock_shell_instance):
        res = await healer.heal_loop(max_attempts=3)
        assert res is True
        assert mock_shell_instance.execute.call_count == 2
        supervisor.swarm_debate.assert_called_once()
        assert "AssertionError" in supervisor.swarm_debate.call_args[0][0]

@pytest.mark.asyncio
async def test_healer_loop_all_failed() -> None:
    supervisor = MagicMock()
    supervisor.swarm_debate = AsyncMock(return_value="Fixed Attempt.")
    healer = HealerAgent(supervisor, test_command="pytest")
    
    mock_shell_instance = AsyncMock()
    mock_shell_instance.execute.return_value = ToolResult(
        tool_call_id="x",
        name="shell",
        content="Failure persists",
        is_error=True
    )
    
    with patch("carbonclaw.agents.healer.ShellTool", return_value=mock_shell_instance):
        res = await healer.heal_loop(max_attempts=3)
        assert res is False
        assert mock_shell_instance.execute.call_count == 3
        assert supervisor.swarm_debate.call_count == 3

