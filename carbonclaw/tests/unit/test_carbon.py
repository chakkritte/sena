import pytest
import json
from pathlib import Path
from carbonclaw.telemetry.carbon import CarbonStore, CarbonRecord, CarbonTracker, get_greener_recommendation

def test_carbon_store_persistence(tmp_path):
    store_path = tmp_path / "emissions.jsonl"
    store = CarbonStore(path=store_path)
    
    record = CarbonRecord(project_name="test", emissions=0.1)
    store.record(record)
    
    records = store.records()
    assert len(records) == 1
    assert records[0].emissions == 0.1
    assert store.total_emissions() == 0.1

def test_carbon_tracker_lifecycle(tmp_path):
    store_path = tmp_path / "emissions.jsonl"
    
    with patch("carbonclaw.telemetry.carbon.EmissionsTracker", create=True) as MockTracker:
        tracker = CarbonTracker(project_name="test-life", enabled=True)
        tracker.enabled = True
        tracker._store = CarbonStore(path=store_path)
        
        # Configure the mock instance
        mock_instance = MockTracker.return_value
        mock_instance.stop.return_value = 0.05
        
        tracker.start()
        emissions = tracker.stop()
        
        assert emissions == 0.05
        assert tracker.last_emissions == 0.05
        assert tracker._store.total_emissions() == 0.05

from unittest.mock import MagicMock, patch

def test_green_recommendation():
    # Simple task
    rec = get_greener_recommendation("hello", 0.1)
    assert "local LLM" in rec
    
    # Complex task
    rec = get_greener_recommendation("complex architect refactor", 0.8)
    assert rec is None
