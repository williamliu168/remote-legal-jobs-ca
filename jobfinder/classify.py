"""Rule-based location classifier: country, remote_policy, Canada-eligibility.

Deterministic, no LLM. Tuned for someone already authorized to work in Canada
who wants remote / remote-heavy work. We only care about three things:

  - is this Canada-based or Canada-eligible-remote?  (the target)
  - is it remote, hybrid, or onsite?
  - if it's remote, is it locked to a non-Canada region?  (then reject)

Country/remote regexes are adapted from the larger reference pipeline; the
US/UK granularity and all visa/work-auth logic have been dropped.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .db import connect
from .profile import load as load_profile
from .roles import classify_role

# ---------------------------------------------------------------------------
# Location signals (the `location` field is freeform per source).
# ---------------------------------------------------------------------------

_CA_LOC = re.compile(
    r"\b(canada|canadian|toronto|vancouver|montreal|ottawa|calgary|edmonton|"
    r"waterloo|kitchener|mississauga|hamilton|winnipeg|halifax|victoria|"
    r"quebec|qu[eé]bec|ontario|alberta|"
    r"british\s*columbia|manitoba|saskatchewan|nova\s*scotia|newfoundland|"
    r"(,\s*)?on\b|,\s*bc\b|,\s*ab\b|,\s*qc\b|,\s*mb\b|,\s*sk\b|,\s*ns\b|,\s*nl\b)",
    re.I,
)

_REMOTE_LOC = re.compile(
    r"\bremote\b|\banywhere\b|\bworldwide\b|\bglobal(ly)?\b|\bdistributed\b|"
    r"\bwork\s*from\s*home\b|\bwfh\b",
    re.I,
)
_WORLDWIDE_LOC = re.compile(
    r"\banywhere\b|\bworldwide\b|\bglobal(ly)?\b|\bnorth\s*america\b|\bamericas\b", re.I)
_HYBRID_LOC = re.compile(r"\bhybrid\b", re.I)

# Specific non-Canada regions a "remote" posting may be LOCKED to. If one of
# these is present and there is NO Canada / worldwide signal, the job is locked
# elsewhere and is not Canada-eligible.
_NON_CA_LOCK = re.compile(
    r"\b(united\s*states|\bu\.?s\.?a?\b|"
    r"new\s*york|san\s*francisco|seattle|boston|chicago|austin|denver|atlanta|"
    r",\s*(ny|tx|wa|ma|il|co|fl|ga|pa|or|nj|va|az|nc|oh|mi|ut|md)\b|"
    r"europe(an)?|\bemea\b|\beu\b|"
    r"united\s*kingdom|\buk\b|england|"
    r"india|latam|latin\s*america|\bapac\b|asia(\s*pacific)?|"
    r"australia|new\s*zealand|brazil|argentina|colombia|philippines|nigeria|estonia|"
    r"germany|france|spain|portugal|poland|netherlands|ireland|japan|singapore|mexico)\b",
    re.I,
)

# JD-text remote signals (more reliable than the location field for remote scope).
_JD_REMOTE_GLOBAL = re.compile(
    r"\b(work\s*from\s*anywhere|remote\s*,?\s*(worldwide|global|anywhere)|"
    r"globally\s*remote|fully\s*remote\s*,?\s*globally)\b",
    re.I,
)
_JD_REMOTE_CA_OK = re.compile(
    r"\b(remote\s*(in|from|,|within)?\s*canada|canada\s*remote|"
    r"canadian\s*residents?|remote\s*-?\s*canada|"
    r"(remote\s*(in\s*)?(us|united\s*states|usa)\s*(and|or|/|&)\s*canada)|"
    r"(canada\s*(and|or|/|&)\s*(us|united\s*states|usa)))\b",
    re.I,
)


def _detect_country(location: str) -> str:
    if not location:
        return "unknown"
    if _CA_LOC.search(location):
        return "CA"
    if _REMOTE_LOC.search(location):
        return "remote"          # remote with no Canada qualifier
    return "other" if location.strip() else "unknown"


def _detect_remote_policy(location: str, jd_text: str) -> str:
    loc = location or ""
    jd = jd_text or ""

    # Canada wins over any other signal (e.g. "Remote, Canada; Remote, US").
    if _JD_REMOTE_CA_OK.search(jd) or (_REMOTE_LOC.search(loc) and _CA_LOC.search(loc)):
        return "remote-ca"
    if _JD_REMOTE_GLOBAL.search(jd) or _WORLDWIDE_LOC.search(loc):
        return "remote-global"
    if _REMOTE_LOC.search(loc):
        if _CA_LOC.search(loc):
            return "remote-ca"
        if _NON_CA_LOCK.search(loc):
            return "remote-other"      # remote, but locked to a non-Canada region
        return "remote-global"          # bare "Remote", no region named → bias to keep
    # Trust `hybrid` only in the structured location field — JD prose mentions it
    # in benefits/FAQ copy and pollutes results.
    if _HYBRID_LOC.search(loc):
        return "hybrid"
    if loc.strip():
        return "onsite"
    return "unknown"


def ca_eligible(location: str, remote_policy: str, country: str) -> bool:
    """Could someone in Canada plausibly take this job? Bias toward KEEP.

    Keep when: Canada-based, OR remote-to-Canada, OR worldwide/global remote.
    Reject a remote job ONLY when it is explicitly locked to a non-Canada region
    and shows no Canada / worldwide signal. When in doubt, keep.
    """
    loc = location or ""
    if country == "CA":
        return True
    if remote_policy in ("remote-ca", "remote-global", "remote-multi", "hybrid"):
        return True
    if remote_policy == "remote-other":
        return False        # remote, but locked to a non-Canada region
    if remote_policy == "onsite":
        return bool(_CA_LOC.search(loc))   # onsite must be in Canada
    # unknown policy / no location: keep only if nothing marks it non-Canada.
    return not _NON_CA_LOCK.search(loc)


def classify_job(location: str, jd_text: str) -> dict:
    loc = location or ""
    country = _detect_country(loc)
    remote = _detect_remote_policy(loc, jd_text or "")
    eligible = ca_eligible(loc, remote, country)
    notes = []
    if country != "unknown":
        notes.append(f"country={country}")
    if remote != "unknown":
        notes.append(f"remote={remote}")
    return {
        "country": country,
        "remote_policy": remote,
        "ca_eligible": 1 if eligible else 0,
        "classify_notes": "; ".join(notes) or None,
    }


def classify_all(force: bool = False) -> dict:
    """Classify every job (or only unclassified ones). Returns summary counts."""
    profile = load_profile()
    if profile.location != "canada":
        raise NotImplementedError(
            f"location lens '{profile.location}' is not implemented (only 'canada')"
        )
    conn = connect()
    where = "" if force else "WHERE classified_at IS NULL"
    rows = conn.execute(
        f"SELECT id, title, location, jd_text FROM jobs {where}"
    ).fetchall()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    by_country: dict[str, int] = {}
    by_remote: dict[str, int] = {}
    by_role: dict[str, int] = {}
    eligible_n = 0

    for r in rows:
        out = classify_job(r["location"] or "", r["jd_text"] or "")
        role, role_notes = classify_role(r["title"] or "", profile.families)
        conn.execute(
            """
            UPDATE jobs SET country = :country, remote_policy = :remote_policy,
                            ca_eligible = :ca_eligible,
                            role_tag = :role_tag, role_notes = :role_notes,
                            classified_at = :ts
            WHERE id = :id
            """,
            {
                "country": out["country"],
                "remote_policy": out["remote_policy"],
                "ca_eligible": out["ca_eligible"],
                "role_tag": role,
                "role_notes": role_notes,
                "ts": now,
                "id": r["id"],
            },
        )
        by_country[out["country"]] = by_country.get(out["country"], 0) + 1
        by_remote[out["remote_policy"]] = by_remote.get(out["remote_policy"], 0) + 1
        by_role[role] = by_role.get(role, 0) + 1
        eligible_n += out["ca_eligible"]

    conn.commit()
    conn.close()
    return {
        "total": len(rows),
        "ca_eligible": eligible_n,
        "by_country": by_country,
        "by_remote": by_remote,
        "by_role": by_role,
    }
