import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from garmin_sync import export, journal, store

DAY = date(2030, 10, 23)
TZ = ZoneInfo("Europe/Prague")


def ms(hour: int, minute: int) -> int:
    # 23 Oct is still summer time: UTC+2
    return int(datetime(2030, 10, 23, hour - 2, minute, tzinfo=timezone.utc).timestamp() * 1000)


def test_daily_rows_missing_is_none_and_tags_without_text(tmp_path: Path):
    store.write_if_changed(store.day_path(tmp_path, "hrv", DAY.isoformat()), {"calendarDate": DAY.isoformat(), "lastNightAvg": 39})
    j = journal.Journal(entries={DAY: journal.Entry(["party", "alcohol"], "private note")})
    rows = export.daily_rows(tmp_path, j, DAY, DAY)
    assert rows == [{"date": "2030-10-23", "sleep_score": None, "sleep_hours": None, "hrv": 39, "resting_hr": None,
                     "body_battery": None, "stress": None, "steps": None, "tags": "party, alcohol"}]
    assert "private" not in json.dumps(rows, ensure_ascii=False)


def test_activity_rows_drop_name_and_gps(tmp_path: Path):
    store.write_if_changed(store.activity_path(tmp_path, DAY.isoformat(), 7), {
        "activityId": 7, "activityName": "Secret route", "startTimeLocal": "2030-10-23 14:50:50",
        "activityType": {"typeKey": "walking"}, "duration": 9508.0, "distance": 9153.2, "averageHR": 100.0,
        "startLatitude": 50.1, "endLongitude": 14.4, "locationName": "Somewhere"})
    rows = export.activity_rows(tmp_path, DAY, DAY)
    assert rows == [{"date": "2030-10-23", "start": "14:50", "type": "walking", "duration_min": 158,
                     "distance_km": 9.2, "avg_hr": 100.0}]


def test_intraday_rows_local_time_and_bad_shapes_skipped(tmp_path: Path):
    store.write_if_changed(store.day_path(tmp_path, "heart_rate", DAY.isoformat()),
                           {"heartRateValues": [[ms(14, 0), 88], [ms(14, 2), None], "x"]})
    store.write_if_changed(store.day_path(tmp_path, "body_battery_intraday", DAY.isoformat()),
                           {"bodyBatteryValuesArray": [[ms(15, 30), 16]]})
    assert export.intraday_rows(tmp_path, DAY, DAY, TZ) == [
        {"time": "2030-10-23T14:00", "metric": "hr", "value": 88},
        {"time": "2030-10-23T15:30", "metric": "body_battery", "value": 16},
    ]


def test_today_has_only_night_metrics(tmp_path: Path):
    iso = DAY.isoformat()
    store.write_if_changed(store.day_path(tmp_path, "hrv", iso), {"calendarDate": iso, "lastNightAvg": 52})
    store.write_if_changed(store.day_path(tmp_path, "sleep", iso), {"calendarDate": iso, "sleepTimeSeconds": 7 * 3600,
                                                                     "sleepScores": {"overall": {"value": 81}}})
    store.write_if_changed(store.day_path(tmp_path, "daily_summary", iso), {
        "calendarDate": iso, "heartRate": {"restingValue": 47}, "bodyBattery": {"maxValue": 90}, "stress": {"avgLevel": 12}})
    store.write_if_changed(store.day_path(tmp_path, "steps", iso), {"calendarDate": iso, "totalSteps": 800})
    [row] = export.daily_rows(tmp_path, journal.Journal(), DAY, DAY, partial=DAY)
    assert (row["hrv"], row["sleep_score"], row["sleep_hours"], row["body_battery"]) == (52, 81, 7.0, 90)
    assert (row["resting_hr"], row["stress"], row["steps"]) == (None, None, None)
    [full] = export.daily_rows(tmp_path, journal.Journal(), DAY, DAY)
    assert full["steps"] == 800
