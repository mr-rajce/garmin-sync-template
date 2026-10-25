import json
from datetime import date
from pathlib import Path

import pytest

from garmin_sync import sync

START = date(2030, 10, 20)
END = date(2030, 10, 21)


class FakeClient:
    """Mimics GarminPersonalApiClient response shapes seen from the real API."""

    def __init__(self, fail: set[str] | None = None, activities: list | None = None):
        self.fail = fail or set()
        self.activities = activities if activities is not None else []
        self.calls: list[str] = []

    def _days(self, s, e, key="calendarDate", **extra):
        return [{key: d.isoformat(), **extra} for d in (s, e) if d <= e][: (e - s).days + 1]

    def _maybe_fail(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError(f"{name} failed")

    def get_daily_summaries(self, s, e):
        self._maybe_fail("daily_summary")
        return {"data": self._days(s, e, totalKilocalories=2400)}

    def get_daily_sleep_summaries(self, s, e):
        self._maybe_fail("sleep")
        return self._days(s, e, sleepTimeSeconds=27000)

    def get_daily_hrv_summaries(self, s, e):
        self._maybe_fail("hrv")
        return {"hrvSummaries": self._days(s, e, lastNightAvg=45)}

    def get_daily_stress(self, s, e):
        self._maybe_fail("stress")
        return self._days(s, e)

    def get_daily_steps(self, s, e):
        self._maybe_fail("steps")
        return self._days(s, e, totalSteps=9000)

    def get_daily_body_battery(self, s, e, chunks=None):
        name = "body_battery_intraday" if chunks else "body_battery"
        self._maybe_fail(name)
        return self._days(s, e, key="date", points=chunks or 3)

    def get_weight_measurements(self, s, e):
        self._maybe_fail("weight")
        return {"dailyWeightSummaries": []}

    def get_daily_hydration(self, s, e):
        self._maybe_fail("hydration")
        return {"unexpected": [1]}

    def get_daily_food_logs(self, day):
        self._maybe_fail("food_logs")
        # Real API shape: even an empty day has metadata.
        meta = {"mealDate": day.isoformat(), "dayStartTime": "07:00:00", "mealDetails": []}
        foods = [{"foodName": "porridge"}] if day == START else []
        return {**meta, "loggedFoodsWithServingSizes": foods}

    def get_daily_heart_rate(self, day):
        self._maybe_fail("heart_rate")
        # Real API shape; a day without the watch has heartRateValues null.
        values = [[1919462400000, 58], [1919462520000, 61]] if day == START else None
        return {"calendarDate": day.isoformat(), "restingHeartRate": 45, "heartRateValues": values}

    def search_activities(self, *, start, limit, start_date, end_date):
        self._maybe_fail("activities")
        return self.activities[start : start + limit]


def test_sync_all_writes_one_file_per_day(tmp_path: Path):
    report = sync.sync_all(FakeClient(), START, END, tmp_path)

    sleep = tmp_path / "sleep/2030/2030-10-20.json"
    assert json.loads(sleep.read_text(encoding="utf-8"))["sleepTimeSeconds"] == 27000
    assert (tmp_path / "body_battery/2030/2030-10-21.json").exists()
    assert report.changed["sleep"] == 2
    assert report.changed["weight"] == 0
    # Food log only for the day that has entries.
    assert report.changed["food_logs"] == 1
    assert not (tmp_path / "food_logs/2030/2030-10-21.json").exists()
    # Intraday heart rate only for the day with values, 15-minute Body Battery separately.
    assert report.changed["heart_rate"] == 1
    assert not (tmp_path / "heart_rate/2030/2030-10-21.json").exists()
    intraday = json.loads((tmp_path / "body_battery_intraday/2030/2030-10-20.json").read_text(encoding="utf-8"))
    assert intraday["points"] == 96


def test_unknown_response_shape_is_reported_not_written(tmp_path: Path):
    report = sync.sync_all(FakeClient(), START, END, tmp_path)
    assert any("hydration" in e and "unknown response shape" in e for e in report.errors)
    assert not (tmp_path / "hydration").exists()


def test_second_run_changes_nothing(tmp_path: Path):
    sync.sync_all(FakeClient(), START, END, tmp_path)
    report = sync.sync_all(FakeClient(), START, END, tmp_path)
    assert sum(report.changed.values()) == 0


def test_one_failing_dataset_does_not_stop_others(tmp_path: Path):
    report = sync.sync_all(FakeClient(fail={"sleep"}), START, END, tmp_path)
    assert any(e.startswith("sleep") for e in report.errors)
    assert (tmp_path / "hrv/2030/2030-10-20.json").exists()


def test_activities_paginate_and_dedupe(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sync.datasets, "ACTIVITY_PAGE_SIZE", 2)
    acts = [
        {"activityId": 1, "startTimeLocal": "2030-10-20 07:00:00"},
        {"activityId": 2, "startTimeLocal": "2030-10-20 18:00:00"},
        {"activityId": 2, "startTimeLocal": "2030-10-20 18:00:00"},
        {"activityId": 3, "startTimeLocal": "2030-10-21 06:30:00"},
    ]
    client = FakeClient(activities=acts)
    report = sync.sync_all(client, START, END, tmp_path)
    assert report.changed["activities"] == 3
    assert (tmp_path / "activities/2030/2030-10-21-3.json").exists()
    assert client.calls.count("activities") == 3  # 2 + 2 + empty page


@pytest.mark.parametrize(
    ("expires", "contains"),
    [
        (None, None),
        ("2031-10-25", None),
        ("2030-11-10", "in 16 days"),
        ("2030-10-01", "expired"),
        ("25.10.2031", "invalid format"),
    ],
)
def test_key_expiry_warning(expires, contains):
    warning = sync.key_expiry_warning(expires, date(2030, 10, 25))
    if contains is None:
        assert warning is None
    else:
        assert contains in warning


def test_parse_days_bounds():
    assert sync.parse_days("7") == 7
    with pytest.raises(Exception):
        sync.parse_days("0")
    with pytest.raises(Exception):
        sync.parse_days("5000")


def test_known_shape_with_empty_list_is_not_an_error(tmp_path: Path):
    class NoWeighIns(FakeClient):
        def get_weight_measurements(self, s, e):
            return {"dailyWeightSummaries": [], "totalAverage": {"from": 1, "until": 2}}

    report = sync.sync_all(NoWeighIns(), START, END, tmp_path)
    assert not any(e.startswith("weight") for e in report.errors)
    assert report.changed["weight"] == 0


def test_item_without_day_does_not_drop_rest_of_window(tmp_path: Path):
    class GapInSleep(FakeClient):
        def get_daily_sleep_summaries(self, s, e):
            return [{"calendarDate": START.isoformat()}, {"id": 7}, {"calendarDate": END.isoformat()}]

    report = sync.sync_all(GapInSleep(), START, END, tmp_path)
    assert (tmp_path / "sleep/2030/2030-10-21.json").exists()
    assert any("sleep" in e and "['id']" in e for e in report.errors)


class RateLimited(Exception):
    def __init__(self, text: str = '{"count":101,"limit":100,"retryInSeconds":18}'):
        self.status_code = 429
        self.response_text = text


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (RateLimited(), 19.0),
        (RateLimited("not json"), sync.RATE_LIMIT_FALLBACK_SECONDS),
        (RuntimeError("other error"), None),
    ],
)
def test_retry_after(exc, expected):
    assert sync.retry_after(exc) == expected


