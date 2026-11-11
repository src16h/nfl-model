# Weekly model review: rules

Every Tuesday morning a scheduled review goes through every part of every model (NFL, NHL, NBA, CFB, Soccer) and
makes only the adjustments the evidence supports. This file is the rulebook. Change it only on purpose.

## Order of work
1. **Pipes first.** Last 7 days of GitHub runs for every workflow (`gh run list`): any failures, fix them.
   Odds credits left on each key. Data freshness (the review flags stale data).
2. **Last week's changes.** Read `docs/review/CHANGES.md`. For each change due for a look, compare before and after
   and keep, adjust or undo it. Note the outcome in that entry.
3. **The scorecard.** Run `python tools/weekly_review.py` and read `docs/review/latest.md`. Every flag gets a look,
   including every prop diagnosis (a single prop type can also be checked with
   `python tools/prop_diagnose.py <nfl|nhl|nba|cfb> <stat> <Over|Under>`).
4. **Deeper checks** where flagged, and on the first review of each month for every sport:
   - CFB: `python tools/cfb_edge_check.py` (model weight vs the close; early totals vs the open)
   - NBA: `python tools/nba_backtest.py`, `python tools/nba_props_check.py 2025 6`
   - NFL / NHL / Soccer: the backtest and calibration numbers each run already publishes (Record tabs, `latest.json`)
   - Parlays in every sport: tickets said vs hit, legs said vs hit, by leg type where tracked
   - Bettable markets: legs and plays must be on lines Hard Rock actually lists (`tools/probe_nba_alts.py` and the
     "Odds market check" workflow show its ladders). Anything not bettable is a bug.
5. **Changes**, within the limits below. Then run each changed sport's workflow and confirm it succeeds and the page
   still loads.
6. **Report**: `docs/review/latest.md` plus a short summary of what changed and why.

## What counts as evidence
- **Plays vs leans.** "Every pick" records are leans on every game, not bets. A losing lean record is a reason to
  look, never by itself a reason to change a play rule.
- **Pause a bet type** (or tighten it): closing-line value negative over 30+ priced plays; or 25+ graded plays at a
  return of -8% or worse that is too big to be luck (z <= -2) or has lasted 150 plays. Prefer the gates in `gates.py`
  (they pause and restore on their own, on exactly these bars since Nov 11 2026); check they are doing it before adding
  a manual rule.
- **Game plays are judged together.** Every sport's game plays come from one rule (Pinnacle calls the price value, the
  model agrees), so `gates.pooled` pools their priced plays: 30+ averaging below 0 at the close (z <= -1.5) pauses game
  plays in every sport, and 40 priced shadow plays averaging 0 or better bring them back. Don't override it by hand.
- **Closing prices come first.** A bet type without closing prices can't be judged in weeks. The scorecard prints
  "prop plays with a closing price: x of y" per sport; under 60% is a pipes problem to fix before anything else.
- **Never just pause a prop type.** Every prop type that is losing (20+ plays, -8% or worse) or paused gets a
  diagnosis (`tools/prop_diagnose.py`, included in the scorecard): projection bias, calibration, edge size, plays vs
  all leans, price paid, line movement, line size / role, zeros, clustering, trend. Read the causes and check them
  against the data:
  - when a cause is clear and fixable (a level bias, overconfidence, heavy juice, low-line players, too many plays a
    night), fix that cause in the model or the play rule, log it, and let the gate's shadow plays test the fix before
    the type comes back;
  - when no cause stands out, it is the model having no edge there: keep it paused and say so in the report;
  - write the diagnosis and the decision in CHANGES.md either way.
- **Recalibrate** a probability (props, parlay legs, a leg type): said vs hit gap of 5+ points over 100+ graded, or 8+
  points over 20+ tickets. Move halfway toward the real rate, not all the way.
- **Loosen a rule or un-pause:** only with 40+ graded results over 3+ weeks, return positive, and closing-line value
  not negative over 15+ priced plays (no closing prices, no comeback). Never on one good week.
- **Model changes** (features, weights, simulation settings): only with a walk-forward test on past seasons that beats
  the current setting out of sample. Write the before / after numbers in CHANGES.md.

## Limits
- At most 3 changes per sport per week. Small steps. The scorecard counts the entries in CHANGES.md and flags a sport
  that is over.
- Code changes: `python -m pytest tests -q` must pass (the Tests workflow runs it on every pull request), and library
  versions in `requirements.txt` are exact; change one on purpose, never by accident.
- No change to secrets, to odds-credit budgets beyond what the month allows, or to workflow schedules unless a run is
  failing or credits run out.
- Hard Rock as the bet price (`standin.py`, no prediction markets) and Pinnacle as the referee stay. The owner bets on
  Hard Rock; don't bring Kalshi or DraftKings Predictions back.
- If something looks wrong but the evidence is thin, write it under "Watch" in CHANGES.md instead of changing it.

## CHANGES.md entry format
```
## 2026-11-03 (weekly review)
- NHL | what changed | evidence (record, sample, z or CLV) | expected effect | look again on YYYY-MM-DD
Watch: ...
Last week's changes: kept / adjusted / undone, with the numbers
```
