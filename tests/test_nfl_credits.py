"""NFL odds credits (Nov 21 2026): fewer prop types a game, core types only when credits run behind the month's
pace, and November's lower reserve. No network: a fake client records what was asked for."""
from datetime import datetime, timedelta, timezone

import pandas as pd

import nflmodel.config as C
import nflmodel.oddsapi as O


class FakeClient:
    def __init__(self, remaining):
        self.remaining, self.spent, self.used, self.calls = remaining, 0, 0, []

    def get(self, path, est_cost=0, **params):
        mk = params["markets"].split(",")
        self.calls.append(mk)
        self.spent += len(mk)
        self.remaining -= len(mk)
        return {}


def _run(remaining, now, n_games=6, tmp_path=None):
    todo = pd.DataFrame({"game_id": [f"g{i}" for i in range(n_games)],
                         "ko": [now + timedelta(hours=3 + i) for i in range(n_games)]})
    matched = {g: {"id": f"ev{g}"} for g in todo["game_id"]}
    cl = FakeClient(remaining)
    _, info = O.fetch_all_props(cl, todo, matched, now, tmp_path / "odds_cache.json")
    return cl, info


def test_no_td_or_count_markets_pulled():
    assert "player_anytime_td" not in C.ODDS_PROP_MARKETS
    assert not C.ODDS_EXTRA_PROP_MARKETS
    assert set(C.ODDS_CORE_MARKETS) <= set(C.ODDS_PROP_MARKETS)


def test_full_pull_early_in_month(tmp_path):
    cl, info = _run(480, datetime(2026, 12, 3, 18, tzinfo=timezone.utc), tmp_path=tmp_path)
    assert all(len(mk) == len(C.ODDS_PROP_MARKETS) for mk in cl.calls) and len(cl.calls) == 6
    assert info["core_only"] == 0


def test_behind_pace_pulls_core_only(tmp_path):
    cl, info = _run(150, datetime(2026, 12, 15, 18, tzinfo=timezone.utc), tmp_path=tmp_path)
    assert cl.calls and all(sorted(mk) == sorted(C.ODDS_CORE_MARKETS) for mk in cl.calls)
    assert info["core_only"] == len(cl.calls)


def test_november_reserve_is_spent_on_core_types(tmp_path):
    cl, info = _run(25, datetime(2026, 11, 22, 16, 45, tzinfo=timezone.utc), tmp_path=tmp_path)
    assert len(cl.calls) == 5 and cl.remaining == 5          # 4 core types x 5 games, 5 credits kept
    assert info["skipped"] == 1 and "reserve of 5" in info["budget_note"]


def test_december_reserve_back_to_normal():
    assert O.reserve_for(datetime(2026, 12, 1, tzinfo=timezone.utc)) == C.ODDS_CREDIT_RESERVE
    assert O.reserve_for(datetime(2026, 11, 30, tzinfo=timezone.utc)) == 5
