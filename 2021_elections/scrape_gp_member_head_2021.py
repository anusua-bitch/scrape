#!/usr/bin/env python3
"""Fast scraper for UP SEC 2021 GP Head/Member candidate tables.

Optimizations implemented:
1) Single-pass UI traversal (post -> district -> block -> gp) without rebuilding state per GP.
2) Batch CSV appends (no full-file re-read/re-write on each GP).
3) Throttled checkpoint writes (`--checkpoint-every`) to reduce disk I/O.
4) Lightweight waits (`--slow-ms`) and quick smoke mode (`--max-gp`).
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

URL = "https://sec.up.nic.in/site/DownloadCandidateFaDebt.aspx"
POST_TYPES = {
    "5": "gram_panchayat_head",
    "6": "gram_panchayat_member",
}

POST_SELECTOR = "#ctl00_ContentPlaceHolder1_ddlPostTypes"
DISTRICT_SELECTOR = "#ctl00_ContentPlaceHolder1_ddlDistrictName"
BLOCK_SELECTOR = "#ctl00_ContentPlaceHolder1_ddlBlockName"
GP_SELECTOR = "#ctl00_ContentPlaceHolder1_ddlGpName"
VIEW_BUTTON_SELECTOR = "#ctl00_ContentPlaceHolder1_btnSubmit"
TABLE_SELECTOR = "#ctl00_ContentPlaceHolder1_GridView1"

META_COLUMNS = ["post_type_id", "post_type", "district", "block", "gram_panchayat", "source_url"]


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

    def key(self) -> Tuple[str, str, str, str]:
        return (self.post_value, self.district_value, self.block_value, self.gp_value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape GP member/head candidates from SEC UP (optimized)")
    parser.add_argument("--output-dir", default="2021_elections/output", help="Directory for CSV/checkpoint files")
    parser.add_argument("--headless", action="store_true", default=False, help="Run browser headless")
    parser.add_argument("--resume", action="store_true", help="Resume from scrape_progress.json")
    parser.add_argument("--max-gp", type=int, default=0, help="Optional cap: scrape at most N GPs")
    parser.add_argument("--slow-ms", type=int, default=120, help="Delay between UI interactions in ms")
    parser.add_argument("--checkpoint-every", type=int, default=25, help="Write checkpoint every N GP combos")
    return parser.parse_args()


def text(s: Optional[str]) -> str:
    return (s or "").strip()


def read_progress(path: Path) -> Dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_progress(path: Path, payload: Dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def should_skip(combo: Combo, progress: Dict) -> bool:
    last = progress.get("last_combo")
    if not last:
        return False
    last_key = (
        last.get("post_value"),
        last.get("district_value"),
        last.get("block_value"),
        last.get("gp_value"),
    )
    return combo.key() <= last_key


def get_options(page, selector: str) -> List[Dict[str, str]]:
    if page.locator(selector).count() == 0:
        return []
    raw = page.eval_on_selector_all(
        f"{selector} option",
        """els => els.map(e => ({value: e.value, label: (e.textContent || '').trim()}))""",
    )
    out = []
    for opt in raw:
        value = text(opt.get("value"))
        label = text(opt.get("label"))
        if value in {"", "-1", "0"}:
            continue
        if "चुनें" in label or "select" in label.lower():
            continue
        out.append({"value": value, "label": label})
    return out


def wait_for_options(page, selector: str, timeout_ms: int = 12000) -> List[Dict[str, str]]:
    started = time.time()
    while (time.time() - started) * 1000 < timeout_ms:
        opts = get_options(page, selector)
        if opts:
            return opts
        page.wait_for_timeout(200)
    return []


def select_and_wait(page, selector: str, value: str, slow_ms: int) -> None:
    page.select_option(selector, value=value)
    if slow_ms > 0:
        page.wait_for_timeout(slow_ms)




def wait_for_table_rows(page, timeout_ms: int = 8000) -> None:
    started = time.time()
    while (time.time() - started) * 1000 < timeout_ms:
        if page.locator(TABLE_SELECTOR).count() and page.locator(f"{TABLE_SELECTOR} tr").count() > 1:
            return
        page.wait_for_timeout(150)


def fetch_grid_rows(page) -> List[Dict[str, str]]:
    if page.locator(TABLE_SELECTOR).count() == 0:
        return []

    row_count = page.locator(f"{TABLE_SELECTOR} tr").count()
    if row_count <= 1:
        return []

    headers = page.eval_on_selector_all(
        f"{TABLE_SELECTOR} tr:first-child th",
        "els => els.map(e => (e.textContent || '').trim())",
    )
    if not headers:
        headers = page.eval_on_selector_all(
            f"{TABLE_SELECTOR} tr:first-child td",
            "els => els.map(e => (e.textContent || '').trim())",
        )

    rows: List[Dict[str, str]] = []
    for i in range(1, row_count):
        cells = page.eval_on_selector_all(
            f"{TABLE_SELECTOR} tr:nth-child({i+1}) td",
            "els => els.map(e => (e.textContent || '').trim())",
        )
        if not any(cells):
            continue

        if headers and len(headers) == len(cells):
            row = {headers[j]: cells[j] for j in range(len(cells))}
        else:
            row = {f"col_{j+1}": cells[j] for j in range(len(cells))}
        rows.append(row)
    return rows


class CSVBatchWriter:
    """Append-only CSV writer with fixed schema for speed."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = None
        self.writer = None
        self.fieldnames: List[str] = []

    def _open(self) -> None:
        file_exists = self.path.exists() and self.path.stat().st_size > 0
        self.file = self.path.open("a", encoding="utf-8-sig", newline="")

        if file_exists:
            with self.path.open("r", encoding="utf-8-sig", newline="") as rf:
                reader = csv.reader(rf)
                self.fieldnames = next(reader, [])
        self.writer = None

    def _ensure_writer(self, sample_row: Dict[str, str]) -> None:
        if self.file is None:
            self._open()
        if self.writer is not None:
            return

        if not self.fieldnames:
            dynamic = sorted(k for k in sample_row.keys() if k not in META_COLUMNS)
            self.fieldnames = META_COLUMNS + dynamic + ["extra_json"]
            self.writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)
            self.writer.writeheader()
        else:
            self.writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)

    def write_rows(self, rows: List[Dict[str, str]]) -> None:
        if not rows:
            return
        self._ensure_writer(rows[0])

        for row in rows:
            unknown = {k: v for k, v in row.items() if k not in self.fieldnames}
            normalized = {k: row.get(k, "") for k in self.fieldnames}
            if "extra_json" in self.fieldnames:
                normalized["extra_json"] = json.dumps(unknown, ensure_ascii=False) if unknown else ""
            self.writer.writerow(normalized)

    def flush(self) -> None:
        if self.file:
            self.file.flush()

    def close(self) -> None:
        if self.file:
            self.file.flush()
            self.file.close()
            self.file = None


