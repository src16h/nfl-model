"""
Closing prices for prop plays (Nov 11 2026). Run with:  python -m pytest tests -q

No network: the odds client is replaced by a fake that counts credits. What these check:
  1. a "close" only counts when its price was fetched after the play was flagged
  2. NHL / NBA: a locked play's market gets its closing pull even when the day's allowance is used up,
     only that market is pulled, the month's reserve is never touched, and the credit is paid back by
     skipping an alt-line pull on a later run
  3. CFB: prices carry the time they were fetched (they never did, so no CFB play could be priced)
"""
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import clv as CLV  # noqa: E402

UTC = timezone.utc


# ---------------------------------------------------------------------------------------------------
# 1. what counts as a closing price
# ---------------------------------------------------------------------------------------------------
def _flag(**kw):
    return {"line": 2.5, "side": "Under", "odds": -115, "book_over": 50.0, "at": "2026-11-11T22:12+00:00", **kw}


def test_same_pull_is_not_a_close():
    fl = _flag(pulled="2026-11-11T22:12:31.5+00:00")
    cl = {"line": 2.5, "book_over": 50.0, "pulled": "2026-11-11T22:12:31.5+00:00"}
    assert CLV.prop_clv(fl, cl) == (None, None, None)


def test_later_pull_is_a_close_and_scores_the_move():
    fl = _flag(pulled="2026-11-11T22:12:31.5+00:00")
    cl = {"line": 2.5, "book_over": 46.0, "pulled": "2026-11-11T23:35:02+00:00"}      # Under went from 50% to 54%
    clv, ev, move = CLV.prop_clv(fl, cl)
    assert move == 0 and clv == pytest.approx(4.0)
    assert ev == pytest.approx(100 * (0.54 * (1 + 100 / 115) - 1))


def test_flag_without_fetch_time_uses_when_it_was_flagged():
    # the price was fetched seconds after the minute stamp, in the same run: still not a close
    same_run = {"line": 2.5, "book_over": 46.0, "pulled": "2026-11-11T22:12:40+00:00"}
    later = {"line": 2.5, "book_over": 46.0, "pulled": "2026-11-11T23:35:00+00:00"}
    assert CLV.prop_clv(_flag(), same_run) == (None, None, None)
    assert CLV.prop_clv(_flag(), later)[2] == 0


def test_no_fetch_time_on_the_close_is_not_a_close():
    assert CLV.prop_clv(_flag(pulled="2026-11-11T22:12:31+00:00"), {"line": 2.5, "book_over": 46.0, "pulled": None}) == (None, None, None)


def test_moved_line_reports_direction_only():
    fl = _flag(pulled="2026-11-11T22:12:31+00:00")
    cl = {"line": 1.5, "book_over": 50.0, "pulled": "2026-11-11T23:35:00+00:00"}       # Under line dropped: toward us
    assert CLV.prop_clv(fl, cl) == (None, None, 1)


def test_close_wanted_lists_play_markets_only():
    players = [{"game_id": 7, "m": {"sog": {"flag": {"at": "x"}}, "points": {"shadow_flag": {"at": "x"}}, "goals": {}}},
               {"game_id": 8, "m": {"sog": {"flag": {"at": None, "legacy": True}}}}]
    plays, shadow = CLV.close_wanted(players)
    assert plays == {7: {"sog"}} and shadow == {7: {"points"}}
    assert CLV.wants_close(plays, "7", "sog") and not CLV.wants_close(plays, 7, "points") and not CLV.wants_close(plays, 8, "sog")


def test_summary_reports_coverage():
    rows = [{"clv": 2.0, "ev": 1.0, "move": 0}, {"clv": None, "ev": None, "move": None}, {"clv": None, "ev": None, "move": -1}]
    s = CLV.prop_summary(rows)
    assert s["plays"] == 3 and s["n"] == 2


