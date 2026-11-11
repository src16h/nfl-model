"""
Pause / restore bars and the pooled game-play check (gates.py). Run with:  python -m pytest tests -q
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gates as GT  # noqa: E402

WIN, LOSS = 100 / 110, -1.0


def rows(n_w, n_l, date="2026-11-01", ev=None, clv=None):
    out = [{"date": date, "res": "W", "units": WIN} for _ in range(n_w)] + [{"date": date, "res": "L", "units": LOSS} for _ in range(n_l)]
    for r in out:
        if ev is not None:
            r["ev"] = ev
        if clv is not None:
            r["clv"] = clv
    return out


@pytest.fixture
def docs(tmp_path):
    for rel in GT.POOL_FILES.values():
        p = tmp_path / "docs" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
    return tmp_path / "docs"


def gate(docs, name, status=None, since=None):
    sport = name.split("_")[0]
    path = docs / GT.POOL_FILES[sport]
    st = GT.load(path, (name,))
    if status:
        st[name].update({"status": status, "since": since or st[name]["since"]})
    return path, st


# ---- active -> paused ------------------------------------------------------------------------------------
def test_a_normal_losing_run_does_not_pause(docs):
    path, st = gate(docs, "nba_prop_pts_Under")
    GT.update(path, st, "nba_prop_pts_Under", [], rows(11, 14), "2026-11-11")          # 25 plays, -16%: ordinary bad luck
    assert st["nba_prop_pts_Under"]["status"] == "active"


def test_a_loss_too_big_to_be_luck_pauses(docs):
    path, st = gate(docs, "nba_prop_pts_Under")
    out = GT.update(path, st, "nba_prop_pts_Under", [], rows(6, 19), "2026-11-11")     # 6-19: z about -2.7
    assert st["nba_prop_pts_Under"]["status"] == "paused" and out["record"]["z"] <= GT.ROI_Z
    assert st["nba_prop_pts_Under"]["history"][-1]["reason"] == "return"


def test_a_long_losing_record_pauses_at_the_backstop(docs):
    path, st = gate(docs, "nba_prop_pts_Under")
    GT.update(path, st, "nba_prop_pts_Under", [], rows(71, 78), "2026-11-11")          # 149 plays at -9%: not yet
    assert st["nba_prop_pts_Under"]["status"] == "active"
    GT.update(path, st, "nba_prop_pts_Under", [], rows(72, 79), "2026-11-11")          # 151 plays at -9%
    assert st["nba_prop_pts_Under"]["status"] == "paused"


def test_losing_to_the_close_pauses_even_when_winning(docs):
    path, st = gate(docs, "nba_prop_pts_Under")
    GT.update(path, st, "nba_prop_pts_Under", [], rows(20, 9, ev=-3.0), "2026-11-11")  # 29 priced: one short
    assert st["nba_prop_pts_Under"]["status"] == "active"
    GT.update(path, st, "nba_prop_pts_Under", [], rows(20, 10, ev=-3.0), "2026-11-11")
    assert st["nba_prop_pts_Under"]["status"] == "paused"
    assert st["nba_prop_pts_Under"]["history"][-1]["reason"] == "lost to the closing line"


def test_only_plays_since_the_gate_date_count(docs):
    path, st = gate(docs, "nba_prop_pts_Under")
    GT.update(path, st, "nba_prop_pts_Under", [], rows(0, 40, date="2026-10-01"), "2026-11-11")
    assert st["nba_prop_pts_Under"]["status"] == "active"


# ---- paused -> active ------------------------------------------------------------------------------------
def test_comeback_needs_priced_plays(docs):
    name = "nba_prop_pts_Under"
    path, st = gate(docs, name, "paused", "2026-10-25")
    GT.update(path, st, name, rows(30, 15), [], "2026-11-11")                          # 45 plays, +27%, no closing prices
    assert st[name]["status"] == "paused"
    GT.update(path, st, name, rows(30, 15, ev=-1.0), [], "2026-11-11")                 # priced, but losing to the close
    assert st[name]["status"] == "paused"
    GT.update(path, st, name, rows(30, 15, ev=1.0), [], "2026-11-11")
    assert st[name]["status"] == "active" and st[name]["since"] == "2026-11-11"


def test_comeback_needs_forty_plays_and_a_positive_return(docs):
    name = "nba_prop_pts_Under"
    path, st = gate(docs, name, "paused", "2026-10-25")
    GT.update(path, st, name, rows(26, 13, ev=1.0), [], "2026-11-11")                  # 39 plays
    assert st[name]["status"] == "paused"
    GT.update(path, st, name, rows(21, 20, ev=1.0), [], "2026-11-11")                  # 41 plays at -2%
    assert st[name]["status"] == "paused"


def test_parlay_gates_come_back_without_a_closing_price(docs):
    path, st = gate(docs, "nhl_edge", "paused", "2026-10-21")
    tix = [{"date": "2026-11-01", "res": "W", "units": 2.6, "p": 30.0} for _ in range(16)] + \
          [{"date": "2026-11-01", "res": "L", "units": -1.0, "p": 30.0} for _ in range(24)]
    GT.update(path, st, "nhl_edge", tix, [], "2026-11-11")
    assert st["nhl_edge"]["status"] == "active"


# ---- the pooled check ------------------------------------------------------------------------------------
def test_pool_stays_active_on_a_small_or_noisy_sample():
    few = [["2026-10-25", -6.0, "p"]] * 29
    assert GT.pooled_state(few)["status"] == "active"
    noisy = [["2026-10-25", v, "p"] for v in ([25.0, -27.0] * 20)]                     # mean -1, but all over the place
    assert GT.pooled_state(noisy)["status"] == "active"


def test_pool_pauses_then_needs_fresh_priced_plays_to_come_back():
    bad = [["2026-10-%02d" % (20 + i % 10), -4.0 + (i % 3), "p"] for i in range(30)]
    st = GT.pooled_state(bad)
    assert st["status"] == "paused" and st["history"][-1]["to"] == "paused" and st["n"] == 0
    stale = bad + [["2026-11-05", 5.0, "s"]] * 60                                      # before POOL_FRESH_FROM: not counted
    assert GT.pooled_state(stale)["status"] == "paused"
    short = bad + [["2026-11-20", 2.0, "s"]] * 39
    assert GT.pooled_state(short)["status"] == "paused" and GT.pooled_state(short)["n"] == 39
    losing = bad + [["2026-11-20", -2.0, "s"]] * 60
    assert GT.pooled_state(losing)["status"] == "paused"
    back = bad + [["2026-11-20", 2.0, "s"]] * 40
    assert GT.pooled_state(back)["status"] == "active"


def test_pool_reads_every_sport_and_holds_back_all_game_plays(docs):
    for sport, name, n in (("nhl", "nhl_game_ml", 12), ("soccer", "soccer_game_1x2", 12), ("nba", "nba_game_ml", 8)):
        path, st = gate(docs, name)
        GT.update(path, st, name, [], [{"date": "2026-10-28", "res": "L", "units": -1.0, "ev": -5.0 + (i % 4)} for i in range(n)], "2026-11-11")
    pool = GT.pooled(docs=docs)
    assert pool["status"] == "paused" and pool["by_sport"] == {"nhl": 12, "soccer": 12, "nba": 8}
    paused = GT.paused_kinds(GT.load(docs / GT.POOL_FILES["cfb"], GT.game_names("cfb")), "cfb", docs=docs)
    assert paused == {"spread", "total", "ml"} and paused.pool_only == {"spread", "total", "ml"}
    picks = {"spread": {"play": True}, "total": {"play": True, "early": True}, "ml": {"play": False}}
    GT.hold_back(picks, paused)
    assert picks["spread"] == {"play": False, "shadow": True}
    assert picks["total"]["play"] is True                                              # CFB early totals are not the pooled rule
    path, st = gate(docs, "nhl_game_ml")
    again = [{"date": "2026-10-28", "res": "L", "units": -1.0, "ev": -5.0 + (i % 4)} for i in range(12)]
    out = GT.update(path, st, "nhl_game_ml", [], again, "2026-11-11")                  # every run passes the full record again
    assert out["status"] == "paused" and out["own_status"] == "active" and "All game plays are paused" in out["why"]
    assert json.loads(path.read_text())["nhl_game_ml"]["status"] == "active"           # its own gate is untouched


def test_early_totals_are_left_out_of_the_pool(docs):
    path, st = gate(docs, "cfb_game_total")
    GT.update(path, st, "cfb_game_total", [], [{"date": "2026-10-28", "res": "L", "units": -1.0, "ev": -9.0, "early": True}] * 40, "2026-11-11")
    assert GT.pooled(docs=docs)["status"] == "active" and st["cfb_game_total"]["ev_rows"] == []


def test_a_sports_own_pause_still_works_without_the_pool(docs):
    st = GT.load(docs / GT.POOL_FILES["nhl"], GT.game_names("nhl"))
    assert GT.paused_kinds(st, "nhl", docs=docs) == {"pl"}                             # the puck line starts paused
