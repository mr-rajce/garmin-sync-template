import json
from datetime import date, timedelta
from pathlib import Path

from garmin_sync import dashboard, store

TODAY = date(2030, 10, 25)
YESTERDAY = TODAY - timedelta(days=1)


def write(root: Path, dataset: str, day: date, payload: dict) -> None:
    store.write_if_changed(store.day_path(root, dataset, day.isoformat()), payload)


def test_missing_day_is_gap_not_zero(tmp_path: Path):
    for i in range(10):
        day = YESTERDAY - timedelta(days=i)
        if i != 3:
            write(tmp_path, "steps", day, {"calendarDate": day.isoformat(), "totalSteps": 5000})
    metric = next(m for m in dashboard.METRICS if m.key == "steps")
    series = dashboard.load_series(tmp_path, metric, YESTERDAY - timedelta(days=9), YESTERDAY)
    assert YESTERDAY - timedelta(days=3) not in series
    assert 0 not in series.values()
    svg = dashboard.svg_chart(series, YESTERDAY - timedelta(days=9), YESTERDAY)
    assert svg.count('stroke="#2563eb"') == 2  # two line segments around the gap


def test_baseline_is_median_of_previous_days_only():
    series = {YESTERDAY - timedelta(days=i): float(i) for i in range(1, 29)}
    series[YESTERDAY] = 1000.0
    assert dashboard.baseline(series, YESTERDAY) == 14.5


def test_baseline_needs_enough_values():
    series = {YESTERDAY - timedelta(days=i): 1.0 for i in range(1, dashboard.MIN_BASELINE_VALUES)}
    assert dashboard.baseline(series, YESTERDAY) is None


def test_build_table_and_charts(tmp_path: Path):
    data, reports = tmp_path / "data", tmp_path / "reports"
    for i in range(30):
        day = YESTERDAY - timedelta(days=i)
        write(data, "sleep", day, {"calendarDate": day.isoformat(), "sleepTimeSeconds": 7 * 3600,
                                   "sleepScores": {"overall": {"value": 80}}})
    write(data, "sleep", YESTERDAY, {"calendarDate": YESTERDAY.isoformat(), "sleepTimeSeconds": 6 * 3600,
                                     "sleepScores": {"overall": {"value": 60}}})
    store.write_if_changed(store.activity_path(data, YESTERDAY.isoformat(), 1), {
        "activityId": 1, "startTimeLocal": f"{YESTERDAY} 07:00:00", "activityName": "Run",
        "activityType": {"typeKey": "running"}, "duration": 1800, "distance": 5000})

    md = dashboard.build(data, reports, TODAY)

    assert "| Sleep score | 60 | 80 | -20 |" in md
    assert "| Sleep duration | 6.0 h | 7.0 | -1.0 |" in md
    assert "| Steps | — | — | — |" in md  # no data: a dash, not zero
    assert "| 2030-10-24 | running | Run | 30 min | 5.0 km |" in md
    assert (reports / "charts/sleep_score.svg").read_text(encoding="utf-8").startswith("<svg")
    assert "No data" in (reports / "charts/steps.svg").read_text(encoding="utf-8")


def test_build_is_deterministic(tmp_path: Path):
    data, reports = tmp_path / "data", tmp_path / "reports"
    write(data, "hrv", YESTERDAY, {"calendarDate": YESTERDAY.isoformat(), "lastNightAvg": 50})
    assert dashboard.build(data, reports, TODAY) == dashboard.build(data, reports, TODAY)
    assert not store.write_if_changed_text(reports / "charts/hrv.svg",
                                           (reports / "charts/hrv.svg").read_text(encoding="utf-8"))


def test_weekly_medians_need_enough_days():
    monday = date(2030, 10, 14)
    series = {monday + timedelta(days=i): float(i) for i in range(5)}  # 5 days: 0..4
    series[monday + timedelta(days=7)] = 99.0  # next week only 1 day
    weekly = dashboard.weekly_medians(series, monday, monday + timedelta(days=13))
    assert weekly == {monday: 2.0}


def test_trend_chart_and_section(tmp_path: Path):
    data, reports = tmp_path / "data", tmp_path / "reports"
    for i in range(60):
        day = YESTERDAY - timedelta(days=i)
        write(data, "hrv", day, {"calendarDate": day.isoformat(), "lastNightAvg": 50 + i % 7})
    md = dashboard.build(data, reports, TODAY)
    assert "## Year: weekly medians" in md
    assert "![HRV (overnight avg), weekly median](charts/hrv_trend.svg)" in md
    assert "Weeks with data: 9 of 52." in md  # 2030-08-26 (Mon) – 2030-10-24 (Thu): 9 weeks
    svg = (reports / "charts/hrv_trend.svg").read_text(encoding="utf-8")
    assert svg.count("<circle") == 9


def test_journal_section(tmp_path: Path):
    from garmin_sync import journal

    j = journal.Journal(
        entries={YESTERDAY: journal.Entry(["alcohol"], "party")},
        periods=[journal.Period(YESTERDAY - timedelta(days=3), None, "illness", "cold")],
    )
    md = dashboard.build(tmp_path / "data", tmp_path / "reports", TODAY, j)
    assert "- **illness** 2030-10-21 – ongoing: cold" in md
    assert "- 2030-10-24 *alcohol*: party" in md
    assert md.index("## Journal, last") < md.index("## Activities in the last")
    assert "No entries." in dashboard.build(tmp_path / "data", tmp_path / "reports", TODAY)
