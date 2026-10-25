"""Download the last N days from the Garmin Personal API into data/.

Usage:  python -m garmin_sync.sync --days 7
Key:    environment variable GARMIN_PERSONAL_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import datasets, store

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MAX_DAYS_BACK = 3 * 365
KEY_EXPIRY_WARNING_DAYS = 30
KEY_REJECTED_STATUSES = {400, 401, 403}
# Garmin allows about 100 requests per minute (HTTP 429 with retryInSeconds).
REQUEST_PAUSE_SECONDS = 0.65
RATE_LIMIT_STATUS = 429
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_FALLBACK_SECONDS = 60


@dataclass
class Report:
    changed: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def count(self, dataset: str, changed: bool) -> None:
        self.changed.setdefault(dataset, 0)
        if changed:
            self.changed[dataset] += 1

    def lines(self) -> list[str]:
        out = [f"- {name}: {n} files changed" for name, n in sorted(self.changed.items())]
        out += [f"- ⚠️ {w}" for w in self.warnings]
        out += [f"- ❌ {e}" for e in self.errors]
        return out


def retry_after(exc: Exception) -> float | None:
    """Seconds to wait after HTTP 429, otherwise None."""
    if getattr(exc, "status_code", None) != RATE_LIMIT_STATUS:
        return None
    try:
        seconds = json.loads(getattr(exc, "response_text", "") or "{}").get("retryInSeconds")
    except (ValueError, AttributeError):
        seconds = None
    if isinstance(seconds, (int, float)) and seconds >= 0:
        return float(seconds) + 1
    return float(RATE_LIMIT_FALLBACK_SECONDS)


class RetryingClient:
    """Client wrapper: on rate limit, waits as long as Garmin says and retries."""

    def __init__(self, client: Any, sleep: Callable[[float], None] = time.sleep) -> None:
        self._client = client
        self._sleep = sleep

    def __getattr__(self, name: str) -> Any:
        method = getattr(self._client, name)
        if not callable(method):
            return method

        def call(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(RATE_LIMIT_RETRIES + 1):
                try:
                    return method(*args, **kwargs)
                except Exception as exc:
                    wait = retry_after(exc)
                    if wait is None or attempt == RATE_LIMIT_RETRIES:
                        raise
                    print(f"Rate limited, waiting {wait:.0f} s ({name})", file=sys.stderr)
                    self._sleep(wait)
            raise AssertionError("unreachable")

        return call


def sync_range_dataset(
    client: Any,
    dataset: datasets.RangeDataset,
    start: date,
    end: date,
    root: Path,
    report: Report,
    pause: Callable[[], None],
) -> None:
    wanted = {d.isoformat() for d in store.date_range(start, end)}
    for first, last in store.windows(start, end, dataset.max_days):
        try:
            raw = dataset.fetch(client, first, last)
        except Exception as exc:  # one dataset must not take down the others
            report.errors.append(f"{dataset.name} {first}..{last}: {exc}")
            return
        finally:
            pause()
        items = dataset.items(raw)
        if items is None:
            if not store.is_empty(raw):
                report.errors.append(
                    f"{dataset.name} {first}..{last}: unknown response shape "
                    f"(keys: {sorted(raw)[:10] if isinstance(raw, dict) else type(raw).__name__})"
                )
                continue
            items = []
        report.count(dataset.name, False)
        for item in items:
            day = store.day_of(item, dataset.day_key)
            if day is None:
                # Garmin marks a day without a record this way (e.g. a night without the watch).
                if isinstance(item, dict) and item.get(dataset.day_key, "") is None:
                    continue
                # One bad item must not drop the rest of the window.
                if not store.is_empty(item):
                    keys = sorted(item)[:10] if isinstance(item, dict) else type(item).__name__
                    report.errors.append(
                        f"{dataset.name} {first}..{last}: item without "
                        f"{dataset.day_key} (keys: {keys})"
                    )
                continue
            if day not in wanted:
                continue
            report.count(dataset.name, store.write_if_changed(store.day_path(root, dataset.name, day), item))


def sync_food_logs(
    client: Any, start: date, end: date, root: Path, report: Report, pause: Callable[[], None]
) -> None:
    report.count(datasets.FOOD_LOGS, False)
    for day in store.date_range(start, end):
        try:
            raw = client.get_daily_food_logs(day)
        except Exception as exc:
            report.errors.append(f"{datasets.FOOD_LOGS} {day}: {exc}")
            return
        finally:
            pause()
        if not datasets.has_food(raw):
            continue
        path = store.day_path(root, datasets.FOOD_LOGS, day.isoformat())
        report.count(datasets.FOOD_LOGS, store.write_if_changed(path, raw))


def sync_activities(
    client: Any, start: date, end: date, root: Path, report: Report, pause: Callable[[], None]
) -> None:
    report.count(datasets.ACTIVITIES, False)
    offset = 0
    seen: set[int] = set()
    for _ in range(datasets.MAX_ACTIVITY_PAGES):
        try:
            page = client.search_activities(
                start=offset, limit=datasets.ACTIVITY_PAGE_SIZE, start_date=start, end_date=end
            )
        except Exception as exc:
            report.errors.append(f"{datasets.ACTIVITIES} offset {offset}: {exc}")
            return
        finally:
            pause()
        items = page if isinstance(page, list) else []
        new = 0
        for item in items:
            activity_id = item.get("activityId") if isinstance(item, dict) else None
            if not isinstance(activity_id, int) or activity_id in seen:
                continue
            seen.add(activity_id)
            new += 1
            day = store.activity_day(item)
            if day is None:
                report.errors.append(f"{datasets.ACTIVITIES} {activity_id}: missing startTimeLocal")
                continue
            path = store.activity_path(root, day, activity_id)
            report.count(datasets.ACTIVITIES, store.write_if_changed(path, item))
        # A short page is not a reliable end; the server may truncate pages.
        if not items or not new:
            return
        offset += len(items)


def sync_all(
    client: Any,
    start: date,
    end: date,
    root: Path,
    pause: Callable[[], None] = lambda: None,
) -> Report:
    report = Report()
    for dataset in datasets.RANGE_DATASETS:
        sync_range_dataset(client, dataset, start, end, root, report, pause)
    sync_food_logs(client, start, end, root, report, pause)
    sync_activities(client, start, end, root, report, pause)
    return report


def key_expiry_warning(expires: str | None, today: date) -> str | None:
    """Warning when the key expires soon (GARMIN_KEY_EXPIRES = YYYY-MM-DD)."""
    if not expires:
        return None
    try:
        expiry = date.fromisoformat(expires.strip())
    except ValueError:
        return f"GARMIN_KEY_EXPIRES has an invalid format: {expires!r} (expected YYYY-MM-DD)"
    left = (expiry - today).days
    if left < 0:
        return f"Garmin key expired on {expiry.isoformat()}, create a new one"
    if left <= KEY_EXPIRY_WARNING_DAYS:
        return f"Garmin key expires on {expiry.isoformat()} (in {left} days), create a new one"
    return None


def parse_days(value: str) -> int:
    days = int(value)
    if not 1 <= days <= MAX_DAYS_BACK:
        raise argparse.ArgumentTypeError(f"--days must be 1–{MAX_DAYS_BACK}")
    return days


def write_step_summary(lines: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("## Garmin sync\n\n" + "\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    from garmin_personal_api import (
        GarminPersonalApiClient,
        HttpError,
        PersonalApiAuthenticator,
        resolve_api_key,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=parse_days, default=7)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)

    today = datetime.now(ZoneInfo(os.environ.get("GARMIN_TZ", "Europe/Prague"))).date()
    start = today - timedelta(days=args.days - 1)

    try:
        key = resolve_api_key()
    except Exception:
        print("GARMIN_PERSONAL_API_KEY is missing.", file=sys.stderr)
        return 2
    with PersonalApiAuthenticator() as authenticator:
        try:
            token = authenticator.obtain_token(key, force_refresh=True)
        except HttpError as exc:
            if exc.status_code in KEY_REJECTED_STATUSES:
                print(
                    f"Garmin rejected the key (HTTP {exc.status_code}). It probably expired or was "
                    "deleted: create a new one at connect.garmin.com/app/settings/personalApiToken "
                    "and save it as the GARMIN_PERSONAL_API_KEY secret.",
                    file=sys.stderr,
                )
                return 2
            raise

    with GarminPersonalApiClient(token.access_token) as client:
        report = sync_all(
            RetryingClient(client),
            start,
            today,
            args.data_dir,
            pause=lambda: time.sleep(REQUEST_PAUSE_SECONDS),
        )

    warning = key_expiry_warning(os.environ.get("GARMIN_KEY_EXPIRES"), today)
    if warning:
        report.warnings.append(warning)
        print(f"::warning::{warning}")

    lines = [f"Range {start.isoformat()} – {today.isoformat()}", "", *report.lines()]
    print("\n".join(lines))
    write_step_summary(lines)
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
