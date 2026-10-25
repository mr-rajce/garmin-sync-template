"""Garmin Personal API datasets: where they come from and how to get per-day items.

Response shapes verified against the real API, except `hydration` and
`food_logs` with entries (no sample with logged water or food yet).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

FOOD_LOGS = "food_logs"
ACTIVITIES = "activities"
ACTIVITY_PAGE_SIZE = 100
MAX_ACTIVITY_PAGES = 50


def has_food(raw: Any) -> bool:
    """True when the day has at least one food entry.

    Garmin returns an object with metadata (mealDate, dayStartTime…) even for
    an empty day; the entries live in lists (loggedFoodsWithServingSizes, mealDetails).
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

    def fetch(self, client: Any, start: date, end: date) -> Any:
        return getattr(client, self.method)(start, end)

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
)
