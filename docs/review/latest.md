# Weekly model review, 2026-11-17

Flags first (high, then medium, then info). Every number is a graded record from the site's own data.

| Level | Sport | What | Why |
|---|---|---|---|
| high | CFB | losing: picks / total | 49-67, -22.69u, -19.6% (z -2.22) |
| high | CFB | said vs hit: calibration / rec | said 49.2%, hit 55.3% over 804 (z 3.46) |
| high | NBA | losing: picks / ml | 55-69, -25.5u, -20.6% (z -2.41) |
| high | NFL | said vs hit: alt_leg_types / QB pass attempts Over | said 77.0%, hit 63.0% over 127 (z -3.75) |
| high | NFL | said vs hit: alt_leg_types / QB completions Over | said 78.2%, hit 69.4% over 160 (z -2.7) |
| high | NHL | losing: picks / ml | 116-161, -49.65u, -17.9% (z -3.14) |
| high | NHL | said vs hit: calibration / saves | said 50.0%, hit 32.9% over 513 (z -7.75) |
| medium | All | backup runs re-ran: cfb.yml | 4 late cron runs ran the model; when the Clock already ran that slot this is a duplicate that spends odds credits |
| medium | All | backup runs re-ran: nba.yml | 8 late cron runs ran the model; when the Clock already ran that slot this is a duplicate that spends odds credits |
| medium | All | backup runs re-ran: nhl.yml | 6 late cron runs ran the model; when the Clock already ran that slot this is a duplicate that spends odds credits |
| medium | All | backup runs re-ran: soccer.yml | 4 late cron runs ran the model; when the Clock already ran that slot this is a duplicate that spends odds credits |
| medium | All | backup runs re-ran: weekly.yml | 5 late cron runs ran the model; when the Clock already ran that slot this is a duplicate that spends odds credits |
| medium | CFB | losing: picks / spread | 50-65, -19.61u, -17.1% (z -1.92) |
| medium | CFB | losing: picks / ml | 53-57, -10.01u, -9.1% (z -1.0) |
| medium | CFB | losing: plays | 10-15, -5.97u, -23.9% (z -1.26) |
| medium | CFB | parlays losing even at the bet-at price: alt | 14-23, -3.97u (-10.7%) at the shortest price the page says to take |
| medium | CFB | over the change limit | 12 changes logged in the last 7 days (limit 3): no more this week unless something is broken |
| medium | NBA | over the change limit | 12 changes logged in the last 7 days (limit 3): no more this week unless something is broken |
| medium | NBA | diagnosed: pts Unders | plays 9-11 (-15.4%); top cause: Projection bias: results ran 1.69 above the model's middle number on 1167 pts props, while the book's line missed by only +0.10. The model's |
| medium | NFL | odds credits low | 57 left this month |
| medium | NFL | said vs hit: tds / Anytime TD / bins / 5 | said 69.8%, hit 77.8% over 27 (z 0.91) |
| medium | NFL | said vs hit: alt_parlays / by_v / 2 (tickets) | said 55.2%, hit 47.1% over 34 (z -0.95) |
| medium | NFL | said vs hit: alt_leg_types / RB carries Under | said 81.5%, hit 71.1% over 38 (z -1.65) |
| medium | NFL | parlays losing even at the bet-at price: alt_parlays | 16-18, -3.01u (-8.9%) at the shortest price the page says to take |
| medium | NFL | over the change limit | 16 changes logged in the last 7 days (limit 3): no more this week unless something is broken |
| medium | NFL | diagnosed: pass_yds Overs | plays 3-3 (-5.2%); top cause: Overconfidence: the model gave the bet side 65.8% and it hit 50.6% over 81. Shrink this prop type's chance toward the book's (betrules reali |
| medium | NFL | diagnosed: pass_yds Unders | plays 3-2 (13.9%); top cause: Overconfidence: the model gave the bet side 60.9% and it hit 43.3% over 67. Shrink this prop type's chance toward the book's (betrules reali |
| medium | NFL | diagnosed: rec Overs | plays 8-17 (-34.7%); top cause: Overconfidence: the model gave the bet side 52.3% and it hit 32.0% over 25. Shrink this prop type's chance toward the book's (betrules reali |
| medium | NFL | diagnosed: rec Unders | plays 10-11 (-13.7%); top cause: Role / volume: lines over 2.5 did much worse (30.0% vs 63.6%). High lines are stars the market prices sharply; the model adds little there. |
| medium | NFL | diagnosed: rec_yds Overs | plays 21-18 (2.0%); top cause: No flaw found, and the plays are at break-even or better. If this type is paused, the gate's shadow record decides when it comes back (40+ g |
| medium | NFL | diagnosed: rush_yds Overs | plays 2-4 (-37.5%); top cause: Overconfidence: the model gave the bet side 70.7% and it hit 44.1% over 236. Shrink this prop type's chance toward the book's (betrules real |
| medium | NHL | losing: picks / pl | 134-143, -28.65u, -10.3% (z -1.81) |
| medium | NHL | losing: picks / total | 131-146, -28.1u, -10.1% (z -1.78) |
| medium | NHL | said vs hit: alt_ladder (tickets) | said 57.8%, hit 65.9% over 44 (z 1.09) |
| medium | NHL | said vs hit: alt_hr (tickets) | said 66.0%, hit 56.5% over 23 (z -0.96) |
| medium | NHL | over the change limit | 13 changes logged in the last 7 days (limit 3): no more this week unless something is broken |
| medium | NHL | diagnosed: points Overs | plays 5-17 (-32.7%); top cause: No single cause stands out: the losses look like the model having no edge on this prop type rather than one fixable flaw. Keep it paused (sh |
| medium | NHL | diagnosed: points Unders | plays 106-104 (-4.8%); top cause: Overconfidence: the model gave the bet side 55.7% and it hit 34.2% over 38. Shrink this prop type's chance toward the book's (betrules reali |
| medium | Soccer | losing: picks / total | 51-59, -17.2u, -15.6% (z -1.73) |
| medium | Soccer | losing: picks_by_league / epl / 1x2 | 7-23, -5.03u, -16.8% (z -0.97) |
| medium | Soccer | losing: picks_by_league / epl / ah | 11-17, -2.7u, -9.6% (z -0.54) |
| medium | Soccer | losing: picks_by_league / epl / total | 15-15, -2.53u, -8.4% (z -0.49) |
| medium | Soccer | losing: picks_by_league / champ / total | 19-30, -12.71u, -25.9% (z -1.91) |
| medium | Soccer | losing: picks_by_league / laliga / ah | 13-17, -4.85u, -16.2% (z -0.93) |
| medium | Soccer | said vs hit: cross_parlays (legs) | said 80.4%, hit 88.9% over 36 (z 1.28) |
| medium | Soccer | over the change limit | 9 changes logged in the last 7 days (limit 3): no more this week unless something is broken |
| info | NFL | winning: live_record / picks / moneyline | 65-36, +9.99u, +9.9% (z 1.05) |

## Drawdowns and baselines

Every bet record in betting order (worst drop from a high point, longest losing run), and the model next to a dumb baseline on the same games. A record only counts as an edge if it beats the baseline.

| Sport | Record | Bets | Units | Return | Max drawdown | Longest losing run |
|---|---|---|---|---|---|---|
| NFL | game plays | 9 | -4.14 | -46.0% | -4.14u | 3 |
| NFL | prop plays | 161 | -0.03 | -0.0% | -21.51u | 7 |
| NHL | game plays (recent list only) | 60 | +7.02 | 11.7% | -8.0u | 8 |
| NHL | prop plays | 446 | -16.43 | -3.7% | -36.07u | 6 |
| NBA | game plays | 8 | -8.0 | -100.0% | -8.0u | 8 |
| NBA | prop plays | 75 | -0.53 | -0.7% | -10.89u | 6 |
| CFB | game plays | 25 | -5.97 | -23.9% | -6.4u | 6 |
| CFB | prop plays | 228 | +12.4 | 5.4% | -15.93u | 6 |
| Soccer | game plays | 24 | +6.95 | 29.0% | -4.0u | 4 |

| Sport | What | Model | Baseline |
|---|---|---|---|
| NFL | moneyline leans | 85 bets, +9.99u (11.7%) | always the favorite: 85 bets, +2.97u (3.5%) |
| NFL | prop plays | 161 bets, -0.03u (-0.0%) | every lean of the same types: 2183 bets, -60.41u (-2.8%) |
| NHL | moneyline leans | 277 bets, -49.65u (-17.9%) | always the favorite: 277 bets, +5.23u (1.9%) |
| NHL | moneyline plays | 23 bets, +4.47u (19.4%) | always the favorite: 23 bets, -3.02u (-13.1%) |
| NHL | prop plays | 446 bets, -16.43u (-3.7%) | every lean of the same types: 5315 bets, -181.66u (-3.4%) |
| NBA | moneyline leans | 124 bets, -25.5u (-20.6%) | always the favorite: 124 bets, +7.33u (5.9%) |
| NBA | moneyline plays | 3 bets, -3.0u (-100.0%) | always the favorite: 3 bets, +0.38u (12.8%) |
| NBA | prop plays | 75 bets, -0.53u (-0.7%) | every lean of the same types: 1623 bets, -35.41u (-2.2%) |
| CFB | moneyline leans | 174 bets, +1.1u (0.6%) | always the favorite: 174 bets, -20.43u (-11.7%) |
| CFB | moneyline plays | 2 bets, -2.0u (-100.0%) | always the favorite: 2 bets, +0.13u (6.7%) |
| CFB | prop plays | 228 bets, +12.4u (5.4%) | every lean of the same types: 1734 bets, -56.71u (-3.3%) |
| Soccer | moneyline leans | 107 bets, -7.91u (-7.4%) | always the favorite: 107 bets, +0.08u (0.1%) |
| Soccer | moneyline plays | 4 bets, -0.4u (-10.0%) | always the favorite: 4 bets, +1.31u (32.8%) |

### Scheduled runs: how late each slot started (last 7 days)

First run of the workflow after each cron time (the Clock's dispatch, or a backup cron run). "Backups that ran" are late cron runs the guard let through: they re-run a covered slot and spend credits.

| Workflow | Slots | Median delay | Worst | Missed slots | Backups that ran |
|---|---|---|---|---|---|
| cfb.yml | 14 | 0 min | 0 min | 0 | 4 (11-16 23:26, 11-13 20:56, 11-12 21:29, 11-11 21:27) |
| nba.yml | 28 | 0 min | 0 min | 0 | 8 (11-17 09:42, 11-16 08:32, 11-15 08:24, 11-14 07:58) |
| nhl.yml | 28 | 0 min | 43 min | 0 | 6 (11-17 10:39, 11-16 09:34, 11-15 09:18, 11-14 08:56) |
| review.yml | 1 | 0 min | 0 min | 0 | 0 |
| soccer.yml | 19 | 0 min | 75 min | 0 | 4 (11-17 02:26, 11-12 21:03, 11-10 23:49, 11-10 20:34) |
| weekly.yml | 15 | 0 min | 0 min | 0 | 5 (11-16 22:50, 11-16 06:09, 11-13 20:26, 11-12 20:44) |


## Prop diagnoses
Every prop type that is losing (20+ plays, -8% or worse) or paused, with what's driving it.

### NFL pass_yds Overs
Plays 3-3 (-0.31u, -5.2%); every Over lean 41-40 (-4.3%). Checks use every lean on this side (too few plays).

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 65.8% and it hit 50.6% over 81. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 148,
  "actual_minus_model": -4.82,
  "actual_minus_line": 1.26,
  "over_rate_at_fair": 50.0,
  "over_rate_z": 0.0
 },
 "calibration_p_raw": {
  "n": 81,
  "said": 65.8,
  "hit": 50.6
 },
 "book_said": {
  "n": 81,
  "book": 50.0,
  "hit": 50.6
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 19,
   "w": 8,
   "l": 11,
   "pct": 42.1,
   "units": -3.89,
   "roi": -20.5
  },
  {
   "edge": "8-+",
   "n": 62,
   "w": 33,
   "l": 29,
   "pct": 53.2,
   "units": 0.4,
   "roi": 0.7
  }
 ],
 "plays_vs_leans": {
  "plays": {
   "n": 6,
   "w": 3,
   "l": 3,
   "pct": 50.0,
   "units": -0.31,
   "roi": -5.2
  },
  "all_leans": {
   "n": 81,
   "w": 41,
   "l": 40,
   "pct": 50.6,
   "units": -3.48,
   "roi": -4.3
  }
 },
 "price": {
  "avg_breakeven": 52.9,
  "hit": 50.6,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 207.5": {
   "n": 42,
   "w": 20,
   "l": 22,
   "pct": 47.6,
   "units": -4.19,
   "roi": -10.0
  },
  "> 207.5": {
   "n": 39,
   "w": 21,
   "l": 18,
   "pct": 53.8,
   "units": 0.71,
   "roi": 1.8
  }
 },
 "zeros": {
  "n": 1,
  "of": 81,
  "share": 1.2
 },
 "clustering": [
  {
   "date": "w04",
   "n": 15,
   "w": 8,
   "l": 7,
   "pct": 53.3,
   "units": 0.15,
   "roi": 1.0
  },
  {
   "date": "w09",
   "n": 13,
   "w": 2,
   "l": 11,
   "pct": 15.4,
   "units": -9.2,
   "roi": -70.8
  },
  {
   "date": "w06",
   "n": 12,
   "w": 7,
   "l": 5,
   "pct": 58.3,
   "units": 1.27,
   "roi": 10.6
  }
 ],
 "trend": {
  "early": {
   "n": 37,
   "w": 21,
   "l": 16,
   "pct": 56.8,
   "units": 2.77,
   "roi": 7.5
  },
  "recent": {
   "n": 44,
   "w": 20,
   "l": 24,
   "pct": 45.5,
   "units": -6.26,
   "roi": -14.2
  }
 }
}
```
</details>

### NFL pass_yds Unders
Plays 3-2 (+0.69u, 13.9%); every Under lean 29-38 (-18.2%). Checks use every lean on this side (too few plays).

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 60.9% and it hit 43.3% over 67. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.
2. Bigger edges did worse (36.4% at 8+ points vs 57% below): big gaps from the book usually mean news the model can't see (injury, role, lineup). Cap the edge for pass_yds lower.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 148,
  "actual_minus_model": -4.82,
  "actual_minus_line": 1.26,
  "over_rate_at_fair": 50.0,
  "over_rate_z": 0.0
 },
 "calibration_p_raw": {
  "n": 67,
  "said": 60.9,
  "hit": 43.3
 },
 "book_said": {
  "n": 67,
  "book": 50.0,
  "hit": 43.3
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 23,
   "w": 13,
   "l": 10,
   "pct": 56.5,
   "units": 1.55,
   "roi": 6.8
  },
  {
   "edge": "8-+",
   "n": 44,
   "w": 16,
   "l": 28,
   "pct": 36.4,
   "units": -13.77,
   "roi": -31.3
  }
 ],
 "plays_vs_leans": {
  "plays": {
   "n": 5,
   "w": 3,
   "l": 2,
   "pct": 60.0,
   "units": 0.69,
   "roi": 13.9
  },
  "all_leans": {
   "n": 67,
   "w": 29,
   "l": 38,
   "pct": 43.3,
   "units": -12.21,
   "roi": -18.2
  }
 },
 "price": {
  "avg_breakeven": 52.9,
  "hit": 43.3,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 244.5": {
   "n": 35,
   "w": 17,
   "l": 18,
   "pct": 48.6,
   "units": -2.89,
   "roi": -8.3
  },
  "> 244.5": {
   "n": 32,
   "w": 12,
   "l": 20,
   "pct": 37.5,
   "units": -9.32,
   "roi": -29.1
  }
 },
 "clustering": [
  {
   "date": "w08",
   "n": 12,
   "w": 7,
   "l": 5,
   "pct": 58.3,
   "units": 1.24,
   "roi": 10.4
  },
  {
   "date": "w09",
   "n": 12,
   "w": 4,
   "l": 8,
   "pct": 33.3,
   "units": -4.44,
   "roi": -37.0
  },
  {
   "date": "w10",
   "n": 10,
   "w": 5,
   "l": 5,
   "pct": 50.0,
   "units": -0.65,
   "roi": -6.5
  }
 ],
 "trend": {
  "early": {
   "n": 26,
   "w": 10,
   "l": 16,
   "pct": 38.5,
   "units": -7.07,
   "roi": -27.2
  },
  "recent": {
   "n": 41,
   "w": 19,
   "l": 22,
   "pct": 46.3,
   "units": -5.14,
   "roi": -12.5
  }
 }
}
```
</details>

### NFL rec Overs
Plays 8-17 (-8.68u, -34.7%); every Over lean 176-185 (-2.1%). Checks use plays.

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 52.3% and it hit 32.0% over 25. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 801,
  "actual_minus_model": 0.34,
  "actual_minus_line": 0.03,
  "over_rate_at_fair": 54.9,
  "over_rate_z": 2.5
 },
 "calibration_p_raw": {
  "n": 25,
  "said": 52.3,
  "hit": 32.0
 },
 "book_said": {
  "n": 25,
  "book": 46.6,
  "hit": 32.0
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 25,
   "w": 8,
   "l": 17,
   "pct": 32.0,
   "units": -8.68,
   "roi": -34.7
  }
 ],
 "plays_vs_leans": {
  "plays": {
   "n": 25,
   "w": 8,
   "l": 17,
   "pct": 32.0,
   "units": -8.68,
   "roi": -34.7
  },
  "all_leans": {
   "n": 361,
   "w": 176,
   "l": 185,
   "pct": 48.8,
   "units": -7.5,
   "roi": -2.1
  }
 },
 "price": {
  "avg_breakeven": 49.4,
  "hit": 32.0,
  "heavy_juice_share": 16.0
 },
 "line_size": {
  "<= 3.5": {
   "n": 16,
   "w": 6,
   "l": 10,
   "pct": 37.5,
   "units": -3.22,
   "roi": -20.1
  },
  "> 3.5": {
   "n": 9,
   "w": 2,
   "l": 7,
   "pct": 22.2,
   "units": -5.45,
   "roi": -60.6
  }
 },
 "zeros": {
  "n": 2,
  "of": 25,
  "share": 8.0
 },
 "clustering": [
  {
   "date": "w05",
   "n": 13,
   "w": 4,
   "l": 9,
   "pct": 30.8,
   "units": -5.72,
   "roi": -44.0
  },
  {
   "date": "w04",
   "n": 12,
   "w": 4,
   "l": 8,
   "pct": 33.3,
   "units": -2.95,
   "roi": -24.6
  }
 ]
}
```
</details>

### NFL rec Unders
Plays 10-11 (-2.87u, -13.7%); every Under lean 242-198 (3.1%). Checks use plays.

**Likely causes, most likely first:**
1. Role / volume: lines over 2.5 did much worse (30.0% vs 63.6%). High lines are stars the market prices sharply; the model adds little there.
2. Projection bias: results ran 0.34 above the model's middle number on 801 rec props, while the book's line missed by only +0.03. The model's level for rec is off; shift it up (or let the prop bias correction learn faster).

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 801,
  "actual_minus_model": 0.34,
  "actual_minus_line": 0.03,
  "over_rate_at_fair": 54.9,
  "over_rate_z": 2.5
 },
 "calibration_p_raw": {
  "n": 21,
  "said": 56.7,
  "hit": 47.6
 },
 "book_said": {
  "n": 21,
  "book": 51.4,
  "hit": 47.6
 },
 "by_edge": [
  {
   "edge": "0-4",
   "n": 1,
   "w": 1,
   "l": 0,
   "pct": 100.0,
   "units": 0.71,
   "roi": 71.4
  },
  {
   "edge": "4-8",
   "n": 20,
   "w": 9,
   "l": 11,
   "pct": 45.0,
   "units": -3.59,
   "roi": -17.9
  }
 ],
 "plays_vs_leans": {
  "plays": {
   "n": 21,
   "w": 10,
   "l": 11,
   "pct": 47.6,
   "units": -2.87,
   "roi": -13.7
  },
  "all_leans": {
   "n": 440,
   "w": 242,
   "l": 198,
   "pct": 55.0,
   "units": 13.64,
   "roi": 3.1
  }
 },
 "price": {
  "avg_breakeven": 54.5,
  "hit": 47.6,
  "heavy_juice_share": 14.0
 },
 "line_size": {
  "<= 2.5": {
   "n": 11,
   "w": 7,
   "l": 4,
   "pct": 63.6,
   "units": 1.35,
   "roi": 12.3
  },
  "> 2.5": {
   "n": 10,
   "w": 3,
   "l": 7,
   "pct": 30.0,
   "units": -4.22,
   "roi": -42.2
  }
 },
 "clustering": [
  {
   "date": "w04",
   "n": 12,
   "w": 7,
   "l": 5,
   "pct": 58.3,
   "units": 0.97,
   "roi": 8.1
  },
  {
   "date": "w05",
   "n": 9,
   "w": 3,
   "l": 6,
   "pct": 33.3,
   "units": -3.85,
   "roi": -42.7
  }
 ]
}
```
</details>

