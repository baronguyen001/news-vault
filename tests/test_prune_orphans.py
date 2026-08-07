"""Tests for scripts/prune_orphans.py.

The build only writes, so pruning is the only thing standing between a removed source row
and a stale page that stays live at its old URL.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "prune_orphans", REPO_ROOT / "scripts" / "prune_orphans.py"
)
assert _SPEC and _SPEC.loader
prune_orphans = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(prune_orphans)


def _make_docs(
    tmp_path: Path,
    *,
    manifest: dict,
    days: tuple[str, ...] = (),
    months: tuple[str, ...] = (),
    entities: tuple[str, ...] = (),
    weeks: tuple[str, ...] = (),
) -> Path:
    docs = tmp_path / "docs"
    for day in days:
        (docs / "d" / day).mkdir(parents=True)
        (docs / "d" / day / "data.enc").write_text("payload", encoding="utf-8")
    for month in months:
        (docs / "idx").mkdir(parents=True, exist_ok=True)
        (docs / "idx" / f"{month}.enc").write_text("payload", encoding="utf-8")
    for slug in entities:
        (docs / "e" / slug).mkdir(parents=True)
    for week in weeks:
        (docs / "w" / week).mkdir(parents=True)
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return docs


def _names(paths: list[Path], docs: Path) -> list[str]:
    return [str(path.relative_to(docs)).replace("\\", "/") for path in paths]


def test_no_orphans_when_manifest_matches_disk(tmp_path: Path) -> None:
    manifest = {"days": [{"d": "2026-08-01"}], "months": ["2026-08"], "entities": [{"slug": "ai"}]}
    docs = _make_docs(
        tmp_path, manifest=manifest, days=("2026-08-01",), months=("2026-08",), entities=("ai",)
    )
    assert prune_orphans.find_orphans(manifest, docs) == []


def test_day_dropped_from_manifest_is_an_orphan(tmp_path: Path) -> None:
    """A day whose last video became junk falls out of the manifest but stays on disk."""
    manifest = {"days": [{"d": "2026-08-01"}], "months": ["2026-08"], "entities": []}
    docs = _make_docs(
        tmp_path,
        manifest=manifest,
        days=("2026-08-01", "2026-07-15"),
        months=("2026-08",),
    )
    assert _names(prune_orphans.find_orphans(manifest, docs), docs) == ["d/2026-07-15"]


def test_emptied_month_index_is_an_orphan(tmp_path: Path) -> None:
    manifest = {"days": [], "months": ["2026-08"], "entities": []}
    docs = _make_docs(tmp_path, manifest=manifest, months=("2026-08", "2026-07"))
    assert _names(prune_orphans.find_orphans(manifest, docs), docs) == ["idx/2026-07.enc"]


def test_stale_entity_page_is_an_orphan(tmp_path: Path) -> None:
    manifest = {"days": [], "months": [], "entities": [{"slug": "ai"}]}
    docs = _make_docs(tmp_path, manifest=manifest, entities=("ai", "bitcoin"))
    assert _names(prune_orphans.find_orphans(manifest, docs), docs) == ["e/bitcoin"]


def test_weeks_are_left_alone_when_manifest_omits_them(tmp_path: Path) -> None:
    """Deleting is irreversible, so an absent manifest key must not mean 'delete all'."""
    manifest = {"days": [], "months": [], "entities": []}
    docs = _make_docs(tmp_path, manifest=manifest, weeks=("2026-W30", "2026-W31"))
    assert prune_orphans.find_orphans(manifest, docs) == []


def test_weeks_are_pruned_when_manifest_lists_them(tmp_path: Path) -> None:
    manifest = {"days": [], "months": [], "entities": [], "weeks": ["2026-W30"]}
    docs = _make_docs(tmp_path, manifest=manifest, weeks=("2026-W30", "2026-W31"))
    assert _names(prune_orphans.find_orphans(manifest, docs), docs) == ["w/2026-W31"]


def test_dry_run_removes_nothing(tmp_path: Path) -> None:
    manifest = {"days": [{"d": "2026-08-01"}], "months": [], "entities": []}
    docs = _make_docs(tmp_path, manifest=manifest, days=("2026-08-01", "2026-07-15"))
    assert prune_orphans.main(["--docs", str(docs)]) == 0
    assert (docs / "d" / "2026-07-15").exists()


def test_apply_removes_the_orphan(tmp_path: Path) -> None:
    manifest = {"days": [{"d": "2026-08-01"}], "months": [], "entities": []}
    docs = _make_docs(tmp_path, manifest=manifest, days=("2026-08-01", "2026-07-15"))
    assert prune_orphans.main(["--docs", str(docs), "--apply", "--no-git"]) == 0
    assert not (docs / "d" / "2026-07-15").exists()
    assert (docs / "d" / "2026-08-01" / "data.enc").exists()


def test_missing_manifest_is_an_error(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    assert prune_orphans.main(["--docs", str(docs)]) == 2
