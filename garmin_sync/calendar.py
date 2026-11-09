"""Calendar: meetings as times and categories, never titles or people (CLAUDE.md, section Optional: calendar).

Usage:  python -m garmin_sync.calendar --in <compact.json> --from <day> --to <day> [--data-dir data]
The input is a compact list an agent copies from the Google Calendar connector, without titles:

    [{"start": "2030-11-04T10:30:00+01:00", "end": "2030-11-04T11:10:00+01:00",
      "all_day": false, "others": 1, "external": false, "declined": false,
      "free": false, "type": "DEFAULT"}, …]

`others` = number of other people (without the owner and without rooms; the organizer counts
when not among the invitees), `external` = at least one of them outside the owner's own email
domain, `group` = an invitee is a group (team, whole company), so there are more people than addresses. This code computes the category and the daily summary; `data/calendar/<year>/<day>.json`
gets only times, categories and the day summary. Days in the input range are rewritten
whole (the current state of the calendar).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from . import store

ROOT = Path(__file__).resolve().parent.parent
DATASET = "calendar"
MEETINGS = ("1:1", "internal", "external")  # categories with other people = meetings
EVENING = time(18, 0)


def category(event: dict[str, Any]) -> str | None:
    """The event's category, or None when it does not count (declined, free)."""
    if event.get("declined") or event.get("free"):
        return None
    kind = event.get("type") or "DEFAULT"
    if kind == "OUT_OF_OFFICE":
        return "out of office"
    if kind == "FOCUS_TIME":
        return "focus"
    if kind not in ("DEFAULT", "FROM_GMAIL"):
        return None
    if event.get("all_day"):
        return "all-day"
    others = int(event.get("others") or 0)
    if event.get("group"):
        others = max(others, 2)
    if others == 0:
        return "own"
    if event.get("external"):
        return "external"
    return "1:1" if others == 1 else "internal"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _merged_minutes(intervals: list[tuple[datetime, datetime]]) -> int:
    """Minutes in the union of intervals (overlapping meetings are not counted twice)."""
    total, end = 0, None
    for s, e in sorted(intervals):
        if end is None or s >= end:
            total += int((e - s).total_seconds() // 60)
            end = e
        elif e > end:
            total += int((e - end).total_seconds() // 60)
            end = e
    return total


def days(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Events split by day (local start date) with a summary per day."""
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        cat = category(ev)
        if cat is None or not ev.get("start") or not ev.get("end"):
            continue
        if ev.get("all_day"):
            d = date.fromisoformat(ev["start"][:10])
            last = max(d, date.fromisoformat(ev["end"][:10]) - timedelta(days=1))  # the end date is exclusive
            while d <= last:
                by_day[d.isoformat()].append({"start": None, "end": None, "category": cat, "all_day": True})
                d += timedelta(days=1)
            continue
        s, e = _parse(ev["start"]), _parse(ev["end"])
        by_day[s.date().isoformat()].append({"start": s, "end": e, "category": cat, "all_day": False})
    out = {}
    for day, items in sorted(by_day.items()):
        timed = sorted((i for i in items if not i["all_day"]), key=lambda i: (i["start"], i["end"]))
        meetings = [i for i in timed if i["category"] in MEETINGS]
        out[day] = {
            "date": day,
            "events": [
                {"start": i["start"].strftime("%H:%M"), "end": i["end"].strftime("%H:%M"), "category": i["category"]}
                for i in timed
            ] + [{"start": None, "end": None, "category": i["category"], "all_day": True} for i in items if i["all_day"]],
            "meetings": len(meetings),
            "meeting_hours": round(_merged_minutes([(i["start"], i["end"]) for i in meetings]) / 60, 2),
            "last_meeting_end": max(i["end"] for i in meetings).strftime("%H:%M") if meetings else None,
            "meetings_after_18": sum(1 for i in meetings if i["end"].time() > EVENING),
        }
    return out


def write(data_dir: Path, summaries: dict[str, dict[str, Any]], covered: list[str]) -> int:
    """Write the days; a day in the input range without events gets an empty record. Returns the number of changes."""
    changed = 0
    for day in covered:
        payload = summaries.get(day) or {"date": day, "events": [], "meetings": 0, "meeting_hours": 0,
                                         "last_meeting_end": None, "meetings_after_18": 0}
        changed += store.write_if_changed(store.day_path(data_dir, DATASET, day), payload)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in", dest="inp", type=Path, required=True)
    parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True, help="first day of the range")
    parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True, help="last day of the range")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args(argv)
    events = json.loads(args.inp.read_text(encoding="utf-8"))
    allowed = {"start", "end", "all_day", "others", "external", "group", "declined", "free", "type"}
    extra = sorted({k for ev in events for k in ev} - allowed)
    if extra:
        raise SystemExit(f"The input has fields that are not allowed {extra}; titles and people must not enter the repo.")
    covered = [d.isoformat() for d in store.date_range(args.start, args.end)]
    changed = write(args.data_dir, {k: v for k, v in days(events).items() if k in covered}, covered)
    print(f"calendar: {len(covered)} days, {changed} changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
