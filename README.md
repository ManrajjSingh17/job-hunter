# Manraj's Job Hunter Bot

Daily automated job discovery + resume tailoring for fresher SDE/Data/BA/APM roles in India.

## What it does

Every morning at 7am IST (Mon–Sat):

1. **Pulls** new job postings from 6 free sources (Adzuna, RemoteOK, Greenhouse, Lever, Ashby, YC)
2. **Filters** for India + fresher (0–1 yr) + your role tracks
3. **Scores** each job 1–10 based on skill match, company tier, freshness
4. **Tailors** a resume prompt per matched job (free mode) OR auto-generates a PDF resume (API mode)
5. **Emails** you a digest at manrajkhatter@gmail.com with apply links + everything ready

You spend 40–50 min applying. The bot does everything else.

---

## Setup (one-time, ~30–45 minutes)

### Step 1 — Fork this repo to your GitHub

1. Go to GitHub.com, click the **+** in the top right → **New repository**
2. Name: `job-hunter` · Set to **Private** · click **Create repository**
3. Clone or upload these files to it. (Easiest: download this repo as a zip, then drag-drop into GitHub's web uploader.)

### Step 2 — Get an Adzuna API key (free, 2 min)

1. Visit https://developer.adzuna.com/signup
2. Sign up with your email
3. After verification, go to **Dashboard** → copy your **Application ID** and **Application Key**
4. Save them somewhere safe — you'll need them in Step 4

### Step 3 — Set up a Gmail App Password (5 min)

This lets the bot send email **as you** without exposing your real Gmail password.

1. Go to https://myaccount.google.com/security
2. Make sure **2-Step Verification** is ON (required). If not, enable it first.
3. Visit https://myaccount.google.com/apppasswords
4. Pick **App: Mail** · **Device: Other** → name it `JobBot` → click **Generate**
5. **Copy the 16-character password** (looks like `abcd efgh ijkl mnop` — copy without spaces)

### Step 4 — Add secrets to your GitHub repo

1. In your forked repo, go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** and add these one by one:

| Secret name           | Value                                            |
|-----------------------|--------------------------------------------------|
| `ADZUNA_APP_ID`       | From Step 2                                      |
| `ADZUNA_APP_KEY`      | From Step 2                                      |
| `GMAIL_USER`          | `manrajkhatter@gmail.com`                        |
| `GMAIL_APP_PASSWORD`  | The 16-char password from Step 3 (no spaces)     |
| `ANTHROPIC_API_KEY`   | Leave blank for now — add in Phase 2             |

### Step 5 — Enable GitHub Actions

1. In your repo, click the **Actions** tab
2. If prompted, click **I understand, enable workflows**
3. Click the **Daily Job Digest** workflow on the left → **Run workflow** → green button → **Run workflow**
4. Wait ~3 minutes — it'll fetch jobs and email you the first digest

### Step 6 — Set up Gmail filter to auto-label (2 min)

So the daily digest doesn't clutter your inbox:

1. Open Gmail → search bar → click ▼ (advanced search)
2. In the **Has the words** field, paste: `from:manrajkhatter@gmail.com X-Job-Bot`
3. Click **Create filter** at the bottom
4. Tick:
   - ✅ **Skip the Inbox (Archive it)**
   - ✅ **Apply the label** → click **Choose label** → **New label** → name it `JobBot` → Create
   - ✅ **Mark as important** (optional but recommended)
5. Click **Create filter**

Now every digest lands directly under the `JobBot` label, never touching your main inbox.

### Step 7 — Done!

Your bot runs automatically Mon–Sat at 7am IST. Open Gmail → click `JobBot` label → see today's digest.

---

## Phase 2 — Upgrade to API mode (after 2 weeks)

Once you're consistently using the free mode and want the system to auto-generate tailored PDFs instead of you copy-pasting prompts:

1. Go to https://console.anthropic.com
2. Sign up · add ₹500 credit (lasts ~1 month at your volume)
3. **Settings → API Keys → Create Key**, copy it
4. In your repo: **Settings → Secrets → ANTHROPIC_API_KEY** → paste the key
5. Edit `config/profile.yaml` → change `mode: "free"` to `mode: "api"`
6. Commit. Next morning, your digest will include PDF resume attachments per job.

---

## Customizing what the bot finds

Open `config/profile.yaml` in your repo. You can edit:

- **Role tracks** — enable/disable SDE, Data, BA, APM
- **Skills list** — add anything you learn (boosts fit score on relevant jobs)
- **Target companies** — add S/A/B tier companies for score boosts
- **Filters** — min CTC, max experience years, max job age, locations
- **Digest size** — `max_jobs` controls cap per email (default: 15)

Edit, commit. Next run uses the new config.

---

## Running locally (optional, for testing)

```bash
pip install -r requirements.txt

export ADZUNA_APP_ID=your_id
export ADZUNA_APP_KEY=your_key
export GMAIL_USER=manrajkhatter@gmail.com
export GMAIL_APP_PASSWORD=your_app_password

python src/run.py
```

---

## Troubleshooting

**No email arrived after 5 minutes**
- Check **Actions** tab in repo for any red ❌ runs
- Click the failed run → expand "Run digest" step → look for the error
- Most common: wrong Gmail app password (regenerate at Step 3)

**Email arrived but says "0 jobs"**
- Normal on weekends or holidays
- If it happens 3 days in a row weekday: loosen filters in `profile.yaml` (lower `min_fit_score`, raise `max_age_hours`)

**Want to test without waiting for 7am**
- Go to **Actions → Daily Job Digest → Run workflow** anytime

---

## What the bot will NOT do (by design)

- ❌ Apply to jobs for you (gets you banned from ATS systems)
- ❌ Auto-message recruiters on LinkedIn (violates ToS)
- ❌ Scrape LinkedIn (will get your account flagged)
- ❌ Submit duplicate applications (deduped via `seen_jobs.json`)

You stay in control of every application that goes out.
