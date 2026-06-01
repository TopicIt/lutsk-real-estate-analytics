from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import CATEGORIES
from database import (
    categories_collected_today,
    count_domria_requests_last_hour,
    daily_snapshots_row_count,
    database_file_info,
    init_db,
    log_collection_run,
)
from domria_scraper import DOMRIA_HOURLY_SAFETY_LIMIT, run as run_domria
from scraper import seed_demo_history


DEFAULT_MAX_REQUESTS = 10


def timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def scheduler_storage_state() -> dict:
    info = database_file_info()
    try:
        info["daily_snapshots_row_count"] = daily_snapshots_row_count()
    except Exception as exc:
        info["daily_snapshots_row_count"] = None
        info["row_count_error"] = str(exc)
    return info


def print_scheduler_storage_state(label: str) -> None:
    print(
        f"Scheduler storage {label}: "
        + json.dumps(scheduler_storage_state(), ensure_ascii=False, sort_keys=True)
    )


def collection_plan(max_requests: int = DEFAULT_MAX_REQUESTS) -> dict:
    init_db()
    category_keys = [category.key for category in CATEGORIES]
    collected_today = categories_collected_today(category_keys)
    missing_today = [key for key in category_keys if key not in collected_today]
    requests_last_hour = count_domria_requests_last_hour()
    safe_slots = max(0, DOMRIA_HOURLY_SAFETY_LIMIT - requests_last_hour)
    request_slots = min(max_requests, safe_slots)
    planned_categories = missing_today[:request_slots]
    deferred_categories = missing_today[request_slots:]
    return {
        "configured_categories": category_keys,
        "collected_today": collected_today,
        "missing_today": missing_today,
        "planned_categories": planned_categories,
        "deferred_categories": deferred_categories,
        "requests_last_hour": requests_last_hour,
        "hourly_safety_limit": DOMRIA_HOURLY_SAFETY_LIMIT,
        "max_requests": max_requests,
        "safe_request_slots": safe_slots,
    }


def print_plan(plan: dict) -> None:
    print("DOM.RIA daily collection dry run")
    print(f"- configured categories: {len(plan['configured_categories'])}")
    print(f"- collected today: {len(plan['collected_today'])}")
    print(f"- missing today: {len(plan['missing_today'])}")
    print(f"- requests used in last hour: {plan['requests_last_hour']}")
    print(f"- hourly safety limit: {plan['hourly_safety_limit']}")
    print(f"- max requests this pass: {plan['max_requests']}")
    print(f"- planned API requests: {len(plan['planned_categories'])}")
    print("Planned categories:")
    if plan["planned_categories"]:
        for key in plan["planned_categories"]:
            print(f"- {key}")
    else:
        print("- (none)")
    if plan["deferred_categories"]:
        print("Deferred categories:")
        for key in plan["deferred_categories"]:
            print(f"- {key}")
    if not plan["planned_categories"] and plan["missing_today"]:
        print("No categories can be collected now because the hourly safety window is full.")
    if not plan["missing_today"]:
        print("All DOM.RIA categories are already collected today.")
    print("Dry run only: no DOM.RIA API requests were made.")


def run_once(max_requests: int = DEFAULT_MAX_REQUESTS) -> dict:
    init_db()
    print_scheduler_storage_state("before run")
    started_at = timestamp()
    last_error = None
    summary: dict | None = None
    try:
        seed_demo_history(days=90, include_today=False, align_to_real=False)
        summary = run_domria(use_demo_fallback=True, force=False, max_requests=max_requests)
        if summary.get("rate_limited_categories"):
            last_error = "HourOverlimit: DOM.RIA stopped safely after rate limit response."
        finished_at = timestamp()
        log_collection_run(
            started_at=started_at,
            finished_at=finished_at,
            success=last_error is None,
            api_requests_made=int(summary.get("api_requests_made", 0)),
            real_categories=list(summary.get("real_categories", [])),
            skipped_categories=list(summary.get("skipped_categories", [])),
            missing_today=list(summary.get("missing_today", [])),
            last_error=last_error,
        )
        print("Scheduler run finished.")
        print(f"- started at: {started_at}")
        print(f"- finished at: {finished_at}")
        print(f"- API requests made: {summary.get('api_requests_made', 0)}")
        print(f"- real categories collected: {len(summary.get('real_categories', []))}")
        print(f"- skipped because already collected today: {len(summary.get('skipped_categories', []))}")
        print(f"- missing after run: {len(summary.get('missing_today', []))}")
        if last_error:
            print(f"- last error: {last_error}")
        print_scheduler_storage_state("after run")
        return summary
    except Exception as exc:
        finished_at = timestamp()
        last_error = str(exc)
        log_collection_run(
            started_at=started_at,
            finished_at=finished_at,
            success=False,
            api_requests_made=int((summary or {}).get("api_requests_made", 0)),
            real_categories=list((summary or {}).get("real_categories", [])),
            skipped_categories=list((summary or {}).get("skipped_categories", [])),
            missing_today=list((summary or {}).get("missing_today", [])),
            last_error=last_error,
        )
        print("Scheduler run failed safely.")
        print(f"- started at: {started_at}")
        print(f"- finished at: {finished_at}")
        print(f"- last error: {last_error}")
        print_scheduler_storage_state("after failed run")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily DOM.RIA collection scheduler.")
    parser.add_argument("--run-once", action="store_true", help="Run one safe daily DOM.RIA collection pass.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be collected without calling DOM.RIA.")
    parser.add_argument(
        "--max-requests",
        type=int,
        default=DEFAULT_MAX_REQUESTS,
        help="Maximum DOM.RIA API requests in one run. Defaults to 10.",
    )
    args = parser.parse_args()

    if args.dry_run:
        print_plan(collection_plan(max_requests=args.max_requests))
        return
    if args.run_once:
        run_once(max_requests=args.max_requests)
        return
    parser.print_help()


if __name__ == "__main__":
    main()
