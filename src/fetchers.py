"""
Fetch jobs from multiple free sources.
Each fetcher returns a list of dicts with a consistent schema:
{
  "id": str,
  "title": str,
  "company": str,
  "location": str,
  "description": str,
  "url": str,
  "posted_at": datetime,
  "source": str,
  "ctc_lpa": float | None,
}
"""
from __future__ import annotations
import os
import re
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
import requests

log = logging.getLogger("fetchers")
IST = timezone(timedelta(hours=5, minutes=30))


# ============================================================
# 1. ADZUNA — free API, 250 calls/day, covers many job boards
# ============================================================
def fetch_adzuna(app_id: str, app_key: str, role_keywords: list[str],
                 country: str = "in", max_per_query: int = 20) -> list[dict]:
    jobs: list[dict] = []
    if not app_id or not app_key:
        log.warning("Adzuna credentials missing — skipping")
        return jobs

    for kw in role_keywords:
        try:
            r = requests.get(
                f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": kw,
                    "results_per_page": max_per_query,
                    "max_days_old": 3,
                    "sort_by": "date",
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            for j in data.get("results", []):
                jobs.append({
                    "id": f"adzuna_{j.get('id')}",
                    "title": j.get("title", "").strip(),
                    "company": (j.get("company") or {}).get("display_name", "").strip(),
                    "location": (j.get("location") or {}).get("display_name", "").strip(),
                    "description": j.get("description", ""),
                    "url": j.get("redirect_url", ""),
                    "posted_at": _parse_iso(j.get("created")),
                    "source": "Adzuna",
                    "ctc_lpa": _adzuna_ctc(j),
                })
            time.sleep(0.5)  # be polite
        except Exception as e:
            log.warning(f"Adzuna fetch failed for '{kw}': {e}")
    return jobs


def _adzuna_ctc(job: dict) -> float | None:
    sal_min = job.get("salary_min")
    sal_max = job.get("salary_max")
    if not (sal_min or sal_max):
        return None
    sal = sal_max or sal_min
    # Adzuna India salaries are usually annual in INR
    if sal > 100000:
        return round(sal / 100000, 1)
    return None


# ============================================================
# 2. REMOTEOK — free, no auth needed
# ============================================================
def fetch_remoteok(role_keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    try:
        r = requests.get(
            "https://remoteok.com/api",
            headers={"User-Agent": "Mozilla/5.0 JobBot"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        # First item is metadata
        listings = [d for d in data if isinstance(d, dict) and d.get("position")]
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        for j in listings:
            title = (j.get("position") or "").lower()
            if not any(kw.lower() in title for kw in role_keywords):
                continue
            posted_at = _parse_iso(j.get("date"))
            if posted_at and posted_at < cutoff:
                continue
            jobs.append({
                "id": f"remoteok_{j.get('id')}",
                "title": j.get("position", ""),
                "company": j.get("company", ""),
                "location": "Remote",
                "description": j.get("description", "")[:5000],
                "url": j.get("url") or f"https://remoteok.com/remote-jobs/{j.get('id')}",
                "posted_at": posted_at,
                "source": "RemoteOK",
                "ctc_lpa": None,
            })
    except Exception as e:
        log.warning(f"RemoteOK fetch failed: {e}")
    return jobs


# ============================================================
# 3. GREENHOUSE — public JSON for many companies
# ============================================================
GREENHOUSE_BOARDS = [
    "razorpay", "atlassian", "stripe", "postman", "hasura",
    "snowflake", "groww", "atlan", "moengage", "innovaccer",
    "browserstack", "chargebee", "freshworks", "mindtickle",
    "uniphore", "whatfix",
]


def fetch_greenhouse(role_keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    for board in GREENHOUSE_BOARDS:
        try:
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
                params={"content": "true"},
                timeout=15,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            for j in data.get("jobs", []):
                title = (j.get("title") or "").lower()
                if not any(kw.lower() in title for kw in role_keywords):
                    continue
                posted_at = _parse_iso(j.get("updated_at"))
                if posted_at and posted_at < cutoff:
                    continue
                # strip HTML from content
                desc = re.sub(r"<[^>]+>", " ", j.get("content", ""))
                desc = re.sub(r"\s+", " ", desc).strip()[:5000]
                jobs.append({
                    "id": f"greenhouse_{board}_{j.get('id')}",
                    "title": j.get("title", ""),
                    "company": board.replace("-", " ").title(),
                    "location": (j.get("location") or {}).get("name", ""),
                    "description": desc,
                    "url": j.get("absolute_url", ""),
                    "posted_at": posted_at,
                    "source": "Greenhouse",
                    "ctc_lpa": None,
                })
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"Greenhouse fetch failed for {board}: {e}")
    return jobs


# ============================================================
# 4. LEVER — public JSON for many companies
# ============================================================
LEVER_BOARDS = [
    "databricks", "phonepe", "cred", "zerodha", "sprinklr",
    "darwinbox", "tekion", "confluentinc",
]


def fetch_lever(role_keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=3)).timestamp() * 1000)
    for board in LEVER_BOARDS:
        try:
            r = requests.get(
                f"https://api.lever.co/v0/postings/{board}",
                params={"mode": "json"},
                timeout=15,
            )
            if r.status_code != 200:
                continue
            for j in r.json():
                title = (j.get("text") or "").lower()
                if not any(kw.lower() in title for kw in role_keywords):
                    continue
                created = j.get("createdAt", 0)
                if created and created < cutoff_ts:
                    continue
                posted_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc) if created else None
                cats = j.get("categories") or {}
                loc = cats.get("location", "")
                desc = j.get("descriptionPlain", "") or re.sub(
                    r"<[^>]+>", " ", j.get("description", ""))
                desc = re.sub(r"\s+", " ", desc).strip()[:5000]
                jobs.append({
                    "id": f"lever_{board}_{j.get('id')}",
                    "title": j.get("text", ""),
                    "company": board.replace("inc", "").title(),
                    "location": loc,
                    "description": desc,
                    "url": j.get("hostedUrl", ""),
                    "posted_at": posted_at,
                    "source": "Lever",
                    "ctc_lpa": None,
                })
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"Lever fetch failed for {board}: {e}")
    return jobs


