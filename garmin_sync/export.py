"""Export for an optional private dashboard in a Claude artifact (CLAUDE.md, section Optional: artifact).

Usage:  python -m garmin_sync.export --out <folder>
Writes only what that section allows: daily summaries, the course of the day
(heart rate, Body Battery) and journal tags. Never raw files, journal text, GPS or activity names.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import journal as journal_mod
from . import store
from .dashboard import METRICS, ROOT, load_series

DAILY_DAYS = 365
INTRADAY_DAYS = 60


def daily_rows(data_dir: Path, journal: journal_mod.Journal, start: date, end: date) -> list[dict[str, Any]]:
    """One row per day: dashboard metrics (missing = None, not zero) and journal tags."""
    series = {m.key: load_series(data_dir, m, start, end) for m in METRICS}
    rows = []
    for day in store.date_range(start, end):
        row: dict[str, Any] = {"date": day.isoformat()}
        for m in METRICS:
            value = series[m.key].get(day)
            row[m.key] = round(value, m.decimals) if value is not None else None
        row["tags"] = ", ".join(journal.tags(day))
        rows.append(row)
    return rows


def activity_rows(data_dir: Path, start: date, end: date) -> list[dict[str, Any]]:
    """Activities without names and GPS: day, start time, type, duration, distance, average heart rate."""
    rows = []
    for day in store.date_range(start, end):
        for path in sorted((data_dir / "activities" / str(day.year)).glob(f"{day.isoformat()}-*.json")):
            a = json.loads(path.read_text(encoding="utf-8"))
            start_local = str(a.get("startTimeLocal") or "")
            rows.append({
                "date": day.isoformat(),
                "start": start_local[11:16] or None,
                "type": (a.get("activityType") or {}).get("typeKey"),
                "duration_min": round(a["duration"] / 60) if isinstance(a.get("duration"), (int, float)) else None,
                "distance_km": round(a["distance"] / 1000, 1) if isinstance(a.get("distance"), (int, float)) else None,
                "avg_hr": a.get("averageHR"),
            })
    return rows


def _local(ms: Any, tz: ZoneInfo) -> str | None:
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(tz).strftime("%Y-%m-%dT%H:%M")


def _pairs(values: Any) -> list[tuple[Any, Any]]:
    """[[timestamp in ms, value], …] → pairs; other shapes are skipped."""
    if not isinstance(values, list):
        return []
    return [(v[0], v[1]) for v in values if isinstance(v, (list, tuple)) and len(v) >= 2]


def intraday_rows(data_dir: Path, start: date, end: date, tz: ZoneInfo) -> list[dict[str, Any]]:
    """Course of the day: heart rate (heart_rate.heartRateValues) and Body Battery (body_battery_intraday)."""
    rows = []
    for day in store.date_range(start, end):
        hr = data_dir / "heart_rate" / str(day.year) / f"{day.isoformat()}.json"
        if hr.exists():
            for ts, value in _pairs(json.loads(hr.read_text(encoding="utf-8")).get("heartRateValues")):
                if isinstance(value, (int, float)) and (t := _local(ts, tz)):
                    rows.append({"time": t, "metric": "hr", "value": value})
        bb = data_dir / "body_battery_intraday" / str(day.year) / f"{day.isoformat()}.json"
        if bb.exists():
            for ts, value in _pairs(json.loads(bb.read_text(encoding="utf-8")).get("bodyBatteryValuesArray")):
                if isinstance(value, (int, float)) and (t := _local(ts, tz)):
                    rows.append({"time": t, "metric": "body_battery", "value": value})
    rows.sort(key=lambda r: (r["time"], r["metric"]))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args(argv)
    tz = ZoneInfo(os.environ.get("GARMIN_TZ", "Europe/Prague"))
    yesterday = datetime.now(tz).date() - timedelta(days=1)
    journal = journal_mod.load(ROOT / "journal")
    args.out.mkdir(parents=True, exist_ok=True)
    outputs = {
        "daily.json": daily_rows(args.data_dir, journal, yesterday - timedelta(days=DAILY_DAYS - 1), yesterday),
        "activities.json": activity_rows(args.data_dir, yesterday - timedelta(days=DAILY_DAYS - 1), yesterday),
        "intraday.json": intraday_rows(args.data_dir, yesterday - timedelta(days=INTRADAY_DAYS - 1), yesterday + timedelta(days=1), tz),
    }
    for name, rows in outputs.items():
        (args.out / name).write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{name}: {len(rows)} rows, {(args.out / name).stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
