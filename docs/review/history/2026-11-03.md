# Weekly model review, 2026-11-03

Flags first (high, then medium, then info). Every number is a graded record from the site's own data.

| Level | Sport | What | Why |
|---|---|---|---|
| high | CFB | losing: picks / total | 49-67, -22.69u, -19.6% (z -2.22) |
| high | CFB | said vs hit: calibration / rec | said 48.9%, hit 55.4% over 509 (z 2.93) |
| high | CFB | said vs hit: calibration / rec_yds | said 49.6%, hit 55.1% over 350 (z 2.06) |
| high | NFL | said vs hit: alt_leg_types / RB rushing yards Over | said 79.5%, hit 66.1% over 165 (z -4.26) |
| high | NHL | losing: picks / ml | 78-102, -27.76u, -15.4% (z -2.18) |
| high | NHL | said vs hit: calibration / saves | said 50.0%, hit 31.9% over 326 (z -6.54) |
| high | Soccer | losing: picks_by_league / champ / 1x2 | 6-19, -10.25u, -41.0% (z -2.16) |
| medium | CFB | losing: picks / spread | 50-65, -19.61u, -17.1% (z -1.92) |
| medium | CFB | losing: picks / ml | 53-57, -10.01u, -9.1% (z -1.0) |
| medium | NBA | losing: picks / ml | 11-15, -6.86u, -26.4% (z -1.42) |
| medium | NBA | losing: picks / spread | 12-14, -3.15u, -12.1% (z -0.65) |
| medium | NFL | said vs hit: tds / 2+ TDs / bins / 2 | said 26.8%, hit 15.2% over 33 (z -1.5) |
| medium | NFL | diagnosed: pass_yds Overs | plays 3-3 (-5.2%); top cause: Overconfidence: the model gave the bet side 66.1% and it hit 56.1% over 57. Shrink this prop type's chance toward the book's (betrules reali |
| medium | NFL | diagnosed: pass_yds Unders | plays 3-2 (13.9%); top cause: Overconfidence: the model gave the bet side 61.1% and it hit 45.5% over 44. Shrink this prop type's chance toward the book's (betrules reali |
| medium | NFL | diagnosed: rec Overs | plays 8-17 (-34.7%); top cause: Overconfidence: the model gave the bet side 52.3% and it hit 32.0% over 25. Shrink this prop type's chance toward the book's (betrules reali |
| medium | NFL | diagnosed: rec Unders | plays 10-11 (-13.7%); top cause: Role / volume: lines over 2.5 did much worse (30.0% vs 63.6%). High lines are stars the market prices sharply; the model adds little there. |
| medium | NFL | diagnosed: rec_yds Overs | plays 21-18 (2.0%); top cause: No flaw found, and the plays are at break-even or better. If this type is paused, the gate's shadow record decides when it comes back (40+ g |
| medium | NFL | diagnosed: rush_yds Overs | plays 2-4 (-37.5%); top cause: Overconfidence: the model gave the bet side 71.2% and it hit 43.4% over 173. Shrink this prop type's chance toward the book's (betrules real |
| medium | NHL | said vs hit: alt_hr (tickets) | said 66.0%, hit 56.5% over 23 (z -0.96) |
| medium | NHL | diagnosed: points Overs | plays 5-17 (-32.7%); top cause: No single cause stands out: the losses look like the model having no edge on this prop type rather than one fixable flaw. Keep it paused (sh |
| medium | NHL | diagnosed: points Unders | plays 106-104 (-4.8%); top cause: Overconfidence: the model gave the bet side 55.7% and it hit 34.2% over 38. Shrink this prop type's chance toward the book's (betrules reali |
| medium | Soccer | losing: picks / 1x2 | 18-48, -10.88u, -16.5% (z -1.41) |
| medium | Soccer | losing: picks / ah | 23-39, -6.67u, -10.8% (z -0.89) |
| medium | Soccer | losing: picks / total | 32-34, -7.97u, -12.1% (z -1.03) |
| medium | Soccer | losing: picks_by_league / champ / total | 9-16, -8.48u, -33.9% (z -1.79) |
| info | NBA | winning: prop_plays | 36-23, +9.36u, +15.9% (z 1.29) |
| info | NFL | winning: live_record / picks / moneyline | 46-26, +8.59u, +11.9% (z 1.07) |
| info | NHL | winning: plays | 32-30, +5.02u, +8.1% (z 0.67) |

## Prop diagnoses
Every prop type that is losing (20+ plays, -8% or worse) or paused, with what's driving it.

### NFL pass_yds Overs
Plays 3-3 (-0.31u, -5.2%); every Over lean 32-25 (6.3%). Checks use every lean on this side (too few plays).

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 66.1% and it hit 56.1% over 57. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 101,
  "actual_minus_model": -8.54,
  "actual_minus_line": -1.25
 },
 "calibration_p_raw": {
  "n": 57,
  "said": 66.1,
  "hit": 56.1
 },
 "book_said": {
  "n": 57,
  "book": 50.0,
  "hit": 56.1
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 12,
   "w": 5,
   "l": 7,
   "pct": 41.7,
   "units": -2.53,
   "roi": -21.1
  },
  {
   "edge": "8-+",
   "n": 45,
   "w": 27,
   "l": 18,
   "pct": 60.0,
   "units": 6.13,
   "roi": 13.6
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
   "n": 57,
   "w": 32,
   "l": 25,
   "pct": 56.1,
   "units": 3.6,
   "roi": 6.3
  }
 },
 "price": {
  "avg_breakeven": 52.8,
  "hit": 56.1,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 205.5": {
   "n": 30,
   "w": 16,
   "l": 14,
   "pct": 53.3,
   "units": 0.29,
   "roi": 1.0
  },
  "> 205.5": {
   "n": 27,
   "w": 16,
   "l": 11,
   "pct": 59.3,
   "units": 3.32,
   "roi": 12.3
  }
 },
 "zeros": {
  "n": 1,
  "of": 57,
  "share": 1.8
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
   "date": "w06",
   "n": 12,
   "w": 7,
   "l": 5,
   "pct": 58.3,
   "units": 1.27,
   "roi": 10.6
  },
  {
   "date": "w08",
   "n": 11,
   "w": 6,
   "l": 5,
   "pct": 54.5,
   "units": 0.38,
   "roi": 3.5
  }
 ],
 "trend": {
  "early": {
   "n": 25,
   "w": 14,
   "l": 11,
   "pct": 56.0,
   "units": 1.5,
   "roi": 6.0
  },
  "recent": {
   "n": 32,
   "w": 18,
   "l": 14,
   "pct": 56.2,
   "units": 2.1,
   "roi": 6.6
  }
 }
}
```
</details>

### NFL pass_yds Unders
Plays 3-2 (+0.69u, 13.9%); every Under lean 20-24 (-13.9%). Checks use every lean on this side (too few plays).

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 61.1% and it hit 45.5% over 44. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.
2. Bigger edges did worse (35.7% at 8+ points vs 62% below): big gaps from the book usually mean news the model can't see (injury, role, lineup). Cap the edge for pass_yds lower.
3. Role / volume: lines over 241.5 did much worse (38.1% vs 52.2%). High lines are stars the market prices sharply; the model adds little there.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 101,
  "actual_minus_model": -8.54,
  "actual_minus_line": -1.25
 },
 "calibration_p_raw": {
  "n": 44,
  "said": 61.1,
  "hit": 45.5
 },
 "book_said": {
  "n": 44,
  "book": 50.0,
  "hit": 45.5
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 16,
   "w": 10,
   "l": 6,
   "pct": 62.5,
   "units": 2.94,
   "roi": 18.4
  },
  {
   "edge": "8-+",
   "n": 28,
   "w": 10,
   "l": 18,
   "pct": 35.7,
   "units": -9.07,
   "roi": -32.4
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
   "n": 44,
   "w": 20,
   "l": 24,
   "pct": 45.5,
   "units": -6.13,
   "roi": -13.9
  }
 },
 "price": {
  "avg_breakeven": 52.8,
  "hit": 45.5,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 241.5": {
   "n": 23,
   "w": 12,
   "l": 11,
   "pct": 52.2,
   "units": -0.29,
   "roi": -1.3
  },
  "> 241.5": {
   "n": 21,
   "w": 8,
   "l": 13,
   "pct": 38.1,
   "units": -5.83,
   "roi": -27.8
  }
 },
 "clustering": [
  {
   "date": "w08",
   "n": 11,
   "w": 7,
   "l": 4,
   "pct": 63.6,
   "units": 2.24,
   "roi": 20.4
  },
  {
   "date": "w05",
   "n": 9,
   "w": 4,
   "l": 5,
   "pct": 44.4,
   "units": -1.44,
   "roi": -16.0
  },
  {
   "date": "w06",
   "n": 9,
   "w": 5,
   "l": 4,
   "pct": 55.6,
   "units": 0.46,
   "roi": 5.2
  }
 ],
 "trend": {
  "early": {
   "n": 17,
   "w": 5,
   "l": 12,
   "pct": 29.4,
   "units": -7.54,
   "roi": -44.3
  },
  "recent": {
   "n": 27,
   "w": 15,
   "l": 12,
   "pct": 55.6,
   "units": 1.41,
   "roi": 5.2
  }
 }
}
```
</details>

### NFL rec Overs
Plays 8-17 (-8.68u, -34.7%); every Over lean 128-122 (1.7%). Checks use plays.

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 52.3% and it hit 32.0% over 25. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 572,
  "actual_minus_model": 0.41,
  "actual_minus_line": 0.1
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
   "n": 250,
   "w": 128,
   "l": 122,
   "pct": 51.2,
   "units": 4.35,
   "roi": 1.7
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
Plays 10-11 (-2.87u, -13.7%); every Under lean 174-148 (1.2%). Checks use plays.

**Likely causes, most likely first:**
1. Role / volume: lines over 2.5 did much worse (30.0% vs 63.6%). High lines are stars the market prices sharply; the model adds little there.
2. Projection bias: results ran 0.41 above the model's middle number on 572 rec props, while the book's line missed by only +0.10. The model's level for rec is off; shift it up (or let the prop bias correction learn faster).

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 572,
  "actual_minus_model": 0.41,
  "actual_minus_line": 0.1
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
   "n": 322,
   "w": 174,
   "l": 148,
   "pct": 54.0,
   "units": 3.86,
   "roi": 1.2
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
Plays 21-18 (+0.78u, 2.0%); every Over lean 120-115 (-3.3%). Checks use plays.

**Likely causes, most likely first:**
1. No flaw found, and the plays are at break-even or better. If this type is paused, the gate's shadow record decides when it comes back (40+ graded over 3+ weeks, positive return, closing value not negative).

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 566,
  "actual_minus_model": 7.64,
  "actual_minus_line": 4.83
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
   "n": 235,
   "w": 120,
   "l": 115,
   "pct": 51.1,
   "units": -7.78,
   "roi": -3.3
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
Plays 2-4 (-2.25u, -37.5%); every Over lean 75-98 (-17.9%). Checks use every lean on this side (too few plays).

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 71.2% and it hit 43.4% over 173. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 320,
  "actual_minus_model": 1.61,
  "actual_minus_line": 3.42
 },
 "calibration_p_raw": {
  "n": 173,
  "said": 71.2,
  "hit": 43.4
 },
 "book_said": {
  "n": 173,
  "book": 49.8,
  "hit": 43.4
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 27,
   "w": 7,
   "l": 20,
   "pct": 25.9,
   "units": -13.83,
   "roi": -51.2
  },
  {
   "edge": "8-+",
   "n": 146,
   "w": 68,
   "l": 78,
   "pct": 46.6,
   "units": -17.11,
   "roi": -11.7
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
   "n": 173,
   "w": 75,
   "l": 98,
   "pct": 43.4,
   "units": -30.95,
   "roi": -17.9
  }
 },
 "price": {
  "avg_breakeven": 52.6,
  "hit": 43.4,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 17.5": {
   "n": 87,
   "w": 35,
   "l": 52,
   "pct": 40.2,
   "units": -20.67,
   "roi": -23.8
  },
  "> 17.5": {
   "n": 86,
   "w": 40,
   "l": 46,
   "pct": 46.5,
   "units": -10.28,
   "roi": -12.0
  }
 },
 "zeros": {
  "n": 12,
  "of": 156,
  "share": 7.7
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
   "date": "w05",
   "n": 35,
   "w": 19,
   "l": 16,
   "pct": 54.3,
   "units": 0.84,
   "roi": 2.4
  },
  {
   "date": "w08",
   "n": 35,
   "w": 11,
   "l": 24,
   "pct": 31.4,
   "units": -14.05,
   "roi": -40.1
  }
 ],
 "trend": {
  "early": {
   "n": 75,
   "w": 38,
   "l": 37,
   "pct": 50.7,
   "units": -2.99,
   "roi": -4.0
  },
  "recent": {
   "n": 98,
   "w": 37,
   "l": 61,
   "pct": 37.8,
   "units": -27.95,
   "roi": -28.5
  }
 }
}
```
</details>

### NHL points Overs
Plays 5-17 (-7.2u, -32.7%); every Over lean 68-160 (-21.8%). Checks use plays.

**Likely causes, most likely first:**
1. No single cause stands out: the losses look like the model having no edge on this prop type rather than one fixable flaw. Keep it paused (shadow plays keep grading it) until the gate's evidence says otherwise.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 1191,
  "actual_minus_model": 0.06,
  "actual_minus_line": 0.03
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
   "n": 228,
   "w": 68,
   "l": 160,
   "pct": 29.8,
   "units": -49.71,
   "roi": -21.8
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
Plays 106-104 (-10.14u, -4.8%); every Under lean 554-409 (-2.4%). Checks use plays.

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 55.7% and it hit 34.2% over 38. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.
2. Role / volume: lines at or under 0.5 did much worse (49.2% vs 69.2%). Low lines are bench and low-volume players whose minutes swing; restrict to starters.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 1191,
  "actual_minus_model": 0.06,
  "actual_minus_line": 0.03
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
   "n": 963,
   "w": 554,
   "l": 409,
   "pct": 57.5,
   "units": -23.17,
   "roi": -2.4
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


## NFL
Updated 12.4 hours ago, odds from None, credits left None.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| plays_record / props | 85-76 | 52.8% | -0.03 | -0.0% | -0.0 |
| live_record / picks / total | 39-34 | 53.4% | 1.45 | 2.0% | 0.18 |
| live_record / picks / moneyline | 46-26 | 63.9% | 8.59 | 11.9% | 1.07 |
| live_record / picks / spread | 35-33 | 51.5% | -1.18 | -1.7% | -0.15 |
| live_record / picks_by_week / 4 / total | 6-10 | 37.5% | -4.55 | -28.4% | -1.2 |
| live_record / picks_by_week / 4 / moneyline | 9-7 | 56.2% | None | None% | None |
| live_record / picks_by_week / 5 / total | 8-7 | 53.3% | 0.27 | 1.8% | 0.07 |
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
| live_record / picks_by_week / 7 / spread | 8-4 | 66.7% | 3.27 | 27.2% | 0.99 |
| alt_plays | 2-7 | 22.2% | 1.45 | 16.1% | 0.51 |
| alt_plays / by_market / spread | 2-6 | 25.0% | 2.45 | 30.6% | 0.91 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| tds / Anytime TD | 1077 | 23.2% | 25.6% | +2.4 | 1.87 |
| tds / Anytime TD / bins / 0 | 209 | 5.3% | 11.0% | +5.7 | 3.68 |
| tds / Anytime TD / bins / 1 | 323 | 15.0% | 14.9% | -0.1 | -0.05 |
| tds / Anytime TD / bins / 2 | 335 | 26.7% | 31.9% | +5.2 | 2.15 |
| tds / Anytime TD / bins / 3 | 136 | 41.2% | 41.2% | +0.0 | 0.0 |
| tds / Anytime TD / bins / 4 | 52 | 57.0% | 50.0% | -7.0 | -1.02 |
| tds / Anytime TD / bins / 5 | 22 | 70.4% | 72.7% | +2.3 | 0.24 |
| tds / 2+ TDs | 839 | 4.9% | 4.1% | -0.8 | -1.07 |
| tds / 2+ TDs / bins / 0 | 725 | 2.7% | 2.5% | -0.2 | -0.33 |
| tds / 2+ TDs / bins / 1 | 73 | 13.7% | 12.3% | -1.4 | -0.35 |
| tds / 2+ TDs / bins / 2 | 33 | 26.8% | 15.2% | -11.6 | -1.5 |
| tds / 2+ TDs / bins / 3 | 8 | 40.2% | 25.0% | -15.2 | -0.88 |
| combos / QB + WR1 overs | 109 | 31.5% | 33.9% | +2.4 | 0.54 |
| combos / QB over + opponent team total over | 111 | 25.3% | 27.0% | +1.7 | 0.41 |
| combos / QB over + team covers | 105 | 27.7% | 24.8% | -2.9 | -0.66 |
| combos / QB over + team total over | 111 | 29.6% | 28.8% | -0.8 | -0.18 |
| combos / RB1 anytime TD + team wins | 111 | 30.5% | 31.5% | +1.0 | 0.23 |
| combos / RB1 rush over + team wins | 111 | 27.2% | 27.9% | +0.7 | 0.17 |
| combos / WR1 over + team total over | 110 | 26.2% | 26.4% | +0.2 | 0.05 |
| combos / team total over + game over | 114 | 37.4% | 41.2% | +3.8 | 0.84 |
| combo_total | 882 | 29.5% | 30.3% | +0.8 | 0.52 |
| alt_parlays (tickets) | 51 | 48.2% | 45.1% | -3.1 | -0.44 |
| alt_parlays (legs) | 205 | 82.7% | 79.5% | -3.2 | -1.21 |
| alt_parlays / by_v / 1 (tickets) | 39 | 46.3% | 38.5% | -7.8 | -0.98 |
| alt_parlays / by_v / 2 (tickets) | 12 | 54.5% | 66.7% | +12.2 | 0.85 |
| alt_mix (tickets) | 9 | 47.1% | 44.4% | -2.7 | -0.16 |
| alt_mix / by_v / 1 (tickets) | 9 | 47.1% | 44.4% | -2.7 | -0.16 |
| alt_leg_types / QB pass attempts Over | 23 | 76.0% | 73.9% | -2.1 | -0.24 |
| alt_leg_types / QB completions Over | 26 | 80.3% | 84.6% | +4.3 | 0.55 |
| alt_leg_types / QB passing yards Over | 161 | 78.0% | 70.2% | -7.8 | -2.39 |
| alt_leg_types / RB rushing yards Over | 165 | 79.5% | 66.1% | -13.4 | -4.26 |
| alt_leg_types / TE receiving yards Over | 83 | 77.3% | 77.1% | -0.2 | -0.04 |
| alt_leg_types / QB completions Under | 13 | 75.2% | 76.9% | +1.7 | 0.14 |
| alt_leg_types / RB carries Under | 10 | 82.3% | 50.0% | -32.3 | -2.68 |
| alt_leg_types / Receptions Under (any position) | 367 | 82.8% | 83.4% | +0.6 | 0.3 |
| alt_leg_types / WR receiving yards Over | 188 | 77.7% | 78.2% | +0.5 | 0.16 |
| alt_leg_types / Receptions Over (any position) | 170 | 78.8% | 78.8% | +0.0 | 0.0 |
| teasers (legs) | 292 | 68.6% | 67.1% | -1.5 | -0.55 |
| cross_parlays (legs) | 6 | 76.7% | 50.0% | -26.7 | -1.55 |

Gates: NFL prop Overs (yardage) paused; NFL receptions props paused; NFL passing-yard Unders paused; NFL spreads active; NFL totals active

## NHL
Updated 12.4 hours ago, odds from odds_api, credits left 465.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| prop_plays | 222-216 | 50.7% | -15.33 | -3.5% | -0.77 |
| by_type / prop / points|Under | 106-104 | 50.5% | -10.14 | -4.8% | -0.73 |
| picks / ml | 78-102 | 43.3% | -27.76 | -15.4% | -2.18 |
| picks / pl | 88-92 | 48.9% | -13.09 | -7.3% | -1.03 |
| picks / total | 88-92 | 48.9% | -12.16 | -6.8% | -0.95 |
| by_type / prop / sog|Under | 89-81 | 52.4% | -2.77 | -1.6% | -0.22 |
| plays | 32-30 | 51.6% | 5.02 | 8.1% | 0.67 |
| by_type / prop / sog|Over | 22-14 | 61.1% | 4.78 | 13.3% | 0.84 |
| by_type / game / total | 16-12 | 57.1% | 2.8 | 10.0% | 0.56 |
| by_type / game / ml | 15-12 | 55.6% | 7.33 | 27.1% | 1.48 |
| by_type / prop / points|Over | 5-17 | 22.7% | -7.2 | -32.7% | -1.61 |
| edge | 6-12 | 33.3% | -4.9 | -27.2% | -1.21 |
| by_type / game / pl | 1-6 | 14.3% | -5.11 | -73.0% | -2.03 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / sog | 6090 | 49.4% | 48.1% | -1.3 | -2.03 |
| calibration / goals | 6090 | 15.4% | 15.6% | +0.2 | 0.43 |
| calibration / assists | 6090 | 22.6% | 25.0% | +2.4 | 4.48 |
| calibration / points | 6090 | 32.9% | 36.0% | +3.1 | 5.15 |
| calibration / saves | 326 | 50.0% | 31.9% | -18.1 | -6.54 |
| alt (tickets) | 96 | 50.9% | 51.0% | +0.1 | 0.02 |
| alt_mix (tickets) | 77 | 48.6% | 50.6% | +2.0 | 0.35 |
| alt_hr (tickets) | 23 | 66.0% | 56.5% | -9.5 | -0.96 |
| alt_old (tickets) | 48 | 46.2% | 39.6% | -6.6 | -0.92 |
| cross_parlays (tickets) | 6 | 47.4% | 66.7% | +19.3 | 0.95 |
| cross_parlays (legs) | 18 | 78.0% | 83.3% | +5.3 | 0.54 |

Gates: NHL points props (Unders) paused; NHL edge parlays paused; NHL moneyline active; NHL puck line paused; NHL totals active; NHL shots on goal Overs active; NHL shots on goal Unders active; NHL goals Overs active; NHL assists Overs active; NHL assists Unders active

## NBA
Updated 9.3 hours ago, odds from odds_api, credits left 461.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| prop_plays | 36-23 | 61.0% | 9.36 | 15.9% | 1.29 |
| picks / ml | 11-15 | 42.3% | -6.86 | -26.4% | -1.42 |
| picks / spread | 12-14 | 46.2% | -3.15 | -12.1% | -0.65 |
| picks / total | 16-10 | 61.5% | 4.67 | 18.0% | 0.96 |
| by_type / prop / pts|Under | 7-7 | 50.0% | -0.99 | -7.1% | -0.28 |
| by_type / prop / pra|Under | 9-1 | 90.0% | 6.81 | 68.1% | 2.27 |
| by_type / prop / fg3m|Under | 4-5 | 44.4% | -2.0 | -22.2% | -0.7 |
| by_type / prop / reb|Under | 7-1 | 87.5% | 5.34 | 66.7% | 1.99 |
| by_type / prop / fg3m|Over | 1-5 | 16.7% | -3.85 | -64.2% | -1.66 |
| by_type / prop / ast|Under | 3-2 | 60.0% | 0.44 | 8.7% | 0.2 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / pts | 549 | 50.0% | 49.4% | -0.6 | -0.28 |
| calibration / reb | 549 | 49.4% | 53.9% | +4.5 | 2.11 |
| calibration / ast | 549 | 48.8% | 52.3% | +3.5 | 1.64 |
| calibration / fg3m | 549 | 42.9% | 46.3% | +3.4 | 1.61 |
| calibration / pra | 549 | 49.9% | 51.9% | +2.0 | 0.94 |
| alt (tickets) | 9 | 49.9% | 55.6% | +5.7 | 0.34 |
| alt_mix (tickets) | 8 | 49.7% | 62.5% | +12.8 | 0.72 |
| cross_parlays (tickets) | 6 | 44.6% | 50.0% | +5.4 | 0.27 |
| cross_parlays (legs) | 18 | 76.5% | 77.8% | +1.3 | 0.13 |

Gates: NBA edge parlays active; NBA moneyline active; NBA spreads active; NBA totals active; NBA points Overs active; NBA points Unders active; NBA rebounds Overs active; NBA rebounds Unders active; NBA assists Overs active; NBA assists Unders active; NBA threes Overs active; NBA threes Unders active; NBA pts+reb+ast Overs active; NBA pts+reb+ast Unders active

## CFB
Updated 12.4 hours ago, odds from odds_api, credits left 491.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| prop_plays | 79-75 | 51.3% | -5.8 | -3.8% | -0.5 |
| picks / total | 49-67 | 42.2% | -22.69 | -19.6% | -2.22 |
| picks / spread | 50-65 | 43.5% | -19.61 | -17.1% | -1.92 |
| picks / ml | 53-57 | 48.2% | -10.01 | -9.1% | -1.0 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / pass_yds | 202 | 50.0% | 52.0% | +2.0 | 0.57 |
| calibration / pass_td | 202 | 48.6% | 46.5% | -2.1 | -0.6 |
| calibration / td | 900 | 37.1% | 36.0% | -1.1 | -0.68 |
| calibration / rush_yds | 303 | 49.5% | 45.5% | -4.0 | -1.39 |
| calibration / rec | 509 | 48.9% | 55.4% | +6.5 | 2.93 |
| calibration / rec_yds | 350 | 49.6% | 55.1% | +5.5 | 2.06 |
| alt (tickets) | 64 | 46.7% | 43.8% | -2.9 | -0.47 |
| teasers (legs) | 464 | 65.5% | 66.8% | +1.3 | 0.59 |

Gates: CFB spreads active; CFB totals active; CFB moneyline active

## Soccer
Updated 12.4 hours ago, odds from odds_api, credits left 460.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| picks / 1x2 | 18-48 | 27.3% | -10.88 | -16.5% | -1.41 |
| picks / total | 32-34 | 48.5% | -7.97 | -12.1% | -1.03 |
| picks / btts | 31-35 | 47.0% | None | None% | None |
| picks / ah | 23-39 | 37.1% | -6.67 | -10.8% | -0.89 |
| picks / dnb | 37-17 | 68.5% | 0.0 | 0.0% | 0.0 |
| picks_by_league / champ / 1x2 | 6-19 | 24.0% | -10.25 | -41.0% | -2.16 |
| picks_by_league / champ / total | 9-16 | 36.0% | -8.48 | -33.9% | -1.79 |
| picks_by_league / champ / btts | 16-9 | 64.0% | None | None% | None |
| picks_by_league / champ / ah | 10-14 | 41.7% | 0.88 | 3.7% | 0.19 |
| picks_by_league / laliga / 1x2 | 9-12 | 42.9% | 7.63 | 36.3% | 1.75 |
| picks_by_league / laliga / total | 13-8 | 61.9% | 1.75 | 8.3% | 0.4 |
| picks_by_league / laliga / btts | 9-12 | 42.9% | None | None% | None |
| picks_by_league / epl / 1x2 | 3-17 | 15.0% | -8.26 | -41.3% | -1.94 |
| picks_by_league / epl / total | 10-10 | 50.0% | -1.24 | -6.2% | -0.29 |
| picks_by_league / epl / btts | 6-14 | 30.0% | None | None% | None |
| picks_by_league / champ / dnb | 15-5 | 75.0% | 0.0 | 0.0% | 0.0 |
| picks_by_league / laliga / ah | 8-12 | 40.0% | -4.85 | -24.2% | -1.14 |
| picks_by_league / laliga / dnb | 14-5 | 73.7% | 0.0 | 0.0% | 0.0 |
| picks_by_league / epl / ah | 5-13 | 27.8% | -2.7 | -15.0% | -0.67 |
| picks_by_league / epl / dnb | 8-7 | 53.3% | 0.0 | 0.0% | 0.0 |
| plays | 7-8 | 46.7% | 6.8 | 45.4% | 1.85 |
| rule | 4-7 | 36.4% | 4.88 | 44.4% | 1.55 |
| by_type / 1x2 | 3-7 | 30.0% | 4.0 | 40.0% | 1.33 |
| by_league / laliga | 2-6 | 25.0% | 1.0 | 12.5% | 0.37 |
| by_type / ah | 4-1 | 80.0% | 2.8 | 56.1% | 1.32 |
| by_league / champ | 4-1 | 80.0% | 2.8 | 56.1% | 1.32 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / goal | 1602 | 9.7% | 8.9% | -0.8 | -1.08 |
| calibration / sot1 | 1602 | 26.2% | 24.5% | -1.7 | -1.55 |
| calibration / sot2 | 1602 | 5.7% | 5.6% | -0.1 | -0.17 |
| alt_parlays (tickets) | 34 | 47.9% | 50.0% | +2.1 | 0.25 |
| alt_parlays (legs) | 102 | 74.3% | 71.6% | -2.7 | -0.62 |
| cross_parlays (legs) | 9 | 79.9% | 77.8% | -2.1 | -0.16 |

Gates: Soccer match result active; Soccer Asian handicap active; Soccer totals active
