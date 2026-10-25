from datetime import date
from pathlib import Path

from garmin_sync import check, journal

MONTH = """# Journal 2030-10

## 2030-10-23
tags: Party, alcohol ,outdoors
14:00–16:00 party outside.

## 2030-10-24
No tags, just a note.
"""

PERIODS = """# Periods

| from | to | tag | note |
|---|---|---|---|
| 2030-10-20 | 2030-10-27 | illness | cold |
| 2030-10-22 |  | injury | knee |
"""


def write(tmp_path: Path) -> journal.Journal:
    (tmp_path / "2030-10.md").write_text(MONTH, encoding="utf-8")
    (tmp_path / "periods.md").write_text(PERIODS, encoding="utf-8")
    return journal.load(tmp_path)


def test_entries_tags_and_text(tmp_path: Path):
    j = write(tmp_path)
    assert j.entries[date(2030, 10, 23)].tags == ["party", "alcohol", "outdoors"]
    assert j.entries[date(2030, 10, 23)].text == "14:00–16:00 party outside."
    assert j.entries[date(2030, 10, 24)].tags == []


def test_periods_cover_days_and_open_end(tmp_path: Path):
    j = write(tmp_path)
    assert j.tags(date(2030, 10, 21)) == ["illness"]
    assert j.tags(date(2030, 10, 23)) == ["party", "alcohol", "outdoors", "illness", "injury"]
    assert j.tags(date(2030, 12, 1)) == ["injury"]  # no "to" = ongoing
    assert j.tags(date(2030, 10, 1)) == []


def test_missing_journal_is_empty(tmp_path: Path):
    j = journal.load(tmp_path / "missing")
    assert j.entries == {} and j.periods == []


def test_only_month_files_and_periods_are_read(tmp_path: Path):
    (tmp_path / "README.md").write_text("## 2030-10-01\ntags: example\n", encoding="utf-8")
    (tmp_path / "2030-10.md").write_text(MONTH, encoding="utf-8")
    j = journal.load(tmp_path)
    assert date(2030, 10, 1) not in j.entries
    assert date(2030, 10, 23) in j.entries


def test_check_line_mentions_journal(tmp_path: Path):
    j = write(tmp_path)
    note = check.journal_note(j, [date(2030, 10, 22), date(2030, 10, 23), date(2030, 10, 24)])
    assert note == (" Journal: 2030-10-22 illness, injury; 2030-10-23 party, alcohol, outdoors, illness, injury;"
                    " 2030-10-24 illness, injury.")
    assert check.journal_note(None, [date(2030, 10, 23)]) == ""
