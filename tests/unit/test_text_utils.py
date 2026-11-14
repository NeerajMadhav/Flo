# tests/unit/test_text_utils.py
from app.utils.text_utils import escape_md, truncate_telegram


def test_truncate():
    assert truncate_telegram("short") == "short"
    long = "word " * 2000
    out = truncate_telegram(long, limit=50)
    assert len(out) <= 50
    assert out.endswith("…")


def test_escape_md():
    assert "\\*" in escape_md("a*b")
