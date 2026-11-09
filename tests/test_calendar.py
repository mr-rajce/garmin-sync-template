import json
from pathlib import Path

import pytest

from garmin_sync import calendar


def ev(start, end, **kw):
    return {"start": f"2030-11-04T{start}:00+01:00", "end": f"2030-11-04T{end}:00+01:00", **kw}


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (ev("09:00", "09:40"), "own"),
        (ev("10:00", "10:50", others=1, group=True), "internal"),
        (ev("10:30", "11:10", others=1), "1:1"),
        (ev("11:30", "12:00", others=4), "internal"),
        (ev("14:00", "15:00", others=3, external=True), "external"),
        (ev("15:00", "16:00", others=3, declined=True), None),
        (ev("10:30", "11:00", free=True), None),
        (ev("08:00", "12:00", type="OUT_OF_OFFICE"), "out of office"),
        (ev("13:00", "14:00", type="FOCUS_TIME"), "focus"),
        (ev("00:00", "00:00", type="WORKING_LOCATION"), None),
    ],
)
def test_category(event, expected):
    assert calendar.category(event) == expected


def test_day_summary_merges_overlaps_and_counts_evening():
    events = [
        ev("09:00", "09:40"),  # own, not a meeting
        ev("10:30", "11:30", others=1),
        ev("11:00", "12:00", others=4),  # the 11:00–11:30 overlap counts once
        ev("17:30", "18:30", others=2, external=True),
    ]
    [day] = calendar.days(events).values()
    assert day["meetings"] == 3
    assert day["meeting_hours"] == 2.5
    assert day["last_meeting_end"] == "18:30"
    assert day["meetings_after_18"] == 1
    assert [e["category"] for e in day["events"]] == ["own", "1:1", "internal", "external"]
    assert set(day["events"][0]) == {"start", "end", "category"}


def test_all_day_event_spans_days():
    out = calendar.days([{"start": "2030-11-04", "end": "2030-11-06", "all_day": True, "others": 0}])
    assert sorted(out) == ["2030-11-04", "2030-11-05"]
    assert out["2030-11-04"]["events"] == [{"start": None, "end": None, "category": "all-day", "all_day": True}]
    assert out["2030-11-04"]["meetings"] == 0


def test_main_rejects_titles_and_writes_empty_days(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([ev("09:00", "10:00", summary="Secret meeting")]), encoding="utf-8")
    with pytest.raises(SystemExit, match="not allowed"):
        calendar.main(["--in", str(bad), "--from", "2030-11-04", "--to", "2030-11-04", "--data-dir", str(tmp_path)])
    good = tmp_path / "good.json"
    good.write_text(json.dumps([ev("09:00", "10:00", others=1)]), encoding="utf-8")
    calendar.main(["--in", str(good), "--from", "2030-11-04", "--to", "2030-11-05", "--data-dir", str(tmp_path)])
    d4 = json.loads((tmp_path / "calendar/2030/2030-11-04.json").read_text(encoding="utf-8"))
    d5 = json.loads((tmp_path / "calendar/2030/2030-11-05.json").read_text(encoding="utf-8"))
    assert d4["events"] == [{"start": "09:00", "end": "10:00", "category": "1:1"}]
    assert d5["meetings"] == 0 and d5["events"] == []
    assert "Secret" not in (tmp_path / "calendar/2030/2030-11-04.json").read_text(encoding="utf-8")