# ---------------------------------------------------------------------------------------------------
# 2. NHL / NBA odds budget
# ---------------------------------------------------------------------------------------------------
class FakeClient:
    """Stands in for the odds client: every event call costs 1 credit and is written down."""
    start = 300
    calls = []

    def __init__(self, key):
        self.key, self.remaining, self.spent = key, None, 0

    def get(self, path, **params):
        cls = type(self)
        cls.start -= 1
        self.remaining, self.spent = cls.start, self.spent + 1
        mkt = params.get("markets", "")
        cls.calls.append((path.split("/events/")[-1].split("/")[0], mkt))
        out = [{"name": n, "description": "Player A", "point": 2.5, "price": -110} for n in ("Over", "Under")]
        return {"home_team": "H", "away_team": "A",
                "bookmakers": [{"key": "hardrockbet", "title": "Hard Rock Bet", "markets": [{"key": mkt, "outcomes": out}]}]}


def _setup(mod_name, tmp_path, monkeypatch, n_games, now, start_in_hours, remaining, spent_today, cached_at, alt_cached=True, debt=0):
    O = importlib.import_module(f"{mod_name}.odds")
    C = importlib.import_module(f"{mod_name}.config")
    FakeClient.start, FakeClient.calls = remaining, []
    monkeypatch.setattr(O, "Client", FakeClient)
    monkeypatch.setattr(C, "odds_key", lambda: "k")
    today = now.astimezone(O.ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    games, lines, cache = [], {}, {}
    for i in range(n_games):
        g = {"game_id": 100 + i, "home": f"H{i}", "away": f"A{i}", "date_et": today, "today_et": today,
             "start": (now + timedelta(hours=start_in_hours + 0.01 * i)).isoformat().replace("+00:00", "Z")}
        games.append(g)
        lines[f"A{i}@H{i}"] = {"event": f"ev{i}", "book": "Hard Rock Bet", "ml_home": -120, "ml_away": 100}
        if cached_at is not None:
            for mkt in C.ODDS_PROP_MARKETS:
                cache[f"{g['game_id']}|{mkt}"] = {"day": today, "rows": {}, "book": "Hard Rock Bet", "at": cached_at.isoformat(), "closed": False}
            if alt_cached:
                cache[f"alt:{g['game_id']}:{C.ALT_MARKETS[0]}"] = {"day": today, "book": [], "sharp": [], "book_name": None}
    state = {"month": today[:7], "day": today, "spent_today": spent_today, "remaining": remaining,
             "lines": lines, "lines_at": now.isoformat(), "close_debt": debt}       # fresh lines: no line pull this run
    sp, cp = tmp_path / "state.json", tmp_path / "cache.json"
    sp.write_text(json.dumps(state))
    cp.write_text(json.dumps(cache))
    return O, C, games, sp, cp


EVENING = datetime(2026, 11, 12, 23, 35, tzinfo=UTC)          # 6:35pm ET
AFTERNOON = datetime(2026, 11, 12, 22, 12, tzinfo=UTC)        # 5:12pm ET


@pytest.mark.parametrize("mod", ["nhlmodel", "nbamodel"])
def test_closing_pull_happens_with_the_days_allowance_used_up(mod, tmp_path, monkeypatch):
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, n_games=6, now=EVENING, start_in_hours=0.5, remaining=300,
                                 spent_today=40, cached_at=AFTERNOON)
    stat = O.PROP_STAT[C.ODDS_PROP_MARKETS[0]]
    props, status = O.run(games, sp, cp, EVENING, close_games={101: {stat}})
    assert FakeClient.calls == [("ev1", C.ODDS_PROP_MARKETS[0])]          # one game, one market, nothing else
    assert status["close_pulls"] == 1 and status["close_debt"] == 1
    cache = json.loads(cp.read_text())
    ent = cache[f"101|{C.ODDS_PROP_MARKETS[0]}"]
    assert ent["closed"] is True and ent["at"] == EVENING.isoformat()
    got = props.get(101) or props.get("101")                              # NBA keeps game ids as text
    assert got["playera"][stat]["pulled"] == EVENING.isoformat()          # the new price knows when it was fetched
    # and it is only pulled once
    FakeClient.calls = []
    O.run(games, sp, cp, EVENING + timedelta(minutes=20), close_games={101: {stat}})
    assert FakeClient.calls == []


