from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    CATEGORIES,
    DISABLED_CATEGORIES,
    DOMRIA_API_BASE_URL,
    DOMRIA_CITIES_API_URL,
    DOMRIA_DEFAULT_CITY_ID,
    DOMRIA_DEFAULT_STATE_ID,
    DOMRIA_LOCAL_CONFIG_PATH,
    Category,
)
from database import (
    categories_collected_today,
    count_domria_requests_last_hour,
    find_today_domria_snapshot,
    init_db,
    log_domria_request,
    save_snapshots,
)
from scraper import build_snapshot, deterministic_demo_count


class DomRiaError(RuntimeError):
    pass


class DomRiaRateLimitError(DomRiaError):
    pass


DOMRIA_HOURLY_SAFETY_LIMIT = 25


def load_domria_config(path: Path = DOMRIA_LOCAL_CONFIG_PATH) -> dict[str, Any]:
    config: dict[str, Any] = {
        "api_key": os.getenv("DOMRIA_API_KEY", ""),
        "state_id": int(os.getenv("DOMRIA_STATE_ID", DOMRIA_DEFAULT_STATE_ID)),
        "city_id": int(os.getenv("DOMRIA_CITY_ID", DOMRIA_DEFAULT_CITY_ID)),
        "categories": {},
        "_config_path": str(path.resolve()),
        "_config_found": path.exists(),
    }

    if path.exists():
        file_config = json.loads(path.read_text(encoding="utf-8-sig"))
        config.update({key: value for key, value in file_config.items() if value not in ("", None)})

    return config


def build_search_params(category: Category, config: dict[str, Any]) -> dict[str, str]:
    if not category.domria_params:
        raise DomRiaError(f"Category {category.key} has no DOM.RIA parameters.")

    params = {key: str(value) for key, value in category.domria_params.items()}
    params["state_id"] = str(config.get("state_id", DOMRIA_DEFAULT_STATE_ID))
    params["city_id"] = str(config.get("city_id", DOMRIA_DEFAULT_CITY_ID))

    category_overrides = config.get("categories", {}).get(category.key, {})
    for key, value in category_overrides.items():
        params[key] = str(value)

    return params


