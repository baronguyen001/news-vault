"""The incremental-rebuild cache: what counts as "this page is still current".

A build that decides wrongly here fails silently and stays wrong. It writes nothing, reports
"0 days built, 120 unchanged", exits 0, and leaves the site serving the old markup. That is
how a gate checkbox once shipped to the home page and to none of the 120 day pages: the
freshness hash covered the payload only, and editing a template changes no payload at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from newsvault import build
from tests.make_fixture import build as make_fixture

PAYLOAD: dict[str, object] = {"day": "2026-08-06", "articles": [{"t": "x"}]}


@pytest.fixture(autouse=True)
def _clear_shell_cache() -> None:
    """`_shell_digest` is cached for the process; a test that repoints it must start clean."""
    build._shell_digest.cache_clear()
    yield
    build._shell_digest.cache_clear()


def test_shell_digest_reads_the_templates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "templates"
    root.mkdir()
    (root / "page.html.j2").write_text("<p>one</p>", encoding="utf-8")
    monkeypatch.setattr(build, "_templates_root", lambda: root)

    first = build._shell_digest()
    build._shell_digest.cache_clear()
    (root / "page.html.j2").write_text("<p>two</p>", encoding="utf-8")

    assert build._shell_digest() != first


def test_shell_digest_notices_a_new_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "templates"
    root.mkdir()
    (root / "page.html.j2").write_text("<p>one</p>", encoding="utf-8")
    monkeypatch.setattr(build, "_templates_root", lambda: root)

    first = build._shell_digest()
    build._shell_digest.cache_clear()
    (root / "extra.html.j2").write_text("<p>two</p>", encoding="utf-8")

    assert build._shell_digest() != first


def test_shell_digest_covers_the_version_stamped_into_every_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A release must not leave pages claiming the old version next to a new manifest."""
    root = tmp_path / "templates"
    root.mkdir()
    (root / "page.html.j2").write_text("<p>one</p>", encoding="utf-8")
    monkeypatch.setattr(build, "_templates_root", lambda: root)

    first = build._shell_digest()
    build._shell_digest.cache_clear()
    monkeypatch.setattr(build, "__version__", "99.99.99")

    assert build._shell_digest() != first


def test_digest_is_stable_for_the_same_payload_and_shell() -> None:
    assert build._digest(PAYLOAD) == build._digest(PAYLOAD)
    assert build._digest(PAYLOAD, with_shell=True) == build._digest(PAYLOAD, with_shell=True)


def test_pages_with_html_hash_differently_from_bare_payloads() -> None:
    assert build._digest(PAYLOAD) != build._digest(PAYLOAD, with_shell=True)


def test_a_template_edit_invalidates_pages_that_render_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression: day, week and entity pages must rebuild when the shell changes."""
    before = build._digest(PAYLOAD, with_shell=True)
    monkeypatch.setattr(build, "_shell_digest", lambda: "deadbeefdeadbeef")

    assert build._digest(PAYLOAD, with_shell=True) != before


def test_a_template_edit_does_not_churn_the_search_shards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shards are encrypted JSON with no page around them.

    Rebuilding them on a template edit would rewrite every `.enc` byte in `docs/idx` for a
    change that cannot affect them, turning a markup tweak into a repository-wide diff.
    """
    before = build._digest(PAYLOAD)
    monkeypatch.setattr(build, "_shell_digest", lambda: "deadbeefdeadbeef")

    assert build._digest(PAYLOAD) == before


def _build(out: Path, db: Path) -> build.BuildReport:
    return build.build_site(
        build.BuildOptions(
            db_path=db,
            out_dir=out,
            password="test-password",
            backfill=True,
            use_brief=False,
        )
    )


def test_second_build_skips_everything_then_a_template_edit_rebuilds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end, against a real fixture database and a real output tree."""
    db = tmp_path / "sample.db"
    make_fixture(db)
    out = tmp_path / "site"

    first = _build(out, db)
    assert first.days_built, "the first build must write something"

    second = _build(out, db)
    assert second.days_built == [], "an unchanged rebuild must write no day pages"
    assert second.days_skipped, "...and must report them as skipped"

    # Now the shell changes, exactly as editing page.html.j2 would.
    build._shell_digest.cache_clear()
    monkeypatch.setattr(build, "_shell_digest", lambda: "0123456789abcdef")
    third = _build(out, db)

    assert sorted(third.days_built) == sorted(second.days_skipped), (
        "every day page must be rewritten when the HTML shell changes"
    )
