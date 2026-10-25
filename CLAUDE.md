# Garmin data: instructions for agents

Personal health and fitness data of one person (the owner of this repo) from Garmin. Write outputs in the language the owner uses with you; if unsure, English.

## Privacy (never break)

- **Never send the data or excerpts of it outside this repo**: no web services, issues, comments in other repos, chat tools.
- Outputs belong only in `reports/` in this repo.
- Never commit the key or a token (`GARMIN_PERSONAL_API_KEY`).

## Data

- `data/<dataset>/<year>/<YYYY-MM-DD>.json` = raw item from the Garmin Personal API for one (local) day. Datasets and endpoints: table in `README.md`.
- `data/activities/<year>/<YYYY-MM-DD>-<activityId>.json` = summary of one activity.
- A missing file = Garmin returned nothing for that day (watch not worn, not synced). **It is not zero.**
- Take field names from the files, not from memory. Before computing anything, open one file of the dataset and look at its fields.
- The last 7 days can still change (Garmin recalculates), today is usually incomplete. Evaluate "yesterday" and older.

Easiest queries via DuckDB (`pip install -e '.[analysis]'`):

```python
import duckdb
duckdb.sql("""
  select *
  from read_json_auto('data/sleep/*/*.json', union_by_name=true)
  order by calendarDate desc limit 14
""").show()
```

## Journal (the owner's context)

The repo is also a journal: the watch data shows *what* happened, the journal *why*. It lives in `journal/` (read by `garmin_sync/journal.py`):

- `journal/<YYYY-MM>.md`: a day entry = heading `## YYYY-MM-DD`, a line `tags: a, b` and free text (time, how much, how they felt).
- `journal/periods.md`: table `| from | to | tag | note |` for states lasting several days (illness, injury, travel, holiday, medication). Empty "to" = ongoing.
- Suggested tags (lowercase, hyphenated): `alcohol`, `party`, `late-meal`, `caffeine-evening`, `stress`, `illness`, `injury`, `medication`, `travel`, `holiday`, `sauna`, `outdoors`. Custom tags are fine, but prefer these where they fit.
- **When the owner says "add to my journal…"**: write it exactly as they said it into the right month file (or `periods.md`), with tags from this list, commit and push to main. Do not embellish; if the date does not match the watch data, write their version and mention the mismatch separately.
- When evaluating: a tag explains, it does not excuse. Still report the deviation with numbers and add the tag. An evening event shows up in the night and the next morning.
- The journal is as sensitive as the data (illness, medication): section Privacy applies.

## How to evaluate

- **Compare with the owner's own baseline, not population norms:** the default baseline is the median of the 28 days before the evaluated period.
- A deviation is worth mentioning when it is clear and lasts 2+ days (one bad day is noise).
- Back every claim with a number and a date (for example "HRV 41 ms on 3 and 4 March, 28-day median 52 ms").
- When data is missing or incomplete, say so. Do not fill in or estimate.
- **No diagnoses or medical advice.** For a long, clear deviation (e.g. resting heart rate 10+ bpm higher for a week) only say it is worth discussing with a doctor.

## Weekly summary

File `reports/<year>-W<week>.md` (the ISO week that just ended). At most one screen:

1. **Summary**: 2–3 sentences on how the week went.
2. **Numbers**: table by day: sleep (h), HRV, resting heart rate, steps, Body Battery max, activities; last row the 28-day median.
3. **What changed**: only clear deviations from the baseline, with numbers.
4. **What to focus on**: at most 2 concrete things for next week, derived from the data.
5. **Missing data**: days and datasets without data.

## Optional: HRV analysis

Only when the owner asks for it (e.g. "include the HRV analysis" in the routine prompt). Add a section **HRV: what came before better and worse nights** to the weekly summary:

- Take the last 28 nights (`data/hrv`, field `lastNightAvg`). Compare the quarter of nights with the highest HRV against the quarter with the lowest.
- For each night look at the day and night before: sleep duration and bedtime (`data/sleep`), average stress and Body Battery (`data/daily_summary`), steps, activities and their timing (`data/activities`, training after 18:00 separately), and work load if the calendar is available (section Optional: calendar).
- For each night also list the journal tags of that day and the day before (section Journal). When a tag has at least 3 nights, compare HRV after nights with and without it.
- Report only differences that are visible between the groups, with numbers (e.g. "nights with HRV above 60 ms: median sleep 7.6 h; below 45 ms: 5.9 h"). With few nights, say it is only a hint.
- From that, at most 2 concrete things to try next week, derived only from the owner's data, no generic advice.
- Check whether the things suggested in the previous summary (previous file in `reports/`) showed up: compare last week's HRV with the median of the 4 weeks before.
- Still no diagnoses or medical advice.

## Optional: calendar

Only when the routine has a Google Calendar connector. Use it read-only, for the owner's calendar over the evaluated period and the 28 days before:

- Write to the repo **only daily aggregates**: number of meetings, hours in meetings, end of the last meeting, meetings after 18:00, all-day events such as travel or holiday. **Never titles, descriptions, locations or attendees** (that is data about other people too).
- Never write to or change the calendar. Never send Garmin data to the calendar or anywhere else.
- Without the connector or without access, skip this and say why.

## Daily check

Done automatically by the GitHub Action after every sync (`garmin_sync/check.py`), without an LLM. Rules:

- Yesterday and the day before against the median of the 28 days before each: sleep (duration, score), HRV, resting heart rate, stress, Body Battery.
- Only a deviation that lasts both days in the unfavourable direction is reported (lower HRV/sleep/Body Battery, higher heart rate/stress).
- Clear = larger than 2× the spread (MAD × 1.4826), at least: sleep 0.75 h, score 8, HRV 6 ms, heart rate 3, stress 6, Body Battery 10.
- If no daily summary arrived for more than 3 days, that is reported (expired key, watch not syncing).
- The entry goes to `reports/daily/<YYYY-MM>.md`; otherwise nothing is written.

Agents do not run it. In the weekly summary, take that week's entries in `reports/daily/` into account.

## Dashboard

`reports/dashboard.md` and `reports/charts/*.svg` are generated by `garmin_sync/dashboard.py` after every sync. Do not edit them by hand; change the code. You can quote its numbers, but verify them against the files in `data/`.

## Development

- `pip install -e '.[dev]' && pytest` must pass before every push.
- Logic lives in pure functions (`garmin_sync/store.py`, `garmin_sync/dashboard.py`); network access only in `garmin_sync/sync.py` → `main()`.
- A new dataset = an entry in `garmin_sync/datasets.py` + a test with the response shape + a row in the table in `README.md`.
