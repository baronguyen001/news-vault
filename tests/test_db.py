"""Tests for the newsvault.db read-only data layer."""

from __future__ import annotations

import sqlite3

import pytest

from newsvault.db import (
    available_days,
    connect,
    counts_by_day,
    load_day,
    load_days,
    load_range,
)
from tests.make_fixture import build


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "sample.db"
    build(path, days=3, per_day=5)
    return path


def test_connect_missing_path(tmp_path):
    missing = tmp_path / "does_not_exist.db"
    with pytest.raises(FileNotFoundError):
        connect(missing)


def test_available_days_and_counts(db_path):
    conn = connect(db_path)

    days = available_days(conn)
    assert len(days) == 3
    assert days == sorted(days)

    counts = counts_by_day(conn)
    assert len(counts) == 3
    assert sum(counts.values()) == 15
    assert set(counts.keys()) == set(days)

    conn.close()


def test_load_day_sorts_and_parses(db_path):
    raw_conn = sqlite3.connect(db_path)
    raw_conn.execute(
        "UPDATE articles SET "
        'analysis=\'{"boi_canh":"context","nguyen_nhan":"cause",'
        '"muc_dich":"goal","lien_he":"link"}\', '
        'key_points=\'["  point one  ",""]\', '
        'tags=\'["tag one","tag-two"]\' '
        "WHERE id = 1"
    )
    raw_conn.commit()
    raw_conn.close()

    conn = connect(db_path)
    days = available_days(conn)
    articles = load_day(conn, days[-1])  # row id 1 is written for the newest day

    assert len(articles) == 5

    scores = [article.score for article in articles]
    assert scores == sorted(scores, reverse=True)

    parsed = next(article for article in articles if article.id == 1)
    assert parsed.key_points == ("point one",)
    assert parsed.tags == ("tag one", "tag-two")
    assert parsed.analysis == {
        "boi_canh": "context",
        "nguyen_nhan": "cause",
        "muc_dich": "goal",
        "lien_he": "link",
    }

    assert all(isinstance(article.key_points, tuple) for article in articles)
    assert all(isinstance(article.tags, tuple) for article in articles)
    assert all(isinstance(article.analysis, dict) for article in articles)
    assert any(article.analysis == {} for article in articles)

    conn.close()


def test_load_range_inclusive(db_path):
    conn = connect(db_path)
    days = available_days(conn)

    articles = load_range(conn, days[0], days[-1])
    assert len(articles) == 15

    day_keys = [article.day for article in articles]
    assert day_keys == sorted(day_keys)
    assert set(day_keys) == set(days)

    conn.close()


def test_load_days_grouped(db_path):
    conn = connect(db_path)
    days = available_days(conn)

    grouped = load_days(conn, days)
    assert set(grouped.keys()) == set(days)
    assert sum(len(group) for group in grouped.values()) == 15

    for group in grouped.values():
        scores = [article.score for article in group]
        assert scores == sorted(scores, reverse=True)

    conn.close()


def test_min_relevance_filter(db_path):
    raw_conn = sqlite3.connect(db_path)
    raw_conn.execute("UPDATE articles SET relevance = 5 WHERE id = 1")
    raw_conn.commit()
    raw_conn.close()

    conn = connect(db_path)
    day = available_days(conn)[0]

    unfiltered = load_day(conn, day)
    filtered = load_day(conn, day, min_relevance=6)

    assert len(filtered) < len(unfiltered)
    assert all(article.relevance >= 6 for article in filtered)

    conn.close()
