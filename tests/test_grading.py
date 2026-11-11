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


# ---- parlay tickets in units ----------------------------------------------------------------------------
import parlaymoney as PM  # noqa: E402


def test_ticket_units_at_each_price():
    rows = [{"hit": True, "bet_at": "+122", "fair": "+108"}, {"hit": False, "bet_at": "+122", "fair": "+108"},
            {"hit": True, "bet_at": "-104", "fair": "-120", "book_odds": "+110"}, {"hit": None, "bet_at": "+150"}]
    m = PM.summary(rows)
    assert m["n"] == 3 and m["hits"] == 2
    assert m["at_bet_at"]["units"] == pytest.approx(1.22 - 1 + 100 / 104, abs=0.01)
    assert m["at_fair"]["units"] == pytest.approx(1.08 - 1 + 100 / 120, abs=0.01)
    assert m["at_book"]["n"] == 1 and m["at_book"]["units"] == pytest.approx(1.10)
    assert PM.dec(None) is None and PM.dec("abc") is None and PM.dec(50) is None and PM.dec("+100") == 2.0


def test_ticket_units_empty():
    assert PM.summary([])["at_bet_at"] == {"n": 0, "units": None, "roi": None}


# ---- logged Hard Rock prices ----------------------------------------------------------------------------
def _log(tmp_path, monkeypatch, **kw):
    import importlib
    L = importlib.import_module("tools.log_ticket_price")
    env = {"SPORT": "NHL", "TICKET": "Alt parlay with a team leg", "TEAM": "TOR", "PRICE": "+135", "DATE": "2026-11-12", **kw}
    path = tmp_path / "ticket_prices.csv"
    monkeypatch.setattr(L, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: __import__("datetime").datetime(2026, 11, 12, 15, tzinfo=tz))}))
    L.main(env, path)
    return path


def test_logged_price_is_saved_and_graded(tmp_path, monkeypatch):
    path = _log(tmp_path, monkeypatch)
    prices = PM.load_prices(path)
    assert prices[0]["kind"] == "alt_mix" and prices[0]["price"] == "+135" and prices[0]["team"] == "tor"
    rows = [{"hit": True, "bet_at": "+120", "sport": "nhl", "kind": "alt_mix", "date": "2026-11-12", "teams": ["TOR", "BOS"]},
            {"hit": False, "bet_at": "+120", "sport": "nhl", "kind": "alt", "date": "2026-11-12", "teams": ["TOR", "BOS"]},     # other type
            {"hit": False, "bet_at": "+120", "sport": "nhl", "kind": "alt_mix", "date": "2026-11-12", "teams": ["NYR", "CGY"]}]  # other game
    m = PM.summary(rows, prices)
    assert m["at_book"]["n"] == 1 and m["at_book"]["units"] == pytest.approx(1.35)


def test_logged_price_finds_the_next_game_and_is_used_once(tmp_path, monkeypatch):
    path = _log(tmp_path, monkeypatch, SPORT="NFL", TICKET="Same-game parlay", TEAM="KC", DATE="2026-11-12", PRICE="-105")
    rows = [{"hit": True, "sport": "nfl", "kind": "alt", "date": "2026-11-11", "teams": ["KC", "DEN"]},    # before the logged date
            {"hit": True, "sport": "nfl", "kind": "alt", "date": "2026-11-15", "teams": ["KC", "BUF"]},    # the bet
            {"hit": True, "sport": "nfl", "kind": "alt", "date": "2026-11-22", "teams": ["KC", "LV"]}]     # a week later: not it
    PM.attach_prices(rows, PM.load_prices(path))
    assert [r.get("logged_price") for r in rows] == [None, "-105", None]


def test_soccer_names_match_loosely(tmp_path, monkeypatch):
    path = _log(tmp_path, monkeypatch, SPORT="Soccer", TICKET="Same-game parlay", TEAM="Man City", PRICE="+150")
    rows = [{"hit": True, "sport": "soccer", "kind": "alt", "date": "2026-11-12", "teams": ["Man City", "Fulham"]}]
    assert PM.attach_prices(rows, PM.load_prices(path))[0]["logged_price"] == "+150"


@pytest.mark.parametrize("bad", [{"SPORT": "CFB"}, {"TICKET": "teaser"}, {"TEAM": "x"}, {"TEAM": "TOR; rm -rf /"}, {"PRICE": "135x"},
                                 {"PRICE": "+50"}, {"DATE": "2026-13-01"}, {"DATE": "2027-01-01"}])
def test_bad_input_is_refused(tmp_path, monkeypatch, bad):
    with pytest.raises(SystemExit):
        _log(tmp_path, monkeypatch, **bad)
    assert not (tmp_path / "ticket_prices.csv").exists()


def test_price_without_a_sign_is_read_as_plus(tmp_path, monkeypatch):
    assert PM.load_prices(_log(tmp_path, monkeypatch, PRICE="135"))[0]["price"] == "+135"
