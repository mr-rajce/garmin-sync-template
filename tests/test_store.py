from datetime import date
from pathlib import Path

import pytest

from garmin_sync import store


def test_windows_split_range_by_max_days():
    got = list(store.windows(date(2030, 1, 1), date(2030, 3, 1), 28))
    assert got == [
        (date(2030, 1, 1), date(2030, 1, 28)),
        (date(2030, 1, 29), date(2030, 2, 25)),
        (date(2030, 2, 26), date(2030, 3, 1)),
    ]


def test_windows_single_day():
    assert list(store.windows(date(2030, 5, 5), date(2030, 5, 5), 31)) == [
        (date(2030, 5, 5), date(2030, 5, 5))
    ]


def test_windows_rejects_zero():
    with pytest.raises(ValueError):
        list(store.windows(date(2030, 1, 1), date(2030, 1, 2), 0))


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"calendarDate": "2030-10-24"}, "2030-10-24"),
        ({"calendarDate": "2030-10-24T00:00:00.0"}, "2030-10-24"),
        ({"calendarDate": None}, None),
        ({"calendarDate": "24.10.2030"}, None),
        ({}, None),
        ("2030-10-24", None),
    ],
)
def test_day_of(item, expected):
    assert store.day_of(item, "calendarDate") == expected


def test_activity_day_from_local_start():
    assert store.activity_day({"startTimeLocal": "2030-10-24 23:30:00"}) == "2030-10-24"


def test_paths(tmp_path: Path):
    assert store.day_path(tmp_path, "sleep", "2030-10-24") == tmp_path / "sleep/2030/2030-10-24.json"
    assert (
        store.activity_path(tmp_path, "2030-10-24", 123)
        == tmp_path / "activities/2030/2030-10-24-123.json"
    )


def test_write_if_changed_is_idempotent_and_key_order_stable(tmp_path: Path):
    path = tmp_path / "a/b.json"
    assert store.write_if_changed(path, {"b": 1, "a": "č"}) is True
    assert store.write_if_changed(path, {"a": "č", "b": 1}) is False
    assert '"a": "č"' in path.read_text(encoding="utf-8")
    assert store.write_if_changed(path, {"a": "č", "b": 2}) is True


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, True),
        ([], True),
        ({}, True),
        ({"foodLogs": [], "meta": None}, True),
        ({"foodLogs": [{"name": "yogurt"}]}, False),
        ([{"x": 1}], False),
    ],
)
def test_is_empty(payload, expected):
    assert store.is_empty(payload) is expected
