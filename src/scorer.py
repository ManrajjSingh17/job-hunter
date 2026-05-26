"""
Score each job for fit with Manraj's profile.
Returns a fit_score from 0-10 based on:
  - Keyword overlap with his skills
  - Company tier boost (S/A/B)
  - Role-track match
  - Freshness
  - Penalties for senior/excluded terms
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Any


def score_job(job: dict, profile: dict) -> tuple[float, dict]:
    """Returns (score, reasoning) where score is 0-10."""
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    company = (job.get("company") or "").lower()
    location = (job.get("location") or "").lower()
    full_text = f"{title} {desc}"

    reasoning: dict[str, Any] = {
        "skill_matches": [],
        "company_tier": None,
        "track_match": None,
        "penalties": [],
        "boosts": [],
    }

    score = 0.0

    # ----- 1. Track match (must match at least one) -----
    matched_tracks: list[tuple[str, float]] = []
    for track_name, track in profile["role_tracks"].items():
        if not track.get("enabled"):
            continue
        for kw in track["keywords"]:
            if kw.lower() in title:
                matched_tracks.append((track_name, track.get("weight", 1.0)))
                break
    if not matched_tracks:
        return 0.0, {"reason": "No role track match"}
    # Take the best-weighted track match
    best_track = max(matched_tracks, key=lambda x: x[1])
    reasoning["track_match"] = best_track[0]
    score += 3.0 * best_track[1]   # base score for matching role

    # ----- 2. Penalties for excluded keywords (senior, lead, etc) -----
    for ex_kw in profile["filters"]["exclude_keywords"]:
        if re.search(rf"\b{re.escape(ex_kw)}\b", title):
            reasoning["penalties"].append(f"title contains '{ex_kw}'")
            return 0.0, reasoning   # hard exclude

    # ----- 3. Location filter -----
    location_keywords = profile["filters"]["location_keywords"]
    if location:
        if not any(lk in location for lk in location_keywords):
            reasoning["penalties"].append(f"location '{location}' not in target geos")
            return 0.0, reasoning

    # ----- 4. Experience filter -----
    max_yrs = profile["filters"]["experience_max_years"]
    # Match patterns like: "3+ years", "3-5 years", "minimum 2 years"
    # For ranges like "0-2 years", take the LOWER bound (min required)
    exp_min = None
    range_match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)\s*(?:years?|yrs?)", full_text)
    if range_match:
        exp_min = int(range_match.group(1))
    else:
        single_matches = re.findall(r"(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience|exp)", full_text)
        if single_matches:
            exp_min = min(int(m) for m in single_matches)
    if exp_min is not None and exp_min > max_yrs:
        reasoning["penalties"].append(f"requires {exp_min}+ yrs exp (max {max_yrs})")
        return 0.0, reasoning

    # Look for fresher signals — boost
    if any(kw in full_text for kw in ["fresher", "graduate", "new grad", "0-1 year",
                                       "entry level", "entry-level", "no prior experience",
                                       "recent graduate", "campus"]):
        score += 1.0
        reasoning["boosts"].append("fresher-friendly phrasing")

    # ----- 5. Skill keyword matches -----
    skill_hits = 0
    for skill in profile["skills"]:
        if re.search(rf"\b{re.escape(skill.lower())}\b", full_text):
            skill_hits += 1
            reasoning["skill_matches"].append(skill)
    # Cap skill bonus at 3.0 (10+ matches = max)
    score += min(skill_hits * 0.3, 3.0)

    # ----- 6. Company tier boost -----
    for tier, companies in [("S", profile["target_companies"]["S_tier"]),
                            ("A", profile["target_companies"]["A_tier"]),
                            ("B", profile["target_companies"]["B_tier"])]:
        if any(c.lower() in company or company in c.lower() for c in companies):
            tier_boost = {"S": 3.0, "A": 2.0, "B": 1.0}[tier]
            score += tier_boost
            reasoning["company_tier"] = tier
            reasoning["boosts"].append(f"{tier}-tier company")
            break

    # ----- 7. Freshness boost — within 24 hrs gets +0.5 -----
    if job.get("posted_at"):
        age_hrs = (datetime.now(timezone.utc) - job["posted_at"]).total_seconds() / 3600
        if age_hrs < 24:
            score += 0.5
            reasoning["boosts"].append("posted <24h ago")
        elif age_hrs > profile["filters"]["max_age_hours"]:
            reasoning["penalties"].append(f"posted {age_hrs:.0f}h ago (>max)")
            return 0.0, reasoning

    # ----- 8. CTC filter -----
    if job.get("ctc_lpa") and job["ctc_lpa"] < profile["filters"]["min_ctc_lpa"]:
        reasoning["penalties"].append(f"CTC {job['ctc_lpa']} LPA < min")
        return 0.0, reasoning

    # Clamp to 0-10
    score = max(0.0, min(10.0, score))
    return round(score, 1), reasoning


def rank_and_filter(jobs: list[dict], profile: dict) -> list[dict]:
    """Score every job, drop low scorers, return top N sorted by score."""
    scored: list[dict] = []
    min_score = profile["filters"]["min_fit_score"]
    for j in jobs:
        score, reasoning = score_job(j, profile)
        if score < min_score:
            continue
        j["fit_score"] = score
        j["fit_reasoning"] = reasoning
        scored.append(j)
    scored.sort(key=lambda x: x["fit_score"], reverse=True)
    return scored[:profile["digest"]["max_jobs"]]
