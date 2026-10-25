"""Daily check: yesterday and the day before against your own 28-day median.

Usage:  python -m garmin_sync.check
No network, no LLM: reads data/, on a deviation appends an entry to reports/daily/<YYYY-MM>.md.
The rules are in CLAUDE.md, section Daily check.
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

from . import journal as journal_mod
from . import store
from .dashboard import BASELINE_DAYS, METRICS, ROOT, Metric, baseline, fmt, load_series

MAD_SCALE = 1.4826  # MAD → standard deviation for a normal distribution
MAD_FACTOR = 2.0
STALE_DAYS = 3


@dataclass(frozen=True)
class Rule:
    bad: str  # "low" = lower is worse, "high" = higher is worse
    min_delta: float  # smaller differences are never reported, even with a tiny spread


RULES: dict[str, Rule] = {
    "sleep_hours": Rule("low", 0.75),
    "sleep_score": Rule("low", 8),
    "hrv": Rule("low", 6),
    "resting_hr": Rule("high", 3),
    "stress": Rule("high", 6),
    "body_battery": Rule("low", 10),
}


def threshold(series: dict[date, float], day: date, rule: Rule) -> float | None:
    """How large a difference from the median is clear: 2× the spread (MAD), at least rule.min_delta."""
    values = [
        series[d]
        for d in store.date_range(day - timedelta(days=BASELINE_DAYS), day - timedelta(days=1))
        if d in series
    ]
    base = baseline(series, day)
    if base is None:
        return None
    mad = median(abs(v - base) for v in values)
    return max(rule.min_delta, MAD_FACTOR * MAD_SCALE * mad)


def deviation(series: dict[date, float], day: date, rule: Rule) -> tuple[float, float] | None:
    """(value, median) when the day is clearly off in the unfavourable direction, otherwise None."""
    value, base, limit = series.get(day), baseline(series, day), threshold(series, day, rule)
    if value is None or base is None or limit is None:
        return None
    delta = value - base if rule.bad == "high" else base - value
    return (value, base) if delta > limit else None


def _day(d: date) -> str:
    return d.isoformat()


def journal_note(journal: journal_mod.Journal | None, days: list[date]) -> str:
    """" Journal: 2030-10-23 alcohol, party." for days with tags, otherwise an empty string."""
    if journal is None:
        return ""
    parts = [f"{_day(d)} {', '.join(tags)}" for d in days if (tags := journal.tags(d))]
    return f" Journal: {'; '.join(parts)}." if parts else ""


def findings(data_dir: Path, today: date, journal: journal_mod.Journal | None = None) -> list[str]:
    """Lines for clear deviations lasting 2 days and for missing data."""
    yesterday, before = today - timedelta(days=1), today - timedelta(days=2)
    load_start = before - timedelta(days=BASELINE_DAYS)
    out: list[str] = []
    for metric in METRICS:
        rule = RULES.get(metric.key)
        if rule is None:
            continue
        series = load_series(data_dir, metric, load_start, yesterday)
        a, b = deviation(series, before, rule), deviation(series, yesterday, rule)
        if a and b:
            # The day before each night too: evening alcohol shows up only in the night.
            days = [before - timedelta(days=1), before, yesterday]
            out.append(_line(metric, rule, before, a, yesterday, b) + journal_note(journal, days))
    latest = _latest_day(data_dir)
    if latest is None or (today - latest).days > STALE_DAYS:
        since = f"since {_day(latest)}" if latest else "at all"
        out.append(
            f"No daily summary from the sync {since}: the key probably expired, or the watch is not syncing."
        )
    return out


def _line(metric: Metric, rule: Rule, d1: date, v1: tuple[float, float], d2: date, v2: tuple[float, float]) -> str:
    unit = f" {metric.unit}" if metric.unit else ""
    word = "lower" if rule.bad == "low" else "higher"
    return (
        f"{metric.label} {word} 2 days in a row: {fmt(v1[0], metric.decimals)}{unit} ({_day(d1)}, "
        f"median {fmt(v1[1], metric.decimals)}) and {fmt(v2[0], metric.decimals)}{unit} ({_day(d2)}, "
        f"median {fmt(v2[1], metric.decimals)})."
    )


def _latest_day(data_dir: Path) -> date | None:
    names = sorted(p.stem for p in (data_dir / "daily_summary").glob("*/*.json"))
    return date.fromisoformat(names[-1]) if names else None


def record(reports_dir: Path, today: date, lines: list[str]) -> bool:
    """Write (or replace) the entry for `today` in reports/daily/<YYYY-MM>.md. True = changed."""
    path = reports_dir / "daily" / f"{today:%Y-%m}.md"
    text = path.read_text(encoding="utf-8") if path.exists() else f"# Daily check {today:%Y-%m}\n"
    heading = f"## {today.isoformat()}"
    entry = heading + "\n\n" + "\n".join(f"- {line}" for line in lines) + "\n"
    pattern = re.compile(rf"^{re.escape(heading)}\n.*?(?=^## |\Z)", re.S | re.M)
    if pattern.search(text):
        new = pattern.sub(entry + "\n", text).rstrip("\n") + "\n"
    else:
        new = text.rstrip("\n") + "\n\n" + entry
    return store.write_if_changed_text(path, new)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)
    today = datetime.now(ZoneInfo(os.environ.get("GARMIN_TZ", "Europe/Prague"))).date()
    lines = findings(args.data_dir, today, journal_mod.load(ROOT / "journal"))
    if not lines:
        print("No deviations")
        return 0
    record(args.reports_dir, today, lines)
    for line in lines:
        print(f"::warning::{line}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Daily check\n\n" + "\n".join(f"- {line}" for line in lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
