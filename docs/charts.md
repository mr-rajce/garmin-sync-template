# How to read the charts

The dashboard (`reports/dashboard.md`, or the [sample with made-up data](sample/dashboard.md)) compares you with **yourself**: every number sits next to your own median of the 28 days before it, not next to population norms. Garmin's own scores and ranges are its estimates; use them for trends, not as measurements to the decimal.

## Common to all charts

- **Blue line and dots**: the daily value.
- **Grey dashed line**: the median of the previous 28 days (shown once at least 7 of them have data). It moves slowly, so a single bad night barely shifts it.
- **A gap in the line**: a day without data (watch not worn or not synced). It is never zero.
- **Last 90 days**, dates on the x axis are the first of each month.
- The last 7 days can still change (Garmin recalculates), and today is incomplete, so the table at the top shows **yesterday**.
- **Table at the top**: yesterday, its 28-day median and the difference. Whether a difference is good depends on the metric (higher HRV is usually better, a higher resting heart rate usually is not).

<a id="sleep_score"></a>
## Sleep score

Garmin's 0–100 score for the night that ended that morning (`data/sleep`, field `sleepScores.overall.value`). It combines duration, sleep stages, restlessness and stress during sleep. Read it with sleep duration: a short night with a high score and a long night with a low score mean different things.

<a id="sleep_hours"></a>
## Sleep duration

Hours asleep in the night that ended that morning (`sleepTimeSeconds`), without awake time. A night counts for the day you woke up, so a late evening shows up on the next date.

<a id="hrv"></a>
## HRV (overnight average)

Heart rate variability: how much the time between heartbeats varies, averaged over the night (`data/hrv`, field `lastNightAvg`, in milliseconds). It differs a lot between people, so only your own trend matters. Compared with your own baseline, lower values often follow hard training, short or late sleep, alcohol, illness or stress; higher values often come with rest and regular sleep. One low night is common; several in a row are worth a look in the journal.

<a id="resting_hr"></a>
## Resting heart rate

Garmin's resting heart rate for the day (`data/daily_summary`, field `heartRate.restingValue`, beats per minute). It usually moves opposite to HRV: a few beats above your median for several days often goes with the same causes as a low HRV.

<a id="body_battery"></a>
## Body Battery max

The highest Body Battery of the day (`bodyBattery.maxValue`, 0–100), usually reached after waking. It shows how well the night recharged you: a low maximum after a normal-length night points at a restless night.

<a id="stress"></a>
## Average stress

Garmin's average stress level for the day (`stress.avgLevel`, 0–100), estimated from heart rate variability while you are not moving. Physical activity is excluded, so a high value on a quiet day often means mental load, illness or a late night.

<a id="steps"></a>
## Steps

Steps for the day (`data/steps`, field `totalSteps`). Useful as context: a day with few steps and high stress reads differently from a day with a long hike.

<a id="trend"></a>
## Year: weekly medians

One point per week (Monday to Sunday): the median of that week, when it has at least 4 days with data. Daily values jump around; the weekly median shows the slow trend over seasons, holidays or a training block. The text under each chart names the highest and the lowest week. The current week is usually incomplete.

## Daily check

`reports/daily/<YYYY-MM>.md`, written by the morning run (`garmin_sync/check.py`). An entry appears only when **two days in a row** are clearly off **in the unfavourable direction**: lower HRV, sleep or Body Battery, higher resting heart rate or stress. "Clearly" means more than twice your usual spread (MAD), with a minimum per metric (sleep 0.75 h, score 8, HRV 6 ms, heart rate 3, stress 6, Body Battery 10). Journal tags of those days and the day before are added, because an evening event shows up in the next night. It also notes when no data arrived for more than 3 days.

## Journal

Tags from `journal/` (party, alcohol, illness…) are listed under the charts and in the daily check. A tag explains a deviation; it does not hide it. See `CLAUDE.md`, section Journal.

## Artifact dashboard (optional)

If you turned on the optional private Claude artifact, it shows the same metrics with hover values and two extra views:

- **Weeks and months**: the median of each metric per ISO week or calendar month, how many days had data and how often each journal tag appeared. Bars show HRV.
- **Course of the day**: heart rate (about every 2 minutes) and Body Battery (every 15 minutes) through a chosen day of the last 60 days, with activities as grey bands. Useful for "what happened on Tuesday afternoon".
