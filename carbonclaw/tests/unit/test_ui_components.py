import pytest
from unittest.mock import patch, MagicMock
from carbonclaw.ui.status_bar import render_status_bar, get_git_branch, get_short_path

def test_get_short_path():
    with patch("os.getcwd", return_value="/home/user/projects/sena"):
        with patch("pathlib.Path.home", return_value="/home/user"):
            assert get_short_path() == "~/projects/sena"

def test_get_git_branch():
    with patch("subprocess.check_output", return_value="feature-testing\n"):
        assert get_git_branch() == "feature-testing"
    
    with patch("subprocess.check_output", side_effect=Exception()):
        assert get_git_branch() == "n/a"

def test_render_status_bar():
    # Test that it returns a Rich Panel and contains expected info
    from carbonclaw.core.models import Message
    
    with patch("carbonclaw.telemetry.carbon.CarbonStore.total_emissions", return_value=0.5):
        panel = render_status_bar(
            model="gpt-4o",
            provider="openai",
            messages=[Message(role="user", content="hi")]
        )
        
        from rich.console import Console
        console = Console(width=100, force_terminal=True)
        with console.capture() as capture:
            console.print(panel)
        output = capture.get()
        
        assert "openai/gpt-4o" in output
        assert "0.5000" in output
