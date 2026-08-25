"""Delete published pages that the latest build no longer produces.

`newsvault.build` only ever writes; it never removes. That is fine while the archive only
grows, but not when rows disappear from the source database — for example when the
summarizer flags a video as junk. 103 of the 120 archived days are video-only, and ten of
them hold a single video, so removing one row can empty a whole day. Without this step the
day keeps its old URL and its stale encrypted payload stays live, which defeats the point
of hiding the video in the first place. `--force` does not help: it only skips the state
cache, so a day that is no longer a build target is never revisited.

The manifest written by the build is the authority on what should exist. Anything under
`docs/d`, `docs/idx`, `docs/e` or `docs/w` that the manifest does not list is an orphan.

Dry run:  python scripts/prune_orphans.py
Delete:   python scripts/prune_orphans.py --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCS = REPO_ROOT / "docs"


def expected_paths(manifest: dict, docs: Path) -> set[Path]:
    """Every directory or file the manifest says the site should contain."""
    expected: set[Path] = set()
    for day in manifest.get("days", []):
        expected.add(docs / "d" / str(day["d"]))
    for month in manifest.get("months", []):
        expected.add(docs / "idx" / f"{month}.enc")
    for entity in manifest.get("entities", []):
        expected.add(docs / "e" / str(entity["slug"]))
    for week in manifest.get("weeks", []):
        label = week["w"] if isinstance(week, dict) else week
        expected.add(docs / "w" / str(label))
    for curated_id in manifest.get("curated", []):
        expected.add(docs / "c" / str(curated_id))
    for substack_id in manifest.get("substack", []):
        expected.add(docs / "sub" / str(substack_id))
    return expected


def find_orphans(manifest: dict, docs: Path) -> list[Path]:
    """Published entries with no corresponding manifest entry, newest last."""
    expected = expected_paths(manifest, docs)
    orphans: list[Path] = []

    for name in ("d", "e", "w", "c", "sub"):
        parent = docs / name
        if not parent.is_dir():
            continue
        # `weeks` is absent from the manifest in some versions; leaving those directories
        # alone is the safe failure mode, since deleting them is not reversible.
        if name == "w" and not manifest.get("weeks"):
            continue
        # Same rule for deep dives, with one extra wrinkle: `docs/c` also holds the
        # listing page itself at `docs/c/index.html`, which is a FILE beside the per-item
        # directories and so is never a candidate here (only directories are scanned).
        # An absent `curated` key means the build did not survey them -> hands off.
        if name == "c" and "curated" not in manifest:
            continue
        # Same non-destructive contract for Substack essays, keyed by `docs/sub`.
        if name == "sub" and "substack" not in manifest:
            continue
        orphans.extend(
            child for child in sorted(parent.iterdir()) if child.is_dir() and child not in expected
        )

    idx = docs / "idx"
    if idx.is_dir():
        orphans.extend(
            child
            for child in sorted(idx.iterdir())
            if child.suffix == ".enc" and child not in expected
        )
    return orphans


def remove(path: Path, docs: Path, *, use_git: bool) -> None:
    """Remove one orphan, staging the deletion with git when the tree is a repository."""
    relative = path.relative_to(docs.parent)
    if use_git:
        result = subprocess.run(
            ["git", "rm", "-r", "--quiet", "--", str(relative)],
            cwd=docs.parent,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
        print(f"  git rm failed ({result.stderr.strip()[:80]}), falling back to unlink")
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove published pages the build no longer emits")
    parser.add_argument("--docs", default=str(DEFAULT_DOCS))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-git", action="store_true", help="delete files instead of git rm")
    args = parser.parse_args(argv)

    docs = Path(args.docs).resolve()
    manifest_path = docs / "manifest.json"
    if not manifest_path.exists():
        print(f"No manifest at {manifest_path} - build first.")
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    orphans = find_orphans(manifest, docs)

    print(
        f"Manifest lists {len(manifest.get('days', []))} days, "
        f"{len(manifest.get('months', []))} months, "
        f"{len(manifest.get('entities', []))} entities."
    )
    if not orphans:
        print("No orphans. Nothing to remove.")
        return 0

    print(f"{len(orphans)} orphan(s):")
    for path in orphans:
        print(f"  {path.relative_to(docs)}")

    if not args.apply:
        print("DRY RUN - nothing removed. Pass --apply to delete.")
        return 0

    for path in orphans:
        remove(path, docs, use_git=not args.no_git)
    print(f"Removed {len(orphans)} orphan(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