@pytest.mark.parametrize("mod", ["nhlmodel", "nbamodel"])
def test_no_locked_play_means_no_closing_pull(mod, tmp_path, monkeypatch):
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, 6, EVENING, 0.5, 300, 40, AFTERNOON)
    _, status = O.run(games, sp, cp, EVENING, close_games={})
    assert FakeClient.calls == [] and not status.get("close_pulls")


@pytest.mark.parametrize("mod", ["nhlmodel", "nbamodel"])
def test_closing_pull_never_touches_the_months_reserve(mod, tmp_path, monkeypatch):
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, 6, EVENING, 0.5, remaining=0, spent_today=40, cached_at=AFTERNOON)
    reserve = C.ODDS_RESERVE
    sp.write_text(json.dumps({**json.loads(sp.read_text()), "remaining": reserve}))
    FakeClient.start = reserve
    stat = O.PROP_STAT[C.ODDS_PROP_MARKETS[0]]
    _, status = O.run(games, sp, cp, EVENING, close_games={101: {stat}})
    assert FakeClient.calls == [] and status.get("close_missed") == 1


@pytest.mark.parametrize("mod", ["nhlmodel", "nbamodel"])
def test_shadow_plays_close_only_from_the_days_allowance(mod, tmp_path, monkeypatch):
    stat_of = lambda O, C: O.PROP_STAT[C.ODDS_PROP_MARKETS[0]]
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, 6, EVENING, 0.5, 300, spent_today=40, cached_at=AFTERNOON)
    O.run(games, sp, cp, EVENING, shadow_games={101: {stat_of(O, C)}})
    assert FakeClient.calls == []                                          # allowance used up: shadow play waits
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, 6, EVENING, 0.5, 300, spent_today=0, cached_at=AFTERNOON)
    _, status = O.run(games, sp, cp, EVENING, shadow_games={101: {stat_of(O, C)}})
    assert ("ev1", C.ODDS_PROP_MARKETS[0]) in FakeClient.calls and status["close_debt"] == 0


@pytest.mark.parametrize("mod", ["nhlmodel", "nbamodel"])
def test_too_early_or_too_fresh_is_not_due(mod, tmp_path, monkeypatch):
    far = importlib.import_module(f"{mod}.config").PROP_CLOSE_HOURS + 1
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, 6, EVENING, start_in_hours=far, remaining=300,
                                 spent_today=40, cached_at=AFTERNOON)
    stat = O.PROP_STAT[C.ODDS_PROP_MARKETS[0]]
    O.run(games, sp, cp, EVENING, close_games={101: {stat}})
    assert FakeClient.calls == []                                          # starts too far out
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, 6, EVENING, 0.5, 300, 40, cached_at=EVENING - timedelta(minutes=20))
    O.run(games, sp, cp, EVENING, close_games={101: {stat}})
    assert FakeClient.calls == []                                          # the saved price is only 20 minutes old