# ============================================================
# 5. ASHBY — public JSON for some companies (Linear, etc.)
# ============================================================
ASHBY_BOARDS = ["linear", "ramp", "vercel"]


def fetch_ashby(role_keywords: list[str]) -> list[dict]:
    jobs: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    for board in ASHBY_BOARDS:
        try:
            r = requests.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{board}",
                params={"includeCompensation": "true"},
                timeout=15,
            )
            if r.status_code != 200:
                continue
            for j in r.json().get("jobs", []):
                title = (j.get("title") or "").lower()
                if not any(kw.lower() in title for kw in role_keywords):
                    continue
                posted_at = _parse_iso(j.get("publishedAt"))
                if posted_at and posted_at < cutoff:
                    continue
                jobs.append({
                    "id": f"ashby_{board}_{j.get('id')}",
                    "title": j.get("title", ""),
                    "company": board.title(),
                    "location": j.get("locationName", ""),
                    "description": j.get("descriptionPlain", "")[:5000],
                    "url": j.get("jobUrl", ""),
                    "posted_at": posted_at,
                    "source": "Ashby",
                    "ctc_lpa": None,
                })
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"Ashby fetch failed for {board}: {e}")
    return jobs


# ============================================================
# 6. YC Work at a Startup (Hacker News-adjacent, via API)
# ============================================================
def fetch_ycombinator(role_keywords: list[str]) -> list[dict]:
    """Pulls fresh YC company job postings via their public listings page.
    YC doesn't have a clean API, so we use their search endpoint."""
    jobs: list[dict] = []
    try:
        r = requests.get(
            "https://www.workatastartup.com/api/jobs/search",
            params={
                "query": "engineer OR analyst OR product",
                "remote": "yes",
            },
            headers={"User-Agent": "Mozilla/5.0 JobBot"},
            timeout=15,
        )
        if r.status_code != 200:
            return jobs
        # YC API is rate-limited and the format changes; if it fails, just skip
        for j in r.json().get("jobs", [])[:40]:
            title = (j.get("title") or "").lower()
            if not any(kw.lower() in title for kw in role_keywords):
                continue
            jobs.append({
                "id": f"yc_{j.get('id')}",
                "title": j.get("title", ""),
                "company": (j.get("company") or {}).get("name", ""),
                "location": j.get("location", "Remote"),
                "description": j.get("description", "")[:5000],
                "url": f"https://www.workatastartup.com/jobs/{j.get('id')}",
                "posted_at": _parse_iso(j.get("created_at")),
                "source": "YC",
                "ctc_lpa": None,
            })
    except Exception as e:
        log.info(f"YC fetch skipped: {e}")
    return jobs


# ============================================================
# UTILITIES
# ============================================================
def _parse_iso(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        if isinstance(s, (int, float)):
            return datetime.fromtimestamp(s / 1000 if s > 1e10 else s, tz=timezone.utc)
        # Handle various ISO formats
        s = str(s).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ============================================================
# MASTER FETCHER
# ============================================================
def fetch_all_jobs(profile: dict) -> list[dict]:
    """Pulls from every enabled source, returns combined deduplicated list."""
    all_keywords: list[str] = []
    for track_name, track in profile["role_tracks"].items():
        if track.get("enabled"):
            all_keywords.extend(track["keywords"])
    all_keywords = list(set(all_keywords))

    log.info(f"Searching {len(all_keywords)} keyword variants across sources")

    jobs: list[dict] = []

    adzuna_id = os.getenv("ADZUNA_APP_ID", "")
    adzuna_key = os.getenv("ADZUNA_APP_KEY", "")
    if adzuna_id and adzuna_key:
        # Limit Adzuna to top keywords to preserve daily quota
        top_kws = all_keywords[:8]
        jobs.extend(fetch_adzuna(adzuna_id, adzuna_key, top_kws))
        log.info(f"Adzuna: {len(jobs)} jobs")

    pre = len(jobs)
    jobs.extend(fetch_remoteok(all_keywords))
    log.info(f"RemoteOK: +{len(jobs) - pre} jobs")

    pre = len(jobs)
    jobs.extend(fetch_greenhouse(all_keywords))
    log.info(f"Greenhouse: +{len(jobs) - pre} jobs")

    pre = len(jobs)
    jobs.extend(fetch_lever(all_keywords))
    log.info(f"Lever: +{len(jobs) - pre} jobs")

    pre = len(jobs)
    jobs.extend(fetch_ashby(all_keywords))
    log.info(f"Ashby: +{len(jobs) - pre} jobs")

    # YC API is flaky — keep it best-effort
    pre = len(jobs)
    jobs.extend(fetch_ycombinator(all_keywords))
    log.info(f"YC: +{len(jobs) - pre} jobs")

    # Dedupe by (company, title) — same job often posted via multiple sources
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for j in jobs:
        key = (j["company"].lower().strip(), j["title"].lower().strip())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(j)

    log.info(f"After dedup: {len(deduped)} unique jobs")
    return deduped
