"""Unit tests for the Carbon-Aware Scheduling Engine."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from carbonclaw.cli.slash import Message, SlashRegistry
from carbonclaw.telemetry.grid import (
    estimate_carbon_savings,
    get_grid_intensity,
    get_optimal_run_time,
)
from carbonclaw.telemetry.scheduler import SchedulerStore


def test_grid_intensity_simulation() -> None:
    """Test simulated carbon intensities across different hours."""
    # Peak evening hour (Highest Intensity)
    intensity_19 = get_grid_intensity(19)
    assert intensity_19 == 450.0

    # Night wind peak hour (Lowest Intensity)
    intensity_3 = get_grid_intensity(3)
    assert intensity_3 == 130.0

    # General blend/mid-afternoon hours
    intensity_12 = get_grid_intensity(12)
    assert intensity_12 == 175.0


def test_optimal_run_time_calculation() -> None:
    """Test detection of greenest execution window within next 12 hours."""
    # If starting at peak load (19:00), optimal time should be shifted to clean hours
    start_time = datetime.datetime(2026, 5, 28, 19, 0, 0)
    opt_time, cur_int, opt_int = get_optimal_run_time(start_time)

    assert opt_time > start_time
    assert opt_int < cur_int
    assert opt_int == 130.0  # Wind peak at night


def test_estimate_carbon_savings() -> None:
    """Test savings estimation based on task type."""
    start_time = datetime.datetime(2026, 5, 28, 19, 0, 0)

    opt_time, savings_research = estimate_carbon_savings(
        "Perform web research on solar panels", start_time
    )
    assert savings_research > 0.0

    # Plan task should have less estimated savings due to lower kWh footprint
    _, savings_plan = estimate_carbon_savings("Create a release plan", start_time)
    assert savings_research > savings_plan


def test_scheduler_store(tmp_path: Path) -> None:
    """Test queueing, retrieving, and updating tasks in persistent storage."""
    db_file = tmp_path / "scheduled_tasks.jsonl"
    store = SchedulerStore(db_file)

    # Assert store is empty
    assert len(store.tasks()) == 0

    # Add a task
    task = store.add_task("Refactor CLI interface", "code")
    assert task.status == "queued"
    assert task.mode == "code"

    # Load tasks and verify
    all_tasks = store.tasks()
    assert len(all_tasks) == 1
    assert all_tasks[0].command == "Refactor CLI interface"

    # Update task status
    success = store.update_task_status(task.id, "running")
    assert success is True

    all_tasks_updated = store.tasks()
    assert all_tasks_updated[0].status == "running"


@pytest.mark.asyncio
async def test_schedule_slash_command(tmp_path: Path) -> None:
    """Test interactive slash command registration and dispatching."""
    db_file = tmp_path / "scheduled_tasks.jsonl"

    # Patch the SchedulerStore to use the test db file
    original_store_init = SchedulerStore.__init__

    def mock_init(self, path=None):
        original_store_init(self, db_file)

    SchedulerStore.__init__ = mock_init

    try:
        registry = SlashRegistry()
        messages: list[Message] = []

        # 1. Test basic usage instructions
        res_usage = await registry.dispatch(messages, "/schedule")
        assert res_usage is not None
        assert "Usage" in res_usage.output

        # 2. Test queueing a task
        res_add = await registry.dispatch(messages, "/schedule Refactor utils module")
        assert res_add is not None
        assert "Task scheduled" in res_add.output

        # 3. Test listing schedule
        res_list = await registry.dispatch(messages, "/schedule list")
        assert res_list is not None
        assert res_list.output is not None

    finally:
        # Restore SchedulerStore initializer
        SchedulerStore.__init__ = original_store_init
