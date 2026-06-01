from __future__ import annotations

import argparse
import math
import random
import re
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    CATEGORIES,
    DEAL_TYPES,
    LOCATION_SCOPES,
    PROPERTY_TYPES,
    ROOMS,
    Category,
    display_name,
)
from database import (
    init_db,
    latest_real_snapshot_for_category,
    real_snapshot_dates_for_category,
    save_snapshot,
    save_snapshots,
    update_demo_counts,
)


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def fetch_html(url: str, timeout: int = 5) -> str | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def parse_listing_count(html: str) -> int | None:
    patterns = [
        r"Знайдено\s+([\d\s]+)",
        r"Ми знайшли\s+([\d\s]+)",
        r"found\s+([\d\s]+)",
        r'"totalCount"\s*:\s*(\d+)',
        r'"totalElements"\s*:\s*(\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return int(re.sub(r"\D", "", match.group(1)))

    card_count = html.count('data-cy="l-card"')
    return card_count if card_count > 0 else None


def deterministic_demo_count(category: Category, snapshot_date: date) -> int:
    base_values = {
        "sale_apartments_all": 510,
        "sale_apartments_1": 120,
        "sale_apartments_2": 210,
        "sale_apartments_3": 156,
        "sale_apartments_4_plus": 42,
        "rent_apartments_all": 185,
        "rent_apartments_1": 68,
        "rent_apartments_2": 79,
        "rent_apartments_3": 34,
        "rent_apartments_4_plus": 9,
        "sale_houses_all": 145,
        "sale_commercial_all": 82,
    }
    base = base_values.get(category.key, 100)
    day_index = (snapshot_date - date(2026, 1, 1)).days
    seed = f"{category.key}-{snapshot_date.isoformat()}"
    noise = random.Random(seed).randint(-9, 9)
    weekly_wave = math.sin(day_index / 5) * 11
    slow_trend = day_index * 0.12
    return max(1, round(base + weekly_wave + slow_trend + noise))


def aligned_demo_count(category: Category, snapshot_date: date, anchor_count: int) -> int:
    day_index = (snapshot_date - date(2026, 1, 1)).days
    days_behind_today = max(0, (date.today() - snapshot_date).days)
    seed = f"aligned-{category.key}-{snapshot_date.isoformat()}-{anchor_count}"
    rng = random.Random(seed)
    noise_pct = rng.uniform(-0.018, 0.018)
    wave_pct = math.sin(day_index / 6.0) * 0.022
    gentle_backfill_pct = min(0.035, days_behind_today * 0.00055)
    variation_pct = max(-0.08, min(0.08, noise_pct + wave_pct + gentle_backfill_pct))
    return max(1, round(anchor_count * (1 + variation_pct)))


def build_snapshot(
    category: Category,
    snapshot_date: date,
    listings_count: int,
    average_price: float | None = None,
    average_price_per_m2: float | None = None,
    data_source: str = "demo",
) -> dict:
    return {
        "date": snapshot_date.isoformat(),
        "source": category.source,
        "data_source": data_source,
        "category_key": category.key,
        "category_name": category.name,
        "deal_type": category.deal_type,
        "property_type": category.property_type,
        "rooms": category.rooms,
        "location_scope": category.location_scope,
        "url": category.url,
        "listings_count": listings_count,
        "average_price": average_price,
        "average_price_per_m2": average_price_per_m2,
    }


def build_manual_snapshot(
    *,
    snapshot_date: date,
    source_name: str,
    deal_type: str,
    property_type: str,
    rooms: str,
    location_scope: str,
    listings_count: int,
) -> dict:
    manual_category = Category(
        deal_type=deal_type,
        property_type=property_type,
        rooms=rooms,
        source=source_name,
        url="manual://entry",
        display_name=display_name(deal_type, property_type, rooms, location_scope),
        location_scope=location_scope,
    )
    return {
        "date": snapshot_date.isoformat(),
        "source": source_name,
        "data_source": "manual",
        "category_key": f"{manual_category.key}_{location_scope}",
        "category_name": manual_category.name,
        "deal_type": deal_type,
        "property_type": property_type,
        "rooms": rooms,
        "location_scope": location_scope,
        "url": "manual://entry",
        "listings_count": listings_count,
        "average_price": None,
        "average_price_per_m2": None,
    }


def collect_current_snapshot(category: Category) -> dict:
    html = fetch_html(category.url)
    parsed_count = parse_listing_count(html) if html else None
    count = parsed_count if parsed_count is not None else deterministic_demo_count(category, date.today())
    return build_snapshot(
        category,
        date.today(),
        count,
        data_source="domria" if parsed_count is not None else "demo",
    )


def seed_demo_history(
    days: int = 90,
    include_today: bool = True,
    align_to_real: bool = False,
) -> None:
    today = date.today()
    snapshots = []
    demo_counts_by_scope = {}
    end_offset = -1 if include_today else 0
    category_real_context = {}
    for category in CATEGORIES:
        latest_real = latest_real_snapshot_for_category(category.key) if align_to_real else None
        real_dates = real_snapshot_dates_for_category(category.key) if align_to_real else set()
        category_real_context[category.key] = {
            "latest_real_count": latest_real["listings_count"] if latest_real else None,
            "real_dates": real_dates,
        }

    for offset in range(days - 1, end_offset, -1):
        snapshot_date = today - timedelta(days=offset)
        snapshot_date_iso = snapshot_date.isoformat()
        for category in CATEGORIES:
            real_context = category_real_context[category.key]
            if snapshot_date_iso in real_context["real_dates"]:
                continue

            listings_count = deterministic_demo_count(category, snapshot_date)
            if align_to_real and real_context["latest_real_count"] is not None:
                listings_count = aligned_demo_count(
                    category,
                    snapshot_date,
                    int(real_context["latest_real_count"]),
                )
            demo_counts_by_scope[(category.key, snapshot_date_iso, category.location_scope)] = listings_count
            snapshots.append(build_snapshot(category, snapshot_date, listings_count))
    save_snapshots(snapshots)
    update_demo_counts(demo_counts_by_scope)


def prompt_choice(prompt: str, options: dict[str, str], default: str | None = None) -> str:
    options_text = ", ".join(f"{key}={label}" for key, label in options.items())
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{prompt} ({options_text}){suffix}: ").strip() or (default or "")
        if value in options:
            return value
        print("Невідоме значення. Спробуйте ще раз.")


def prompt_text(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("Поле не може бути порожнім.")


def prompt_int(prompt: str, default: int | None = None) -> int:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if not value and default is not None:
            return default
        try:
            parsed = int(value)
        except ValueError:
            print("Потрібне ціле число.")
            continue
        if parsed >= 0:
            return parsed
        print("Число має бути невід’ємним.")


def parse_manual_date(value: str | None) -> date:
    if not value:
        return date.today()
    return date.fromisoformat(value)


def insert_manual_snapshot(args: argparse.Namespace) -> dict:
    init_db()
    snapshot_date = parse_manual_date(args.date) if args.date else parse_manual_date(
        prompt_text("Дата у форматі YYYY-MM-DD", date.today().isoformat())
    )
    source_name = args.source_name or prompt_text("Назва джерела", "OLX")
    deal_type = args.deal_type or prompt_choice("Тип угоди", DEAL_TYPES, "sale")
    property_type = args.property_type or prompt_choice("Тип нерухомості", PROPERTY_TYPES, "apartments")
    rooms_default = "all" if property_type != "apartments" else "all"
    rooms = "all"
    if property_type == "apartments":
        rooms = args.rooms or prompt_choice("Кімнати", ROOMS, rooms_default)
    else:
        rooms = args.rooms or "all"
    location_scope = args.location_scope or prompt_choice(
        "Локація", LOCATION_SCOPES, "lutsk"
    )
    listings_count = (
        args.listings_count
        if args.listings_count is not None
        else prompt_int("Кількість оголошень")
    )

    snapshot = build_manual_snapshot(
        snapshot_date=snapshot_date,
        source_name=source_name,
        deal_type=deal_type,
        property_type=property_type,
        rooms=rooms,
        location_scope=location_scope,
        listings_count=listings_count,
    )
    save_snapshot(snapshot)
    print(
        "Manual snapshot saved: "
        f"{snapshot['date']} | {source_name} | {deal_type} | {property_type} | "
        f"{rooms} | {location_scope} | {listings_count}"
    )
    return snapshot


def run(
    use_live: bool = False,
    force: bool = False,
    max_requests: int | None = None,
    seed_demo_only: bool = False,
    align_to_real: bool = False,
) -> None:
    init_db()
    if use_live:
        seed_demo_history(days=90, include_today=False, align_to_real=align_to_real)
        from domria_scraper import run as run_domria

        run_domria(use_demo_fallback=True, force=force, max_requests=max_requests)
        print("Real estate snapshots saved with DOM.RIA live mode and demo fallback.")
    else:
        seed_demo_history(days=90, include_today=True, align_to_real=align_to_real)
        if seed_demo_only and align_to_real:
            print("Demo history rebuilt and aligned to the latest real DOM.RIA values where available.")
        elif seed_demo_only:
            print("Demo history rebuilt.")
        else:
            print("Demo real estate snapshots saved. Use --live to try parsing configured URLs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Lutsk real estate listing snapshots.")
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Rebuild demo history without making live requests.",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Insert one manual market data row without calling external APIs.",
    )
    parser.add_argument(
        "--date",
        help="Manual entry date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--source-name",
        help="Manual entry source name, for example OLX.",
    )
    parser.add_argument(
        "--deal-type",
        choices=sorted(DEAL_TYPES),
        help="Manual entry deal type.",
    )
    parser.add_argument(
        "--property-type",
        choices=sorted(PROPERTY_TYPES),
        help="Manual entry property type.",
    )
    parser.add_argument(
        "--rooms",
        choices=sorted(ROOMS),
        help="Manual entry rooms filter.",
    )
    parser.add_argument(
        "--location-scope",
        choices=sorted(LOCATION_SCOPES),
        help="Manual entry location scope.",
    )
    parser.add_argument(
        "--listings-count",
        type=int,
        help="Manual entry listing count.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Try DOM.RIA API before falling back to demo data.",
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
    parser.add_argument(
        "--align-to-real",
        action="store_true",
        help="When seeding demo history, align demo values to the latest real DOM.RIA row when available.",
    )
    args = parser.parse_args()
    if args.manual:
        insert_manual_snapshot(args)
    else:
        run(
            use_live=args.live,
            force=args.force,
            max_requests=args.max_requests,
            seed_demo_only=args.seed_demo,
            align_to_real=args.align_to_real,
        )