### NFL rec_yds Overs
Plays 21-18 (+0.78u, 2.0%); every Over lean 170-186 (-9.7%). Checks use plays.

**Likely causes, most likely first:**
1. No flaw found, and the plays are at break-even or better. If this type is paused, the gate's shadow record decides when it comes back (40+ graded over 3+ weeks, positive return, closing value not negative).

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 798,
  "actual_minus_model": 6.94,
  "actual_minus_line": 4.43,
  "over_rate_at_fair": 50.8,
  "over_rate_z": 0.43
 },
 "calibration_p_raw": {
  "n": 39,
  "said": 57.8,
  "hit": 53.8
 },
 "book_said": {
  "n": 39,
  "book": 49.9,
  "hit": 53.8
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 24,
   "w": 12,
   "l": 12,
   "pct": 50.0,
   "units": -1.23,
   "roi": -5.1
  },
  {
   "edge": "8-+",
   "n": 15,
   "w": 9,
   "l": 6,
   "pct": 60.0,
   "units": 2.01,
   "roi": 13.4
  }
 ],
 "plays_vs_leans": {
  "plays": {
   "n": 39,
   "w": 21,
   "l": 18,
   "pct": 53.8,
   "units": 0.78,
   "roi": 2.0
  },
  "all_leans": {
   "n": 356,
   "w": 170,
   "l": 186,
   "pct": 47.8,
   "units": -34.52,
   "roi": -9.7
  }
 },
 "price": {
  "avg_breakeven": 52.7,
  "hit": 53.8,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 32.5": {
   "n": 21,
   "w": 11,
   "l": 10,
   "pct": 52.4,
   "units": -0.13,
   "roi": -0.6
  },
  "> 32.5": {
   "n": 18,
   "w": 10,
   "l": 8,
   "pct": 55.6,
   "units": 0.91,
   "roi": 5.0
  }
 },
 "zeros": {
  "n": 1,
  "of": 39,
  "share": 2.6
 },
 "clustering": [
  {
   "date": "w06",
   "n": 14,
   "w": 9,
   "l": 5,
   "pct": 64.3,
   "units": 3.01,
   "roi": 21.5
  },
  {
   "date": "w05",
   "n": 13,
   "w": 3,
   "l": 10,
   "pct": 23.1,
   "units": -7.34,
   "roi": -56.5
  },
  {
   "date": "w04",
   "n": 12,
   "w": 9,
   "l": 3,
   "pct": 75.0,
   "units": 5.12,
   "roi": 42.6
  }
 ]
}
```
</details>

### NFL rush_yds Overs
Plays 2-4 (-2.25u, -37.5%); every Over lean 104-132 (-16.6%). Checks use every lean on this side (too few plays).

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 70.7% and it hit 44.1% over 236. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 436,
  "actual_minus_model": 1.13,
  "actual_minus_line": 2.94,
  "over_rate_at_fair": 41.5,
  "over_rate_z": -3.54
 },
 "calibration_p_raw": {
  "n": 236,
  "said": 70.7,
  "hit": 44.1
 },
 "book_said": {
  "n": 236,
  "book": 49.8,
  "hit": 44.1
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 40,
   "w": 12,
   "l": 28,
   "pct": 30.0,
   "units": -17.34,
   "roi": -43.3
  },
  {
   "edge": "8-+",
   "n": 196,
   "w": 92,
   "l": 104,
   "pct": 46.9,
   "units": -21.86,
   "roi": -11.2
  }
 ],
 "plays_vs_leans": {
  "plays": {
   "n": 6,
   "w": 2,
   "l": 4,
   "pct": 33.3,
   "units": -2.25,
   "roi": -37.5
  },
  "all_leans": {
   "n": 236,
   "w": 104,
   "l": 132,
   "pct": 44.1,
   "units": -39.2,
   "roi": -16.6
  }
 },
 "price": {
  "avg_breakeven": 52.7,
  "hit": 44.1,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 18.5": {
   "n": 120,
   "w": 51,
   "l": 69,
   "pct": 42.5,
   "units": -23.54,
   "roi": -19.6
  },
  "> 18.5": {
   "n": 116,
   "w": 53,
   "l": 63,
   "pct": 45.7,
   "units": -15.66,
   "roi": -13.5
  }
 },
 "zeros": {
  "n": 18,
  "of": 215,
  "share": 8.4
 },
 "clustering": [
  {
   "date": "w04",
   "n": 40,
   "w": 19,
   "l": 21,
   "pct": 47.5,
   "units": -3.84,
   "roi": -9.6
  },
  {
   "date": "w08",
   "n": 38,
   "w": 13,
   "l": 25,
   "pct": 34.2,
   "units": -13.3,
   "roi": -35.0
  },
  {
   "date": "w05",
   "n": 35,
   "w": 19,
   "l": 16,
   "pct": 54.3,
   "units": 0.84,
   "roi": 2.4
  }
 ],
 "trend": {
  "early": {
   "n": 106,
   "w": 50,
   "l": 56,
   "pct": 47.2,
   "units": -11.28,
   "roi": -10.6
  },
  "recent": {
   "n": 130,
   "w": 54,
   "l": 76,
   "pct": 41.5,
   "units": -27.92,
   "roi": -21.5
  }
 }
}
```
</details>

