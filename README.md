# Injury watch

Daily NFL injury monitoring, volume-beneficiary mapping, and prop line tracking.
Free nflverse data, no API keys.

## Setup

```
pip install nflreadpy pandas pyarrow
python injury_watch.py build-map      # once, then weekly
```

## Daily

```
python3 dashboard.py
```

Writes `dashboard.html` and opens it in your browser. Everything lives there:
what changed overnight, every skill player on the report, and where each one's
volume goes if he sits. Click any player to expand.

The header shows when the nflverse feed last updated. If that timestamp is not
today's date, you are looking at stale data.

Terminal version, same data:

```
python3 injury_watch.py snapshot
```

Saves a dated injury snapshot, diffs it against the last one, and prints status
changes (WORSE / BETTER / NEW), skill players first. For each skill player who
got worse, it lists who absorbed his volume before, and whether you have a line
logged on that beneficiary.

## Line tracking

```
python injury_watch.py log --team LV --player "Michael Mayer" \
    --market rec_yds --line 28.5 --over -110 --under -120
python injury_watch.py lines
```

Log the same player again each day. The tool shows movement from your first
entry, and flags LINE UNMOVED when a starter's status worsened but the
beneficiary's price has not reacted yet. That flag is the whole point.

Markets are free text. Stay consistent: rec_yds, rec, rush_yds, pass_yds, ru_re_yds.

## The week

| Day | What lands | What to do |
|---|---|---|
| Mon | Coach presser, MRI results, IR moves | Softest info, softest prices |
| Tue | Players off, quiet | Last cheap day |
| Wed | First official practice report | Biggest price move happens here |
| Thu | Second report | |
| Fri | Final report and designation | Prices are sharp |
| Sun | Inactives, 90 min pre-kick | Last call |

The trade is Monday and Tuesday. Log the beneficiary's line as soon as it posts
so you have a baseline to measure against.

## How absence is detected

Weekly roster status, where ACT means active, INA means inactive, and RES means
injured reserve. A player is counted absent only in weeks he was rostered and
listed INA or RES. Mid-season signings and season-ending injuries are both
handled, and nothing is keyed on name spelling.

## Reading the output

`n=4/8` means the split rests on 4 games without and 8 games with.

`[anecdote]` means two games or fewer. Around half the rows carry that flag, so
treat the map as a ranking of who is next in line rather than as a projection of
how much they gain.

A player who has never missed a game has no row. Use the depth chart for those.

## Projecting volume for anyone

```
python injury_watch.py project --team CIN --player "Chase" --metric targets
```

Works for every player, including ones who have never missed a game. It takes
the injured player's share and redistributes it across teammates weighted by
their existing share and their position, then reports each man's projected share
and percentage volume increase.

Early in the season this runs on last year's usage, which the output labels.
Players no longer on the roster are excluded and named.

Where a player does have absence history, run `beneficiaries` too and compare.
The model spreads volume smoothly; real coaches concentrate it. For Bowers the
model gives Mayer +29% volume while the actual games without him gave +14 points
of target share. When the two disagree, the real games win.

The position weights in `DEFAULT_AFFINITY` are judgment, not fitted. Edit them
as you learn what individual offences do.

## The bet

Buying a beneficiary's over early is paying a low price on a role expansion that
may not happen. It only works when the chance of the starter sitting exceeds
what the price implies. If the starter suits up, the beneficiary reverts.

Middle: over 48.5 on Tuesday, starter ruled out Friday, line now 62.5, take the
under at 62.5. Anything between pays both.

## Known limits

- The injury table holds one row per player per week, so the Wed/Thu/Fri
  progression is not in the source. Your daily snapshots build it. Confirm the
  feed actually refreshes mid-week by comparing consecutive runs.
- No practice reports exist Monday or Tuesday. Those days rely on coach pressers
  and beat writers, and stay manual.
- Rest days are now detected. The feed labels them "Not injury related -
  resting player", and a pure maintenance day is demoted out of the alerts. A
  rest day attached to a real ailment still counts.
- Snap share falls back to last season early in the year, marked in the output.
- Share splits ignore game script. A backup whose share rose in a blowout is
  measuring the blowout.
