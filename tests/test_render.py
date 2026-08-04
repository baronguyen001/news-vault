from __future__ import annotations

from pathlib import Path

import pytest

from newsvault.render import SiteMeta, relative_base, render_page, write_json, write_page


@pytest.fixture
def meta() -> SiteMeta:
    return SiteMeta(
        site="Kho tin",
        version="0.1.0",
        kdf_iterations=250000,
        site_url="https://example.com",
    )


@pytest.fixture
def config() -> dict[str, object]:
    return {
        "kind": "day",
        "base": "../../",
        "version": "0.1.0",
        "kdfIterations": 250000,
        "site": "Kho tin",
        "day": "2026-08-04",
        "dataUrl": "data.enc",
        "prev": "2026-08-03",
        "next": "",
        "manifestUrl": "../../manifest.json",
        "indexBase": "../../idx/",
    }


def test_rendered_shell_has_required_markup(meta: SiteMeta, config: dict[str, object]) -> None:
    secret_title = "Super Secret Article Title That Must Not Leak"
    html = render_page(
        kind="day",
        base="../../",
        title="04/08/2026 — Kho tin",
        config=config,
        meta=meta,
    )
    assert secret_title not in html
    assert 'id="gate-pass"' in html
    assert 'id="app"' in html
    assert '<script type="application/json" id="nv-config">' in html
    assert html.count("<script defer src=") >= 3


def test_relative_base() -> None:
    assert relative_base(0) == ""
    assert relative_base(1) == "../"
    assert relative_base(2) == "../../"


def test_write_page(tmp_path: Path) -> None:
    write_page(tmp_path / "x" / "index.html", "<html></html>")
    assert (tmp_path / "x" / "index.html").read_text(encoding="utf-8") == "<html></html>"


def test_write_json_trailing_newline(tmp_path: Path) -> None:
    write_json(tmp_path / "x" / "data.json", {"b": 2, "a": 1})
    text = (tmp_path / "x" / "data.json").read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert '"a": 1' in text
