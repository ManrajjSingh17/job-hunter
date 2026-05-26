"""
Daily entrypoint. Runs the full pipeline:
  fetch → score → tailor → email → log seen jobs (to dedupe across days)
"""
from __future__ import annotations
import os
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
import yaml

# Allow running both as `python -m src.run` and `python src/run.py`
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fetchers import fetch_all_jobs
from src.scorer import rank_and_filter
from src.tailor import build_tailoring_prompt, tailor_via_api, render_resume_pdf
from src.emailer import build_html_digest, send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("run")

ROOT = Path(__file__).resolve().parent.parent
SEEN_PATH = ROOT / "seen_jobs.json"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)


def load_seen() -> set[str]:
    if SEEN_PATH.exists():
        try:
            return set(json.loads(SEEN_PATH.read_text()))
        except Exception:
            return set()
    return set()


def save_seen(seen: set[str]) -> None:
    SEEN_PATH.write_text(json.dumps(sorted(list(seen)[-2000:])))   # keep last 2000


def main() -> int:
    profile = yaml.safe_load((ROOT / "config" / "profile.yaml").read_text())
    base_resume = json.loads((ROOT / "config" / "base_resume.json").read_text())
    mode = profile.get("mode", "free")

    log.info(f"Starting daily run · mode={mode}")

    # 1. Fetch
    jobs = fetch_all_jobs(profile)
    if not jobs:
        log.warning("No jobs fetched from any source")
        if profile["digest"]["send_if_zero"]:
            send_email("<p>No jobs fetched today — sources may be down.</p>",
                       "🎯 Job digest — 0 matches", profile["email"])
        return 0

    # 2. Dedupe vs. previously seen
    seen = load_seen()
    new_jobs = [j for j in jobs if j["id"] not in seen]
    log.info(f"{len(new_jobs)} new (of {len(jobs)} fetched)")

    # 3. Score and filter
    top_jobs = rank_and_filter(new_jobs, profile)
    log.info(f"{len(top_jobs)} jobs cleared scoring threshold")

    if not top_jobs and not profile["digest"]["send_if_zero"]:
        log.info("No high-fit jobs — skipping email")
        # Still mark fetched jobs as seen so we don't re-rank tomorrow
        seen.update(j["id"] for j in jobs)
        save_seen(seen)
        return 0

    # 4. Tailor
    attachments: list[Path] = []
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    for j in top_jobs:
        if mode == "free":
            j["tailoring_prompt"] = build_tailoring_prompt(j, base_resume)
        elif mode == "api" and api_key:
            md = tailor_via_api(j, base_resume, api_key)
            if md:
                # write PDF
                safe_co = "".join(c for c in j["company"] if c.isalnum())[:20]
                pdf_path = OUT_DIR / f"Resume_{safe_co}_{j['id'][-8:]}.pdf"
                if render_resume_pdf(md, pdf_path):
                    attachments.append(pdf_path)
                    j["resume_attached"] = True
            # Still embed prompt as fallback
            j["tailoring_prompt"] = build_tailoring_prompt(j, base_resume)

    # 5. Email
    strong = sum(1 for j in top_jobs if j["fit_score"] >= 7)
    subject = f"🎯 {len(top_jobs)} jobs for you today ({strong} strong)"
    html = build_html_digest(top_jobs, profile, mode)
    send_email(html, subject, profile["email"], attachments=attachments)

    # 6. Mark all fetched as seen
    seen.update(j["id"] for j in jobs)
    save_seen(seen)
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
