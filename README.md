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

```bash
python 2021_elections/scrape_gp_member_head_2021.py --headless --resume
```

### 7) Where to find output

Check:

- `2021_elections/output/gp_member_head_candidates_2021.csv`
- `2021_elections/output/gp_member_candidates_2021.csv`
- `2021_elections/output/gp_head_candidates_2021.csv`

---

## Ready-to-use Colab notebook

If you want a direct copy-paste notebook, use:

- `notebooks/UP_GP_Scraper_Colab.ipynb`

Open it in Colab and run cells top-to-bottom.

---

## Beginner guide: continue in Google Colab

> Colab sessions are temporary. Save outputs to Google Drive so progress is not lost.

### 1) Open Colab and mount Drive

In a new notebook cell:

```python
from google.colab import drive
drive.mount('/content/drive')
```

### 2) Clone repo into Drive (persistent)

```bash
%cd /content/drive/MyDrive
!git clone <YOUR_REPO_URL> scrape
%cd /content/drive/MyDrive/scrape
```

If repo already exists:

```bash
%cd /content/drive/MyDrive/scrape
!git pull
```

### 3) Install dependencies in Colab

```bash
!pip install -r requirements.txt
!playwright install chromium
!playwright install-deps chromium
```

### 4) Run a smoke test

```bash
!python 2021_elections/scrape_gp_member_head_2021.py --headless --max-gp 5 --output-dir /content/drive/MyDrive/scrape/2021_elections/output
```

### 5) Run/continue full scrape

```bash
!python 2021_elections/scrape_gp_member_head_2021.py --headless --resume --output-dir /content/drive/MyDrive/scrape/2021_elections/output
```

Because output/checkpoint are in Drive, you can safely rerun this later and it will continue.

### 6) Download the final CSV

```python
from google.colab import files
files.download('/content/drive/MyDrive/scrape/2021_elections/output/gp_member_head_candidates_2021.csv')
```

---

## Useful tips

- Use `--resume` for long runs.
- Keep `--headless` on for server/Colab runs.
- Start with `--max-gp 5` or `--max-gp 20` to verify setup.
- If the website is temporarily slow/unavailable, just rerun with `--resume`.

## Quick command summary

```bash
# Smoke test
python 2021_elections/scrape_gp_member_head_2021.py --headless --max-gp 5

# Full run with resume
python 2021_elections/scrape_gp_member_head_2021.py --headless --resume
```


## Speed optimization tips (for very large runs)

Use these flags to improve throughput:

- `--slow-ms 80` (or 100/120 depending on stability)
- `--checkpoint-every 50` (reduce disk writes)
- `--resume` (safe restart after disconnects)

Example high-throughput run:

```bash
python 2021_elections/scrape_gp_member_head_2021.py --headless --resume --slow-ms 100 --checkpoint-every 50
```

If you see missed selections/timeouts, increase `--slow-ms` gradually (100 -> 140 -> 180).

