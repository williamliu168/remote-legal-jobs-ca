"""RemoteOK public API scraper (no auth).

    https://remoteok.com/api

Returns a JSON array whose FIRST element is a legal/metadata notice; real jobs
start at index 1. Each job: id/slug, position (title), company, location, url,
description, date, tags[]. RemoteOK is tech/dev-skewed so it yields fewer legal
hits than Remotive, but it's free and cheap to include. A real User-Agent is
required or the endpoint may reject the request. Firehose → filter to
Canada-eligible at scrape time.
"""
from __future__ import annotations

import httpx

from ..classify import classify_job
from ..db import connect
from .common import USER_AGENT, strip_html, upsert_jobs

API_URL = "https://remoteok.com/api"


def scrape() -> dict:
    """Fetch the feed, keep CA-eligible postings, upsert."""
    conn = connect()
    jobs = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        try:
            r = client.get(API_URL, timeout=30.0)
            r.raise_for_status()
            payload = r.json()
        except httpx.HTTPError as e:
            print(f"  [skip] remoteok: {e}")
            conn.close()
            return {"remoteok": 0}

    for j in payload[1:]:                       # element 0 is metadata
        if not isinstance(j, dict):
            continue
        tags = j.get("tags") or []
        location = (j.get("location") or "").strip() or (", ".join(tags) if tags else None)
        jd = strip_html(j.get("description", ""))
        if not classify_job(location or "", jd)["ca_eligible"]:
            continue
        sid = str(j.get("id") or j.get("slug") or j.get("url") or "")
        if not sid:
            continue
        jobs.append({
            "source": "remoteok",
            "source_id": sid,
            "company": (j.get("company") or "").strip() or "(unknown)",
            "title": (j.get("position") or "").strip(),
            "location": location,
            "url": j.get("url"),
            "jd_text": jd,
            "posted_at": j.get("date"),
        })
    upsert_jobs(conn, jobs)
    conn.close()
    print(f"  remoteok: {len(jobs)} Canada-eligible jobs")
    return {"remoteok": len(jobs)}
