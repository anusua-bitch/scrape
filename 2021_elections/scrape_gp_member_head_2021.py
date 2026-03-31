#!/usr/bin/env python3
"""Scrape UP SEC 2021 Gram Panchayat Member/Head candidate details.

Target page:
https://sec.up.nic.in/site/DownloadCandidateFaDebt.aspx

This script uses Playwright because the form is dynamic (ASP.NET postbacks).
It iterates post type -> district -> block -> gram panchayat and clicks View.

Outputs (in --output-dir):
- gp_member_head_candidates_2021.csv (combined)
- gp_member_candidates_2021.csv
- gp_head_candidates_2021.csv
- scrape_progress.json (checkpoint for resume)
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

URL = "https://sec.up.nic.in/site/DownloadCandidateFaDebt.aspx"
POST_TYPES = {
    "5": "gram_panchayat_head",
    "6": "gram_panchayat_member",
}


@dataclass
class Combo:
    post_value: str
    post_label: str
    district_value: str
    district_label: str
    block_value: str
    block_label: str
    gp_value: str
    gp_label: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape GP member/head candidates from SEC UP")
    parser.add_argument("--output-dir", default="2021_elections/output", help="Directory for CSV/checkpoint files")
    parser.add_argument("--headless", action="store_true", default=False, help="Run browser in headless mode")
    parser.add_argument("--resume", action="store_true", help="Resume from scrape_progress.json if present")
    parser.add_argument("--max-gp", type=int, default=0, help="Optional cap: scrape at most N gram panchayats (for smoke test)")
    parser.add_argument("--slow-ms", type=int, default=250, help="Pause between interactions in milliseconds")
    return parser.parse_args()


def text(s: Optional[str]) -> str:
    return (s or "").strip()


def safe_filename(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


def read_progress(path: Path) -> Dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_progress(path: Path, payload: Dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_options(page, selector: str) -> List[Dict[str, str]]:
    if page.locator(selector).count() == 0:
        return []
    opts = page.eval_on_selector_all(
        f"{selector} option",
        """els => els.map(e => ({value: e.value, label: (e.textContent || '').trim()}))""",
    )
    cleaned = []
    for opt in opts:
        value = text(opt.get("value"))
        label = text(opt.get("label"))
        if value in {"", "-1", "0"}:
            continue
        if "चुनें" in label or "select" in label.lower():
            continue
        cleaned.append({"value": value, "label": label})
    return cleaned


def select_and_wait(page, selector: str, value: str, sleep_ms: int) -> None:
    page.select_option(selector, value=value)
    page.wait_for_timeout(sleep_ms)


def wait_for_non_default_options(page, selector: str, timeout_ms: int = 10000) -> List[Dict[str, str]]:
    started = time.time()
    while (time.time() - started) * 1000 < timeout_ms:
        opts = get_options(page, selector)
        if opts:
            return opts
        page.wait_for_timeout(250)
    return []


def fetch_grid_rows(page) -> List[Dict[str, str]]:
    table_sel = "#ctl00_ContentPlaceHolder1_GridView1"
    if page.locator(table_sel).count() == 0:
        return []

    rows_count = page.locator(f"{table_sel} tr").count()
    if rows_count <= 1:
        return []

    headers = page.eval_on_selector_all(
        f"{table_sel} tr:first-child th",
        "els => els.map(e => (e.textContent || '').trim())",
    )
    if not headers:
        headers = page.eval_on_selector_all(
            f"{table_sel} tr:first-child td",
            "els => els.map(e => (e.textContent || '').trim())",
        )

    data_rows = []
    for r in range(1, rows_count):
        cells = page.eval_on_selector_all(
            f"{table_sel} tr:nth-child({r+1}) td",
            "els => els.map(e => (e.textContent || '').trim())",
        )
        if not any(cells):
            continue
        if headers and len(headers) == len(cells):
            row = {headers[i]: cells[i] for i in range(len(cells))}
        else:
            row = {f"col_{i+1}": cells[i] for i in range(len(cells))}
        data_rows.append(row)
    return data_rows


def iter_all_combinations(page, slow_ms: int):
    district_sel = "#ctl00_ContentPlaceHolder1_ddlDistrictName"
    block_sel = "#ctl00_ContentPlaceHolder1_ddlBlockName"
    gp_sel = "#ctl00_ContentPlaceHolder1_ddlGpName"

    for post_value, post_label in POST_TYPES.items():
        select_and_wait(page, "#ctl00_ContentPlaceHolder1_ddlPostTypes", post_value, slow_ms)

        districts = wait_for_non_default_options(page, district_sel)
        for district in districts:
            select_and_wait(page, "#ctl00_ContentPlaceHolder1_ddlPostTypes", post_value, slow_ms)
            select_and_wait(page, district_sel, district["value"], slow_ms)

            blocks = wait_for_non_default_options(page, block_sel)
            for block in blocks:
                select_and_wait(page, "#ctl00_ContentPlaceHolder1_ddlPostTypes", post_value, slow_ms)
                select_and_wait(page, district_sel, district["value"], slow_ms)
                select_and_wait(page, block_sel, block["value"], slow_ms)

                gps = wait_for_non_default_options(page, gp_sel)
                for gp in gps:
                    yield Combo(
                        post_value=post_value,
                        post_label=post_label,
                        district_value=district["value"],
                        district_label=district["label"],
                        block_value=block["value"],
                        block_label=block["label"],
                        gp_value=gp["value"],
                        gp_label=gp["label"],
                    )


def should_skip(combo: Combo, progress: Dict) -> bool:
    last = progress.get("last_combo")
    if not last:
        return False

    key = (
        combo.post_value,
        combo.district_value,
        combo.block_value,
        combo.gp_value,
    )
    last_key = (
        last.get("post_value"),
        last.get("district_value"),
        last.get("block_value"),
        last.get("gp_value"),
    )
    return key <= last_key


def append_rows(csv_path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        return
    fieldnames = sorted({k for row in rows for k in row.keys()})

    # If file exists, preserve existing schema by unioning header.
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as rf:
            reader = csv.reader(rf)
            existing = next(reader, [])
        fieldnames = sorted(set(fieldnames).union(existing))

        # Re-write existing data to accommodate new columns if needed.
        with csv_path.open("r", encoding="utf-8-sig", newline="") as rf:
            existing_rows = list(csv.DictReader(rf))
        merged_rows = existing_rows + rows
        deduped = []
        seen = set()
        for row in merged_rows:
            key = tuple(row.get(k, "") for k in fieldnames)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)

        with csv_path.open("w", encoding="utf-8-sig", newline="") as wf:
            writer = csv.DictWriter(wf, fieldnames=fieldnames)
            writer.writeheader()
            for row in deduped:
                writer.writerow(row)
    else:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def scrape(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    progress_path = output_dir / "scrape_progress.json"
    combined_csv = output_dir / "gp_member_head_candidates_2021.csv"
    member_csv = output_dir / "gp_member_candidates_2021.csv"
    head_csv = output_dir / "gp_head_candidates_2021.csv"

    progress = read_progress(progress_path) if args.resume else {}

    scraped_gp_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(args.slow_ms)

        for combo in iter_all_combinations(page, args.slow_ms):
            if args.resume and should_skip(combo, progress):
                continue

            # Rebuild full form state for reliability on ASP.NET postback pages.
            select_and_wait(page, "#ctl00_ContentPlaceHolder1_ddlPostTypes", combo.post_value, args.slow_ms)
            select_and_wait(page, "#ctl00_ContentPlaceHolder1_ddlDistrictName", combo.district_value, args.slow_ms)
            select_and_wait(page, "#ctl00_ContentPlaceHolder1_ddlBlockName", combo.block_value, args.slow_ms)
            select_and_wait(page, "#ctl00_ContentPlaceHolder1_ddlGpName", combo.gp_value, args.slow_ms)

            try:
                page.click("#ctl00_ContentPlaceHolder1_btnSubmit", timeout=15_000)
                page.wait_for_timeout(args.slow_ms + 300)
            except PlaywrightTimeoutError:
                print(f"[WARN] View button timeout at {combo}")
                continue

            table_rows = fetch_grid_rows(page)
            enriched = []
            for row in table_rows:
                row2 = dict(row)
                row2.update(
                    {
                        "post_type_id": combo.post_value,
                        "post_type": combo.post_label,
                        "district": combo.district_label,
                        "block": combo.block_label,
                        "gram_panchayat": combo.gp_label,
                        "source_url": URL,
                    }
                )
                enriched.append(row2)

            if enriched:
                append_rows(combined_csv, enriched)
                if combo.post_value == "6":
                    append_rows(member_csv, enriched)
                elif combo.post_value == "5":
                    append_rows(head_csv, enriched)

            scraped_gp_count += 1
            progress = {
                "updated_at_unix": int(time.time()),
                "scraped_gp_count": scraped_gp_count,
                "last_combo": combo.__dict__,
            }
            write_progress(progress_path, progress)

            print(
                f"[OK] {combo.post_label} | {combo.district_label} | {combo.block_label} | {combo.gp_label} -> {len(enriched)} rows"
            )

            if args.max_gp and scraped_gp_count >= args.max_gp:
                print(f"[STOP] Reached --max-gp={args.max_gp}")
                break

        context.close()
        browser.close()

    print(f"Done. Processed GP combinations: {scraped_gp_count}")
    print(f"Combined CSV: {combined_csv}")


if __name__ == "__main__":
    scrape(parse_args())
