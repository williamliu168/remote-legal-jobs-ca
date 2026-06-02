"""Markdown shortlist generator (re-runnable, no LLM).

Writes shortlist.md at the repo root, organized so the most relevant roles are
on top. The top "surfaced" section is whatever the active profile matches (see
profile.yaml); nothing is silently dropped — non-Canada-eligible jobs are
relegated to a compact count table at the bottom.

Sections:
  1. ⭐  Surfaced — profile matches (Canada-eligible)        [the primary list]
  2. 🏠  Remote — Canada (remote-ca, all roles)
  3. 🌍  Remote — global / worldwide (CA-eligible)
  4. 🏙️  Canada — onsite / hybrid
  5. 🗂️  Everything else (not Canada-eligible)  — relegated count-by-location
"""
from __future__ import annotations

import datetime
from pathlib import Path

from .db import connect
from .profile import is_surfaced
from .profile import load as load_profile

OUT = Path(__file__).parent.parent / "shortlist.md"

_REMOTE_RANK = {"remote-ca": 0, "remote-global": 1, "remote-multi": 1, "hybrid": 2, "onsite": 3}


def _cell(s, n=44):
    return (s or "").replace("|", "/").replace("\n", " ")[:n]


def _mark(role_tag: str) -> str:
    return "⭐ " if is_surfaced(role_tag) else ""


def basic(items) -> list[str]:
    out = ["| Company | Title | Location | Remote | Role | Link |",
           "|---|---|---|---|---|---|"]
    for r in items:
        out.append(
            f"| {_cell(r['company'], 28)} | {_mark(r['role_tag'])}{_cell(r['title'])} | "
            f"{_cell(r['location'], 26)} | {r['remote_policy'] or '?'} | {r['role_tag'] or '?'} | "
            f"[link]({r['url']}) |"
        )
    return out if items else ["| _(none)_ |  |  |  |  |  |"]


def main() -> None:
    profile = load_profile()
    con = connect()
    rows = con.execute(
        "SELECT company, title, location, url, country, remote_policy, role_tag, ca_eligible "
        "FROM jobs"
    ).fetchall()
    con.close()

    surfaced, remote_ca, remote_global, ca_onsite, relegated = [], [], [], [], []
    for r in rows:
        if not r["ca_eligible"]:
            relegated.append(r)
            continue
        if is_surfaced(r["role_tag"]):
            surfaced.append(r)
        rp = r["remote_policy"]
        if rp == "remote-ca":
            remote_ca.append(r)
        elif rp in ("remote-global", "remote-multi"):
            remote_global.append(r)
        elif r["country"] == "CA" and rp in ("onsite", "hybrid"):
            ca_onsite.append(r)

    surfaced.sort(key=lambda r: (_REMOTE_RANK.get(r["remote_policy"], 9),
                                 r["company"] or "", r["title"] or ""))
    for lst in (remote_ca, remote_global, ca_onsite):
        lst.sort(key=lambda r: (r["company"] or "", r["title"] or ""))

    tags = ", ".join(profile.surface_tags) or "—"
    today = datetime.date.today()
    L = [
        "# Remote-Canada job shortlist", "",
        f"_Generated {today} from {len(rows)} scraped postings (rule-based; no LLM). "
        f"Profile **{profile.name}** surfaces **{profile.label}** roles on top; "
        f"nothing is dropped. Browse/triage with `python -m jobfinder.cli serve`._", "",
        f"**Counts:** ⭐ {profile.label} {len(surfaced)} · 🏠 remote-CA {len(remote_ca)} · "
        f"🌍 remote-global {len(remote_global)} · 🏙️ CA onsite/hybrid {len(ca_onsite)} · "
        f"🗂️ relegated (not CA-eligible) {len(relegated)}", "",
        f"## ⭐ {profile.label} — surfaced (Canada-eligible)", "",
        f"_The primary list: titles matching the profile ({tags}), "
        f"sorted remote-CA → remote-global → hybrid/onsite._", "",
    ] + basic(surfaced)

    L += ["", "## 🏠 Remote — Canada (all roles)", ""] + basic(remote_ca)
    L += ["", "## 🌍 Remote — global / worldwide (Canada-eligible)", ""] + basic(remote_global)
    L += ["", "## 🏙️ Canada — onsite / hybrid", ""] + basic(ca_onsite)

    L += ["", f"## 🗂️ Everything else — not Canada-eligible ({len(relegated)})", ""]
    if relegated:
        by_loc: dict[str, int] = {}
        for r in relegated:
            key = (r["location"] or "?").strip()[:40] or "?"
            by_loc[key] = by_loc.get(key, 0) + 1
        L += ["_Relegated, not dropped — browse with `serve` (filter view=all). "
              "Counts by location:_", "", "| Location | Count |", "|---|---|"]
        L += [f"| {k.replace('|', '/')} | {n} |"
              for k, n in sorted(by_loc.items(), key=lambda kv: -kv[1])[:50]]
    else:
        L.append("_(none)_")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"surfaced={len(surfaced)} remote-ca={len(remote_ca)} remote-global={len(remote_global)} "
          f"ca-onsite={len(ca_onsite)} relegated={len(relegated)} -> {OUT}")


if __name__ == "__main__":
    main()
