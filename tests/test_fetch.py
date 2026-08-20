"""fetch.py encoding-selection tests: a declared charset must never be overridden
by chardet's apparent_encoding (which misdetects UTF-8 pages as Windows-1252 and
would corrupt the parsed text into mojibake)."""

from __future__ import annotations

from ow2_patch.fetch import _pick_encoding


class FakeResp:
    def __init__(self, encoding, apparent):
        self.encoding = encoding
        self.apparent_encoding = apparent


def test_declared_charset_wins_over_apparent():
    # pages served with charset=utf-8 where chardet guesses Windows-1252
    assert _pick_encoding(FakeResp("utf-8", "Windows-1252")) == "utf-8"


def test_requests_default_latin1_triggers_sniffing():
    # no charset declared -> requests leaves ISO-8859-1 -> use detection
    assert _pick_encoding(FakeResp("ISO-8859-1", "utf-8")) == "utf-8"
    assert _pick_encoding(FakeResp("latin-1", "utf-8")) == "utf-8"


def test_no_encoding_at_all_falls_back_to_utf8():
    assert _pick_encoding(FakeResp(None, None)) == "utf-8"
    assert _pick_encoding(FakeResp("", "utf-8")) == "utf-8"
