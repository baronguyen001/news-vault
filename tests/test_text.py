"""Tests for newsvault.text helpers."""

from __future__ import annotations

from newsvault.text import VI_STOPWORDS, excerpt, fold, slugify, tokens


def test_fold_basic() -> None:
    assert fold("Kinh tế & Tài chính") == "kinh te & tai chinh"
    assert fold("Đường sắt ĐÔ THỊ") == "duong sat do thi"
    assert fold("  nhiều   khoảng  trắng ") == "nhieu khoang trang"
    assert fold("") == ""


def test_fold_d_character() -> None:
    assert fold("Đường") == "duong"


def test_slugify() -> None:
    assert slugify("Kinh tế & Tài chính") == "kinh-te-tai-chinh"
    assert slugify("Đông Nam Á") == "dong-nam-a"
    assert slugify("!!!") == "x"
    assert slugify("") == "x"


def test_tokens() -> None:
    token_set = tokens("Lãi suất và tỷ giá")
    assert "lai" in token_set
    assert "va" not in token_set
    assert tokens("") == set()
    assert "the" not in tokens("The quick brown fox")


def test_excerpt() -> None:
    assert excerpt("một hai ba bốn", 7) == "một hai…"
    assert excerpt("short text", 20) == "short text"
    assert excerpt("one two three", 6) == "one…"
    assert excerpt("", 10) == ""


def test_stopwords_coverage() -> None:
    required = {
        "va",
        "cua",
        "cho",
        "voi",
        "trong",
        "khi",
        "khong",
        "nhung",
        "cac",
        "nhieu",
        "theo",
        "truoc",
        "nguoi",
        "viec",
        "duoc",
        "phai",
        "rat",
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "are",
        "was",
        "were",
        "has",
        "have",
        "been",
        "will",
        "would",
        "its",
        "it",
        "on",
        "in",
        "at",
        "to",
        "of",
        "by",
        "an",
        "as",
    }
    assert required.issubset(VI_STOPWORDS)
    assert 80 <= len(VI_STOPWORDS) <= 200


def test_stopwords_do_not_swallow_news_terms() -> None:
    """Folding drops diacritics, so a careless stopword deletes a real term.

    Every string below is the folded form of a word this archive reports on daily:
    lai/lãi (interest), nhat/Nhật (Japan), dau/dầu (oil), nen/nền (economy),
    dang/Đảng (the Party), chinh/chính (policy), gia/giá (price), tai/tài (finance),
    van/văn (culture), can/cần (needs), vi/vi phạm (violation), tu/tư (investment).
    """
    live_terms = {
        "lai",
        "nhat",
        "dau",
        "nen",
        "dang",
        "chinh",
        "gia",
        "cao",
        "tai",
        "van",
        "chi",
        "can",
        "ca",
        "du",
        "vi",
        "bao",
        "moi",
        "co",
        "tu",
        "la",
    }
    assert live_terms.isdisjoint(VI_STOPWORDS)
    assert "lai" in tokens("Lãi suất tăng")
    assert "nhat" in tokens("Kinh tế Nhật Bản")
    assert "dau" in tokens("Giá dầu thế giới")
