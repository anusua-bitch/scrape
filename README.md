# Uttar Pradesh Panchayat Candidates Dataset - 2015, 2021

Code for creation of dataset of Panchayat candidates (village level) in the Indian state of Uttar Pradesh during the 2015 and 2021 elections.

> Note: The previous Google Sheet link is no longer available (returns HTTP 410 as of March 30, 2026).

## Getting updated source metadata

You can now pull a lightweight freshness snapshot directly from the official SEC UP candidate endpoint:

```bash
python update_data_snapshot.py
```

This writes `latest_snapshot.json` with:
- fetch timestamp (UTC)
- source URL
- currently listed post types on the official page

The Selenium scraping scripts in `2015_elections/` and `2021_elections/` have also been updated to use `https://sec.up.nic.in/...` URLs.

## List of Variables

<img width="500" alt="Screenshot 2022-01-24 at 10 01 28 PM" src="https://user-images.githubusercontent.com/16442168/150903096-99dc3a29-28a7-4404-9ea8-ccf84801d08a.png">

## 2021 Gram Panchayat Member + Head (full UP) scraper

Scraper script:

- `2021_elections/scrape_gp_member_head_2021.py`

This scraper is built for the dynamic ASP.NET page:

- `https://sec.up.nic.in/site/DownloadCandidateFaDebt.aspx`

It targets only the two Gram Panchayat-level post types:
A new Playwright-based scraper is available at:

- `2021_elections/scrape_gp_member_head_2021.py`

It targets only the two GP-level post types from `DownloadCandidateFaDebt.aspx`:

- `5` → Gram Panchayat Head (`ग्राम पंचायत प्रधान`)
- `6` → Gram Panchayat Member (`ग्राम पंचायत सदस्य`)

The script loops:

`post type -> district -> block -> gram panchayat -> View button -> result grid`

It also supports:

- checkpoint resume (`--resume`)
- optional limit for testing (`--max-gp`)

Outputs are saved to `2021_elections/output/`:

- `gp_member_head_candidates_2021.csv` (combined)
- `gp_member_candidates_2021.csv`
- `gp_head_candidates_2021.csv`
- `scrape_progress.json` (resume checkpoint)

---

## Beginner guide: run on your local computer

### 1) Install Python

- Install Python 3.10+ from https://www.python.org/downloads/
- During installation on Windows, check **"Add Python to PATH"**.

### 2) Download this project

Use one of these methods:

- Download ZIP from GitHub and extract it, OR
- Use Git:

```bash
git clone <YOUR_REPO_URL>
cd scrape
```

### 3) Create and activate a virtual environment (recommended)

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS/Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4) Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

If you get browser-library errors on Linux, run:

```bash
playwright install-deps chromium
```

### 5) Run a small test first (recommended)

```bash
python 2021_elections/scrape_gp_member_head_2021.py --headless --max-gp 5
```

### 6) Run the full scrape
### Setup

```bash
pip install playwright
playwright install chromium
```

### Run

```bash
python 2021_elections/scrape_gp_member_head_2021.py --headless --resume
```

Outputs are written to `2021_elections/output/`:

- `gp_member_head_candidates_2021.csv` (combined)
- `gp_member_candidates_2021.csv`
- `gp_head_candidates_2021.csv`
- `scrape_progress.json` (resume checkpoint)

### Smoke test

```bash
python 2021_elections/scrape_gp_member_head_2021.py --headless --max-gp 5
```
