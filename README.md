# Garmin sync

Your own Garmin data, downloaded every morning into JSON files in **your own private GitHub repo**, with a dashboard of charts and an automatic daily check for unusual values. Claude Code can then work on top of it: a weekly summary, or questions like "how did I sleep before big meetings?".

- Source: the official [Garmin Connect Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api), using Garmin's SDK [`garmin-connect-personal-api-python`](https://github.com/garmin/connect-personal-api-python).
- The Personal API is for one person's own data, not for building a service for other users.
- Read-only. Nothing is ever written to Garmin.
- No server, no third-party service: GitHub Actions runs the download, the data stays in your repo.

```
Garmin Personal API ──(GitHub Action every morning, last 7 days)──► data/<dataset>/<year>/<YYYY-MM-DD>.json
                                                                     │
                                  reports/dashboard.md (charts) ◄────┤
                                  Claude Code routines (optional) ◄──┘
```

## Setup (about 10 minutes)

> **Keep your copy private.** It will hold your health data, and git keeps it in history forever. Create it from the template as **Private**. Do **not** fork: a fork of a public repo is public.

1. **Create your repo:** on this page click **Use this template → Create a new repository**, pick a name and choose **Private**.
2. **Create a Garmin key:** on the Garmin Connect website open [Personal API token](https://connect.garmin.com/app/settings/personalApiToken) and create a key valid for 1 year. It is shown only once.
3. **Store the key as a secret:** in your new repo go to **Settings → Secrets and variables → Actions → Secrets → New repository secret**. Name `GARMIN_PERSONAL_API_KEY`, value the key. Never paste the key into a chat, issue or file.
4. **Store the expiry date:** same page, **Variables** tab → **New repository variable**. Name `GARMIN_KEY_EXPIRES`, value the key's **expiry** date as `YYYY-MM-DD` (one year from today, not today). The sync starts warning 30 days before.
5. **Time zone (optional):** variable `GARMIN_TZ`, e.g. `Europe/London`. Default `Europe/Prague`. It decides what "today" is.
6. **First fill:** **Actions → Garmin sync → Run workflow**, set `days` to `365` (up to `1095` = 3 years). It takes a few minutes because of Garmin's rate limit.
7. Done. It now runs every morning at 04:17 UTC. If something fails (for example an expired key), the run goes red and GitHub emails you.

**Check it:** open `reports/dashboard.md` in your repo and compare a few values with the Garmin Connect app (sleep score, resting heart rate). They should match exactly.

## Data

| Folder | What | Max days per request |
|---|---|---|
| `daily_summary` | daily summary: calories burned, steps, resting/max heart rate, stress, Body Battery, intensity minutes, hydration goal | 365 |
| `sleep` | sleep summary incl. sleep score and stages | 31 |
| `hrv` | overnight HRV | 31 |
| `stress` | daily stress | 28 |
| `steps` | daily steps | 28 |
| `body_battery` | Body Battery with sleep/activity events | 31 |
| `weight` | weight (only days with a measurement) | 31 |
| `hydration` | water intake (only if you log it) | 31 |
| `food_logs` | food logged in Garmin Connect (only days with entries) | per day |
| `activities/<year>/<day>-<id>.json` | activity summaries (not .FIT files; may include GPS start/end coordinates) | paged |

- **A missing file means Garmin returned nothing for that day** (watch not worn or not synced). It is not zero. Nights without the watch are skipped.
- **Why 7 days every morning:** watches sync late and Garmin recalculates past days. A file is rewritten only when its content changes, so each daily commit shows what actually changed.
- **Rate limit:** Garmin allows about 100 requests per minute. The sync pauses 0.65 s between requests and, on HTTP 429, waits as long as Garmin says.
- **Calories eaten:** Garmin only has them if you log food in Garmin Connect. The `food_logs` shape with real entries has not been verified yet; if the sync reports an unknown shape, the data is not saved wrongly, it is reported.

## Journal

`journal/` holds your context for the data: party, alcohol, illness, injury, travel. A day entry goes to `journal/<YYYY-MM>.md` (`## YYYY-MM-DD`, `tags: …`, text), longer states to `journal/periods.md`. Easiest: tell Claude "add to my journal: …". Format and tags: `CLAUDE.md`. The daily check and the dashboard show the tags; the optional HRV analysis compares nights with and without them.

## Dashboard

[`reports/dashboard.md`](reports/dashboard.md): yesterday's values against your own 28-day median, 90-day charts (sleep score and duration, HRV, resting heart rate, Body Battery, stress, steps), a one-year trend of weekly medians (HRV, resting heart rate, sleep score and duration) and recent activities. It is regenerated after every sync from the data in the repo; nothing is sent anywhere. GitHub renders it on the web and in the mobile app.

Locally: `python -m garmin_sync.dashboard`.

## Daily check

After every sync, `garmin_sync/check.py` compares yesterday and the day before with your 28-day median. A clear deviation that lasts both days is written to `reports/daily/<YYYY-MM>.md` and shown as a warning in Actions. Rules are in `CLAUDE.md`. No Claude involved, no cost.

## Agents (optional)

Rules for agents are in [`CLAUDE.md`](CLAUDE.md): data never leaves the repo, comparisons are against your own baseline, every claim has a number and a date, no diagnoses.

For a weekly summary, create a routine in claude.ai → **Routines → New routine** and select **your repo as the source** (a routine without the repo as its source cannot reach the data):

- **Weekly summary** (Monday morning): "Write the weekly summary for the ISO week that just ended into reports/YEAR-WWEEK.md (e.g. reports/2030-W43.md) as described in CLAUDE.md. Back every claim with a number and a date, a missing day is not zero, no diagnoses. Commit only that file to main and push. Never send the data outside the repo."

Optional, described in `CLAUDE.md`:

- **HRV analysis:** add "Include the HRV analysis." to the prompt. It compares your best and worst nights of the last 28 and what came before them, and suggests at most 2 things to try, based only on your data.
- **Calendar:** add only the **Google Calendar** connector to the routine (and no others: the fewer connectors, the fewer ways for health data to leave). The summary then includes daily meeting load, never meeting titles or attendees.

Note: the routine form may swallow text in angle brackets such as `<year>`, so the prompt above uses YEAR-WWEEK instead.

## Local development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
GARMIN_PERSONAL_API_KEY=… python -m garmin_sync.sync --days 7
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `GARMIN_PERSONAL_API_KEY is missing` | The secret is not set, or has a different name. |
| `Garmin rejected the key (HTTP 401/403)` | The key expired or was deleted. Create a new one and replace the secret. |
| Warning "key expires … in 0 days" | `GARMIN_KEY_EXPIRES` holds the creation date. Set the expiry date. |
| `unknown response shape` | Garmin changed or has an unverified format. Nothing wrong was saved; open an issue or fix `garmin_sync/datasets.py`. |
| Push rejected | Two runs overlapped. The next run catches up. |

## License

MIT, see [LICENSE](LICENSE).
