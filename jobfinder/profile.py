"""Load the active search profile (profile.yaml).

The profile is the business definition — what roles to surface, under what label,
for which location lens. Everything else in the package is generic infrastructure
that consumes a Profile. Swap profile.yaml to repurpose the tool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .roles import Family, compile_families

PROFILE_PATH = Path(__file__).parent.parent / "profile.yaml"


@dataclass
class Profile:
    name: str
    label: str
    location: str
    match: dict
    families: list[Family]
    surface_tags: tuple[str, ...] = field(default_factory=tuple)


_cache: Profile | None = None


def load(path: Path | None = None) -> Profile:
    """Read and compile profile.yaml (cached)."""
    global _cache
    if _cache is not None and path is None:
        return _cache
    p = path or PROFILE_PATH
    if not p.exists():
        raise FileNotFoundError(f"Missing {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    fam_specs = data.get("families") or []
    families = compile_families(fam_specs, data.get("match"))
    prof = Profile(
        name=data.get("name", "default"),
        label=data.get("label", "Surfaced roles"),
        location=(data.get("location") or "canada").lower(),
        match=data.get("match") or {},
        families=families,
        surface_tags=tuple(f.tag for f in families),
    )
    if path is None:
        _cache = prof
    return prof


def is_surfaced(role_tag: str | None) -> bool:
    """A job is 'surfaced' if its title matched any profile family (tag != 'other')."""
    return bool(role_tag) and role_tag != "other"
