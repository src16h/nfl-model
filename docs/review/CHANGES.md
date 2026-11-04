# Model changes log

Every adjustment from the weekly review (and big fixes made by hand), newest first. Rules: docs/review/RULES.md.

## 2026-11-03 (weekly review)
- NBA | same-game parlay player legs held to Hard Rock's real ladder depth: at most 8 points, 2 rebounds, 2 assists, 1 three under the book's main line (nbamodel/config.py ALT_MAX_DROP, on top of the 2-rung rule); locked tickets with a deeper leg are rebuilt | new "nbamain" probe (Odds market check, 2 games, 96 Hard Rock player lines): Hard Rock's lowest rung sits 2-9 points, 1-4 boards/assists, 0-2 threes under the main; the old rule allowed 162 legs on those lines and 21 were on rungs Hard Rock doesn't list (9.5 pts under 18.5/19.5 mains, 1.5 reb/ast under 4.5-5.5 mains, 0.5 threes under 2.5); new rule 127 legs, 1 off. In the last 4 days of tickets about 38 of 55 player legs were deeper than the new limits | every leg bettable at Hard Rock; legs slightly less likely each, so tickets reach the odds window with shallower legs | look again on 2026-11-10 (rerun "nbamain" probe, check tickets still build most nights)
- Tools | Odds market check gets "nbamain" and "nhlmain" (Hard Rock main line vs lowest alt rung per player; about 16 NBA / 4 NHL credits) | the Kalshi-style ladders were the guide until today's switch back to Hard Rock | n/a | n/a

Diagnosed (no change):
- NHL points Unders (paused): plays 106-104, -4.8% (all before Oct 21). The diagnosis's top cause (overconfidence, 55.7% said vs 34.2% hit) rests on 38 plays from one night (Oct 19). The cleaner split in the plays is edge size: raw edge under 4 went 41-63 (-23.7%), 4+ went 49-33 (+8.1u). But it does not hold out of sample: since the pause, Under leans with 4+ edge went 36-35 (-10.7%) and under 4 went 40-47. Low lines (0.5) are 197 of 210 plays, so line size can't separate them. No fixable cause: the model has no edge on points Unders. Keep paused. Note: with the points realization factor at its 0.40 floor, no shadow play has cleared the bar since Oct 21 (0 graded), so this gate can't reopen on its own; that is acceptable while there is no edge.
- NHL points Overs (paused, also blocked): plays 5-17, every Over lean 68-160 (-21.8%). No single cause. No edge; keep paused.
- NFL receptions Overs (plays 8-17, -34.7%) and Unders (10-11, -13.7%), all weeks 4-5, before receptions were removed from plays. Overs: said 52% at the bet side, hit 32% over 25. Unders: lines over 2.5 went 3-7; level bias +0.41 catches vs the model (book +0.10). Leans on both sides are near break-even (Overs 128-122 +1.7%, Unders 174-148 +1.2%), so there is no edge to fix toward. Keep receptions out of plays.
- NFL rushing-yard Overs: Over leans said 71.2%, hit 43.4% over 173 (8+ edges 68-78). Overs are already leans only (PROP_PLAY_SIDES = Under); the gap is the model reading big Over edges the market already prices. No change.
- NFL passing-yard Unders (paused): leans 20-24; 8+ edges 10-18, 4-8 edges 10-6; recent half 15-12. Thin (44). Gate's shadow plays decide; possible future fix is an edge cap (PROP_EDGE_CAP) if 8+ edges keep losing. Watch.
- NFL passing-yard Overs (3-3 plays) and receiving-yard Overs (21-18, +2.0%): Overs are leans only; no flaw found in rec_yds Overs.

Watch:
- NHL alt ladder parlay (Nov 1): legs Over 0.5 shots under a 2.5 main (13 of 15 ladder legs) — not yet checked against Hard Rock's own shots ladder ("player_shots_alternate"). The "nhlmain" probe ran too early (no Hard Rock props posted yet); run it on a game day afternoon.
- NHL saves: said 50.0%, hit 31.9% over 326 (model's middle number runs high). Blocked from plays, and saves legs are main line only at about 50%, so nothing bettable uses it. Fixing the saves projection is a model change and needs a walk-forward test.
- CFB receptions / receiving yards: said 48.9% / 49.6%, hit 55.4% / 55.1% (509 / 350) — meets the recalibration size, but not changed: the calibration only counts players who show up in the box score (zero-catch games are missing), the plays already remove the slate-wide gap to the book, and the bettable use (alt legs) runs the other way: receiving-yard alt legs said 71.2%, hit 66.7% over 72. Raising the projection would make those legs more overconfident.
- CFB rushing-yard alt legs: said 79.4%, hit 60.0% over 30 legs (thin).
- NFL Anytime TD low bin: said 5.3%, hit 11.0% over 209; bin 2 said 26.7%, hit 31.9% over 335; overall said 23.2%, hit 25.6% over 1,077. TDs are not plays; check how much of this is from before the Oct 20 TD curve before refitting.
- NFL 2+ TDs bin 2: said 26.8%, hit 15.2% over 33 (thin).
- Soccer: plays 7-8 but +6.8u; closing-line value -5.0 over 11 priced plays (needs 30). Championship 1x2 leans 6-19 are leans, not bets.
- NBA: game lines 0-2 as plays (n tiny); props 36-23 (+15.9%) with closing value +1.5 over 6. Backtest 2026: margin miss 11.7 vs market 10.6 (107 games), the model is behind the close on sides; spreads/ML picks are leans.
- Credits (Nov 3): NFL 415, NHL 465 (453 after probe), NBA 461 (434 after probe), CFB 491, Soccer 460. One CFB run failed Oct 31 14:44 and the rerun 2 minutes later passed; every other run in the last 7 days passed.

Last week's changes: none due yet (first look-again dates are Nov 10 and Nov 17). The Nov 3 by-hand changes (Hard Rock only; NHL 16+ minute forwards) are this week's and are counted against this week's limits (NHL 1 of 3).

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
