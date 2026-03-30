"""Fetch a lightweight latest snapshot from the UP SEC candidate download page.

This script avoids Selenium and captures currently available post types from the
same endpoint used by the original scrapers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import urlopen

URL = "https://sec.up.nic.in/site/DownloadCandidateFaDebt.aspx"
OUTPUT_PATH = Path("latest_snapshot.json")


class PostTypeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_target_select = False
        self.in_option = False
        self.current_option_value = ""
        self.current_option_text_parts: list[str] = []
        self.options: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)

        if tag == "select" and attrs_dict.get("id") == "ctl00_ContentPlaceHolder1_ddlPostTypes":
            self.in_target_select = True
        elif self.in_target_select and tag == "option":
            self.in_option = True
            self.current_option_value = attrs_dict.get("value", "") or ""
            self.current_option_text_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self.in_target_select:
            self.in_target_select = False
        elif tag == "option" and self.in_option:
            option_text = "".join(self.current_option_text_parts).strip()
            if option_text:
                self.options.append(
                    {
                        "value": self.current_option_value,
                        "label": option_text,
                    }
                )
            self.in_option = False
            self.current_option_value = ""
            self.current_option_text_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_option:
            self.current_option_text_parts.append(data)


def fetch_snapshot() -> dict[str, object]:
    with urlopen(URL, timeout=60) as response:  # nosec B310 - fixed trusted endpoint
        html = response.read().decode("utf-8", errors="ignore")

    parser = PostTypeParser()
    parser.feed(html)

    return {
        "source_url": URL,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "post_types": parser.options,
        "post_type_count": len(parser.options),
    }


def main() -> None:
    snapshot = fetch_snapshot()
    OUTPUT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} with {snapshot['post_type_count']} post types")


if __name__ == "__main__":
    main()
