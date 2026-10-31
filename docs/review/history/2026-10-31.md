# Weekly model review, 2026-10-31

Flags first (high, then medium, then info). Every number is a graded record from the site's own data.

| Level | Sport | What | Why |
|---|---|---|---|
| high | CFB | losing: picks / spread | 33-53, -22.98u, -26.7% (z -2.61) |
| high | CFB | said vs hit: calibration / rec | said 49.0%, hit 56.1% over 380 (z 2.77) |
| high | CFB | said vs hit: calibration / rec_yds | said 49.6%, hit 57.6% over 264 (z 2.6) |
| high | NFL | said vs hit: alt_leg_types / RB rushing yards Over | said 79.9%, hit 66.3% over 196 (z -4.75) |
| high | NHL | losing: picks / ml | 69-92, -25.81u, -16.0% (z -2.14) |
| high | NHL | said vs hit: calibration / saves | said 50.1%, hit 32.1% over 290 (z -6.13) |
| medium | CFB | losing: picks / total | 39-48, -12.74u, -14.6% (z -1.44) |
| medium | CFB | losing: picks / ml | 34-47, -10.01u, -12.4% (z -1.17) |
| medium | CFB | diagnosed: rush_yds Unders | plays 16-17 (-9.0%); top cause: Bigger edges did worse (41.7% at 8+ points vs 58% below): big gaps from the book usually mean news the model can't see (injury, role, lineup |
| medium | NFL | losing: live_record / picks / spread | 26-29, -5.36u, -9.7% (z -0.76) |
| medium | NFL | said vs hit: tds / Anytime TD / bins / 4 | said 57.1%, hit 48.8% over 43 (z -1.1) |
| medium | NFL | said vs hit: tds / 2+ TDs / bins / 2 | said 27.0%, hit 17.2% over 29 (z -1.19) |
| medium | NFL | diagnosed: pass_yds Overs | plays 3-3 (-5.2%); top cause: Overconfidence: the model gave the bet side 66.5% and it hit 55.3% over 47. Shrink this prop type's chance toward the book's (betrules reali |
| medium | NFL | diagnosed: pass_yds Unders | plays 3-2 (13.9%); top cause: Overconfidence: the model gave the bet side 61.2% and it hit 38.2% over 34. Shrink this prop type's chance toward the book's (betrules reali |
| medium | NFL | diagnosed: rec Overs | plays 8-17 (-34.7%); top cause: Overconfidence: the model gave the bet side 52.3% and it hit 32.0% over 25. Shrink this prop type's chance toward the book's (betrules reali |
| medium | NFL | diagnosed: rec Unders | plays 10-11 (-13.7%); top cause: Role / volume: lines over 2.5 did much worse (30.0% vs 63.6%). High lines are stars the market prices sharply; the model adds little there. |
| medium | NFL | diagnosed: rec_yds Overs | plays 21-18 (2.0%); top cause: No flaw found, and the plays are at break-even or better. If this type is paused, the gate's shadow record decides when it comes back (40+ g |
| medium | NFL | diagnosed: rush_yds Overs | plays 2-4 (-37.5%); top cause: Overconfidence: the model gave the bet side 71.2% and it hit 46.1% over 141. Shrink this prop type's chance toward the book's (betrules real |
| medium | NHL | odds credits low | 29 left this month |
| medium | NHL | losing: picks / pl | 76-85, -17.04u, -10.6% (z -1.41) |
| medium | NHL | said vs hit: alt_hr (tickets) | said 66.0%, hit 56.5% over 23 (z -0.96) |
| medium | NHL | diagnosed: points Overs | plays 5-17 (-32.7%); top cause: No single cause stands out: the losses look like the model having no edge on this prop type rather than one fixable flaw. Keep it paused (sh |
| medium | NHL | diagnosed: points Unders | plays 106-104 (-4.8%); top cause: Overconfidence: the model gave the bet side 55.7% and it hit 34.2% over 38. Shrink this prop type's chance toward the book's (betrules reali |
| medium | Soccer | losing: picks / 1x2 | 10-31, -4.6u, -11.2% (z -0.76) |

## Prop diagnoses
Every prop type that is losing (20+ plays, -8% or worse) or paused, with what's driving it.

### NFL pass_yds Overs
Plays 3-3 (-0.31u, -5.2%); every Over lean 26-21 (4.7%). Checks use every lean on this side (too few plays).

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 66.5% and it hit 55.3% over 47. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.
2. Role / volume: lines at or under 205.5 did much worse (45.8% vs 65.2%). Low lines are bench and low-volume players whose minutes swing; restrict to starters.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 81,
  "actual_minus_model": -3.07,
  "actual_minus_line": 4.65
 },
 "calibration_p_raw": {
  "n": 47,
  "said": 66.5,
  "hit": 55.3
 },
 "book_said": {
  "n": 47,
  "book": 50.0,
  "hit": 55.3
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 11,
   "w": 5,
   "l": 6,
   "pct": 45.5,
   "units": -1.53,
   "roi": -13.9
  },
  {
   "edge": "8-+",
   "n": 36,
   "w": 21,
   "l": 15,
   "pct": 58.3,
   "units": 3.75,
   "roi": 10.4
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
   "n": 47,
   "w": 26,
   "l": 21,
   "pct": 55.3,
   "units": 2.22,
   "roi": 4.7
  }
 },
 "price": {
  "avg_breakeven": 52.8,
  "hit": 55.3,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 205.5": {
   "n": 24,
   "w": 11,
   "l": 13,
   "pct": 45.8,
   "units": -3.19,
   "roi": -13.3
  },
  "> 205.5": {
   "n": 23,
   "w": 15,
   "l": 8,
   "pct": 65.2,
   "units": 5.42,
   "roi": 23.6
  }
 },
 "zeros": {
  "n": 0,
  "of": 47,
  "share": 0.0
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
   "date": "w05",
   "n": 10,
   "w": 6,
   "l": 4,
   "pct": 60.0,
   "units": 1.35,
   "roi": 13.5
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
   "n": 22,
   "w": 12,
   "l": 10,
   "pct": 54.5,
   "units": 0.72,
   "roi": 3.3
  }
 }
}
```
</details>

### NFL pass_yds Unders
Plays 3-2 (+0.69u, 13.9%); every Under lean 13-21 (-27.6%). Checks use every lean on this side (too few plays).

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 61.2% and it hit 38.2% over 34. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.
2. Bigger edges did worse (30.4% at 8+ points vs 55% below): big gaps from the book usually mean news the model can't see (injury, role, lineup). Cap the edge for pass_yds lower.
3. Role / volume: lines over 242.5 did much worse (31.2% vs 44.4%). High lines are stars the market prices sharply; the model adds little there.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 81,
  "actual_minus_model": -3.07,
  "actual_minus_line": 4.65
 },
 "calibration_p_raw": {
  "n": 34,
  "said": 61.2,
  "hit": 38.2
 },
 "book_said": {
  "n": 34,
  "book": 50.0,
  "hit": 38.2
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 11,
   "w": 6,
   "l": 5,
   "pct": 54.5,
   "units": 0.37,
   "roi": 3.4
  },
  {
   "edge": "8-+",
   "n": 23,
   "w": 7,
   "l": 16,
   "pct": 30.4,
   "units": -9.74,
   "roi": -42.4
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
   "n": 34,
   "w": 13,
   "l": 21,
   "pct": 38.2,
   "units": -9.37,
   "roi": -27.6
  }
 },
 "price": {
  "avg_breakeven": 52.8,
  "hit": 38.2,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 242.5": {
   "n": 18,
   "w": 8,
   "l": 10,
   "pct": 44.4,
   "units": -2.85,
   "roi": -15.8
  },
  "> 242.5": {
   "n": 16,
   "w": 5,
   "l": 11,
   "pct": 31.2,
   "units": -6.52,
   "roi": -40.7
  }
 },
 "clustering": [
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
  },
  {
   "date": "w04",
   "n": 8,
   "w": 1,
   "l": 7,
   "pct": 12.5,
   "units": -6.1,
   "roi": -76.2
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
   "n": 17,
   "w": 8,
   "l": 9,
   "pct": 47.1,
   "units": -1.83,
   "roi": -10.8
  }
 }
}
```
</details>

### NFL rec Overs
Plays 8-17 (-8.68u, -34.7%); every Over lean 102-97 (2.6%). Checks use plays.

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 52.3% and it hit 32.0% over 25. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 465,
  "actual_minus_model": 0.43,
  "actual_minus_line": 0.15
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
   "n": 199,
   "w": 102,
   "l": 97,
   "pct": 51.3,
   "units": 5.14,
   "roi": 2.6
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
Plays 10-11 (-2.87u, -13.7%); every Under lean 143-123 (0.8%). Checks use plays.

**Likely causes, most likely first:**
1. Role / volume: lines over 2.5 did much worse (30.0% vs 63.6%). High lines are stars the market prices sharply; the model adds little there.
2. Projection bias: results ran 0.43 above the model's middle number on 465 rec props, while the book's line missed by only +0.15. The model's level for rec is off; shift it up (or let the prop bias correction learn faster).

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 465,
  "actual_minus_model": 0.43,
  "actual_minus_line": 0.15
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
   "n": 266,
   "w": 143,
   "l": 123,
   "pct": 53.8,
   "units": 2.22,
   "roi": 0.8
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
Plays 21-18 (+0.78u, 2.0%); every Over lean 99-91 (-1.3%). Checks use plays.

**Likely causes, most likely first:**
1. No flaw found, and the plays are at break-even or better. If this type is paused, the gate's shadow record decides when it comes back (40+ graded over 3+ weeks, positive return, closing value not negative).

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 464,
  "actual_minus_model": 7.59,
  "actual_minus_line": 5.05
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
   "n": 190,
   "w": 99,
   "l": 91,
   "pct": 52.1,
   "units": -2.39,
   "roi": -1.3
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
Plays 2-4 (-2.25u, -37.5%); every Over lean 65-76 (-12.8%). Checks use every lean on this side (too few plays).

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 71.2% and it hit 46.1% over 141. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 260,
  "actual_minus_model": 1.11,
  "actual_minus_line": 2.98
 },
 "calibration_p_raw": {
  "n": 141,
  "said": 71.2,
  "hit": 46.1
 },
 "book_said": {
  "n": 141,
  "book": 49.9,
  "hit": 46.1
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 20,
   "w": 5,
   "l": 15,
   "pct": 25.0,
   "units": -10.63,
   "roi": -53.1
  },
  {
   "edge": "8-+",
   "n": 121,
   "w": 60,
   "l": 61,
   "pct": 49.6,
   "units": -7.38,
   "roi": -6.1
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
   "n": 141,
   "w": 65,
   "l": 76,
   "pct": 46.1,
   "units": -18.01,
   "roi": -12.8
  }
 },
 "price": {
  "avg_breakeven": 52.7,
  "hit": 46.1,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 18.5": {
   "n": 72,
   "w": 29,
   "l": 43,
   "pct": 40.3,
   "units": -17.11,
   "roi": -23.8
  },
  "> 18.5": {
   "n": 69,
   "w": 36,
   "l": 33,
   "pct": 52.2,
   "units": -0.89,
   "roi": -1.3
  }
 },
 "zeros": {
  "n": 11,
  "of": 129,
  "share": 8.5
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
   "date": "w07",
   "n": 32,
   "w": 14,
   "l": 18,
   "pct": 43.8,
   "units": -5.62,
   "roi": -17.6
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
   "n": 66,
   "w": 27,
   "l": 39,
   "pct": 40.9,
   "units": -15.01,
   "roi": -22.7
  }
 }
}
```
</details>

### NHL points Overs
Plays 5-17 (-7.2u, -32.7%); every Over lean 63-156 (-23.6%). Checks use plays.

**Likely causes, most likely first:**
1. No single cause stands out: the losses look like the model having no edge on this prop type rather than one fixable flaw. Keep it paused (shadow plays keep grading it) until the gate's evidence says otherwise.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 1155,
  "actual_minus_model": 0.05,
  "actual_minus_line": 0.02
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
   "n": 219,
   "w": 63,
   "l": 156,
   "pct": 28.8,
   "units": -51.64,
   "roi": -23.6
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
Plays 106-104 (-10.14u, -4.8%); every Under lean 542-394 (-1.9%). Checks use plays.

**Likely causes, most likely first:**
1. Overconfidence: the model gave the bet side 55.7% and it hit 34.2% over 38. Shrink this prop type's chance toward the book's (betrules realization k) or raise its edge bar.
2. Role / volume: lines at or under 0.5 did much worse (49.2% vs 69.2%). Low lines are bench and low-volume players whose minutes swing; restrict to starters.

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 1155,
  "actual_minus_model": 0.05,
  "actual_minus_line": 0.02
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
   "n": 936,
   "w": 542,
   "l": 394,
   "pct": 57.9,
   "units": -17.36,
   "roi": -1.9
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

### CFB rush_yds Unders
Plays 16-17 (-2.97u, -9.0%); every Under lean 85-66 (5.4%). Checks use plays.

**Likely causes, most likely first:**
1. Bigger edges did worse (41.7% at 8+ points vs 58% below): big gaps from the book usually mean news the model can't see (injury, role, lineup). Cap the edge for rush_yds lower.
2. Role / volume: lines over 60.5 did much worse (37.5% vs 58.8%). High lines are stars the market prices sharply; the model adds little there.
3. Projection bias: results ran 8.60 above the model's middle number on 243 rush_yds props, while the book's line missed by only +1.63. The model's level for rush_yds is off; shift it up (or let the prop bias correction learn faster).

<details><summary>All checks</summary>

```
{
 "projection": {
  "n": 243,
  "actual_minus_model": 8.6,
  "actual_minus_line": 1.63
 },
 "calibration_p_raw": {
  "n": 24,
  "said": 58.4,
  "hit": 50.0
 },
 "calibration_p_adj": {
  "n": 14,
  "said": 56.6,
  "hit": 57.1
 },
 "book_said": {
  "n": 24,
  "book": 50.0,
  "hit": 50.0
 },
 "by_edge": [
  {
   "edge": "4-8",
   "n": 12,
   "w": 7,
   "l": 5,
   "pct": 58.3,
   "units": 1.18,
   "roi": 9.8
  },
  {
   "edge": "8-+",
   "n": 12,
   "w": 5,
   "l": 7,
   "pct": 41.7,
   "units": -2.64,
   "roi": -22.0
  }
 ],
 "plays_vs_leans": {
  "plays": {
   "n": 33,
   "w": 16,
   "l": 17,
   "pct": 48.5,
   "units": -2.97,
   "roi": -9.0
  },
  "all_leans": {
   "n": 151,
   "w": 85,
   "l": 66,
   "pct": 56.3,
   "units": 8.2,
   "roi": 5.4
  }
 },
 "price": {
  "avg_breakeven": 53.3,
  "hit": 48.5,
  "heavy_juice_share": 0.0
 },
 "line_size": {
  "<= 60.5": {
   "n": 17,
   "w": 10,
   "l": 7,
   "pct": 58.8,
   "units": 1.79,
   "roi": 10.5
  },
  "> 60.5": {
   "n": 16,
   "w": 6,
   "l": 10,
   "pct": 37.5,
   "units": -4.76,
   "roi": -29.7
  }
 },
 "clustering": [
  {
   "date": "2026-w08",
   "n": 14,
   "w": 8,
   "l": 6,
   "pct": 57.1,
   "units": 1.01,
   "roi": 7.2
  },
  {
   "date": "2026-w07",
   "n": 10,
   "w": 4,
   "l": 6,
   "pct": 40.0,
   "units": -2.48,
   "roi": -24.8
  },
  {
   "date": "2026-w06",
   "n": 9,
   "w": 4,
   "l": 5,
   "pct": 44.4,
   "units": -1.51,
   "roi": -16.7
  }
 ]
}
```
</details>


## NFL
Updated 0.7 hours ago, odds from None, credits left None.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| plays_record / props | 85-76 | 52.8% | -0.03 | -0.0% | -0.0 |
| live_record / picks / total | 31-29 | 51.7% | -0.82 | -1.4% | -0.11 |
| live_record / picks / moneyline | 35-24 | 59.3% | 4.2 | 7.1% | 0.58 |
| live_record / picks / spread | 26-29 | 47.3% | -5.36 | -9.7% | -0.76 |
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
| live_record / picks_by_week / 7 / spread | 8-4 | 66.7% | 3.27 | 27.2% | 0.99 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| tds / Anytime TD | 892 | 23.1% | 25.2% | +2.1 | 1.49 |
| tds / Anytime TD / bins / 0 | 189 | 5.1% | 9.5% | +4.4 | 2.75 |
| tds / Anytime TD / bins / 1 | 257 | 14.8% | 15.6% | +0.8 | 0.36 |
| tds / Anytime TD / bins / 2 | 268 | 26.9% | 31.7% | +4.8 | 1.77 |
| tds / Anytime TD / bins / 3 | 113 | 40.9% | 39.8% | -1.1 | -0.24 |
| tds / Anytime TD / bins / 4 | 43 | 57.1% | 48.8% | -8.3 | -1.1 |
| tds / Anytime TD / bins / 5 | 22 | 70.4% | 72.7% | +2.3 | 0.24 |
| tds / 2+ TDs | 654 | 5.1% | 4.4% | -0.7 | -0.81 |
| tds / 2+ TDs / bins / 0 | 563 | 2.6% | 2.7% | +0.1 | 0.15 |
| tds / 2+ TDs / bins / 1 | 54 | 13.5% | 13.0% | -0.5 | -0.11 |
| tds / 2+ TDs / bins / 2 | 29 | 27.0% | 17.2% | -9.8 | -1.19 |
| tds / 2+ TDs / bins / 3 | 8 | 40.2% | 25.0% | -15.2 | -0.88 |
| combos / QB + WR1 overs | 85 | 31.6% | 35.3% | +3.7 | 0.73 |
| combos / QB over + opponent team total over | 87 | 25.3% | 27.6% | +2.3 | 0.49 |
| combos / QB over + team covers | 81 | 27.7% | 25.9% | -1.8 | -0.36 |
| combos / QB over + team total over | 87 | 29.6% | 27.6% | -2.0 | -0.41 |
| combos / RB1 anytime TD + team wins | 87 | 31.0% | 31.0% | +0.0 | 0.0 |
| combos / RB1 rush over + team wins | 87 | 27.2% | 28.7% | +1.5 | 0.31 |
| combos / WR1 over + team total over | 86 | 26.2% | 25.6% | -0.6 | -0.13 |
| combos / team total over + game over | 88 | 37.5% | 42.0% | +4.5 | 0.87 |
| combo_total | 688 | 29.5% | 30.5% | +1.0 | 0.58 |
| alt_parlays (tickets) | 41 | 46.7% | 39.0% | -7.7 | -0.99 |
| alt_parlays (legs) | 172 | 82.6% | 78.5% | -4.1 | -1.42 |
| alt_parlays / by_v / 1 (tickets) | 39 | 46.3% | 38.5% | -7.8 | -0.98 |
| alt_mix (tickets) | 9 | 47.1% | 44.4% | -2.7 | -0.16 |
| alt_mix / by_v / 1 (tickets) | 9 | 47.1% | 44.4% | -2.7 | -0.16 |
| alt_leg_types / QB passing yards Over | 184 | 78.5% | 71.7% | -6.8 | -2.25 |
| alt_leg_types / RB rushing yards Over | 196 | 79.9% | 66.3% | -13.6 | -4.75 |
| alt_leg_types / TE receiving yards Over | 91 | 76.7% | 71.4% | -5.3 | -1.2 |
| alt_leg_types / Receptions Under (any position) | 382 | 82.4% | 82.7% | +0.3 | 0.15 |
| alt_leg_types / WR receiving yards Over | 184 | 78.3% | 79.9% | +1.6 | 0.53 |
| alt_leg_types / Receptions Over (any position) | 184 | 80.0% | 79.9% | -0.1 | -0.03 |
| teasers (legs) | 240 | 68.6% | 67.5% | -1.1 | -0.37 |

Gates: NFL prop Overs (yardage) paused; NFL receptions props paused; NFL passing-yard Unders paused; NFL spreads active; NFL totals active

## NHL
Updated 0.7 hours ago, odds from odds_api, credits left 29.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| prop_plays | 220-210 | 51.2% | -11.68 | -2.7% | -0.59 |
| by_type / prop / points|Under | 106-104 | 50.5% | -10.14 | -4.8% | -0.73 |
| by_type / prop / sog|Under | 87-75 | 53.7% | 0.88 | 0.5% | 0.07 |
| picks / ml | 69-92 | 42.9% | -25.81 | -16.0% | -2.14 |
| picks / pl | 76-85 | 47.2% | -17.04 | -10.6% | -1.41 |
| picks / total | 78-83 | 48.4% | -11.49 | -7.1% | -0.95 |
| plays | 31-30 | 50.8% | 4.12 | 6.7% | 0.55 |
| by_type / prop / sog|Over | 22-14 | 61.1% | 4.78 | 13.3% | 0.84 |
| by_type / game / total | 16-12 | 57.1% | 2.8 | 10.0% | 0.56 |
| by_type / game / ml | 14-12 | 53.8% | 6.43 | 24.7% | 1.33 |
| by_type / prop / points|Over | 5-17 | 22.7% | -7.2 | -32.7% | -1.61 |
| edge | 6-12 | 33.3% | -4.9 | -27.2% | -1.21 |
| by_type / game / pl | 1-6 | 14.3% | -5.11 | -73.0% | -2.03 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / sog | 5452 | 49.3% | 48.2% | -1.1 | -1.62 |
| calibration / goals | 5452 | 15.3% | 15.5% | +0.2 | 0.41 |
| calibration / assists | 5452 | 22.5% | 24.8% | +2.3 | 4.07 |
| calibration / points | 5452 | 32.7% | 35.7% | +3.0 | 4.72 |
| calibration / saves | 290 | 50.1% | 32.1% | -18.0 | -6.13 |
| alt (tickets) | 80 | 50.6% | 57.5% | +6.9 | 1.23 |
| alt_mix (tickets) | 62 | 48.3% | 48.4% | +0.1 | 0.02 |
| alt_hr (tickets) | 23 | 66.0% | 56.5% | -9.5 | -0.96 |
| alt_old (tickets) | 48 | 46.2% | 39.6% | -6.6 | -0.92 |

Gates: NHL points props (Unders) paused; NHL edge parlays paused; NHL moneyline active; NHL puck line paused; NHL totals active; NHL shots on goal Overs active; NHL shots on goal Unders active; NHL goals Overs active; NHL assists Overs active; NHL assists Unders active

## NBA
Updated 0.7 hours ago, odds from odds_api, credits left 488.


Gates: NBA edge parlays active; NBA moneyline active; NBA spreads active; NBA totals active; NBA points Overs active; NBA points Unders active; NBA rebounds Overs active; NBA rebounds Unders active; NBA assists Overs active; NBA assists Unders active; NBA threes Overs active; NBA threes Unders active; NBA pts+reb+ast Overs active; NBA pts+reb+ast Unders active

## CFB
Updated 0.5 hours ago, odds from odds_api, credits left 140.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| prop_plays | 68-65 | 51.1% | -5.46 | -4.1% | -0.5 |
| picks / total | 39-48 | 44.8% | -12.74 | -14.6% | -1.44 |
| picks / spread | 33-53 | 38.4% | -22.98 | -26.7% | -2.61 |
| picks / ml | 34-47 | 42.0% | -10.01 | -12.4% | -1.17 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / pass_yds | 154 | 50.0% | 53.2% | +3.2 | 0.79 |
| calibration / pass_td | 154 | 48.5% | 47.4% | -1.1 | -0.27 |
| calibration / td | 680 | 37.3% | 36.2% | -1.1 | -0.59 |
| calibration / rush_yds | 229 | 49.5% | 45.9% | -3.6 | -1.09 |
| calibration / rec | 380 | 49.0% | 56.1% | +7.1 | 2.77 |
| calibration / rec_yds | 264 | 49.6% | 57.6% | +8.0 | 2.6 |
| alt (tickets) | 49 | 46.3% | 49.0% | +2.7 | 0.38 |
| teasers (legs) | 348 | 65.6% | 67.2% | +1.6 | 0.63 |

Gates: CFB spreads active; CFB totals active; CFB moneyline active

## Soccer
Updated 0.3 hours ago, odds from odds_api, credits left 125.

| Record | W-L | Hit | Units | Return | z |
|---|---|---|---|---|---|
| picks / 1x2 | 10-31 | 24.4% | -4.6 | -11.2% | -0.76 |
| picks / total | 21-20 | 51.2% | -2.56 | -6.2% | -0.42 |
| picks / btts | 21-20 | 51.2% | None | None% | None |
| picks / ah | 16-22 | 42.1% | 0.88 | 2.3% | 0.15 |
| picks / dnb | 21-11 | 65.6% | 0.0 | 0.0% | 0.0 |
| picks_by_league / champ / 1x2 | 6-11 | 35.3% | -2.25 | -13.2% | -0.57 |
| picks_by_league / champ / total | 7-10 | 41.2% | -3.87 | -22.8% | -0.99 |
| picks_by_league / champ / btts | 11-6 | 64.7% | None | None% | None |
| picks_by_league / champ / ah | 9-7 | 56.2% | 0.88 | 5.5% | 0.23 |
| picks_by_league / champ / dnb | 10-3 | 76.9% | 0.0 | 0.0% | 0.0 |
| picks_by_league / laliga / 1x2 | 3-10 | 23.1% | 3.65 | 28.1% | 1.07 |
| picks_by_league / laliga / total | 8-5 | 61.5% | 1.1 | 8.5% | 0.32 |
| picks_by_league / laliga / btts | 6-7 | 46.2% | None | None% | None |
| picks_by_league / laliga / ah | 5-7 | 41.7% | None | None% | None |
| picks_by_league / epl / 1x2 | 1-10 | 9.1% | -6.0 | -54.5% | -1.9 |
| picks_by_league / epl / total | 6-5 | 54.5% | 0.22 | 2.0% | 0.07 |
| picks_by_league / epl / btts | 4-7 | 36.4% | None | None% | None |
| picks_by_league / laliga / dnb | 7-4 | 63.6% | 0.0 | 0.0% | 0.0 |
| plays | 6-5 | 54.5% | 5.8 | 52.8% | 1.84 |
| picks_by_league / epl / ah | 2-8 | 20.0% | None | None% | None |
| picks_by_league / epl / dnb | 4-4 | 50.0% | 0.0 | 0.0% | 0.0 |
| rule | 3-4 | 42.9% | 3.88 | 55.5% | 1.55 |
| by_type / 1x2 | 2-4 | 33.3% | 3.0 | 50.0% | 1.29 |
| by_league / laliga | 2-4 | 33.3% | 3.0 | 50.0% | 1.29 |
| by_type / ah | 4-1 | 80.0% | 2.8 | 56.1% | 1.32 |
| by_league / champ | 4-1 | 80.0% | 2.8 | 56.1% | 1.32 |

| Said vs hit | n | Said | Hit | Gap | z |
|---|---|---|---|---|---|
| calibration / goal | 986 | 9.8% | 8.0% | -1.8 | -1.9 |
| calibration / sot1 | 986 | 26.4% | 24.6% | -1.8 | -1.28 |
| calibration / sot2 | 986 | 5.8% | 6.0% | +0.2 | 0.27 |
| alt_parlays (tickets) | 20 | 47.6% | 50.0% | +2.4 | 0.21 |
| alt_parlays (legs) | 60 | 74.2% | 71.7% | -2.5 | -0.44 |

Gates: Soccer match result active; Soccer Asian handicap active; Soccer totals active
