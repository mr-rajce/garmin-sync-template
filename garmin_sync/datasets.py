"""Garmin Personal API datasets: where they come from and how to get per-day items.

Response shapes verified against the real API, except `hydration` and
`food_logs` with entries (no sample with logged water or food yet).
Intraday heart rate came back only for roughly the last 5 months.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

FOOD_LOGS = "food_logs"
ACTIVITIES = "activities"
ACTIVITY_PAGE_SIZE = 100
MAX_ACTIVITY_PAGES = 50


def has_entries(raw: Any) -> bool:
    """True when a per-day response has at least one entry.

    Garmin returns an object with metadata even for an empty day (for food
    mealDate, dayStartTime…); the entries live in lists (loggedFoodsWithServingSizes,
    heartRateValues for heart rate). A day without a non-empty list is not saved.
    """
    if isinstance(raw, list):
        return bool(raw)
    if isinstance(raw, dict):
        return any(isinstance(v, list) and v for v in raw.values())
    return False


@dataclass(frozen=True)
class RangeDataset:
    name: str
    method: str  # GarminPersonalApiClient method taking (start, end)
    max_days: int  # longest range per request
    day_key: str = "calendarDate"
    list_key: str | None = None  # None = the response is the list itself
    params: tuple[tuple[str, Any], ...] = ()  # extra method arguments

    def fetch(self, client: Any, start: date, end: date) -> Any:
        return getattr(client, self.method)(start, end, **dict(self.params))

    def items(self, raw: Any) -> list[Any] | None:
        """Per-day items, or None when the response has an unexpected shape."""
        if self.list_key is None:
            return raw if isinstance(raw, list) else None
        if isinstance(raw, dict) and isinstance(raw.get(self.list_key), list):
            return raw[self.list_key]
        return None


RANGE_DATASETS: tuple[RangeDataset, ...] = (
    RangeDataset("daily_summary", "get_daily_summaries", 365, list_key="data"),
    RangeDataset("sleep", "get_daily_sleep_summaries", 31),
    RangeDataset("hrv", "get_daily_hrv_summaries", 31, list_key="hrvSummaries"),
    RangeDataset("stress", "get_daily_stress", 28),
    RangeDataset("steps", "get_daily_steps", 28),
    RangeDataset("body_battery", "get_daily_body_battery", 31, day_key="date"),
    RangeDataset(
        "weight",
        "get_weight_measurements",
        31,
        day_key="summaryDate",
        list_key="dailyWeightSummaries",
    ),
    RangeDataset("hydration", "get_daily_hydration", 31),
    # 96 min/max pairs per day = every 15 minutes; separate so a failure cannot break daily Body Battery.
    RangeDataset("body_battery_intraday", "get_daily_body_battery", 31, day_key="date", params=(("chunks", 96),)),
)


@dataclass(frozen=True)
class DayDataset:
    """A dataset Garmin returns one day at a time (the method takes one date)."""

    name: str
    method: str

    def fetch(self, client: Any, day: date) -> Any:
        return getattr(client, self.method)(day)


DAY_DATASETS: tuple[DayDataset, ...] = (
    DayDataset(FOOD_LOGS, "get_daily_food_logs"),
    DayDataset("heart_rate", "get_daily_heart_rate"),
)
