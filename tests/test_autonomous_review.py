import datetime as dt

from newsvault import autonomous_review as review


def test_manifest_is_secret_free_and_has_all_repositories(monkeypatch, tmp_path):
    roots = {"one": tmp_path}
    monkeypatch.setattr(review, "ROOTS", roots)
    monkeypatch.setattr(review, "DATABASES", {})
    monkeypatch.setattr(review, "_git_state", lambda _: {"dirty": False, "entries": 0})

    result = review.build_manifest(now=dt.datetime(2026, 9, 11, tzinfo=dt.UTC), days=21)

    assert result["schema"] == 1
    assert result["window_days"] == 21
    assert result["repositories"]["one"]["git"]["dirty"] is False
    assert "token" not in str(result).lower()


def test_manifest_turns_retryable_backlog_into_action(monkeypatch, tmp_path):
    monkeypatch.setattr(review, "ROOTS", {"youtube-summarizer": tmp_path})
    monkeypatch.setattr(review, "DATABASES", {"youtube-summarizer": tmp_path / "videos.db"})
    monkeypatch.setattr(review, "_git_state", lambda _: {"dirty": False, "entries": 0})
    monkeypatch.setattr(review, "_db_health", lambda *_: {"retryable": 3})

    result = review.build_manifest(now=dt.datetime(2026, 9, 11, tzinfo=dt.UTC))

    assert result["findings"] == [{"fingerprint": "youtube-summarizer:retryable",
                                    "component": "youtube-summarizer", "severity": "high",
                                    "evidence": 3, "action": "repair-and-verify"}]