### NHL points Overs
Plays 5-17 (-7.2u, -32.7%); every Over lean 80-168 (-17.0%). Checks use plays.

**Likely causes, most likely first:**
1. No single cause stands out: the losses look like the model having no edge on this prop type rather than one fixable flaw. Keep it paused (shadow plays keep grading it) until the gate's evidence says otherwise.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 1273,
  "actual_minus_model": 0.07,
  "actual_minus_line": 0.03,
  "over_rate_at_fair": 41.4,
  "over_rate_z": -6.14
 },
 "by_edge": [],
 "plays_vs_leans": {
  "plays": {
   "n": 22,
   "w": 5,
   "l": 17,
   "pct": 22.7,
   "units": -7.2,
   "roi": -32.7
  },
  "all_leans": {
   "n": 248,
   "w": 80,
   "l": 168,
   "pct": 32.3,
   "units": -42.05,
   "roi": -17.0
  }
 },
 "price": {
  "avg_breakeven": 31.4,
  "hit": 22.7,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 0.5": {
   "n": 22,
   "w": 5,
   "l": 17,
   "pct": 22.7,
   "units": -7.2,
   "roi": -32.7
  },
  "> 0.5": {
   "n": 0,
   "w": 0,
   "l": 0,
   "pct": null,
   "units": 0,
   "roi": null
  }
 },
 "zeros": {
  "n": 0,
  "of": 0,
  "share": 0.0
 },
 "clustering": [
  {
   "date": "2026-10-08",
   "n": 7,
   "w": 1,
   "l": 6,
   "pct": 14.3,
   "units": -3.25,
   "roi": -46.4
  },
  {
   "date": "2026-10-09",
   "n": 7,
   "w": 0,
   "l": 7,
   "pct": 0.0,
   "units": -7.0,
   "roi": -100.0
  },
  {
   "date": "2026-10-10",
   "n": 4,
   "w": 0,
   "l": 4,
   "pct": 0.0,
   "units": -4.0,
   "roi": -100.0
  }
 ],
 "trend": {
  "early": {
   "n": 14,
   "w": 1,
   "l": 13,
   "pct": 7.1,
   "units": -10.25,
   "roi": -73.2
  },
  "recent": {
   "n": 8,
   "w": 4,
   "l": 4,
   "pct": 50.0,
   "units": 3.05,
   "roi": 38.1
  }
 }
}
```
</details>

### NHL points Unders
Plays 106-104 (-10.14u, -4.8%); every Under lean 593-432 (-2.0%). Checks use plays.

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 55.7% and it hit 34.2% over 38. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.
2. Role / volume: lines at or under 0.5 did much worse (49.2% vs 69.2%). Low lines are bench and low-volume players whose minutes swing; restrict to starters.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 1273,
  "actual_minus_model": 0.07,
  "actual_minus_line": 0.03,
  "over_rate_at_fair": 41.4,
  "over_rate_z": -6.14
 },
 "calibration_p_raw": {
  "n": 202,
  "said": 52.7,
  "hit": 49.0
 },
 "calibration_p_adj": {
  "n": 38,
  "said": 55.7,
  "hit": 34.2
 },
 "book_said": {
  "n": 202,
  "book": 49.0,
  "hit": 49.0
 },
 "by_edge": [
  {
   "edge": "0-4",
   "n": 104,
   "w": 41,
   "l": 63,
   "pct": 39.4,
   "units": -24.65,
   "roi": -23.7
  },
  {
   "edge": "4-8",
   "n": 65,
   "w": 38,
   "l": 27,
   "pct": 58.5,
   "units": 5.02,
   "roi": 7.7
  },
  {
   "edge": "8-+",
   "n": 17,
   "w": 11,
   "l": 6,
   "pct": 64.7,
   "units": 3.05,
   "roi": 17.9
  }
 ],
 "plays_vs_leans": {
  "plays": {
   "n": 210,
   "w": 106,
   "l": 104,
   "pct": 50.5,
   "units": -10.14,
   "roi": -4.8
  },
  "all_leans": {
   "n": 1025,
   "w": 593,
   "l": 432,
   "pct": 57.9,
   "units": -20.49,
   "roi": -2.0
  }
 },
 "price": {
  "avg_breakeven": 52.8,
  "hit": 50.5,
  "heavy_juice_share": 27.0,
  "heavy_juice": {
   "n": 57,
   "w": 37,
   "l": 20,
   "pct": 64.9,
   "units": -1.15,
   "roi": -2.0
  }
 },
 "line_size": {
  "<= 0.5": {
   "n": 197,
   "w": 97,
   "l": 100,
   "pct": 49.2,
   "units": -11.02,
   "roi": -5.6
  },
  "> 0.5": {
   "n": 13,
   "w": 9,
   "l": 4,
   "pct": 69.2,
   "units": 0.88,
   "roi": 6.8
  }
 },
 "clustering": [
  {
   "date": "2026-10-15",
   "n": 53,
   "w": 26,
   "l": 27,
   "pct": 49.1,
   "units": -5.83,
   "roi": -11.0
  },
  {
   "date": "2026-10-17",
   "n": 39,
   "w": 21,
   "l": 18,
   "pct": 53.8,
   "units": 2.39,
   "roi": 6.1
  },
  {
   "date": "2026-10-19",
   "n": 38,
   "w": 13,
   "l": 25,
   "pct": 34.2,
   "units": -13.08,
   "roi": -34.4
  }
 ],
 "trend": {
  "early": {
   "n": 24,
   "w": 17,
   "l": 7,
   "pct": 70.8,
   "units": 5.98,
   "roi": 24.9
  },
  "recent": {
   "n": 186,
   "w": 89,
   "l": 97,
   "pct": 47.8,
   "units": -16.12,
   "roi": -8.7
  }
 }
}
```
</details>

