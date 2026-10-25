"""Generate reports/dashboard.md with SVG charts from the data in data/.

Usage:  python -m garmin_sync.dashboard
Sends nothing anywhere: reads data/ and writes only to reports/.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from . import journal as journal_mod
from . import store

ROOT = Path(__file__).resolve().parent.parent
CHART_DAYS = 90
TREND_WEEKS = 52
MIN_WEEK_VALUES = 4
TREND_METRICS = ("hrv", "resting_hr", "sleep_score", "sleep_hours")
BASELINE_DAYS = 28
MIN_BASELINE_VALUES = 7
RECENT_ACTIVITY_DAYS = 30
MAX_ACTIVITIES = 10
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _get(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _num(value: Any, scale: float = 1.0) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value * scale


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    dataset: str
    extract: Callable[[dict[str, Any]], float | None]
    decimals: int = 0


METRICS: tuple[Metric, ...] = (
    Metric("sleep_score", "Sleep score", "", "sleep", lambda d: _num(_get(d, "sleepScores", "overall", "value"))),
    Metric("sleep_hours", "Sleep duration", "h", "sleep", lambda d: _num(d.get("sleepTimeSeconds"), 1 / 3600), 1),
    Metric("hrv", "HRV (overnight avg)", "ms", "hrv", lambda d: _num(d.get("lastNightAvg"))),
    Metric("resting_hr", "Resting heart rate", "bpm", "daily_summary", lambda d: _num(_get(d, "heartRate", "restingValue"))),
    Metric("body_battery", "Body Battery max", "", "daily_summary", lambda d: _num(_get(d, "bodyBattery", "maxValue"))),
    Metric("stress", "Average stress", "", "daily_summary", lambda d: _num(_get(d, "stress", "avgLevel"))),
    Metric("steps", "Steps", "", "steps", lambda d: _num(d.get("totalSteps"))),
)


def load_series(data_dir: Path, metric: Metric, start: date, end: date) -> dict[date, float]:
    """Values per day. A day without a file or value is absent from the series (not zero)."""
    out: dict[date, float] = {}
    for day in store.date_range(start, end):
        path = store.day_path(data_dir, metric.dataset, day.isoformat())
        if not path.exists():
            continue
        value = metric.extract(json.loads(path.read_text(encoding="utf-8")))
        if value is not None:
            out[day] = value
    return out


def baseline(series: dict[date, float], day: date) -> float | None:
    """Median of the BASELINE_DAYS days before `day` (excluding it), if there are enough values."""
    values = [
        series[d]
        for d in store.date_range(day - timedelta(days=BASELINE_DAYS), day - timedelta(days=1))
        if d in series
    ]
    return median(values) if len(values) >= MIN_BASELINE_VALUES else None


def fmt(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}"


def _segments(points: list[tuple[date, float | None]]) -> list[list[tuple[date, float]]]:
    """Split a series into continuous segments; a missing day is a gap in the line."""
    segments: list[list[tuple[date, float]]] = []
    current: list[tuple[date, float]] = []
    for day, value in points:
        if value is None:
            if current:
                segments.append(current)
            current = []
        else:
            current.append((day, value))
    if current:
        segments.append(current)
    return segments


def weekly_medians(series: dict[date, float], start: date, end: date) -> dict[date, float]:
    """Median of each week (key = Monday), only when the week has at least MIN_WEEK_VALUES values."""
    out: dict[date, float] = {}
    monday = start - timedelta(days=start.weekday())
    while monday <= end:
        values = [series[d] for d in store.date_range(monday, monday + timedelta(days=6)) if d in series]
        if len(values) >= MIN_WEEK_VALUES:
            out[monday] = median(values)
        monday += timedelta(days=7)
    return out


def svg_chart(
    series: dict[date, float],
    start: date,
    end: date,
    decimals: int = 0,
    step: int = 1,
    show_baseline: bool = True,
) -> str:
    """Line chart: values every `step` days (blue), optionally the rolling 28-day median (grey, dashed)."""
    width, height = 720, 220
    left, right, top, bottom = 52, 12, 12, 28
    days = list(store.date_range(start, end))[::step]
    medians = {d: baseline(series, d) for d in days} if show_baseline else {}
    values = [series[d] for d in days if d in series] + [m for m in medians.values() if m is not None]
    if not values:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="60" viewBox="0 0 {width} 60">'
            f'<rect width="100%" height="100%" fill="#ffffff"/>'
            f'<text x="{width / 2}" y="35" text-anchor="middle" font-family="sans-serif" font-size="13" '
            f'fill="#666666">No data in the last {(end - start).days + 1} days</text></svg>\n'
        )
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.1 or max(abs(hi) * 0.1, 1)
    lo, hi = lo - pad, hi + pad
    span_x = max((end - start).days, 1)

    def x(day: date) -> float:
        return left + (day - start).days * (width - left - right) / span_x

    def y(value: float) -> float:
        return top + (hi - value) * (height - top - bottom) / (hi - lo)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="11">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for i in range(5):
        value = lo + (hi - lo) * i / 4
        parts.append(
            f'<line x1="{left}" x2="{width - right}" y1="{y(value):.1f}" y2="{y(value):.1f}" stroke="#e5e5e5"/>'
            f'<text x="{left - 6}" y="{y(value) + 4:.1f}" text-anchor="end" fill="#666666">'
            f"{fmt(value, decimals)}</text>"
        )
    for day in store.date_range(start, end):
        if day.day == 1:
            parts.append(
                f'<line x1="{x(day):.1f}" x2="{x(day):.1f}" y1="{top}" y2="{height - bottom}" stroke="#f0f0f0"/>'
                f'<text x="{x(day):.1f}" y="{height - 10}" text-anchor="middle" fill="#666666">'
                f"{day.day} {MONTHS[day.month - 1]}</text>"
            )
    for segment in _segments([(d, medians.get(d)) for d in days]):
        coords = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in segment)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="#999999" stroke-width="1.5" stroke-dasharray="4 3"/>')
    for segment in _segments([(d, series.get(d)) for d in days]):
        coords = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in segment)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="#2563eb" stroke-width="1.5"/>')
        parts += [f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="2" fill="#2563eb"/>' for d, v in segment]
    parts.append("</svg>\n")
    return "\n".join(parts)


def _duration(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)):
        return "—"
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"


def _distance(meters: Any) -> str:
    return f"{meters / 1000:.1f} km" if isinstance(meters, (int, float)) and meters > 0 else "—"


def recent_activities(data_dir: Path, start: date, end: date) -> list[dict[str, Any]]:
    out = []
    for day in store.date_range(start, end):
        folder = data_dir / "activities" / str(day.year)
        for path in sorted(folder.glob(f"{day.isoformat()}-*.json")):
            out.append(json.loads(path.read_text(encoding="utf-8")))
    out.sort(key=lambda a: str(a.get("startTimeLocal", "")), reverse=True)
    return out[:MAX_ACTIVITIES]


def journal_section(journal: journal_mod.Journal, start: date, end: date) -> list[str]:
    """Journal for the period: entries per day and periods overlapping it."""
    lines = [f"## Journal, last {RECENT_ACTIVITY_DAYS} days", ""]
    periods = [p for p in journal.periods if p.start <= end and (p.end is None or p.end >= start)]
    for p in periods:
        until = p.end.isoformat() if p.end else "ongoing"
        lines.append(f"- **{p.tag}** {p.start.isoformat()} – {until}" + (f": {p.note}" if p.note else ""))
    for day in sorted(d for d in journal.entries if start <= d <= end):
        entry = journal.entries[day]
        tags = f" *{', '.join(entry.tags)}*" if entry.tags else ""
        lines.append(f"- {day.isoformat()}{tags}" + (f": {entry.text}" if entry.text else ""))
    if len(lines) == 2:
        lines.append("No entries. Write to `journal/` (see CLAUDE.md, section Journal).")
    return lines + [""]


def build(data_dir: Path, reports_dir: Path, today: date, journal: journal_mod.Journal | None = None) -> str:
    """Write charts to reports/charts/ and return the dashboard markdown."""
    yesterday = today - timedelta(days=1)
    chart_start = yesterday - timedelta(days=CHART_DAYS - 1)
    trend_end = yesterday - timedelta(days=yesterday.weekday())  # Monday of the last week
    trend_start = trend_end - timedelta(weeks=TREND_WEEKS - 1)
    load_start = min(chart_start - timedelta(days=BASELINE_DAYS), trend_start)
    charts_dir = reports_dir / "charts"

    lines = [
        "# Garmin dashboard",
        "",
        f"As of {yesterday.isoformat()} (today is usually incomplete, hence yesterday). "
        f"Compared with the median of the {BASELINE_DAYS} days before. Regenerated after every sync.",
        "Clear deviations lasting 2 days: [daily check](daily/).",
        "",
        f"| Metric | Yesterday | {BASELINE_DAYS}-day median | Difference |",
        "|---|---:|---:|---:|",
    ]
    sections = []
    trends = []
    for metric in METRICS:
        series = load_series(data_dir, metric, load_start, yesterday)
        value, base = series.get(yesterday), baseline(series, yesterday)
        diff = value - base if value is not None and base is not None else None
        sign = "+" if diff is not None and diff > 0 else ""
        unit = f" {metric.unit}" if metric.unit else ""
        lines.append(
            f"| {metric.label} | {fmt(value, metric.decimals)}{unit if value is not None else ''} "
            f"| {fmt(base, metric.decimals)} | {sign}{fmt(diff, metric.decimals)} |"
        )
        store.write_if_changed_text(
            charts_dir / f"{metric.key}.svg", svg_chart(series, chart_start, yesterday, metric.decimals)
        )
        in_chart = sum(1 for d in store.date_range(chart_start, yesterday) if d in series)
        sections += [
            f"### {metric.label}" + (f" ({metric.unit})" if metric.unit else ""),
            "",
            f"![{metric.label}](charts/{metric.key}.svg)",
            "",
            f"Days with data: {in_chart} of {CHART_DAYS}.",
            "",
        ]
        if metric.key in TREND_METRICS:
            weekly = weekly_medians(series, trend_start, yesterday)
            store.write_if_changed_text(
                charts_dir / f"{metric.key}_trend.svg",
                svg_chart(weekly, trend_start, trend_end, metric.decimals, step=7, show_baseline=False),
            )
            trends += [
                f"### {metric.label}" + (f" ({metric.unit})" if metric.unit else ""),
                "",
                f"![{metric.label}, weekly median](charts/{metric.key}_trend.svg)",
                "",
            ]
            if weekly:
                hi = max(weekly, key=weekly.__getitem__)
                lo = min(weekly, key=weekly.__getitem__)
                trends += [
                    f"Highest: week of {hi.isoformat()}, {fmt(weekly[hi], metric.decimals)}. "
                    f"Lowest: week of {lo.isoformat()}, {fmt(weekly[lo], metric.decimals)}. "
                    f"Weeks with data: {len(weekly)} of {TREND_WEEKS}.",
                    "",
                ]

    lines += [
        "",
        f"## Last {CHART_DAYS} days",
        "",
        "Blue: daily value. Grey dashed: median of the previous 28 days. A gap is a day without data, not zero.",
        "",
        *sections,
        f"## Year: weekly medians ({TREND_WEEKS} weeks)",
        "",
        f"One point = median of a week (Monday–Sunday) with at least {MIN_WEEK_VALUES} days of data. "
        "Shows the long-term trend that daily values hide.",
        "",
        *trends,
    ]
    lines += journal_section(journal or journal_mod.Journal(), yesterday - timedelta(days=RECENT_ACTIVITY_DAYS - 1), today)
    lines += [f"## Activities in the last {RECENT_ACTIVITY_DAYS} days", ""]
    activities = recent_activities(data_dir, yesterday - timedelta(days=RECENT_ACTIVITY_DAYS - 1), today)
    if activities:
        lines += ["| Date | Type | Name | Duration | Distance |", "|---|---|---|---:|---:|"]
        for a in activities:
            lines.append(
                f"| {str(a.get('startTimeLocal', ''))[:10]} | {_get(a, 'activityType', 'typeKey') or '—'} "
                f"| {a.get('activityName') or '—'} | {_duration(a.get('duration'))} | {_distance(a.get('distance'))} |"
            )
    else:
        lines.append("No activities.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)
    today = datetime.now(ZoneInfo(os.environ.get("GARMIN_TZ", "Europe/Prague"))).date()
    markdown = build(args.data_dir, args.reports_dir, today, journal_mod.load(ROOT / "journal"))
    changed = store.write_if_changed_text(args.reports_dir / "dashboard.md", markdown)
    print(f"reports/dashboard.md {'updated' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
