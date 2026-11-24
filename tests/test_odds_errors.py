"""Odds API error messages (Nov 24 2026): a used-up month is not a bad key."""
import io
import urllib.error

import pytest

import dailyodds


def _raise(code, body):
    def f(*a, **k):
        raise urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(body.encode()))
    return f


def test_out_of_credits_says_so(monkeypatch):
    monkeypatch.setattr(dailyodds.urllib.request, "urlopen",
                        _raise(401, '{"message":"Usage quota has been reached","error_code":"OUT_OF_USAGE_CREDITS"}'))
    with pytest.raises(dailyodds.Fatal, match="out of NBA odds credits"):
        dailyodds.Client("k", "NBA", "ODDS_API_KEY_NBA").get("/v4/sports/x/odds")


def test_bad_key_still_says_check_the_secret(monkeypatch):
    monkeypatch.setattr(dailyodds.urllib.request, "urlopen",
                        _raise(401, '{"message":"API key is not valid","error_code":"INVALID_KEY"}'))
    with pytest.raises(dailyodds.Fatal, match="Check the ODDS_API_KEY_NBA secret"):
        dailyodds.Client("k", "NBA", "ODDS_API_KEY_NBA").get("/v4/sports/x/odds")
