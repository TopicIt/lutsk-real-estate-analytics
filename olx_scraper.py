from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import OLX_RENT_APARTMENTS_URL, OLX_SALE_APARTMENTS_URL
from database import init_db, save_snapshots_with_counts
from scraper import build_manual_snapshot


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT_SECONDS = 15

OLX_TARGETS = {
    "sale_apartments_all": {
        "url": OLX_SALE_APARTMENTS_URL,
        "deal_type": "sale",
        "property_type": "apartments",
        "rooms": "all",
        "location_scope": "lutsk",
    },
    "rent_apartments_all": {
        "url": OLX_RENT_APARTMENTS_URL,
        "deal_type": "rent",
        "property_type": "apartments",
        "rooms": "all",
        "location_scope": "lutsk",
    },
}


class OlxFetchError(RuntimeError):
    pass


def fetch_olx_page(url: str) -> str:
    if not url:
        raise OlxFetchError("OLX URL is not configured.")

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.7,en;q=0.6",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status_code = getattr(response, "status", response.getcode())
            if status_code != 200:
                raise OlxFetchError(f"OLX returned HTTP {status_code}.")
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore")
    except urllib.error.HTTPError as exc:
        raise OlxFetchError(f"OLX returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise OlxFetchError(f"Could not fetch OLX page: {exc}") from exc


def _clean_count(value: str) -> int | None:
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else None


def parse_olx_count(html_text: str) -> int | None:
    if not html_text:
        return None

    decoded = html.unescape(html_text)
    text = re.sub(r"<[^>]+>", " ", decoded)
    text = re.sub(r"\s+", " ", text)

    patterns = [
        r'"total(?:Count|Elements|Ads|Results)"\s*:\s*(\d+)',
        r'"total_count"\s*:\s*(\d+)',
        r'"advertsCount"\s*:\s*(\d+)',
        r"(?:Знайдено|Найдено|Found)\s+([\d\s\u00a0]+)\s+(?:оголош|объяв|ad|result)",
        r"(?:Ми знайшли|Мы нашли)\s+([\d\s\u00a0]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, decoded, flags=re.IGNORECASE)
        if not match:
            match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_count(match.group(1))

    return None


def get_olx_count(url: str) -> int | None:
    try:
        html_text = fetch_olx_page(url)
    except OlxFetchError as exc:
        print(f"OLX fetch failed: {exc}")
        return None
    parsed_count = parse_olx_count(html_text)
    if parsed_count is None:
        print("OLX parse failed: listing count was not found.")
    return parsed_count


def collect_olx_counts() -> dict:
    results = {}
    for key, target in OLX_TARGETS.items():
        results[key] = get_olx_count(target["url"])
    return results


def collect_olx_snapshot_summary(save: bool = False) -> dict:
    snapshot_date = date.today()
    results = {}
    errors = []
    snapshots = []

    for key, target in OLX_TARGETS.items():
        url = target["url"]
        item = {
            "key": key,
            "url": url,
            "count": None,
            "saved": False,
            "error": None,
        }
        try:
            html_text = fetch_olx_page(url)
            count = parse_olx_count(html_text)
            if count is None:
                item["error"] = "Listing count was not found in OLX HTML."
            else:
                item["count"] = count
                snapshots.append(
                    build_manual_snapshot(
                        snapshot_date=snapshot_date,
                        source_name="OLX",
                        deal_type=target["deal_type"],
                        property_type=target["property_type"],
                        rooms=target["rooms"],
                        location_scope=target["location_scope"],
                        listings_count=count,
                    )
                )
        except OlxFetchError as exc:
            item["error"] = str(exc)

        if item["error"]:
            errors.append(f"{key}: {item['error']}")
        results[key] = item

    save_counts = {"created": 0, "updated": 0}
    if save and snapshots:
        init_db()
        save_counts = save_snapshots_with_counts(snapshots)
        saved_keys = {snapshot["deal_type"] for snapshot in snapshots}
        for item in results.values():
            if item["count"] is not None and item["key"].split("_", 1)[0] in saved_keys:
                item["saved"] = True

    saved_rows = save_counts["created"] + save_counts["updated"]
    skipped_rows = len([item for item in results.values() if item["count"] is None])
    return {
        "success": saved_rows > 0 if save else not errors,
        "date": snapshot_date.isoformat(),
        "sale_count": results["sale_apartments_all"]["count"],
        "rent_count": results["rent_apartments_all"]["count"],
        "saved_rows": saved_rows,
        "created_rows": save_counts["created"],
        "updated_rows": save_counts["updated"],
        "skipped_rows": skipped_rows,
        "errors": errors,
        "results": results,
    }


def print_test_results() -> dict:
    summary = collect_olx_snapshot_summary(save=False)
    for key, item in summary["results"].items():
        print(f"{key} URL: {item['url'] or '(not configured)'}")
        if item["count"] is None:
            print(f"{key} parsed count: failed")
            if item["error"]:
                print(f"{key} error: {item['error']}")
        else:
            print(f"{key} parsed count: {item['count']}")
    return summary


def save_manual_counts() -> int:
    summary = collect_olx_snapshot_summary(save=True)
    if summary["saved_rows"] == 0:
        print("OLX save skipped. Could not parse any trusted counts.")
        for error in summary["errors"]:
            print(f"- {error}")
        return 1
    print(
        "OLX manual snapshots saved: "
        f"created {summary['created_rows']}, updated {summary['updated_rows']}."
    )
    print(f"- sale_apartments_all: {summary['sale_count']}")
    print(f"- rent_apartments_all: {summary['rent_count']}")
    if summary["errors"]:
        print("Skipped:")
        for error in summary["errors"]:
            print(f"- {error}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OLX listing count proof of concept.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Fetch configured OLX pages and print parsed counts without saving.",
    )
    parser.add_argument(
        "--save-manual",
        action="store_true",
        help="Fetch configured OLX counts and save them as OLX/manual rows.",
    )
    args = parser.parse_args()

    if args.test:
        print_test_results()
        return 0
    if args.save_manual:
        return save_manual_counts()

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
