from datetime import date, timedelta
from pathlib import Path

from garmin_sync import check, store

TODAY = date(2030, 10, 25)


def write_hrv(root: Path, values: dict[date, float]) -> None:
    for day, value in values.items():
        store.write_if_changed(store.day_path(root, "hrv", day.isoformat()),
                               {"calendarDate": day.isoformat(), "lastNightAvg": value})
        store.write_if_changed(store.day_path(root, "daily_summary", day.isoformat()),
                               {"calendarDate": day.isoformat()})


def stable(days: int = 40, value: float = 60) -> dict[date, float]:
    return {TODAY - timedelta(days=i): value + (i % 3) for i in range(1, days)}


def test_two_bad_days_in_a_row_are_reported(tmp_path: Path):
    values = stable()
    values[TODAY - timedelta(days=2)] = 45
    values[TODAY - timedelta(days=1)] = 44
    write_hrv(tmp_path, values)
    lines = check.findings(tmp_path, TODAY)
    assert lines == ["HRV (overnight avg) lower 2 days in a row: 45 ms (2030-10-23, median 61) "
                     "and 44 ms (2030-10-24, median 61)."]


def test_single_bad_day_is_noise(tmp_path: Path):
    values = stable()
    values[TODAY - timedelta(days=1)] = 40
    write_hrv(tmp_path, values)
    assert check.findings(tmp_path, TODAY) == []


def test_good_direction_is_not_reported(tmp_path: Path):
    values = stable()
    values[TODAY - timedelta(days=2)] = 90
    values[TODAY - timedelta(days=1)] = 95
    write_hrv(tmp_path, values)
    assert check.findings(tmp_path, TODAY) == []


def test_small_difference_below_minimum_is_not_reported(tmp_path: Path):
    values = {TODAY - timedelta(days=i): 60.0 for i in range(1, 40)}  # zero spread
    values[TODAY - timedelta(days=2)] = 55
    values[TODAY - timedelta(days=1)] = 55
    write_hrv(tmp_path, values)
    assert check.findings(tmp_path, TODAY) == []  # 5 ms < minimum 6 ms


def test_missing_day_is_not_a_deviation(tmp_path: Path):
    values = stable()
    values[TODAY - timedelta(days=2)] = 40
    del values[TODAY - timedelta(days=1)]
    write_hrv(tmp_path, values)
    assert check.findings(tmp_path, TODAY) == []


def test_stale_data_is_reported(tmp_path: Path):
    write_hrv(tmp_path, {TODAY - timedelta(days=i): 60 for i in range(5, 40)})
    assert check.findings(tmp_path, TODAY) == [
        "No daily summary from the sync since 2030-10-20: the key probably expired, or the watch is not syncing."
    ]


def test_record_is_idempotent_per_day(tmp_path: Path):
    assert check.record(tmp_path, TODAY, ["A"]) is True
    assert check.record(tmp_path, TODAY, ["A"]) is False
    assert check.record(tmp_path, TODAY, ["B"]) is True
    assert check.record(tmp_path, TODAY + timedelta(days=1), ["C"]) is True
    text = (tmp_path / "daily/2030-10.md").read_text(encoding="utf-8")
    assert text == "# Daily check 2030-10\n\n## 2030-10-25\n\n- B\n\n## 2030-10-26\n\n- C\n"
