import pytest
from unittest.mock import MagicMock
from carbonclaw.core.router import SmartRouter, RoutingStrategy
from carbonclaw.config.settings import CarbonClawConfig

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