### NBA pts Unders
Plays 9-11 (-3.08u, -15.4%); every Under lean 483-420 (-0.1%). Checks use plays.

**Likely causes, most likely first:**
1. Projection bias: results ran 1.69 above the model's middle number on 1167 pts props, while the book's line missed by only +0.10. The model's level for pts is off; shift it up (or let the prop bias correction learn faster).

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 1167,
  "actual_minus_model": 1.69,
  "actual_minus_line": 0.1,
  "over_rate_at_fair": 56.1,
  "over_rate_z": 4.19
 },
 "calibration_p_raw": {
  "n": 20,
  "said": 58.3,
  "hit": 45.0
 },
 "calibration_p_adj": {
  "n": 20,
  "said": 55.5,
  "hit": 45.0
 },
 "book_said": {
  "n": 20,
  "book": 49.0,
  "hit": 45.0
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 4,
   "w": 1,
   "l": 3,
   "pct": 25.0,
   "units": -2.0,
   "roi": -50.0
  },
  {
   "edge": "8-+",
   "n": 16,
   "w": 8,
   "l": 8,
   "pct": 50.0,
   "units": -1.08,
   "roi": -6.7
  }
 ],
 "plays_vs_leans": {
  "plays": {
   "n": 20,
   "w": 9,
   "l": 11,
   "pct": 45.0,
   "units": -3.08,
   "roi": -15.4
  },
  "all_leans": {
   "n": 903,
   "w": 483,
   "l": 420,
   "pct": 53.5,
   "units": -0.79,
   "roi": -0.1
  }
 },
 "price": {
  "avg_breakeven": 52.4,
  "hit": 45.0,
  "heavy_juice_share": 0.0
 },
 "line_move": {
  "n": 20,
  "avg_pts_toward_play": 0.0,
  "toward": 0,
  "against": 0
 },
 "line_size": {
  "<= 14.5": {
   "n": 12,
   "w": 5,
   "l": 7,
   "pct": 41.7,
   "units": -2.58,
   "roi": -21.5
  },
  "> 14.5": {
   "n": 8,
   "w": 4,
   "l": 4,
   "pct": 50.0,
   "units": -0.5,
   "roi": -6.2
  }
 },
 "clustering": [
  {
   "date": "2026-10-31",
   "n": 8,
   "w": 4,
   "l": 4,
   "pct": 50.0,
   "units": -0.56,
   "roi": -7.0
  },
  {
   "date": "2026-11-04",
   "n": 6,
   "w": 2,
   "l": 4,
   "pct": 33.3,
   "units": -2.09,
   "roi": -34.8
  },
  {
   "date": "2026-11-01",
   "n": 4,
   "w": 2,
   "l": 2,
   "pct": 50.0,
   "units": -0.43,
   "roi": -10.8
  }
 ],
 "trend": {
  "early": {
   "n": 12,
   "w": 6,
   "l": 6,
   "pct": 50.0,
   "units": -0.99,
   "roi": -8.2
  },
  "recent": {
   "n": 8,
   "w": 3,
   "l": 5,
   "pct": 37.5,
   "units": -2.09,
   "roi": -26.1
  }
 }
}
```
</details>


## NFL
Updated 6.1 hours ago, odds from odds_api, credits left 57.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| plays_record / props | 85-76 | 52.8% | -0.03 | -0.0% | -0.0 |
| live_record / picks / total | 52-50 | 51.0% | -2.73 | -2.7% | -0.28 |
| live_record / picks / moneyline | 65-36 | 64.4% | 9.99 | 9.9% | 1.05 |
| live_record / picks / spread | 52-44 | 54.2% | 3.27 | 3.4% | 0.35 |
| live_record / picks_by_week / 4 / total | 6-10 | 37.5% | -4.55 | -28.4% | -1.2 |
| live_record / picks_by_week / 4 / moneyline | 9-7 | 56.2% | None | None% | None |
| live_record / picks_by_week / 5 / total | 8-7 | 53.3% | 0.27 | 1.8% | 0.07 |
| live_record / picks_by_week / 9 / total | 5-10 | 33.3% | -5.45 | -36.3% | -1.48 |
| live_record / picks_by_week / 9 / moneyline | 12-3 | 80.0% | 2.22 | 14.8% | 0.6 |
| live_record / picks_by_week / 4 / spread | 5-9 | 35.7% | -4.45 | -31.8% | -1.25 |
| live_record / picks_by_week / 5 / spread | 8-6 | 57.1% | 1.27 | 9.1% | 0.36 |
| live_record / picks_by_week / 5 / moneyline | 10-4 | 71.4% | 5.51 | 39.4% | 1.55 |
| live_record / picks_by_week / 6 / spread | 5-9 | 35.7% | -4.45 | -31.8% | -1.25 |
| live_record / picks_by_week / 6 / total | 9-5 | 64.3% | 3.18 | 22.7% | 0.89 |
| live_record / picks_by_week / 6 / moneyline | 6-8 | 42.9% | -3.6 | -25.7% | -1.01 |
| live_record / picks_by_week / 7 / total | 7-7 | 50.0% | -0.64 | -4.6% | -0.18 |
| live_record / picks_by_week / 7 / moneyline | 10-4 | 71.4% | 3.28 | 23.4% | 0.92 |
| live_record / picks_by_week / 8 / spread | 9-5 | 64.3% | 3.18 | 22.7% | 0.89 |
| live_record / picks_by_week / 8 / total | 9-5 | 64.3% | 3.18 | 22.7% | 0.89 |
| live_record / picks_by_week / 8 / moneyline | 11-3 | 78.6% | 3.39 | 24.2% | 0.95 |
| live_record / picks_by_week / 9 / spread | 9-5 | 64.3% | 3.18 | 22.7% | 0.89 |
| live_record / picks_by_week / 10 / spread | 8-6 | 57.1% | 1.27 | 9.1% | 0.36 |
| live_record / picks_by_week / 10 / total | 8-6 | 57.1% | 1.27 | 9.1% | 0.36 |
| live_record / picks_by_week / 10 / moneyline | 7-7 | 50.0% | -0.82 | -5.9% | -0.23 |
| alt_plays | 3-10 | 23.1% | -1.12 | -8.6% | -0.33 |
| live_record / picks_by_week / 7 / spread | 8-4 | 66.7% | 3.27 | 27.2% | 0.99 |
| alt_plays / by_market / spread | 3-8 | 27.3% | 0.88 | 8.0% | 0.28 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| tds / Anytime TD | 1518 | 23.6% | 25.1% | +1.5 | 1.38 |
| tds / Anytime TD / bins / 0 | 246 | 5.6% | 11.4% | +5.8 | 3.96 |
| tds / Anytime TD / bins / 1 | 474 | 14.9% | 15.6% | +0.7 | 0.43 |
| tds / Anytime TD / bins / 2 | 506 | 26.6% | 28.7% | +2.1 | 1.07 |
| tds / Anytime TD / bins / 3 | 200 | 41.2% | 40.0% | -1.2 | -0.34 |
| tds / Anytime TD / bins / 4 | 65 | 57.0% | 50.8% | -6.2 | -1.01 |
| tds / Anytime TD / bins / 5 | 27 | 69.8% | 77.8% | +8.0 | 0.91 |
| tds / 2+ TDs | 1280 | 4.8% | 4.1% | -0.7 | -1.17 |
| tds / 2+ TDs / bins / 0 | 1109 | 2.8% | 2.3% | -0.5 | -1.01 |
| tds / 2+ TDs / bins / 1 | 117 | 13.4% | 13.7% | +0.3 | 0.1 |
| tds / 2+ TDs / bins / 2 | 46 | 26.8% | 19.6% | -7.2 | -1.1 |
| tds / 2+ TDs / bins / 3 | 8 | 40.2% | 25.0% | -15.2 | -0.88 |
| combos / QB + WR1 overs | 163 | 31.6% | 33.1% | +1.5 | 0.41 |
| combos / QB over + opponent team total over | 166 | 25.4% | 26.5% | +1.1 | 0.33 |
| combos / QB over + team covers | 158 | 27.7% | 27.8% | +0.1 | 0.03 |
| combos / QB over + team total over | 166 | 29.6% | 30.7% | +1.1 | 0.31 |
| combos / RB1 anytime TD + team wins | 166 | 29.8% | 30.7% | +0.9 | 0.25 |
| combos / RB1 rush over + team wins | 166 | 26.9% | 24.1% | -2.8 | -0.81 |
| combos / WR1 over + team total over | 169 | 26.2% | 24.3% | -1.9 | -0.56 |
| combos / team total over + game over | 172 | 37.3% | 40.1% | +2.8 | 0.76 |
| combo_total | 1326 | 29.3% | 29.7% | +0.4 | 0.32 |
| alt_parlays (tickets) | 73 | 50.4% | 42.5% | -7.9 | -1.35 |
| alt_parlays (legs) | 282 | 82.4% | 77.7% | -4.7 | -2.07 |
| alt_parlays / by_v / 1 (tickets) | 39 | 46.3% | 38.5% | -7.8 | -0.98 |
| alt_parlays / by_v / 2 (tickets) | 34 | 55.2% | 47.1% | -8.1 | -0.95 |
| alt_mix (tickets) | 19 | 51.0% | 36.8% | -14.2 | -1.24 |
| alt_mix / by_v / 1 (tickets) | 9 | 47.1% | 44.4% | -2.7 | -0.16 |
| alt_mix / by_v / 2 (tickets) | 10 | 54.6% | 30.0% | -24.6 | -1.56 |
| alt_ladder (tickets) | 5 | 60.0% | 80.0% | +20.0 | 0.91 |
| alt_leg_types / QB pass attempts Over | 127 | 77.0% | 63.0% | -14.0 | -3.75 |
| alt_leg_types / QB completions Over | 160 | 78.2% | 69.4% | -8.8 | -2.7 |
| alt_leg_types / QB passing yards Over | 137 | 75.5% | 68.6% | -6.9 | -1.88 |
| alt_leg_types / RB rushing yards Over | 121 | 76.9% | 71.9% | -5.0 | -1.3 |
| alt_leg_types / TE receiving yards Over | 74 | 75.5% | 74.3% | -1.2 | -0.24 |
| alt_leg_types / QB pass attempts Under | 90 | 76.5% | 68.9% | -7.6 | -1.7 |
| alt_leg_types / QB completions Under | 163 | 78.9% | 80.4% | +1.5 | 0.47 |
| alt_leg_types / RB carries Under | 38 | 81.5% | 71.1% | -10.4 | -1.65 |
| alt_leg_types / Receptions Under (any position) | 400 | 83.1% | 82.0% | -1.1 | -0.59 |
| alt_leg_types / WR receiving yards Over | 194 | 75.7% | 76.3% | +0.6 | 0.19 |
| alt_leg_types / Receptions Over (any position) | 153 | 77.6% | 79.7% | +2.1 | 0.62 |
| teasers (legs) | 408 | 68.5% | 68.9% | +0.4 | 0.17 |
| weather / overs (tickets) | 113 | 47.3% | 41.6% | -5.7 | -1.21 |
| cross_parlays (tickets) | 6 | 45.0% | 33.3% | -11.7 | -0.58 |
| cross_parlays (legs) | 18 | 76.7% | 72.2% | -4.5 | -0.45 |

Parlay tickets in units (1 unit a ticket). Bet-at = the shortest price the page says to take, so it is the best case for following the page. Hard Rock's own same-game price isn't in the odds feed.

| Tickets | W-L | At bet-at price | At fair price | At Hard Rock's price |
|---|---|---|---|---|
| alt_parlays | 31-42 | -3.01u (-8.9%) over 34 | -11.32u (-15.5%) over 73 | n/a |
| alt_mix | 7-12 | -4.09u (-40.9%) over 10 | -4.99u (-26.3%) over 19 | n/a |
| alt_ladder | 4-1 | +2.13u (+42.6%) over 5 | +1.67u (+33.3%) over 5 | n/a |
| cross_parlays | 2-4 | -1.41u (-23.5%) over 6 | -1.53u (-25.5%) over 6 | n/a |

Gates: NFL prop Overs (yardage) paused; NFL receptions props paused; NFL passing-yard Unders paused; NFL longest completion Unders paused; NFL longest completion Overs paused; NFL spreads paused; NFL totals paused

## NHL
Updated 3.0 hours ago, odds from odds_api, credits left 152.

Prop plays with a closing price since 2026-11-12: 1 of 1, 1 at the same line (the only ones with a closing value).

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| prop_plays | 225-221 | 50.4% | -16.43 | -3.7% | -0.82 |
| picks / ml | 116-161 | 41.9% | -49.65 | -17.9% | -3.14 |
| picks / pl | 134-143 | 48.4% | -28.65 | -10.3% | -1.81 |
| picks / total | 131-146 | 47.3% | -28.1 | -10.1% | -1.78 |
| by_type / prop / points|Under | 106-104 | 50.5% | -10.14 | -4.8% | -0.73 |
| by_type / prop / sog|Under | 92-86 | 51.7% | -3.87 | -2.2% | -0.31 |
| plays | 32-31 | 50.8% | 4.02 | 6.4% | 0.53 |
| by_type / prop / sog|Over | 22-14 | 61.1% | 4.78 | 13.3% | 0.84 |
| by_type / game / ml | 15-13 | 53.6% | 6.33 | 22.6% | 1.26 |
| by_type / game / total | 16-12 | 57.1% | 2.8 | 10.0% | 0.56 |
| by_type / prop / points|Over | 5-17 | 22.7% | -7.2 | -32.7% | -1.61 |
| edge | 6-12 | 33.3% | -4.9 | -27.2% | -1.21 |
| by_type / game / pl | 1-6 | 14.3% | -5.11 | -73.0% | -2.03 |
| alt_plays | 3-3 | 50.0% | -0.08 | -1.3% | -0.03 |
| alt_by_market / team_total | 3-3 | 50.0% | -0.08 | -1.3% | -0.03 |
| by_type / game / alt | 3-3 | 50.0% | -0.08 | -1.3% | -0.03 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / sog | 9378 | 49.7% | 48.6% | -1.1 | -2.13 |
| calibration / goals | 9378 | 15.6% | 15.5% | -0.1 | -0.27 |
| calibration / assists | 9378 | 22.8% | 24.9% | +2.1 | 4.85 |
| calibration / points | 9378 | 33.2% | 35.6% | +2.4 | 4.94 |
| calibration / saves | 513 | 50.0% | 32.9% | -17.1 | -7.75 |
| alt (tickets) | 174 | 50.3% | 52.3% | +2.0 | 0.53 |
| alt_mix (tickets) | 160 | 49.3% | 51.2% | +1.9 | 0.48 |
| alt_ladder (tickets) | 44 | 57.8% | 65.9% | +8.1 | 1.09 |
| alt_hr (tickets) | 23 | 66.0% | 56.5% | -9.5 | -0.96 |
| alt_old (tickets) | 48 | 46.2% | 39.6% | -6.6 | -0.92 |
| cross_parlays (tickets) | 30 | 48.4% | 50.0% | +1.6 | 0.18 |
| cross_parlays (legs) | 90 | 78.6% | 78.9% | +0.3 | 0.07 |
| cross_parlays / by_style / spreads (tickets) | 15 | 47.8% | 46.7% | -1.1 | -0.09 |
| cross_parlays / by_style / mix (tickets) | 15 | 49.0% | 53.3% | +4.3 | 0.33 |

Parlay tickets in units (1 unit a ticket). Bet-at = the shortest price the page says to take, so it is the best case for following the page. Hard Rock's own same-game price isn't in the odds feed.

| Tickets | W-L | At bet-at price | At fair price | At Hard Rock's price |
|---|---|---|---|---|
| alt | 91-83 | +10.72u (+8.5%) over 126 | +8.04u (+4.6%) over 174 | n/a |
| alt_mix | 82-78 | +15.64u (+12.0%) over 130 | +6.73u (+4.2%) over 160 | n/a |
| alt_ladder | 29-15 | +9.72u (+22.1%) over 44 | +6.23u (+14.2%) over 44 | n/a |
| alt_hr | 13-10 | n/a | -3.1u (-13.5%) over 23 | n/a |
| alt_old | 19-29 | n/a | -6.7u (-14.0%) over 48 | n/a |
| cross_parlays | 15-15 | +2.06u (+6.9%) over 30 | +1.11u (+3.7%) over 30 | n/a |

Gates: NHL points props (Unders) paused; NHL edge parlays paused; NHL moneyline paused; NHL puck line paused; NHL totals paused; NHL shots on goal Overs active; NHL shots on goal Unders active; NHL goals Overs active; NHL assists Overs active; NHL assists Unders active

## NBA
Updated 2.8 hours ago, odds from odds_api, credits left 113.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| picks / ml | 55-69 | 44.4% | -25.5 | -20.6% | -2.41 |
| picks / spread | 60-64 | 48.4% | -9.26 | -7.5% | -0.88 |
| picks / total | 62-62 | 50.0% | -5.63 | -4.5% | -0.53 |
| prop_plays | 39-36 | 52.0% | -0.53 | -0.7% | -0.06 |
| by_type / prop / pts|Under | 9-11 | 45.0% | -3.08 | -15.4% | -0.72 |
| by_type / prop / pra|Under | 9-3 | 75.0% | 4.81 | 40.1% | 1.46 |
| by_type / prop / ast|Under | 3-8 | 27.3% | -5.56 | -50.6% | -1.77 |
| by_type / prop / reb|Under | 8-2 | 80.0% | 5.54 | 55.4% | 1.84 |
| by_type / prop / fg3m|Under | 4-5 | 44.4% | -2.0 | -22.2% | -0.7 |
| plays | 0-8 | 0.0% | -8.0 | -100.0% | -2.98 |
| by_type / game / ml | 0-8 | 0.0% | -8.0 | -100.0% | -2.98 |
| edge | 3-3 | 50.0% | 2.78 | 46.3% | 1.19 |
| by_type / prop / fg3m|Over | 1-5 | 16.7% | -3.85 | -64.2% | -1.66 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / pts | 2676 | 50.0% | 51.4% | +1.4 | 1.45 |
| calibration / reb | 2676 | 49.8% | 54.3% | +4.5 | 4.66 |
| calibration / ast | 2676 | 49.0% | 53.4% | +4.4 | 4.55 |
| calibration / fg3m | 2676 | 42.5% | 46.4% | +3.9 | 4.08 |
| calibration / pra | 2676 | 50.0% | 53.7% | +3.7 | 3.83 |
| alt (tickets) | 15 | 49.4% | 46.7% | -2.7 | -0.21 |
| alt_mix (tickets) | 67 | 53.5% | 58.2% | +4.7 | 0.77 |
| cross_parlays (tickets) | 30 | 44.7% | 43.3% | -1.4 | -0.15 |
| cross_parlays (legs) | 90 | 76.5% | 73.3% | -3.2 | -0.72 |
| cross_parlays / by_style / spreads (tickets) | 15 | 44.8% | 46.7% | +1.9 | 0.15 |
| cross_parlays / by_style / mix (tickets) | 15 | 44.6% | 40.0% | -4.6 | -0.36 |

Parlay tickets in units (1 unit a ticket). Bet-at = the shortest price the page says to take, so it is the best case for following the page. Hard Rock's own same-game price isn't in the odds feed.

| Tickets | W-L | At bet-at price | At fair price | At Hard Rock's price |
|---|---|---|---|---|
| alt | 7-8 | +0.17u (+1.1%) over 15 | -0.82u (-5.5%) over 15 | n/a |
| alt_mix | 39-28 | +11.7u (+17.5%) over 67 | +6.55u (+9.8%) over 67 | n/a |
| cross_parlays | 13-17 | -0.11u (-0.4%) over 30 | -0.96u (-3.2%) over 30 | n/a |

Gates: NBA edge parlays active; NBA moneyline paused; NBA spreads paused; NBA totals paused; NBA points Overs active; NBA points Unders active; NBA rebounds Overs active; NBA rebounds Unders active; NBA assists Overs active; NBA assists Unders active; NBA threes Overs active; NBA threes Unders active; NBA pts+reb+ast Overs active; NBA pts+reb+ast Unders active

## CFB
Updated 4.9 hours ago, odds from odds_api, credits left 175.

Prop plays with a closing price since 2026-11-12: 23 of 37, 8 at the same line (the only ones with a closing value).

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| prop_plays | 128-100 | 56.1% | 12.4 | 5.4% | 0.86 |
| picks / total | 49-67 | 42.2% | -22.69 | -19.6% | -2.22 |
| picks / spread | 50-65 | 43.5% | -19.61 | -17.1% | -1.92 |
| picks / ml | 53-57 | 48.2% | -10.01 | -9.1% | -1.0 |
| plays | 10-15 | 40.0% | -5.97 | -23.9% | -1.26 |
| early_totals | 8-11 | 42.1% | -3.88 | -20.4% | -0.94 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / pass_yds | 315 | 50.0% | 47.6% | -2.4 | -0.85 |
| calibration / pass_td | 315 | 48.7% | 46.7% | -2.0 | -0.71 |
| calibration / td | 1415 | 36.6% | 35.3% | -1.3 | -1.02 |
| calibration / rush_yds | 482 | 49.4% | 47.7% | -1.7 | -0.75 |
| calibration / rec | 804 | 49.2% | 55.3% | +6.1 | 3.46 |
| calibration / rec_yds | 560 | 49.6% | 54.1% | +4.5 | 2.13 |
| alt (tickets) | 85 | 46.2% | 44.7% | -1.5 | -0.28 |
| teasers (legs) | 728 | 65.6% | 66.8% | +1.2 | 0.68 |

Parlay tickets in units (1 unit a ticket). Bet-at = the shortest price the page says to take, so it is the best case for following the page. Hard Rock's own same-game price isn't in the odds feed.

| Tickets | W-L | At bet-at price | At fair price | At Hard Rock's price |
|---|---|---|---|---|
| alt | 38-47 | -3.97u (-10.7%) over 37 | -2.26u (-2.7%) over 85 | n/a |

Gates: CFB spreads paused; CFB totals paused; CFB moneyline paused

## Soccer
Updated 0.3 hours ago, odds from odds_api, credits left 381.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| picks / 1x2 | 32-78 | 29.1% | -7.91 | -7.2% | -0.79 |
| picks / total | 51-59 | 46.4% | -17.2 | -15.6% | -1.73 |
| picks / btts | 51-59 | 46.4% | None | None% | None |
| picks / ah | 45-61 | 42.5% | -6.67 | -6.3% | -0.68 |
| picks / dnb | 60-27 | 69.0% | 0.0 | 0.0% | 0.0 |
| picks_by_league / champ / 1x2 | 16-33 | 32.7% | -1.51 | -3.1% | -0.23 |
| picks_by_league / champ / total | 19-30 | 38.8% | -12.71 | -25.9% | -1.91 |
| picks_by_league / champ / btts | 27-22 | 55.1% | None | None% | None |
| picks_by_league / champ / ah | 21-27 | 43.8% | 0.88 | 1.8% | 0.13 |
| picks_by_league / champ / dnb | 27-12 | 69.2% | 0.0 | 0.0% | 0.0 |
| picks_by_league / laliga / 1x2 | 9-22 | 29.0% | -1.37 | -4.4% | -0.26 |
| picks_by_league / laliga / total | 17-14 | 54.8% | -1.95 | -6.3% | -0.37 |
| picks_by_league / laliga / btts | 12-19 | 38.7% | None | None% | None |
| picks_by_league / epl / 1x2 | 7-23 | 23.3% | -5.03 | -16.8% | -0.97 |
| picks_by_league / epl / total | 15-15 | 50.0% | -2.53 | -8.4% | -0.49 |
| picks_by_league / epl / btts | 12-18 | 40.0% | None | None% | None |
| picks_by_league / laliga / ah | 13-17 | 43.3% | -4.85 | -16.2% | -0.93 |
| picks_by_league / epl / ah | 11-17 | 39.3% | -2.7 | -9.6% | -0.54 |
| picks_by_league / laliga / dnb | 19-6 | 76.0% | 0.0 | 0.0% | 0.0 |
| plays | 10-14 | 41.7% | 6.95 | 29.0% | 1.5 |
| picks_by_league / epl / dnb | 14-9 | 60.9% | 0.0 | 0.0% | 0.0 |
| rule | 7-13 | 35.0% | 5.03 | 25.2% | 1.19 |
| by_type / 1x2 | 6-13 | 31.6% | 4.15 | 21.8% | 1.0 |
| by_league / champ | 7-7 | 50.0% | 2.95 | 21.1% | 0.83 |
| by_league / laliga | 2-6 | 25.0% | 1.0 | 12.5% | 0.37 |
| by_type / ah | 4-1 | 80.0% | 2.8 | 56.1% | 1.32 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / goal | 2591 | 9.8% | 9.2% | -0.6 | -1.03 |
| calibration / sot1 | 2591 | 26.4% | 25.6% | -0.8 | -0.92 |
| calibration / sot2 | 2591 | 5.8% | 5.8% | +0.0 | 0.0 |
| alt_parlays (tickets) | 60 | 47.7% | 48.3% | +0.6 | 0.09 |
| alt_parlays (legs) | 180 | 74.2% | 73.9% | -0.3 | -0.09 |
| cross_parlays (tickets) | 12 | 51.8% | 66.7% | +14.9 | 1.03 |
| cross_parlays (legs) | 36 | 80.4% | 88.9% | +8.5 | 1.28 |
| cross_parlays / by_style / spreads (tickets) | 5 | 52.5% | 60.0% | +7.5 | 0.34 |
| cross_parlays / by_style / mix (tickets) | 7 | 51.3% | 71.4% | +20.1 | 1.06 |

Parlay tickets in units (1 unit a ticket). Bet-at = the shortest price the page says to take, so it is the best case for following the page. Hard Rock's own same-game price isn't in the odds feed.

| Tickets | W-L | At bet-at price | At fair price | At Hard Rock's price |
|---|---|---|---|---|
| alt_parlays | 29-31 | +2.41u (+6.0%) over 40 | +0.6u (+1.0%) over 60 | n/a |
| cross_parlays | 8-4 | +3.7u (+30.8%) over 12 | +3.22u (+26.9%) over 12 | -1.0u (-100.0%) over 1 |

Gates: Soccer match result paused; Soccer Asian handicap paused; Soccer totals paused
