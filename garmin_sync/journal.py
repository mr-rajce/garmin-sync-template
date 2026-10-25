"""Journal: the owner's context for the data (party, illness, injury…) in journal/.

- journal/<YYYY-MM>.md: entries per day, `## YYYY-MM-DD`, a line `tags: a, b`, then free text.
- journal/periods.md: table of longer states `| from | to | tag | note |` (empty "to" = ongoing).
The format is described in CLAUDE.md, section Journal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

PERIODS_FILE = "periods.md"
_MONTH_FILE = re.compile(r"\d{4}-\d{2}\.md")
_DAY = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$", re.M)
_TAGS = re.compile(r"^tags:\s*(.*)$", re.M | re.I)
_ROW = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\d{4}-\d{2}-\d{2})?\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|", re.M)


@dataclass
class Entry:
    tags: list[str] = field(default_factory=list)
    text: str = ""


@dataclass(frozen=True)
class Period:
    start: date
    end: date | None  # None = ongoing
    tag: str
    note: str

    def covers(self, day: date) -> bool:
        return self.start <= day and (self.end is None or day <= self.end)


def _tags(raw: str) -> list[str]:
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def parse_entries(text: str) -> dict[date, Entry]:
    out: dict[date, Entry] = {}
    matches = list(_DAY.finditer(text))
    for i, m in enumerate(matches):
        body = text[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        entry = out.setdefault(date.fromisoformat(m.group(1)), Entry())
        tags = _TAGS.search(body)
        if tags:
            entry.tags += [t for t in _tags(tags.group(1)) if t not in entry.tags]
            body = body[: tags.start()] + body[tags.end() :]
        note = " ".join(body.split())
        entry.text = f"{entry.text} {note}".strip() if note else entry.text
    return out


def parse_periods(text: str) -> list[Period]:
    return [
        Period(date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2)) if m.group(2) else None,
               m.group(3).strip().lower(), m.group(4).strip())
        for m in _ROW.finditer(text)
    ]


@dataclass
class Journal:
    entries: dict[date, Entry] = field(default_factory=dict)
    periods: list[Period] = field(default_factory=list)

    def tags(self, day: date) -> list[str]:
        """Tags of a day: from its entry and from periods covering it (no duplicates, in order)."""
        out = list(self.entries[day].tags) if day in self.entries else []
        for period in self.periods:
            if period.covers(day) and period.tag not in out:
                out.append(period.tag)
        return out


def load(journal_dir: Path) -> Journal:
    """Load the whole journal. A missing folder = an empty journal."""
    journal = Journal()
    if not journal_dir.is_dir():
        return journal
    for path in sorted(journal_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if path.name == PERIODS_FILE:
            journal.periods += parse_periods(text)
        elif _MONTH_FILE.fullmatch(path.name):
            for day, entry in parse_entries(text).items():
                existing = journal.entries.setdefault(day, Entry())
                existing.tags += [t for t in entry.tags if t not in existing.tags]
                existing.text = f"{existing.text} {entry.text}".strip()
    return journal