def request_json(url: str, timeout: int = 15) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "lutsk-real-estate-analytics/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        if exc.code == 429 and "HourOverlimit" in body:
            raise DomRiaRateLimitError(f"HTTP {exc.code}: {body}") from exc
        raise DomRiaError(f"HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        raise DomRiaError(str(exc)) from exc


def fetch_listing_count(
    category: Category,
    api_key: str,
    config: dict[str, Any],
    timeout: int = 15,
) -> tuple[int, int, str]:
    params = build_search_params(category, config)
    params["api_key"] = api_key
    query = urllib.parse.urlencode(params)
    endpoint = f"{DOMRIA_API_BASE_URL}?{query}"
    payload = request_json(endpoint, timeout=timeout)

    if "count" not in payload:
        raise DomRiaError(f"DOM.RIA response for {category.key} did not include count.")

    return int(payload["count"]), 200, endpoint


def fetch_city_name(api_key: str, state_id: int, city_id: int) -> str | None:
    query = urllib.parse.urlencode({"api_key": api_key, "lang_id": 4})
    payload = request_json(f"{DOMRIA_CITIES_API_URL}/{state_id}?{query}", timeout=20)
    for item in payload:
        if int(item.get("cityID", -1)) == int(city_id):
            return item.get("name")
    return None


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return "no"
    return f"yes, length: {len(api_key)} characters"


def config_report() -> dict[str, Any]:
    config = load_domria_config()
    api_key = str(config.get("api_key", ""))
    report = {
        "config_found": bool(config.get("_config_found")),
        "config_path": config.get("_config_path"),
        "api_key_found": bool(api_key),
        "api_key_status": mask_api_key(api_key),
        "city_id": int(config.get("city_id", DOMRIA_DEFAULT_CITY_ID)),
        "state_id": int(config.get("state_id", DOMRIA_DEFAULT_STATE_ID)),
        "categories": [],
        "disabled_categories": [],
        "city_name": None,
        "city_verified_for_lutsk": False,
        "city_verification_error": None,
    }

    for category in CATEGORIES:
        report["categories"].append(
            {
                "key": category.key,
                "display_name": category.display_name,
                "mapping": {
                    "deal_type": category.deal_type,
                    "property_type": category.property_type,
                    "rooms": category.rooms,
                },
                "params": build_search_params(category, config),
            }
        )
    for category in DISABLED_CATEGORIES:
        report["disabled_categories"].append(category.key)

    if api_key:
        try:
            city_name = fetch_city_name(api_key, report["state_id"], report["city_id"])
            report["city_name"] = city_name
            report["city_verified_for_lutsk"] = city_name == "Луцьк"
        except DomRiaError as exc:
            report["city_verification_error"] = str(exc)

    return report


def print_config_report() -> None:
    report = config_report()
    print(f"config file found: {'yes' if report['config_found'] else 'no'}")
    print(f"config path: {report['config_path']}")
    print(f"API key found: {report['api_key_status']}")
    print(f"current city_id: {report['city_id']}")
    print(f"current state_id: {report['state_id']}")
    if report["city_name"]:
        print(f"resolved city name: {report['city_name']}")
        print(
            "city_id is Lutsk: "
            + ("yes" if report["city_verified_for_lutsk"] else "no")
        )
    elif report["city_verification_error"]:
        print(f"city verification: failed ({report['city_verification_error']})")
    else:
        print("city verification: skipped (no API key)")
    print("current category mapping:")
    for item in report["categories"]:
        mapping = item["mapping"]
        print(
            f"- {item['key']}: deal_type={mapping['deal_type']}, "
            f"property_type={mapping['property_type']}, rooms={mapping['rooms']}"
        )
    print("configured DOM.RIA parameters per category:")
    for item in report["categories"]:
        print(f"- {item['key']}: {json.dumps(item['params'], ensure_ascii=False, sort_keys=True)}")
    if report["disabled_categories"]:
        print("disabled by default:")
        for key in report["disabled_categories"]:
            print(f"- {key}")


def collect_domria_snapshots(
    use_demo_fallback: bool = True,
    force: bool = False,
    max_requests: int | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    config = load_domria_config()
    api_key = str(config.get("api_key") or os.getenv("DOMRIA_API_KEY") or "")
    snapshot_date = date.today()
    snapshots: list[dict] = []
    collected_today = categories_collected_today([category.key for category in CATEGORIES])
    missing_today = [category.key for category in CATEGORIES if category.key not in collected_today]
    requests_last_hour = count_domria_requests_last_hour()
    summary = {
        "categories_configured": len(CATEGORIES),
        "api_requests_made": 0,
        "real_categories": [],
        "demo_categories": [],
        "skipped_categories": [],
        "rate_limited_categories": [],
        "remaining_categories": [],
        "requests_last_hour": requests_last_hour,
        "remaining_safe_requests": max(0, DOMRIA_HOURLY_SAFETY_LIMIT - requests_last_hour),
        "collected_today": collected_today,
        "missing_today": missing_today,
        "city_id": int(config.get("city_id", DOMRIA_DEFAULT_CITY_ID)),
        "state_id": int(config.get("state_id", DOMRIA_DEFAULT_STATE_ID)),
    }
    stop_live_requests = False

    if not api_key:
        if not use_demo_fallback:
            raise DomRiaError("DOM.RIA API key is missing. Set DOMRIA_API_KEY or domria_config.json.")
        for category in CATEGORIES:
            summary["demo_categories"].append(category.key)
            snapshots.append(
                build_snapshot(
                    category,
                    snapshot_date,
                    deterministic_demo_count(category, snapshot_date),
                    data_source="demo",
                )
            )
        return snapshots, summary

    for category in CATEGORIES:
        if stop_live_requests:
            summary["demo_categories"].append(category.key)
            summary["remaining_categories"].append(category.key)
            snapshots.append(
                build_snapshot(
                    category,
                    snapshot_date,
                    deterministic_demo_count(category, snapshot_date),
                    data_source="demo",
                )
            )
            continue

        cached_snapshot = None if force else find_today_domria_snapshot(
            deal_type=category.deal_type,
            property_type=category.property_type,
            rooms=category.rooms,
            location_scope=category.location_scope,
        )
        if cached_snapshot:
            print(f"Skipping API request: today's DOM.RIA data already exists for {category.key}")
            summary["skipped_categories"].append(category.key)
            snapshots.append(
                {
                    key: cached_snapshot[key]
                    for key in (
                        "date",
                        "source",
                        "data_source",
                        "category_key",
                        "category_name",
                        "deal_type",
                        "property_type",
                        "rooms",
                        "location_scope",
                        "url",
                        "listings_count",
                        "average_price",
                        "average_price_per_m2",
                    )
                }
            )
            continue

        if count_domria_requests_last_hour() >= DOMRIA_HOURLY_SAFETY_LIMIT:
            print("DOM.RIA hourly safety limit reached. Try again later.")
            stop_live_requests = True
            summary["remaining_categories"].append(category.key)
            snapshots.append(
                build_snapshot(
                    category,
                    snapshot_date,
                    deterministic_demo_count(category, snapshot_date),
                    data_source="demo",
                )
            )
            continue

        if max_requests is not None and summary["api_requests_made"] >= max_requests:
            summary["remaining_categories"].append(category.key)
            stop_live_requests = True
            snapshots.append(
                build_snapshot(
                    category,
                    snapshot_date,
                    deterministic_demo_count(category, snapshot_date),
                    data_source="demo",
                )
            )
            continue

        try:
            summary["api_requests_made"] += 1
            count, status_code, endpoint = fetch_listing_count(category, api_key, config)
            log_domria_request(
                endpoint=endpoint,
                category_key=category.key,
                status_code=status_code,
                success=True,
            )
            data_source = "domria"
            summary["real_categories"].append(category.key)
        except DomRiaRateLimitError:
            if not use_demo_fallback:
                raise
            log_domria_request(
                endpoint=DOMRIA_API_BASE_URL,
                category_key=category.key,
                status_code=429,
                success=False,
                error_reason="HourOverlimit",
            )
            stop_live_requests = True
            count = deterministic_demo_count(category, snapshot_date)
            data_source = "demo"
            summary["demo_categories"].append(category.key)
            summary["rate_limited_categories"].append(category.key)
        except DomRiaError:
            if not use_demo_fallback:
                raise
            log_domria_request(
                endpoint=DOMRIA_API_BASE_URL,
                category_key=category.key,
                status_code=None,
                success=False,
                error_reason="DomRiaError",
            )
            count = deterministic_demo_count(category, snapshot_date)
            data_source = "demo"
            summary["demo_categories"].append(category.key)
        snapshots.append(build_snapshot(category, snapshot_date, count, data_source=data_source))

    summary["requests_last_hour"] = count_domria_requests_last_hour()
    summary["remaining_safe_requests"] = max(0, DOMRIA_HOURLY_SAFETY_LIMIT - summary["requests_last_hour"])
    summary["collected_today"] = categories_collected_today([category.key for category in CATEGORIES])
    summary["missing_today"] = [
        category.key for category in CATEGORIES if category.key not in summary["collected_today"]
    ]
    return snapshots, summary


def run(
    use_demo_fallback: bool = True,
    force: bool = False,
    max_requests: int | None = None,
) -> dict[str, Any]:
    init_db()
    snapshots, summary = collect_domria_snapshots(
        use_demo_fallback=use_demo_fallback,
        force=force,
        max_requests=max_requests,
    )
    save_snapshots(snapshots)
    estimated_monthly = summary["categories_configured"] * 30
    print(f"Saved {len(snapshots)} DOM.RIA snapshots.")
    print("DOM.RIA scraping summary:")
    print(f"- categories configured: {summary['categories_configured']}")
    print(f"- API requests made: {summary['api_requests_made']}")
    print(f"- skipped because already collected today: {len(summary['skipped_categories'])}")
    print(f"- successful real responses: {len(summary['real_categories'])}")
    print(f"- fallback/demo responses: {len(summary['demo_categories'])}")
    if summary["rate_limited_categories"]:
        print(f"- rate-limited categories: {len(summary['rate_limited_categories'])}")
    print(f"- requests made in last hour: {summary['requests_last_hour']}")
    print(f"- remaining safe requests: {summary['remaining_safe_requests']}")
    print(
        "Estimated monthly usage: "
        f"{summary['categories_configured']} categories x 30 days = {estimated_monthly} requests/month"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Lutsk real estate snapshots from DOM.RIA.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Show whether the config file and API key are detected, without printing the key itself.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore today's cached DOM.RIA rows and make live API requests again.",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="Maximum number of DOM.RIA API requests to make in one run.",
    )
    args = parser.parse_args()

    if args.check_config:
        print_config_report()
    else:
        run(use_demo_fallback=True, force=args.force, max_requests=args.max_requests)
