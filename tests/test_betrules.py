"""
The shared betting rules (betrules.py). Run with:  python -m pytest tests -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import betrules as BR  # noqa: E402


# ---- prices ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("odds,pay,imp", [(-110, 100 / 110, 110 / 210), (150, 1.5, 0.4), (100, 1.0, 0.5), (-200, 0.5, 2 / 3)])
def test_payout_and_implied(odds, pay, imp):
    assert BR.payout(odds) == pytest.approx(pay) and BR.implied(odds) == pytest.approx(imp)


def test_fair_probs_even_market_is_a_coin_flip():
    assert BR.fair_probs(-110, -110) == pytest.approx([0.5, 0.5])


def test_fair_probs_sum_to_one_and_keep_the_order():
    for odds in [(-110, -110), (700, -1100), (150, 230, 180), (-250, 320, 700)]:
        p = BR.fair_probs(*odds)
        assert sum(p) == pytest.approx(1.0) and all(0 < x < 1 for x in p)
        imp = [BR.implied(o) for o in odds]
        assert sorted(range(len(p)), key=p.__getitem__) == sorted(range(len(p)), key=imp.__getitem__)


def test_fair_probs_takes_more_off_the_longshot_than_the_old_way():
    dog, fav = BR.fair_probs(700, -1100)
    old = BR.implied(700) / (BR.implied(700) + BR.implied(-1100))
    assert dog < old and dog == pytest.approx(BR.implied(700) - (BR.implied(700) + BR.implied(-1100) - 1) / 2, abs=1e-6)


def test_fair_probs_without_vig_just_rescales():
    assert BR.fair_probs(100, 100) == pytest.approx([0.5, 0.5])
    assert BR.fair_probs(120, 100) == pytest.approx([x / (BR.implied(120) + 0.5) for x in (BR.implied(120), 0.5)])


# ---- the sharp-referee play rule ------------------------------------------------------------------------
def test_a_good_price_with_the_model_on_side_is_a_play():
    d = BR.decide_sharp(0.53, 100, -120, -112, -104)          # Pinnacle makes this side about 51.9%: +3.8% at +100
    assert d["play"] and d["why"] is None and 1.5 <= d["ev"] <= 8


def test_not_enough_value_is_not_a_play():
    d = BR.decide_sharp(0.60, -110, -110, -108, -108)
    assert not d["play"] and "price" in d["why"]


def test_a_huge_gap_is_treated_as_a_stale_line():
    d = BR.decide_sharp(0.60, 150, -180, -110, -110)
    assert not d["play"] and "stale" in d["why"]


def test_model_below_the_book_blocks_the_play():
    d = BR.decide_sharp(0.40, 100, -120, -112, -104)
    assert not d["play"] and d["why"] == "model disagrees"


def test_model_far_above_pinnacle_blocks_the_play():
    d = BR.decide_sharp(0.62, 100, -120, -112, -104)          # model 62% vs Pinnacle about 52%: that is not agreement
    assert not d["play"] and d["why"] == "model too far from Pinnacle"


def test_longshots_are_capped():
    d = BR.decide_sharp(0.26, 320, -400, 270, -330)           # worth about 5% at Pinnacle's chance, but +320
    assert 1.5 <= d["ev"] <= 8 and not d["play"] and "longshot" in d["why"]


def test_no_sharp_price_means_no_play():
    assert BR.decide_sharp(0.55, -105, -115, None, None)["why"] == "no sharp price"
    assert BR.decide_sharp(0.55, None, -115, -110, -110)["why"] == "no price"


def test_converted_sharp_chance_is_used_as_given():
    d = BR.decide_sharp(0.53, -105, -115, None, None, sharp_p=0.535)
    assert d["sharp"] == 53.5 and d["ev"] == pytest.approx(100 * (0.535 * (1 + 100 / 105) - 1), abs=0.05)


# ---- props --------------------------------------------------------------------------------------------
def test_prop_blend_sits_between_model_and_book():
    d = BR.decide_prop(0.40, 0.50, -115, -115, "rush_yds", weight=0.5)
    assert d["side"] == "Under" and d["p"] == pytest.approx(55.0) and d["raw_edge"] == pytest.approx(10.0)


def test_prop_needs_profit_at_the_price_and_overs_need_more():
    assert not BR.decide_prop(0.46, 0.50, -115, -115, "x", weight=0.5)["play"]            # 52% under at -115 loses money
    assert BR.decide_prop(0.38, 0.50, -115, -115, "x", weight=0.5)["play"]                # 56% under clears 2.5%
    over = BR.decide_prop(0.609, 0.50, -115, -115, "x", weight=0.5)                       # 55.45% over: +3.7%, needs 4.0%
    under = BR.decide_prop(0.391, 0.50, -115, -115, "x", weight=0.5)
    assert under["play"] and not over["play"]


def test_calibration_never_grows_an_edge_and_floors():
    real = {"x": {"k": 0.5}}
    a = BR.decide_prop(0.30, 0.50, -115, -115, "x", weight=0.5)
    b = BR.decide_prop(0.30, 0.50, -115, -115, "x", weight=0.5, real=real)
    assert b["edge"] == pytest.approx(a["edge"] / 2, abs=0.11) and b["pre"] == a["pre"]
    rows = [("x", 0.6, 0.5, False)] * 200                     # claimed 10 points every time, delivered minus 50
    assert BR.realization_table(rows)["x"]["k"] == BR.REAL_FLOOR
    rows = [("x", 0.6, 0.5, True)] * 200                      # delivered far more than claimed: still capped at 1
    assert BR.realization_table(rows)["x"]["k"] == 1.0


def test_bias_needs_a_sample_and_is_capped():
    assert BR.bias_table([("x", 0.5, False)] * 39)["x"]["shift"] == 0.0
    t = BR.bias_table([("x", 0.5, False)] * 5000)["x"]
    assert t["shift"] == -BR.BIAS_CAP
    small = BR.bias_table([("x", 0.5, i % 5 < 2) for i in range(300)])["x"]["shift"]      # 40% overs, 300 props
    assert -0.25 < small < 0


def test_blocked_and_capped_types_are_not_plays():
    assert not BR.decide_prop(0.30, 0.50, -115, -115, "x", weight=0.5, blocked=[("x", "Under")])["play"]
    assert not BR.decide_prop(0.30, 0.50, -115, -115, "x", weight=0.5, raw_cap=15)["play"]


def test_gap_to_play_and_reach_table():
    need = BR.gap_to_play("x", "Under", weight=0.5)
    assert need is not None and BR.decide_prop(0.5 - need / 100, 0.5, -115, -115, "x", weight=0.5)["play"]
    assert not BR.decide_prop(0.5 - (need - 0.5) / 100, 0.5, -115, -115, "x", weight=0.5)["play"]
    rows = BR.reach_table([("x", "Under"), ("x", "Over"), ("y", "Under")], weight=0.5, play_min=4, play_max=15,
                          caps={("x", "Under"): need}, off={("x", "Over")}, paused={("y", "Under")})
    assert [r["status"] for r in rows] == ["cannot qualify", "side off", "paused"]
    assert BR.reach_table([("x", "Under")], weight=0.5, play_min=4, play_max=15)[0]["status"] == "open"
