"""
Resume tailoring — two modes:
  FREE: produce a ready-to-paste prompt for claude.ai
  API:  call the Anthropic API and produce a tailored resume directly
"""
from __future__ import annotations
import json
import os
import logging
from pathlib import Path

log = logging.getLogger("tailor")


def build_tailoring_prompt(job: dict, base_resume: dict) -> str:
    """Returns a markdown prompt ready to paste into claude.ai."""
    return f"""You are helping me tailor my resume for a specific job. I'm {base_resume['name']}, a final-year BTech CS student at Thapar University with a Business Analyst internship at Stellent.ai and a prior Data & Research Analyst internship at Mosaic Digital (Hindustan Times).

I'm applying to **{job['company']}** for the role of **{job['title']}**.

Job description below. My base resume (as structured data) is below that.

Do this:
1. Extract the top 10 keywords/skills the ATS would scan for in this JD.
2. List which of those are MISSING in my base resume but I can honestly claim from my projects/internships (if any).
3. Rewrite my Experience and Projects bullets so that:
   - Every relevant JD keyword I can honestly claim is woven in
   - Bullets remain truthful — no inventing skills or fabricating metrics
   - Each bullet leads with an action verb and includes a quantified outcome where possible
   - Tone stays professional
4. Suggest a 2-line tailored Summary at the top.
5. Flag any sections to de-emphasize or remove for this specific role.

Then output the FINAL tailored resume in clean markdown so I can copy it into Google Docs.

=== JOB DESCRIPTION ===
**Company:** {job['company']}
**Title:** {job['title']}
**Location:** {job.get('location', 'N/A')}
**URL:** {job['url']}

{job['description'][:4000]}

=== BASE RESUME ===
```json
{json.dumps(base_resume, indent=2)}
```

Return as:
- KEYWORDS FOUND
- KEYWORDS MISSING (and which I can honestly claim)
- TAILORED SUMMARY
- TAILORED RESUME (full markdown, ready to paste)
- SECTIONS TO REMOVE/DEEMPHASIZE
"""


def tailor_via_api(job: dict, base_resume: dict, api_key: str) -> str | None:
    """Calls Anthropic API to generate a tailored resume directly.
    Returns the tailored resume markdown, or None on failure."""
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        log.error("anthropic package not installed — pip install anthropic")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_tailoring_prompt(job, base_resume)

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        log.error(f"API call failed for {job['company']}: {e}")
        return None


def render_resume_pdf(markdown_text: str, out_path: Path) -> bool:
    """Render the tailored markdown resume to a PDF using reportlab.
    Returns True on success."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib import colors
    except ImportError:
        log.error("reportlab not installed")
        return False

    doc = SimpleDocTemplate(
        str(out_path), pagesize=letter,
        leftMargin=0.45 * inch, rightMargin=0.45 * inch,
        topMargin=0.3 * inch, bottomMargin=0.25 * inch,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Normal"], fontName="Times-Bold",
                        fontSize=20, alignment=TA_CENTER, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Normal"], fontName="Times-Bold",
                        fontSize=12, alignment=TA_LEFT, spaceBefore=5, spaceAfter=2)
    body = ParagraphStyle("body", parent=styles["Normal"], fontName="Times-Roman",
                          fontSize=10.5, leading=13)

    story = []
    for line in markdown_text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 3))
            continue
        if line.startswith("# "):
            story.append(Paragraph(line[2:], h1))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], h2))
            story.append(HRFlowable(width="100%", thickness=0.5,
                                     color=colors.black, spaceAfter=3))
        elif line.startswith(("- ", "* ", "• ")):
            story.append(Paragraph(f"• {line[2:]}", body))
        else:
            story.append(Paragraph(line, body))

    try:
        doc.build(story)
        return True
    except Exception as e:
        log.error(f"PDF render failed: {e}")
        return False