def test_retrying_client_waits_and_retries():
    class Flaky:
        calls = 0

        def get_daily_food_logs(self, day):
            self.calls += 1
            if self.calls < 3:
                raise RateLimited()
            return {"ok": day}

    waits: list[float] = []
    client = sync.RetryingClient(Flaky(), sleep=waits.append)
    assert client.get_daily_food_logs("2030-10-20") == {"ok": "2030-10-20"}
    assert waits == [19.0, 19.0]


def test_retrying_client_gives_up_and_passes_other_errors():
    class Always:
        def search_activities(self, **kwargs):
            raise RateLimited()

        def get_daily_steps(self, s, e):
            raise RuntimeError("500")

    waits: list[float] = []
    client = sync.RetryingClient(Always(), sleep=waits.append)
    with pytest.raises(RateLimited):
        client.search_activities(start=0)
    assert len(waits) == sync.RATE_LIMIT_RETRIES
    with pytest.raises(RuntimeError):
        client.get_daily_steps(1, 2)
    assert len(waits) == sync.RATE_LIMIT_RETRIES


def test_day_with_null_date_is_skipped_silently(tmp_path: Path):
    # Real shape: a night without the watch has calendarDate null.
    class NightWithoutWatch(FakeClient):
        def get_daily_sleep_summaries(self, s, e):
            return [{"calendarDate": None, "id": 1, "deepSleepSeconds": None}, {"calendarDate": END.isoformat()}]

    report = sync.sync_all(NightWithoutWatch(), START, END, tmp_path)
    assert not any(e.startswith("sleep") for e in report.errors)
    assert (tmp_path / "sleep/2030/2030-10-21.json").exists()


def test_failing_intraday_does_not_break_daily_body_battery(tmp_path: Path):
    report = sync.sync_all(FakeClient(fail={"body_battery_intraday"}), START, END, tmp_path)
    assert [e for e in report.errors if e.startswith("body_battery")] == [
        "body_battery_intraday 2030-10-20..2030-10-21: body_battery_intraday failed"
    ]
    assert report.changed["body_battery"] == 2
