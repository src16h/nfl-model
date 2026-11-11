"""
Grading: a result has to be scored the same way every time. Run with:  python -m pytest tests -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import altlines as AL  # noqa: E402
import clv as CLV  # noqa: E402
from nflmodel import tracker as T  # noqa: E402

PAY110 = 100 / 110


# ---- NFL props ------------------------------------------------------------------------------------------
STATS = {"rush_yds": 61.0, "rec_yds": 40.0, "rush_td": 1, "rec_td": 0}


@pytest.mark.parametrize("line,lean,outcome,result,profit", [
    ("60.5", "Over", "Over", "win", PAY110), ("60.5", "Under", "Over", "loss", -1.0),
    ("61.5", "Under", "Under", "win", 100 / 120), ("61", "Over", "Push", "push", 0.0)])
def test_nfl_prop_grades(line, lean, outcome, result, profit):
    r = {"stat": "rush_yds", "line": line, "lean": lean, "over_odds": "-110", "under_odds": "-120"}
    g = T._grade_one(r, STATS, "t")
    assert (g["outcome"], g["lean_result"]) == (outcome, result) and g["profit"] == pytest.approx(profit, abs=1e-3)


def test_nfl_td_props_and_voids():
    yes = T._grade_one({"stat": "anytime_td", "line": None, "lean": "Over", "over_odds": "+150"}, STATS, "t")
    assert yes["lean_result"] == "win" and yes["profit"] == pytest.approx(1.5)
    two = T._grade_one({"stat": "tds", "line": "1.5", "lean": "Over", "over_odds": "+600"}, STATS, "t")
    assert two["lean_result"] == "loss"
    void = T._grade_one({"stat": "rush_yds", "line": "60.5", "lean": "Over"}, None, "t")
    assert void["outcome"] == "Void" and void["profit"] == 0.0


def test_a_locked_play_is_graded_at_the_price_it_was_flagged_at():
    r = {"stat": "rush_yds", "line": "70.5", "lean": "Over", "over_odds": "-110", "under_odds": "-110",     # the line moved after the flag
         "flag": {"line": "60.5", "lean": "Over", "odds": "+105", "at": "2026-11-13T23:07+00:00"}}
    T._grade_with_flag(r, STATS, "t")
    assert r["result"]["lean_result"] == "loss"                      # at the latest line (70.5) the Over lost
    assert r["flag_result"]["lean_result"] == "win" and r["flag_result"]["profit"] == pytest.approx(1.05)


# ---- alt lines, team totals, quarter lines -------------------------------------------------------------
@pytest.mark.parametrize("bet,score,res,units", [
    ({"market": "spread", "team": "home", "side": "home", "line": -3.5, "odds": -110}, (24, 20), "W", PAY110),
    ({"market": "spread", "team": "home", "side": "home", "line": -3.5, "odds": -110}, (23, 20), "L", -1.0),
    ({"market": "spread", "team": "away", "side": "away", "line": 3.0, "odds": -110}, (23, 20), "P", 0.0),
    ({"market": "total", "team": None, "side": "over", "line": 43.5, "odds": 120}, (24, 20), "W", 1.2),
    ({"market": "total", "team": None, "side": "under", "line": 44.0, "odds": -105}, (24, 20), "P", 0.0),
    ({"market": "team_total", "team": "away", "side": "over", "line": 19.5, "odds": -115}, (24, 20), "W", 100 / 115),
    ({"market": "spread", "team": "home", "side": "home", "line": -0.75, "odds": 100}, (2, 1), "HW", 0.5),     # wins by one: half win
    ({"market": "spread", "team": "home", "side": "home", "line": -0.25, "odds": 100}, (1, 1), "HL", -0.5),    # draw: half loss
])
def test_alt_line_grades(bet, score, res, units):
    r, u = AL.grade(bet, *score)
    assert r == res and u == pytest.approx(units, abs=1e-6)


# ---- closing value of a game play ----------------------------------------------------------------------
def test_flat_line_scores_zero_clv_and_minus_the_vig():
    g = {"home": "A", "away": "B"}
    c = CLV.close("nhl", "ml", {"side": "A"}, g, {"ml_home": -110, "ml_away": -110}, None)
    clv, ev = CLV.measure(-110, c)
    assert clv == pytest.approx(0.0) and ev == pytest.approx(100 * (0.5 * (1 + PAY110) - 1))


def test_beating_the_close_is_positive():
    g = {"home": "A", "away": "B"}
    c = CLV.close("nhl", "ml", {"side": "A"}, g, {"ml_home": -140, "ml_away": 120}, None)      # we took A at -110, it closed -140
    clv, ev = CLV.measure(-110, c)
    assert clv > 0 and ev > 0
    c = CLV.close("nhl", "ml", {"side": "B"}, g, {"ml_home": -140, "ml_away": 120}, None)      # the other side at -110 got worse
    assert CLV.measure(-110, c)[1] < 0


def test_total_close_at_a_different_line_is_shifted_our_way():
    g = {"home": "A", "away": "B"}
    same = CLV.close("nhl", "total", {"side": "Over"}, g, {"total": 6.0, "over_odds": -110, "under_odds": -110}, 6.0)
    up = CLV.close("nhl", "total", {"side": "Over"}, g, {"total": 6.5, "over_odds": -110, "under_odds": -110}, 6.0)
    assert up["novig"] > same["novig"]                               # we hold Over 6, the market moved to 6.5
    under = CLV.close("nhl", "total", {"side": "Under"}, g, {"total": 6.5, "over_odds": -110, "under_odds": -110}, 6.0)
    assert under["novig"] < same["novig"]


def test_first_flag_is_kept_until_the_side_changes():
    a = CLV.snapshot({"ml": {"play": True, "side": "A", "odds": -110, "line": None}}, None, "t1")
    b = CLV.snapshot({"ml": {"play": True, "side": "A", "odds": -130, "line": None}}, a, "t2")
    assert b["ml"]["odds"] == -110 and b["ml"]["ts"] == "t1"
    c = CLV.snapshot({"ml": {"play": True, "side": "B", "odds": 115, "line": None}}, b, "t3")
    assert c["ml"]["side"] == "B" and c["ml"]["ts"] == "t3"
