"""Unit tests for FastAPI web dashboard, ESG tracking, and extension endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from carbonclaw.telemetry.carbon import CarbonRecord, CarbonStore
from carbonclaw.web.app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_esg_dashboard(client: TestClient) -> None:
    response = client.get("/esg/dashboard")
    assert response.status_code == 200
    assert "CarbonClaw" in response.text
    assert "ESG & Sustainability Dashboard" in response.text


def test_api_esg_stats(client: TestClient, tmp_path) -> None:
    # Set up a mock carbon store to populate records
    store_file = tmp_path / "emissions_test.jsonl"
    store = CarbonStore(path=store_file)
    store.record(CarbonRecord(project_name="proj-alpha", emissions=0.005))
    store.record(CarbonRecord(project_name="proj-beta", emissions=0.002))

    # We will patch the CarbonStore init to use our temp file
    import unittest.mock
    original_init = CarbonStore.__init__
    def mock_init(self, path=None):
        original_init(self, path=store_file)

    with unittest.mock.patch.object(CarbonStore, "__init__", mock_init):
        response = client.get("/api/esg/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_emissions_grams" in data
        assert data["total_emissions_grams"] == pytest.approx(7.0, 0.001)
        assert data["by_project"]["proj-alpha"] == pytest.approx(5.0, 0.001)
        assert data["by_project"]["proj-beta"] == pytest.approx(2.0, 0.001)
        assert "leaderboard" in data
        assert "offsets" in data


def test_api_extension_badge(client: TestClient) -> None:
    # Clean grid or fossil grid simulation
    payload = {"code": "def hello_world():\n    print('Hello world!')", "filename": "test.py"}
    response = client.post("/api/extension/badge", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "badge" in data
    assert "emissions_estimate_grams" in data
    assert "grid_intensity" in data
    assert "tokens" in data


def test_api_extension_approve_safe(client: TestClient) -> None:
    payload = {
        "action": "shell",
        "arguments": {"command": "pytest --version"}
    }
    response = client.post("/api/extension/approve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is True
    assert "impact" in data


def test_api_extension_approve_dangerous(client: TestClient) -> None:
    payload = {
        "action": "shell",
        "arguments": {"command": "rm -rf /Users/chakkritt/Documents/proj"}
    }
    response = client.post("/api/extension/approve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["approved"] is False
    assert "Action rejected" in data["message"]


def test_github_webhook_no_action(client: TestClient) -> None:
    payload = {
        "action": "completed",
        "workflow_run": {"conclusion": "success", "name": "CI"}
    }
    response = client.post("/webhooks/github", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["triggered"] is False
    assert "no action required" in data["message"]


def test_github_webhook_trigger_healer(client: TestClient) -> None:
    payload = {
        "action": "completed",
        "workflow_run": {"conclusion": "failure", "name": "CI"}
    }
    # Mock supervisor agent so we don't make real LLM / Provider calls
    import unittest.mock
    mock_supervisor = unittest.mock.AsyncMock()
    with unittest.mock.patch(
        "carbonclaw.agents.supervisor.SupervisorAgent.create_default",
        return_value=mock_supervisor,
    ):
        response = client.post("/webhooks/github", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["triggered"] is True
        assert "Failing workflow run detected" in data["message"]
