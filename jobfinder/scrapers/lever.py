"""Lever public postings scraper (no auth).

    https://api.lever.co/v0/postings/{slug}?mode=json

Returns a flat array of postings: id, text (title), categories.{location,...},
description / descriptionPlain, lists[] (sections), hostedUrl, createdAt (ms).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import httpx

from ..db import connect
from .common import USER_AGENT, strip_html, upsert_jobs

API_URL = "https://api.lever.co/v0/postings/{slug}"


def fetch_board(slug: str, client: httpx.Client, display_name: str | None = None) -> list[dict]:
    """Fetch all postings for a Lever slug."""
    url = API_URL.format(slug=slug)
    r = client.get(url, params={"mode": "json"}, timeout=30.0)
    r.raise_for_status()
    payload = r.json()
    company = display_name or slug.replace("-", " ").replace("_", " ").title()
    jobs = []
    for p in payload:
        cats = p.get("categories") or {}
        description = p.get("descriptionPlain") or strip_html(p.get("description", ""))
        extra = []
        for lst in p.get("lists") or []:
            heading = (lst.get("text") or "").strip()
            body = strip_html(lst.get("content") or "")
            if body:
                extra.append(f"{heading}:\n{body}" if heading else body)
        if p.get("additional"):
            extra.append(strip_html(p["additional"]))
        jd_text = "\n\n".join([description] + extra).strip()

        posted_ms = p.get("createdAt")
        posted_iso = (
            datetime.fromtimestamp(posted_ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")
            if posted_ms else None
        )
        jobs.append({
            "source": "lever",
            "source_id": str(p["id"]),
            "company": company,
            "title": (p.get("text") or "").strip(),
            "location": cats.get("location"),
            "url": p.get("hostedUrl"),
            "jd_text": jd_text,
            "posted_at": posted_iso,
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
                print(f"  [skip] lever:{slug}: HTTP {e.response.status_code}")
                counts[slug] = 0
                continue
            except httpx.HTTPError as e:
                print(f"  [skip] lever:{slug}: {e}")
                counts[slug] = 0
                continue
            upsert_jobs(conn, jobs)
            counts[slug] = len(jobs)
            print(f"  lever:{slug}: {len(jobs)} jobs")
    conn.close()
    return counts