@pytest.mark.parametrize("mod", ["nhlmodel", "nbamodel"])
def test_debt_is_paid_by_skipping_alt_pulls_latest_games_first(mod, tmp_path, monkeypatch):
    # next afternoon: nothing pulled yet, allowance already used, 2 credits owed for yesterday's closing pulls
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, n_games=6, now=AFTERNOON, start_in_hours=2.0, remaining=300,
                                 spent_today=40, cached_at=None, debt=2)
    _, status = O.run(games, sp, cp, AFTERNOON)
    main_prop, main_alt = C.ODDS_PROP_MARKETS[0], C.ALT_MARKETS[0]
    props = [c for c in FakeClient.calls if c[1] == main_prop]
    alts = [c for c in FakeClient.calls if c[1] == main_alt]
    assert len(props) == 6                                                 # every game still gets its main prop market
    assert [a[0] for a in alts] == ["ev0", "ev1", "ev2", "ev3"]            # the two latest games lose their alt pull
    assert status["alt_skipped"] == 2 and status["close_debt"] == 0
    assert len(FakeClient.calls) == 10                                     # 12 without the debt: the 2 credits are paid back
    # a later run the same day does not quietly pull them after all
    FakeClient.calls = []
    O.run(games, sp, cp, AFTERNOON + timedelta(minutes=30))
    assert [c for c in FakeClient.calls if c[1] == main_alt] == []


@pytest.mark.parametrize("mod", ["nhlmodel", "nbamodel"])
def test_alt_cut_is_capped_at_its_share(mod, tmp_path, monkeypatch):
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, 6, AFTERNOON, 2.0, 300, 40, cached_at=None, debt=6)
    _, status = O.run(games, sp, cp, AFTERNOON)
    alts = [c for c in FakeClient.calls if c[1] == C.ALT_MARKETS[0]]
    assert len(alts) == 3 and status["alt_skipped"] == 3 and status["close_debt"] == 3   # half the alt pulls, rest carried


@pytest.mark.parametrize("mod", ["nhlmodel", "nbamodel"])
def test_no_debt_means_nothing_changes(mod, tmp_path, monkeypatch):
    O, C, games, sp, cp = _setup(mod, tmp_path, monkeypatch, 6, AFTERNOON, 2.0, 300, 40, cached_at=None, debt=0)
    _, status = O.run(games, sp, cp, AFTERNOON)
    assert len([c for c in FakeClient.calls if c[1] == C.ALT_MARKETS[0]]) == 6 and not status.get("alt_skipped")


def test_closing_on_credit_stops_at_the_debt_limit(tmp_path, monkeypatch):
    O, C, games, sp, cp = _setup("nbamodel", tmp_path, monkeypatch, 6, EVENING, 0.5, 300, 40, AFTERNOON, debt=0)
    monkeypatch.setattr(C, "CLOSE_DEBT_MAX", 3)
    want = {100 + i: {O.PROP_STAT[m] for m in C.ODDS_PROP_MARKETS[:2]} for i in range(6)}     # 12 markets want a close
    _, status = O.run(games, sp, cp, EVENING, close_games=want)
    assert status["close_pulls"] == 3 and status["close_debt"] == 3 and status["close_missed"] == 9
    assert [c[0] for c in FakeClient.calls] == ["ev0", "ev0", "ev1"]       # soonest games first


# ---------------------------------------------------------------------------------------------------
# 3. CFB
# ---------------------------------------------------------------------------------------------------
class FakeCFBClient(FakeClient):
    def get(self, path, **params):
        if path.endswith("/events"):                      # the free list of event ids
            return [{"id": "ev0", "home_team": "Home U Cats", "away_team": "Away U Dogs"}]
        mk = params["markets"].split(",")
        cls = type(self)
        cls.start -= len(mk)
        self.remaining, self.spent = cls.start, self.spent + len(mk)
        cls.calls.append(("ev0", params["markets"]))
        out = [{"name": n, "description": "Player A", "point": 55.5, "price": -110} for n in ("Over", "Under")]
        return {"bookmakers": [{"key": "hardrockbet", "title": "Hard Rock Bet", "markets": [{"key": m, "outcomes": out} for m in mk]}]}


