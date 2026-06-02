"""Greenhouse public job board scraper (no auth).

    https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true

Companies that hire in-house counsel / compliance / privacy on Greenhouse are
where this catches legal roles. Given company slugs, fetch all postings and
upsert into `jobs`.
"""
from __future__ import annotations

from typing import Iterable

import httpx

from ..db import connect
from .common import USER_AGENT, strip_html, upsert_jobs

API_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def fetch_board(slug: str, client: httpx.Client, display_name: str | None = None) -> list[dict]:
    """Fetch all jobs for one company slug. Returns normalized dicts."""
    url = API_URL.format(slug=slug)
    r = client.get(url, params={"content": "true"}, timeout=30.0)
    r.raise_for_status()
    payload = r.json()
    company = display_name or slug.replace("-", " ").replace("_", " ").title()
    jobs = []
    for j in payload.get("jobs", []):
        offices = j.get("offices") or []
        location = j.get("location", {}).get("name") or ", ".join(
            o.get("name", "") for o in offices if o.get("name")
        )
        jobs.append({
            "source": "greenhouse",
            "source_id": str(j["id"]),
            "company": company,
            "title": (j.get("title") or "").strip(),
            "location": (location or "").strip() or None,
            "url": j.get("absolute_url"),
            "jd_text": strip_html(j.get("content", "")),
            "posted_at": j.get("updated_at") or j.get("first_published"),
        })
    return jobs


def scrape(slugs: Iterable[str | tuple[str, str]]) -> dict:
    """Fetch boards for each slug, upsert into DB. Returns {slug: count}."""
    conn = connect()
    counts: dict[str, int] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for item in slugs:
            slug, display = item if isinstance(item, tuple) else (item, None)
            slug = (slug or "").strip().lower()
            if not slug:
                continue
            try:
                jobs = fetch_board(slug, client, display_name=display)
            except httpx.HTTPStatusError as e:
                print(f"  [skip] greenhouse:{slug}: HTTP {e.response.status_code}")
                counts[slug] = 0
                continue
            except httpx.HTTPError as e:
                print(f"  [skip] greenhouse:{slug}: {e}")
                counts[slug] = 0
                continue
            upsert_jobs(conn, jobs)
            counts[slug] = len(jobs)
            print(f"  greenhouse:{slug}: {len(jobs)} jobs")
    conn.close()
    return counts
