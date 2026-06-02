"""Shared scraper helpers: HTML→text, a polite User-Agent, and the upsert.

All four scrapers normalize each posting to this dict shape:

    {source, source_id, company, title, location, url, jd_text, posted_at}

and call `upsert_jobs(conn, jobs)`, which inserts or refreshes by
(source, source_id). New jobs default to status 'seen'.
"""
from __future__ import annotations

import html
import re
import sqlite3
from datetime import datetime, timezone

USER_AGENT = "jobfinder/0.1 (+https://github.com/williamliu168/remote-legal-jobs-ca; personal job search)"


def strip_html(s: str) -> str:
    """Cheap HTML→text. Good enough for keyword classification + reading."""
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|div|li|h[1-6])>", "\n", s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "- ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)                  # second pass: double-encoded entities
    s = s.replace("\xa0", " ")            # nbsp → space
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def upsert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> int:
    """Insert/refresh jobs by (source, source_id). Returns rows touched."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for job in jobs:
        conn.execute(
            """
            INSERT INTO jobs(source, source_id, company, title, location,
                             url, jd_text, posted_at, scraped_at, status)
            VALUES(:source, :source_id, :company, :title, :location,
                   :url, :jd_text, :posted_at, :scraped_at, 'seen')
            ON CONFLICT(source, source_id) DO UPDATE SET
                title     = excluded.title,
                location  = excluded.location,
                url       = excluded.url,
                jd_text   = excluded.jd_text,
                posted_at = excluded.posted_at
            """,
            {**job, "scraped_at": now},
        )
        n += 1
    conn.commit()
    return n
