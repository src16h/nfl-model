# Model changes log

Every adjustment from the weekly review (and big fixes made by hand), newest first. Rules: docs/review/RULES.md.

## 2026-11-03 (by hand)
- NHL | same-game parlay shot legs: forwards need 16+ projected minutes (defensemen and goalies exempt) | Over 0.5 shots legs Oct 25-Nov 2: players averaging <14 min hit 75.0% (said 81.0%, n=28), 14-17 min 80.8% (said 82.6%, n=130), 17+ min 86.8% (said 83.9%, n=174); tickets 3 for 16 since Oct 31 (said ~53%) | fewer depth-forward misses, legs closer to what they say | look again on 2026-11-17
- All sports | prediction market removed: plays, alt lines and parlays judged at Hard Rock's own price again (no Kalshi blend, no DK cents or fee); pages show Hard Rock odds and take American odds only | the owner bets on Hard Rock | prices match what Hard Rock pays; CFB game-line pull drops to 2 credits | look again on 2026-11-10
- Undoes the 2026-10-31 "DraftKings Predictions stand-in" entry below.

## 2026-10-31 (set up by hand, before the first weekly review)
- All sports | plays judged at a DraftKings Predictions stand-in price (Hard Rock + Kalshi + DK fee, standin.py), Pinnacle still the referee | DK Predictions has no odds feed | fewer plays, priced closer to what DK pays | look again on 2026-11-10
- CFB | new play rules: early totals (3+ days out, 4+ pts off the line) and Pinnacle value only; old leans retired | model weight vs the close 0.01 spreads / -0.03 totals; early totals vs the open 234-170 (57.9%) 2023-2026 | early totals near 55-58% | look again on 2026-11-17
- NBA | new model and page (ratings, props, parlays) | walk-forward margin miss 11.4 vs 11.0 for the close; props calibrated within 2-3 points | first graded week | look again on 2026-11-10
- NBA | alt parlay legs only on posted ladder lines (points 9.5/14.5..., reb/ast 1.5/3.5..., threes 0.5/1.5...), book-posted players, 20+ minutes | legs like Over 0.5 rebounds can't be bet | every ticket bettable | look again on 2026-11-10
- Soccer | Parlays tab, cross-game parlays, same-game tickets lock 3h before kickoff | parlays were hidden and graded on the last rebuilt version | honest ticket record | look again on 2026-11-10
- NFL / NHL / NBA / Soccer | cross-game alt parlays (crossgame.py), legs shaded -0.10 log-odds until graded | same-game alt legs ran about 4 points too confident | look again on 2026-11-17

Watch:
- NHL saves props: said 50%, hit 32% over 290 (already blocked from plays)
- NFL RB rushing Over alt legs: said 80%, hit 66% over 196 (gate has them off)
- CFB receptions / receiving-yard props run high: said 49-50%, hit 56-58% over 260-380
- NHL key nearly out of credits this month (resets Nov 1); NFL key too