def scrape(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    progress_path = output_dir / "scrape_progress.json"
    combined_path = output_dir / "gp_member_head_candidates_2021.csv"
    member_path = output_dir / "gp_member_candidates_2021.csv"
    head_path = output_dir / "gp_head_candidates_2021.csv"

    progress = read_progress(progress_path) if args.resume else {}

    combined_writer = CSVBatchWriter(combined_path)
    member_writer = CSVBatchWriter(member_path)
    head_writer = CSVBatchWriter(head_path)

    processed = 0
    skipped = 0
    start_ts = time.time()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(max(args.slow_ms, 50))

        for post_value, post_label in POST_TYPES.items():
            select_and_wait(page, POST_SELECTOR, post_value, args.slow_ms)
            districts = wait_for_options(page, DISTRICT_SELECTOR)

            for district in districts:
                select_and_wait(page, DISTRICT_SELECTOR, district["value"], args.slow_ms)
                blocks = wait_for_options(page, BLOCK_SELECTOR)

                for block in blocks:
                    select_and_wait(page, BLOCK_SELECTOR, block["value"], args.slow_ms)
                    gps = wait_for_options(page, GP_SELECTOR)

                    for gp in gps:
                        combo = Combo(
                            post_value=post_value,
                            post_label=post_label,
                            district_value=district["value"],
                            district_label=district["label"],
                            block_value=block["value"],
                            block_label=block["label"],
                            gp_value=gp["value"],
                            gp_label=gp["label"],
                        )

                        if args.resume and should_skip(combo, progress):
                            skipped += 1
                            continue

                        select_and_wait(page, GP_SELECTOR, gp["value"], max(60, args.slow_ms // 2))

                        try:
                            page.click(VIEW_BUTTON_SELECTOR, timeout=10_000)
                            wait_for_table_rows(page, timeout_ms=9000)
                        except PlaywrightTimeoutError:
                            print(f"[WARN] View click timeout at {combo}")
                            continue

                        raw_rows = fetch_grid_rows(page)
                        enriched_rows: List[Dict[str, str]] = []
                        for row in raw_rows:
                            row_out = dict(row)
                            row_out.update(
                                {
                                    "post_type_id": combo.post_value,
                                    "post_type": combo.post_label,
                                    "district": combo.district_label,
                                    "block": combo.block_label,
                                    "gram_panchayat": combo.gp_label,
                                    "source_url": URL,
                                }
                            )
                            enriched_rows.append(row_out)

                        if enriched_rows:
                            combined_writer.write_rows(enriched_rows)
                            if combo.post_value == "6":
                                member_writer.write_rows(enriched_rows)
                            else:
                                head_writer.write_rows(enriched_rows)

                        processed += 1

                        if processed % args.checkpoint_every == 0:
                            progress = {
                                "updated_at_unix": int(time.time()),
                                "scraped_gp_count": processed,
                                "skipped_due_resume": skipped,
                                "last_combo": asdict(combo),
                                "elapsed_seconds": int(time.time() - start_ts),
                            }
                            write_progress(progress_path, progress)
                            combined_writer.flush()
                            member_writer.flush()
                            head_writer.flush()

                        if processed % 50 == 0:
                            elapsed = max(1, int(time.time() - start_ts))
                            rate = processed / elapsed
                            print(f"[INFO] processed={processed} skipped={skipped} rate={rate:.2f} gp/sec")

                        print(
                            f"[OK] {combo.post_label} | {combo.district_label} | {combo.block_label} | {combo.gp_label} -> {len(enriched_rows)} rows"
                        )

                        if args.max_gp and processed >= args.max_gp:
                            progress = {
                                "updated_at_unix": int(time.time()),
                                "scraped_gp_count": processed,
                                "skipped_due_resume": skipped,
                                "last_combo": asdict(combo),
                                "elapsed_seconds": int(time.time() - start_ts),
                            }
                            write_progress(progress_path, progress)
                            combined_writer.flush()
                            member_writer.flush()
                            head_writer.flush()
                            print(f"[STOP] Reached --max-gp={args.max_gp}")
                            context.close()
                            browser.close()
                            combined_writer.close()
                            member_writer.close()
                            head_writer.close()
                            return

        context.close()
        browser.close()

    progress = {
        "updated_at_unix": int(time.time()),
        "scraped_gp_count": processed,
        "skipped_due_resume": skipped,
        "elapsed_seconds": int(time.time() - start_ts),
    }
    write_progress(progress_path, progress)
    combined_writer.close()
    member_writer.close()
    head_writer.close()

    print(f"Done. Processed GP combinations: {processed}")
    print(f"Skipped (resume): {skipped}")
    print(f"Combined CSV: {combined_path}")


if __name__ == "__main__":
    scrape(parse_args())
