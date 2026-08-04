from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import requests

from newsvault.brief import BriefResult, fallback_brief, generate_brief
from newsvault.model import Article


def _article(**kwargs: object) -> Article:
    defaults = {
        "id": 1,
        "url": "https://example.com/1",
        "source": "VnExpress",
        "source_key": "vnexpress",
        "region": "domestic",
        "title": "Original title",
        "title_vi": "Tiêu đề",
        "published_at": "Wed, 29 Jul 2026 12:00:36 +0700",
        "published_iso": "2026-07-29T12:00:36+07:00",
        "day": "2026-07-29",
        "fetched_at": "2026-07-29T06:09:27.518450+00:00",
        "category": "Kinh tế & Tài chính",
        "topic": "Kinh tế/Tài chính",
        "summary_vi": "Đây là tóm tắt. Câu thứ hai nói thêm chi tiết.",
        "key_points": (),
        "tags": (),
        "analysis": {},
        "impact_level": "cao",
        "is_law_policy": False,
        "relevance": 8,
        "score": 80,
    }
    defaults.update(kwargs)
    return Article(**defaults)


def test_fallback_brief_respects_limit() -> None:
    articles = [_article(id=i, score=i * 10) for i in range(1, 8)]
    result = fallback_brief(articles, limit=5)
    assert isinstance(result, BriefResult)
    assert len(result.bullets) <= 5
    assert result.source == "fallback"
    assert result.error == ""
    assert "VnExpress" in result.bullets[0]


def test_generate_brief_no_key_no_network() -> None:
    with patch("newsvault.brief.requests.post") as mock_post:
        result = generate_brief("2026-08-04", [_article()], api_key=None)
    assert mock_post.called is False
    assert result.source == "fallback"
    assert result.error == "no api key"


def _mock_response(status: int, text: str | None = None) -> object:
    body = {}
    if text is not None:
        body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return type("Resp", (), {"status_code": status, "json": staticmethod(lambda: body)})()


def test_generate_brief_success() -> None:
    payload = {"bullets": ["A", "B", "C", "D", "E"]}
    response = _mock_response(200, json.dumps(payload))
    with patch("newsvault.brief.requests.post", return_value=response) as mock_post:
        result = generate_brief("2026-08-04", [_article()], api_key="secret")
    assert mock_post.call_count == 1
    assert result.source == "gemini"
    assert result.bullets == tuple(payload["bullets"])
    assert result.error == ""


def test_generate_brief_500_fallback() -> None:
    response = _mock_response(500)
    with patch("newsvault.brief.requests.post", return_value=response):
        result = generate_brief("2026-08-04", [_article()], api_key="secret")
    assert result.source == "fallback"
    assert result.error
    assert "secret" not in result.error


def test_generate_brief_no_candidates_fallback() -> None:
    response = type("Resp", (), {"status_code": 200, "json": staticmethod(dict)})()
    with patch("newsvault.brief.requests.post", return_value=response):
        result = generate_brief("2026-08-04", [_article()], api_key="secret")
    assert result.source == "fallback"
    assert result.error == "missing candidates"


def test_generate_brief_invalid_json_fallback() -> None:
    response = _mock_response(200, "not json")
    with patch("newsvault.brief.requests.post", return_value=response):
        result = generate_brief("2026-08-04", [_article()], api_key="secret")
    assert result.source == "fallback"
    assert result.error == "invalid candidate json"


def test_generate_brief_request_exception_fallback() -> None:
    with patch("newsvault.brief.requests.post", side_effect=requests.RequestException("boom")):
        result = generate_brief("2026-08-04", [_article()], api_key="secret")
    assert result.source == "fallback"
    assert result.error == "network error"


def test_generate_brief_key_not_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    secret = "SUPER_SECRET_KEY_123"
    response = _mock_response(500)
    with (
        caplog.at_level("WARNING"),
        patch("newsvault.brief.requests.post", return_value=response),
    ):
        result = generate_brief("2026-08-04", [_article()], api_key=secret)
    assert result.source == "fallback"
    assert secret not in result.error
    for record in caplog.records:
        assert secret not in record.message
        formatted = record.getMessage()
        assert secret not in formatted
