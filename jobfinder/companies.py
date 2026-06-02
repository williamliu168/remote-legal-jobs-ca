"""Load companies.yaml and group slugs per platform (greenhouse | lever)."""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent.parent / "companies.yaml"


def load(enabled_only: bool = True, tag: str | None = None) -> list[dict]:
    """Return the list of company records (optionally filtered by enabled/tag)."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    rows = data.get("companies") or []
    if enabled_only:
        rows = [r for r in rows if r.get("enabled", True)]
    if tag:
        rows = [r for r in rows if tag in (r.get("tags") or [])]
    return rows


def grouped(enabled_only: bool = True, tag: str | None = None) -> dict[str, list[tuple[str, str | None]]]:
    """Return {platform: [(slug, display_name_or_None), ...]}."""
    out: dict[str, list[tuple[str, str | None]]] = {}
    for r in load(enabled_only=enabled_only, tag=tag):
        platform = (r.get("platform") or "").lower()
        slug = r.get("slug")
        if not platform or not slug:
            continue
        out.setdefault(platform, []).append((slug, r.get("display_name")))
    return out
