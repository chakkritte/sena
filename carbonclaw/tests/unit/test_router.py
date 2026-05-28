
import pytest

from carbonclaw.config.settings import CarbonClawConfig
from carbonclaw.core.router import RoutingStrategy, SmartRouter


@pytest.fixture
def config():
    return CarbonClawConfig(default_provider="openai", default_model="gpt-4o-mini")

@pytest.fixture
def router(config):
    return SmartRouter(config)

def test_calculate_complexity(router):
    # Simple task
    assert router.calculate_complexity("hello") < 0.5

    # Long task
    long_task = "x" * 2500
    assert router.calculate_complexity(long_task) > 0.5

    # Complex keyword
    assert router.calculate_complexity("Refactor this architect") > router.calculate_complexity("Say hi")

def test_routing_sustainability(router):
    # Simple task should go to ollama
    p, m, t = router.route("Hello world", strategy=RoutingStrategy.SUSTAINABILITY)
    assert p == "ollama"

    # Complex task should go to default cloud provider
    p, m, t = router.route("Refactor the entire architectural pattern of this deep system", strategy=RoutingStrategy.SUSTAINABILITY)
    assert p == "openai"

def test_metrics_learning(router):
    # Simulate some requests
    router.update_metrics("openai", 500, True)
    assert router.stats["openai"].avg_latency_ms == 500
    assert router.stats["openai"].request_count == 1

    router.update_metrics("openai", 1000, True)
    assert router.stats["openai"].avg_latency_ms < 1000
    assert router.stats["openai"].avg_latency_ms > 500

def test_unhealthy_provider(router):
    # Simulate errors
    for _ in range(5):
        router.update_metrics("openai", 100, False)

    assert router.stats["openai"].is_healthy is False

    # Routing should avoid openai now
    p, m, t = router.route("Complex task", strategy=RoutingStrategy.BALANCED)
    assert p != "openai"


def test_carbon_budget_parsing() -> None:
    """Test parsing strings of carbon units (mg, g, kg) to float values in grams."""
    from carbonclaw.telemetry.carbon import parse_carbon_budget

    assert parse_carbon_budget("5g") == 5.0
    assert parse_carbon_budget("500mg") == 0.5
    assert parse_carbon_budget("1kg") == 1000.0
    assert parse_carbon_budget(12.5) == 12.5
    assert parse_carbon_budget(None) is None
    assert parse_carbon_budget("invalid") is None


def test_carbon_budgeted_routing(router) -> None:
    """Test routing adjustments when carbon budget is low or exhausted."""
    from carbonclaw.telemetry.carbon import CarbonRecord, CarbonStore

    store = CarbonStore()
    store.clear()

    # Set a tiny budget of 1g
    router.config.carbon_budget = 1.0

    # 1. Budget under limit: complex task normally goes to cloud (openai)
    p, m, t = router.route("Refactor architectural pattern", strategy=RoutingStrategy.SUSTAINABILITY)
    assert p == "openai"

    # 2. Add an emission record to exhaust the budget (1.2g emitted)
    store.record(CarbonRecord(project_name="test", emissions=0.0012)) # 0.0012 kg = 1.2g

    # Complex task should now be forced to local Ollama due to budget exhaustion
    p, m, t = router.route("Refactor architectural pattern", strategy=RoutingStrategy.SUSTAINABILITY)
    assert p == "ollama"

    store.clear()

