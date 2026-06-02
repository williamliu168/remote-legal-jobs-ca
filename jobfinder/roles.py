"""Generic role-matching engine.

This module knows nothing about legal (or any) roles — it compiles "families"
defined in the active profile (profile.yaml) and tags job titles by them. The
business definition lives entirely in the profile; see jobfinder/profile.py.

A family compiles to one regex = its `patterns` (verbatim) OR its `keywords`
(each escaped and word-boundary wrapped). `classify_role` returns the tag of the
first family that matches (and whose optional `exclude` does not), else 'other'.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Family:
    tag: str
    regex: re.Pattern
    exclude: re.Pattern | None = None


def _build_regex(keywords, patterns, word_boundary: bool, flags: int) -> re.Pattern | None:
    parts: list[str] = list(patterns or [])
    for kw in keywords or []:
        esc = re.escape(str(kw))
        parts.append(rf"\b{esc}\b" if word_boundary else esc)
    if not parts:
        return None
    return re.compile("(?:" + "|".join(parts) + ")", flags)


def compile_families(families: list[dict], match_cfg: dict | None = None) -> list[Family]:
    """Compile profile family dicts into ordered Family objects."""
    match_cfg = match_cfg or {}
    word_boundary = match_cfg.get("word_boundary", True)
    flags = 0 if match_cfg.get("case_sensitive", False) else re.I
    out: list[Family] = []
    for fam in families or []:
        regex = _build_regex(fam.get("keywords"), fam.get("patterns"), word_boundary, flags)
        if regex is None:
            continue
        excl = _build_regex(None, fam.get("exclude"), word_boundary, flags)
        out.append(Family(tag=fam["tag"], regex=regex, exclude=excl))
    return out


def classify_role(title: str, families: list[Family]) -> tuple[str, str | None]:
    """Return (tag, matched_snippet) for the first matching family, else ('other', None)."""
    t = (title or "").strip()
    if not t:
        return ("other", None)
    for fam in families:
        if fam.exclude and fam.exclude.search(t):
            continue
        m = fam.regex.search(t)
        if m:
            return (fam.tag, m.group(0).lower())
    return ("other", None)