def _cfb(tmp_path, monkeypatch, now, kickoff_in, cached_at, spent_week=0, remaining=300):
    import cfbmodel.config as C
    import cfbmodel.odds as O
    FakeCFBClient.start, FakeCFBClient.calls = remaining, []
    monkeypatch.setattr(O, "Client", FakeCFBClient)
    monkeypatch.setattr(C, "odds_key", lambda: "k")
    monkeypatch.setattr(O, "game_lines", lambda *a, **k: None)
    g = {"game_id": 500, "home_full": "Home U Cats", "away_full": "Away U Dogs", "p4_home": True, "p4_away": True,
         "start": (now + timedelta(hours=kickoff_in)).isoformat().replace("+00:00", "Z")}
    cache = {}
    if cached_at is not None:
        row = {"playera": {"line": 55.5, "over": -110, "under": -110}}
        cache = {f"500|{m}": {"rows": row, "book": "Hard Rock Bet", "at": cached_at.isoformat(), "closed": False} for m in C.ODDS_PROP_MARKETS}
    sp, cp = tmp_path / "state.json", tmp_path / "cache.json"
    sp.write_text(json.dumps({"remaining": remaining, "week": now.strftime("%G-%V"), "spent_week": spent_week}))
    cp.write_text(json.dumps(cache))
    return O, C, [g], sp, cp


SAT = datetime(2026, 11, 14, 16, 5, tzinfo=UTC)               # Saturday 11:05am ET


def test_cfb_prices_carry_when_they_were_fetched(tmp_path, monkeypatch):
    O, C, games, sp, cp = _cfb(tmp_path, monkeypatch, SAT, kickoff_in=20, cached_at=None)
    props, _ = O.run(games, sp, cp, SAT)
    assert props[500]["playera"]["rush_yds"]["pulled"] == SAT.isoformat()


def test_cfb_closing_pull_is_only_the_play_market_and_ignores_the_weeks_allowance(tmp_path, monkeypatch):
    fri = SAT - timedelta(hours=18)
    O, C, games, sp, cp = _cfb(tmp_path, monkeypatch, SAT, kickoff_in=0.9, cached_at=fri, spent_week=10_000)
    props, status = O.run(games, sp, cp, SAT, close_games={500: {"rush_yds"}})
    assert FakeCFBClient.calls == [("ev0", "player_rush_yds")] and status["close_pulls"] == 1
    assert props[500]["playera"]["rush_yds"]["pulled"] == SAT.isoformat()
    assert props[500]["playera"]["pass_yds"]["pulled"] == fri.isoformat()             # other markets keep their old price
    FakeCFBClient.calls = []
    O.run(games, sp, cp, SAT + timedelta(minutes=30), close_games={500: {"rush_yds"}})
    assert FakeCFBClient.calls == []                                                   # once per game and market


def test_cfb_closing_pull_respects_the_reserve(tmp_path, monkeypatch):
    import cfbmodel.config as C
    O, C, games, sp, cp = _cfb(tmp_path, monkeypatch, SAT, 0.9, SAT - timedelta(hours=18), spent_week=10_000, remaining=C.ODDS_RESERVE)
    O.run(games, sp, cp, SAT, close_games={500: {"rush_yds"}})
    assert FakeCFBClient.calls == []


# ---------------------------------------------------------------------------------------------------
# 4. NFL: the prop log's closing value only counts a later price
# ---------------------------------------------------------------------------------------------------
def test_nfl_prop_clv_needs_a_later_price():
    from nflmodel import tracker as T
    fl = {"line": "55.5", "lean": "Under", "odds": "-115", "at": "2026-11-13T23:07+00:00", "pulled": "2026-11-13T23:07:10+00:00"}
    row = {"line": "55.5", "over_odds": "-105", "under_odds": "-125"}
    assert T.prop_clv({**row, "pulled": "2026-11-13T23:07:10+00:00"}, fl) is None    # same pull
    assert T.prop_clv({**row, "pulled": None}, fl) is None                           # unknown: not counted
    got = T.prop_clv({**row, "pulled": "2026-11-15T16:45:00+00:00"}, fl)
    pu, po = 125 / 225, 105 / 205
    assert got == pytest.approx(round(100 * (pu / (pu + po) * (1 + 100 / 115) - 1), 2))
