"""Grid carbon intensity API client and simulator for CarbonClaw."""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass
class IntensitySlot:
    """A specific hour slot and its projected carbon intensity in g CO2/kWh."""

    hour: int
    intensity: float
    description: str


# Simulation of a standard grid carbon intensity profile over a 24-hour cycle.
# 22:00 - 05:00: Wind peaking, low demand (cleanest) -> ~150g
# 10:00 - 15:00: Solar peaking -> ~200g
# 17:00 - 21:00: Peak load, fossil fuels online (dirtiest) -> ~450g
# Other hours: General blend -> ~280g
GRID_PROFILE = {
    0: IntensitySlot(0, 140.0, "Wind Peak / Low Demand"),
    1: IntensitySlot(1, 135.0, "Wind Peak / Low Demand"),
    2: IntensitySlot(2, 130.0, "Wind Peak / Low Demand"),
    3: IntensitySlot(3, 130.0, "Wind Peak / Low Demand"),
    4: IntensitySlot(4, 140.0, "Wind Peak / Low Demand"),
    5: IntensitySlot(5, 160.0, "Early Morning transition"),
    6: IntensitySlot(6, 220.0, "Morning ramp"),
    7: IntensitySlot(7, 280.0, "Morning blend"),
    8: IntensitySlot(8, 290.0, "Morning blend"),
    9: IntensitySlot(9, 250.0, "Solar ramp starting"),
    10: IntensitySlot(10, 190.0, "Solar Peak"),
    11: IntensitySlot(11, 180.0, "Solar Peak"),
    12: IntensitySlot(12, 175.0, "Solar Peak"),
    13: IntensitySlot(13, 180.0, "Solar Peak"),
    14: IntensitySlot(14, 190.0, "Solar Peak"),
    15: IntensitySlot(15, 210.0, "Solar fading"),
    16: IntensitySlot(16, 260.0, "Evening ramp"),
    17: IntensitySlot(17, 380.0, "Evening Peak Load"),
    18: IntensitySlot(18, 440.0, "Evening Peak Load (Highest Intensity)"),
    19: IntensitySlot(19, 450.0, "Evening Peak Load (Highest Intensity)"),
    20: IntensitySlot(20, 420.0, "Evening Peak Load"),
    21: IntensitySlot(21, 350.0, "Late Evening blend"),
    22: IntensitySlot(22, 220.0, "Night wind ramp starting"),
    23: IntensitySlot(23, 160.0, "Night Wind Peak"),
}


def get_grid_intensity(hour: int | None = None) -> float:
    """Get the simulated grid intensity in g CO2/kWh for a given hour (default current hour)."""
    if hour is None:
        hour = datetime.datetime.now().hour
    return GRID_PROFILE.get(hour % 24, IntensitySlot(hour, 280.0, "Blend")).intensity


def get_optimal_run_time(
    current_time: datetime.datetime | None = None,
) -> tuple[datetime.datetime, float, float]:
    """Find the optimal run time in the next 12 hours.

    Returns:
        A tuple of (optimal_datetime, current_intensity, optimal_intensity)
    """
    if current_time is None:
        current_time = datetime.datetime.now()

    current_intensity = get_grid_intensity(current_time.hour)

    # Scan the next 12 hours to find the slot with the lowest carbon intensity
    best_time = current_time
    best_intensity = current_intensity

    for offset in range(1, 13):
        scan_time = current_time + datetime.timedelta(hours=offset)
        scan_intensity = get_grid_intensity(scan_time.hour)
        if scan_intensity < best_intensity:
            best_intensity = scan_intensity
            best_time = scan_time

    # If the current time is already in a green slot, or no cleaner slot within 12 hours:
    # return a delay of 0 (current time)
    if best_intensity >= current_intensity - 10:  # Allow 10g tolerance
        return current_time, current_intensity, current_intensity

    return best_time, current_intensity, best_intensity


def estimate_carbon_savings(
    task: str, current_time: datetime.datetime | None = None
) -> tuple[datetime.datetime, float]:
    """Estimate the carbon savings in grams of CO2 if delayed to the greenest slot.

    Returns:
        A tuple of (scheduled_datetime, carbon_savings_grams)
    """
    scheduled_time, cur_intensity, opt_intensity = get_optimal_run_time(current_time)

    # Task specific kWh multipliers
    # Simulating standard LLM run energy footprint (average token size + execution duration)
    kwh_map = {
        "research": 0.15,  # Map-reduce browser operations take substantial power
        "heal": 0.08,      # Local test runner + multiple LLM self-heals
        "code": 0.05,
        "plan": 0.03,
    }

    task_lower = task.lower()
    task_kwh = 0.04  # Default
    for key, kwh in kwh_map.items():
        if key in task_lower:
            task_kwh = kwh
            break

    # Emissions = kwh * intensity (g CO2 / kWh)
    cur_emissions = task_kwh * cur_intensity
    opt_emissions = task_kwh * opt_intensity
    savings = cur_emissions - opt_emissions

    # Make sure we don't return negative savings
    savings = max(0.0, savings)

    return scheduled_time, savings
