"""Unit tests for the Agent Template Marketplace."""

from __future__ import annotations

from pathlib import Path

from carbonclaw.config.templates import AgentTemplate, TemplateManager


def test_save_and_load_template(tmp_path: Path) -> None:
    manager = TemplateManager(path=tmp_path)

    template = AgentTemplate(
        name="test-swarm",
        description="A swarm for testing templates.",
        default_provider="ollama",
        default_model="llama3",
        routing_strategy="latency",
        tools=["file_read", "file_write"],
        system_prompt="Test system prompt",
    )

    # Save the template
    path = manager.save_template(template)
    assert path.exists()
    assert path.name == "test-swarm.json"

    # Load the template
    loaded = manager.load_template("test-swarm")
    assert loaded is not None
    assert loaded.name == "test-swarm"
    assert loaded.description == "A swarm for testing templates."
    assert loaded.default_provider == "ollama"
    assert loaded.default_model == "llama3"
    assert loaded.routing_strategy == "latency"
    assert loaded.tools == ["file_read", "file_write"]
    assert loaded.system_prompt == "Test system prompt"


def test_list_templates(tmp_path: Path) -> None:
    manager = TemplateManager(path=tmp_path)

    t1 = AgentTemplate(name="swarm-a", description="A")
    t2 = AgentTemplate(name="swarm-b", description="B")

    manager.save_template(t1)
    manager.save_template(t2)

    templates = manager.list_templates()
    assert len(templates) == 2
    names = {t.name for t in templates}
    assert names == {"swarm-a", "swarm-b"}


def test_mock_pull(tmp_path: Path) -> None:
    manager = TemplateManager(path=tmp_path)

    # Pull sustainability-swarm
    t = manager.mock_pull("sustainability-swarm")
    assert t is not None
    assert t.name == "sustainability-swarm"
    assert t.routing_strategy == "sustainability"

    # Pull non-existent swarm
    t_unknown = manager.mock_pull("unknown-swarm")
    assert t_unknown is None
