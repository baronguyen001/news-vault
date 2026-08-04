from __future__ import annotations

import importlib.resources
import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import jinja2
from markupsafe import Markup


@dataclass(frozen=True, slots=True)
class SiteMeta:
    site: str
    version: str
    kdf_iterations: int
    site_url: str


def environment() -> jinja2.Environment:
    """Return the configured Jinja2 environment."""
    return jinja2.Environment(
        loader=jinja2.PackageLoader("newsvault", "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_page(
    *,
    kind: str,
    base: str,
    title: str,
    config: Mapping[str, object],
    meta: SiteMeta,
) -> str:
    """Render one HTML shell page."""
    template = environment().get_template("page.html.j2")
    config_json = json.dumps(dict(config), ensure_ascii=False)
    config_json = config_json.replace("</", "<\\/")
    return template.render(
        kind=kind,
        base=base,
        title=title,
        config=config,
        config_json=Markup(config_json),
        meta=meta,
    )


def write_page(path: Path, html: str) -> None:
    """Write an HTML string to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def write_json(path: Path, data: object) -> None:
    """Write JSON to disk with stable formatting and a trailing newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def copy_assets(out_dir: Path) -> list[Path]:
    """Copy bundled JS and CSS assets into the output directory."""
    out_dir = Path(out_dir)
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    source_root = importlib.resources.files("newsvault") / "assets"
    for item in source_root.iterdir():
        if item.is_file() and item.suffix in (".js", ".css"):
            dest = assets_dir / item.name
            shutil.copy2(item, dest)
            copied.append(dest)

    return copied


def write_static(out_dir: Path, meta: SiteMeta) -> None:
    """Write static files that belong at the site root."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    (out_dir / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    manifest = {
        "name": meta.site,
        "short_name": "Kho tin",
        "start_url": ".",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#0f172a",
        "lang": "vi",
    }
    write_json(out_dir / "manifest.webmanifest", manifest)


def relative_base(depth: int) -> str:
    """Return the relative path prefix for a page at a given folder depth."""
    return "../" * depth
