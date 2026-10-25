"""Pure helpers: date ranges, file paths and writing JSON only when it changed."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def date_range(start: date, end: date) -> Iterator[date]:
    """Every day from start to end, inclusive."""
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def windows(start: date, end: date, max_days: int) -> Iterator[tuple[date, date]]:
    """Split a range into windows of at most max_days (endpoints limit the range)."""
    if max_days < 1:
        raise ValueError("max_days must be at least 1")
    first = start
    while first <= end:
        last = min(first + timedelta(days=max_days - 1), end)
        yield first, last
        first = last + timedelta(days=1)


def _iso_day(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def day_of(item: Any, key: str) -> str | None:
    """The item's day as YYYY-MM-DD, or None when the field is missing or malformed."""
    if not isinstance(item, dict):
        return None
    return _iso_day(item.get(key))


def activity_day(item: dict[str, Any]) -> str | None:
    """The activity's day, by local start time."""
    return _iso_day(item.get("startTimeLocal"))


def day_path(root: Path, dataset: str, day: str) -> Path:
    return root / dataset / day[:4] / f"{day}.json"


def activity_path(root: Path, day: str, activity_id: int) -> Path:
    return root / "activities" / day[:4] / f"{day}-{activity_id}.json"


def dumps(payload: Any) -> str:
    """Stable JSON: sorted keys, readable non-ASCII, trailing newline."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_if_changed(path: Path, payload: Any) -> bool:
    """Write JSON only when the content changed. Returns True when written."""
    return write_if_changed_text(path, dumps(payload))


def write_if_changed_text(path: Path, text: str) -> bool:
    """Write text only when the content changed. Returns True when written."""
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def is_empty(payload: Any) -> bool:
    """True for a response without data: None, empty list/object, object of empty values."""
    if payload is None:
        return True
    if isinstance(payload, dict):
        return all(is_empty(v) for v in payload.values())
    if isinstance(payload, (list, str)):
        return len(payload) == 0
    return False
