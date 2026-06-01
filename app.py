from __future__ import annotations

import json
import os
import secrets
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import CATEGORIES, DEAL_TYPES, LOCATION_SCOPES, PROPERTY_TYPES, ROOMS
from database import (
    analytics_debug_summary,
    collection_status_summary,
    database_absolute_path,
    delete_manual_snapshot,
    domria_status_snapshot,
    fetch_filter_options,
    fetch_latest_manual_snapshots,
    fetch_manual_snapshot_groups,
    fetch_snapshots,
    fetch_suspicious_manual_snapshots,
    init_db,
    save_snapshot,
    save_snapshots_with_counts,
    storage_detailed_diagnostics,
    storage_diagnostics,
)
from scheduler import run_once as run_domria_collection_once
from scraper import build_manual_snapshot


app = Flask(__name__)


PERIODS = {
    "7": 7,
    "30": 30,
    "90": 90,
    "all": None,
}

SOURCE_PRIORITY = {
    "manual": 0,
    "domria": 1,
    "demo": 2,
}

SOURCE_OPTIONS = {
    "olx": {
        "label": "OLX",
        "status": "Ручні дані OLX",
        "borderColor": "#111111",
        "backgroundColor": "rgba(17, 17, 17, 0.08)",
    },
    "domria": {
        "label": "DOM.RIA",
        "status": "Реальні дані DOM.RIA",
        "borderColor": "#2f6f73",
        "backgroundColor": "rgba(47, 111, 115, 0.08)",
    },
    "demo": {
        "label": "Демо",
        "status": "Демо-дані",
        "borderColor": "#9a6a2f",
        "backgroundColor": "rgba(154, 106, 47, 0.08)",
    },
}

SOURCE_ORDER = ("olx", "domria", "demo")

BULK_OLX_GROUPS = [
    {
        "title": "Продаж квартир",
        "fields": [
            ("sale_apartments_all", "Усі кімнати", "sale", "apartments", "all"),
            ("sale_apartments_1", "1 кімната", "sale", "apartments", "1"),
            ("sale_apartments_2", "2 кімнати", "sale", "apartments", "2"),
            ("sale_apartments_3", "3 кімнати", "sale", "apartments", "3"),
            ("sale_apartments_4_plus", "4+ кімнат", "sale", "apartments", "4_plus"),
        ],
    },
    {
        "title": "Оренда квартир",
        "fields": [
            ("rent_apartments_all", "Усі кімнати", "rent", "apartments", "all"),
            ("rent_apartments_1", "1 кімната", "rent", "apartments", "1"),
            ("rent_apartments_2", "2 кімнати", "rent", "apartments", "2"),
            ("rent_apartments_3", "3 кімнати", "rent", "apartments", "3"),
            ("rent_apartments_4_plus", "4+ кімнат", "rent", "apartments", "4_plus"),
        ],
    },
    {
        "title": "Продаж",
        "fields": [
            ("sale_houses_all", "Будинки, усі", "sale", "houses", "all"),
            ("sale_commercial_all", "Комерційна, усі", "sale", "commercial", "all"),
            ("sale_land_all", "Земля, усі", "sale", "land", "all"),
        ],
    },
]


def is_production() -> bool:
    return os.getenv("FLASK_ENV") == "production" or bool(os.getenv("RAILWAY_ENVIRONMENT"))


def is_development() -> bool:
    return os.getenv("FLASK_ENV") == "development"


def require_admin_access() -> Response | None:
    if not is_production():
        return None

    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        abort(404)

    auth = request.authorization
    if auth and auth.password == admin_password:
        return None

    return Response(
        "Admin password required.",
        401,
        {"WWW-Authenticate": 'Basic realm="Admin"'},
    )


def log_storage_diagnostics() -> None:
    diagnostics = storage_diagnostics()
    print(
        "Storage diagnostics: "
        + json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
    )


def initialize_application() -> None:
    init_db()
    print(f"Database initialized at {database_absolute_path()}")
    log_storage_diagnostics()


def collection_timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def collection_result_from_summary(
    summary: dict,
    *,
    started_at: str,
    finished_at: str,
) -> dict:
    last_error = (
        "HourOverlimit: DOM.RIA stopped safely after rate limit response."
        if summary.get("rate_limited_categories")
        else None
    )
    return {
        "success": last_error is None,
        "api_requests_made": int(summary.get("api_requests_made", 0)),
        "categories_collected": len(summary.get("real_categories", [])),
        "categories_skipped": len(summary.get("skipped_categories", [])),
        "categories_missing_today": len(summary.get("missing_today", [])),
        "last_error": last_error,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def run_collection_in_web_process() -> tuple[dict, int]:
    started_at = collection_timestamp()
    try:
        summary = run_domria_collection_once()
        finished_at = collection_timestamp()
        return collection_result_from_summary(
            summary,
            started_at=started_at,
            finished_at=finished_at,
        ), 200
    except Exception as exc:
        finished_at = collection_timestamp()
        return {
            "success": False,
            "api_requests_made": 0,
            "categories_collected": 0,
            "categories_skipped": 0,
            "categories_missing_today": 0,
            "last_error": str(exc),
            "started_at": started_at,
            "finished_at": finished_at,
        }, 500


def require_collection_token():
    expected_token = os.getenv("COLLECTION_TOKEN", "")
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    supplied_token = authorization[len(prefix):].strip() if authorization.startswith(prefix) else ""

    if not expected_token or not supplied_token:
        return jsonify({"error": "Unauthorized"}), 401
    if not secrets.compare_digest(supplied_token, expected_token):
        return jsonify({"error": "Unauthorized"}), 401
    return None


def change_between(values: list[int], days: int) -> int | None:
    if not values:
        return None
    if len(values) <= days:
        return values[-1] - values[0]
    return values[-1] - values[-days - 1]


def trend_label(values: list[int]) -> str:
    change_7 = change_between(values, 7)
    if change_7 is None or abs(change_7) <= 3:
        return "Стабільно"
    return "Зростає" if change_7 > 0 else "Знижується"


def choose_preferred_source_rows(rows: list[dict]) -> list[dict]:
    selected = {}
    for row in rows:
        key = (
            row["date"],
            row.get("deal_type"),
            row.get("property_type"),
            row.get("rooms"),
            row.get("location_scope"),
        )
        current = selected.get(key)
        if current is None:
            selected[key] = row
            continue
        current_priority = SOURCE_PRIORITY.get(current.get("data_source"), 99)
        row_priority = SOURCE_PRIORITY.get(row.get("data_source"), 99)
        if row_priority < current_priority:
            selected[key] = row
    return list(selected.values())


def source_key(row: dict) -> str | None:
    data_source = row.get("data_source") or "demo"
    source = (row.get("source") or "").strip().lower()
    if data_source == "manual" and source == "olx":
        return "olx"
    if data_source == "domria":
        return "domria"
    if data_source == "demo":
        return "demo"
    return None


def source_availability(rows: list[dict]) -> dict:
    available_keys = {source_key(row) for row in rows}
    return {key: key in available_keys for key in SOURCE_ORDER}


def default_source(availability: dict) -> str:
    for key in SOURCE_ORDER:
        if availability.get(key):
            return key
    return "demo"


def dedupe_source_rows(rows: list[dict]) -> list[dict]:
    selected = {}
    for row in rows:
        key = (
            source_key(row),
            row["date"],
            row.get("deal_type"),
            row.get("property_type"),
            row.get("rooms"),
            row.get("location_scope"),
        )
        if key[0] is not None:
            selected.setdefault(key, row)
    return list(selected.values())


def series_label(filters: dict) -> str:
    labels = {
        "sale": "Продаж",
        "rent": "Оренда",
        "apartments": "квартири",
        "houses": "будинки",
        "commercial": "комерційна нерухомість",
        "land": "земельні ділянки",
        "all": "усі кімнати",
        "1": "1 кімната",
        "2": "2 кімнати",
        "3": "3 кімнати",
        "4_plus": "4+ кімнат",
        "lutsk": "Луцьк",
        "lutsk_suburbs": "Луцьк + передмістя",
    }
    parts = [
        labels.get(filters.get("deal_type"), filters.get("deal_type", "")),
        labels.get(filters.get("property_type"), filters.get("property_type", "")),
    ]
    rooms = filters.get("rooms")
    if filters.get("property_type") == "apartments" and rooms:
        parts.append(labels.get(rooms, rooms))
    location_scope = filters.get("location_scope")
    if location_scope:
        parts.append(labels.get(location_scope, location_scope))
    return " · ".join(part for part in parts if part)


def build_source_summary(rows: list[dict]) -> dict:
    source_values = {source_key(row) for row in rows if source_key(row)}
    if len(source_values) == 1:
        key = next(iter(source_values))
        return {
            "data_source": key,
            "label": SOURCE_OPTIONS[key]["label"],
            "status": SOURCE_OPTIONS[key]["status"],
        }
    if not source_values:
        return {
            "data_source": "demo",
            "label": "Демо",
            "status": SOURCE_OPTIONS["demo"]["status"],
        }
    return {
        "data_source": "multiple",
        "label": "Кілька джерел",
        "status": "Окремі лінії джерел",
    }


def build_single_source_series(
    rows: list[dict],
    filters: dict | None = None,
    selected_source: str | None = None,
) -> dict:
    rows = dedupe_source_rows(rows)
    totals_by_date = defaultdict(int)

    for row in rows:
        totals_by_date[row["date"]] += row["listings_count"]

    labels = sorted(totals_by_date)
    values = [totals_by_date[label] for label in labels]

    datasets = [
        {
            "label": series_label(filters or {}) or "Вибраний сегмент",
            "data": values,
            "borderColor": "#111111",
            "backgroundColor": "rgba(17, 17, 17, 0.08)",
            "tension": 0.28,
            "fill": True,
        }
    ]

    source = build_source_summary(rows)
    if selected_source in SOURCE_OPTIONS:
        source = {
            "data_source": selected_source,
            "label": SOURCE_OPTIONS[selected_source]["label"],
            "status": SOURCE_OPTIONS[selected_source]["status"],
        }

    return {
        "labels": labels,
        "datasets": datasets,
        "metrics": {
            "current": values[-1] if values else 0,
            "change7": change_between(values, 7) or 0,
            "change30": change_between(values, 30) or 0,
            "trend": trend_label(values),
        },
        "source": source,
    }


def build_all_source_series(rows: list[dict]) -> dict:
    rows = dedupe_source_rows(rows)
    labels = sorted({row["date"] for row in rows})
    datasets = []

    for key in SOURCE_ORDER:
        source_rows = [row for row in rows if source_key(row) == key]
        if not source_rows:
            continue
        values_by_date = defaultdict(int)
        for row in source_rows:
            values_by_date[row["date"]] += row["listings_count"]
        option = SOURCE_OPTIONS[key]
        datasets.append(
            {
                "label": option["label"],
                "data": [values_by_date.get(label) for label in labels],
                "borderColor": option["borderColor"],
                "backgroundColor": option["backgroundColor"],
                "tension": 0.28,
                "fill": False,
                "spanGaps": True,
            }
        )

    return {
        "labels": labels,
        "datasets": datasets,
        "metrics": {
            "current": "Кілька джерел",
            "change7": "Кілька джерел",
            "change30": "Кілька джерел",
            "trend": "Кілька джерел",
        },
        "source": {
            "data_source": "multiple",
            "label": "Кілька джерел",
            "status": "Окремі лінії джерел",
        },
    }


def rows_by_date(rows: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        totals[row["date"]] += row["listings_count"]
    return dict(totals)


def latest_value(values_by_date: dict[str, int]) -> int | None:
    if not values_by_date:
        return None
    return values_by_date[sorted(values_by_date)[-1]]


def latest_created_at(rows: list[dict]) -> str | None:
    timestamps = [row["created_at"] for row in rows if row.get("created_at")]
    return max(timestamps) if timestamps else None


def build_public_trend(deal_type: str) -> dict:
    base_filters = {
        "deal_type": deal_type,
        "property_type": "apartments",
        "rooms": "all",
        "location_scope": "lutsk",
    }
    domria_rows = fetch_snapshots(**base_filters, source_filter="domria")
    olx_rows = fetch_snapshots(**base_filters, source_filter="olx")
    domria_by_date = rows_by_date(domria_rows)
    olx_by_date = rows_by_date(olx_rows)
    labels = sorted(set(domria_by_date) | set(olx_by_date))

    return {
        "labels": labels,
        "datasets": [
            {
                "label": "DOM.RIA",
                "data": [domria_by_date.get(label) for label in labels],
                "borderColor": SOURCE_OPTIONS["domria"]["borderColor"],
                "backgroundColor": SOURCE_OPTIONS["domria"]["backgroundColor"],
                "tension": 0.28,
                "fill": False,
                "spanGaps": True,
            },
            {
                "label": "OLX",
                "data": [olx_by_date.get(label) for label in labels],
                "borderColor": SOURCE_OPTIONS["olx"]["borderColor"],
                "backgroundColor": SOURCE_OPTIONS["olx"]["backgroundColor"],
                "tension": 0.28,
                "fill": False,
                "spanGaps": True,
            },
        ],
        "latest": {
            "domria": latest_value(domria_by_date),
            "olx": latest_value(olx_by_date),
        },
        "last_update": latest_created_at(domria_rows + olx_rows),
    }


def default_admin_bulk_form() -> dict:
    return {
        "source_name": "OLX",
        "location_scope": "lutsk",
        "date": date.today().isoformat(),
    }


def default_admin_form() -> dict:
    return {
        "source_name": "OLX",
        "deal_type": "sale",
        "property_type": "apartments",
        "rooms": "all",
        "location_scope": "lutsk",
        "listings_count": "",
        "date": date.today().isoformat(),
    }


def render_admin_page(
    *,
    bulk_form: dict | None = None,
    form: dict | None = None,
    errors: list[str] | None = None,
    message: str | None = None,
    collection_result: dict | None = None,
):
    init_db()
    return render_template(
        "admin.html",
        bulk_form=bulk_form or default_admin_bulk_form(),
        bulk_groups=BULK_OLX_GROUPS,
        bulk_snapshot_groups=fetch_manual_snapshot_groups(20),
        collection_result=collection_result,
        entries=fetch_latest_manual_snapshots(50),
        errors=errors or [],
        filters=fetch_filter_options(),
        form=form or default_admin_form(),
        message=message,
        suspicious_entries=fetch_suspicious_manual_snapshots(50),
    )


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analytics")
def analytics():
    return render_template("analytics.html")


@app.route("/analytics/advanced")
def analytics_advanced():
    return render_template("analytics_advanced.html", filters=fetch_filter_options(), periods=PERIODS.keys())


@app.route("/admin", methods=["GET", "POST"])
def admin():
    admin_response = require_admin_access()
    if admin_response is not None:
        return admin_response

    init_db()
    filters = fetch_filter_options()
    bulk_form = default_admin_bulk_form()
    form = default_admin_form()
    errors: list[str] = []
    message = request.args.get("message")

    if request.method == "POST":
        form_kind = request.form.get("form_kind", "single")
        if form_kind == "bulk":
            bulk_form.update(
                {
                    "source_name": "OLX",
                    "location_scope": request.form.get("bulk_location_scope", "lutsk").strip(),
                    "date": request.form.get("bulk_date", "").strip(),
                }
            )
            if not bulk_form["date"]:
                errors.append("Дата не може бути порожньою.")
            try:
                snapshot_date = date.fromisoformat(bulk_form["date"])
            except ValueError:
                snapshot_date = None
                errors.append("Дата має бути у форматі YYYY-MM-DD.")
            if bulk_form["location_scope"] not in LOCATION_SCOPES:
                errors.append("Невідоме охоплення локації.")

            snapshots = []
            ignored = 0
            for group in BULK_OLX_GROUPS:
                for field_name, _label, deal_type, property_type, rooms in group["fields"]:
                    raw_value = request.form.get(field_name, "").strip()
                    if not raw_value:
                        ignored += 1
                        continue
                    try:
                        listings_count = int(raw_value)
                    except ValueError:
                        errors.append(f"{field_name}: значення має бути цілим числом.")
                        continue
                    if listings_count <= 0:
                        errors.append(f"{field_name}: значення має бути додатним.")
                        continue
                    if snapshot_date is not None:
                        snapshots.append(
                            build_manual_snapshot(
                                snapshot_date=snapshot_date,
                                source_name="OLX",
                                deal_type=deal_type,
                                property_type=property_type,
                                rooms=rooms,
                                location_scope=bulk_form["location_scope"],
                                listings_count=listings_count,
                            )
                        )

            if not errors:
                counts = save_snapshots_with_counts(snapshots)
                return redirect(
                    url_for(
                        "admin",
                        message=(
                            "Bulk-знімок OLX збережено: "
                            f"створено {counts['created']}, оновлено {counts['updated']}, "
                            f"пропущено порожніх {ignored}."
                        ),
                    )
                )
        else:
            form.update(
                {
                    "source_name": request.form.get("source_name", "").strip(),
                    "deal_type": request.form.get("deal_type", "sale").strip(),
                    "property_type": request.form.get("property_type", "apartments").strip(),
                    "rooms": request.form.get("rooms", "all").strip(),
                    "location_scope": request.form.get("location_scope", "lutsk").strip(),
                    "listings_count": request.form.get("listings_count", "").strip(),
                    "date": request.form.get("date", "").strip(),
                }
            )
            form["source_name"] = "OLX"

            if not form["date"]:
                errors.append("Дата не може бути порожньою.")
            try:
                snapshot_date = date.fromisoformat(form["date"])
            except ValueError:
                snapshot_date = None
                errors.append("Дата має бути у форматі YYYY-MM-DD.")

            try:
                listings_count = int(form["listings_count"])
                if listings_count <= 0:
                    errors.append("Кількість оголошень має бути додатною.")
            except ValueError:
                listings_count = None
                errors.append("Кількість оголошень має бути цілим числом.")

            if not form["source_name"]:
                errors.append("Назва джерела не може бути порожньою.")
            if form["deal_type"] not in DEAL_TYPES:
                errors.append("Невідомий тип угоди.")
            if form["property_type"] not in PROPERTY_TYPES:
                errors.append("Невідомий тип нерухомості.")
            if form["rooms"] not in ROOMS:
                errors.append("Невідоме значення кімнат.")
            if form["location_scope"] not in LOCATION_SCOPES:
                errors.append("Невідоме охоплення локації.")
            if form["property_type"] != "apartments":
                form["rooms"] = "all"

            if not errors and snapshot_date is not None and listings_count is not None:
                snapshot = build_manual_snapshot(
                    snapshot_date=snapshot_date,
                    source_name=form["source_name"],
                    deal_type=form["deal_type"],
                    property_type=form["property_type"],
                    rooms=form["rooms"],
                    location_scope=form["location_scope"],
                    listings_count=listings_count,
                )
                save_snapshot(snapshot)
                return redirect(url_for("admin", message="Ручний рядок збережено."))

    return render_admin_page(
        bulk_form=bulk_form,
        form=form,
        errors=errors,
        message=message,
    )


@app.route("/admin/run-collection", methods=["POST"])
def admin_run_collection():
    admin_response = require_admin_access()
    if admin_response is not None:
        return admin_response

    collection_result, status_code = run_collection_in_web_process()
    if status_code == 200:
        return render_admin_page(
            message="DOM.RIA collection finished.",
            collection_result=collection_result,
        )

    return render_admin_page(
        errors=["DOM.RIA collection failed. See details below."],
        collection_result=collection_result,
    ), status_code


@app.route("/admin/manual/<int:snapshot_id>/delete", methods=["POST"])
def delete_manual_entry(snapshot_id: int):
    admin_response = require_admin_access()
    if admin_response is not None:
        return admin_response

    init_db()
    deleted = delete_manual_snapshot(snapshot_id)
    message = "Ручний рядок видалено." if deleted else "Ручний рядок не знайдено."
    return redirect(url_for("admin", message=message))


@app.route("/api/analytics/trends", methods=["GET"])
def analytics_trends_api():
    init_db()
    sale = build_public_trend("sale")
    rent = build_public_trend("rent")
    update_candidates = [
        value
        for value in (
            sale.get("last_update"),
            rent.get("last_update"),
        )
        if value
    ]
    return jsonify(
        {
            "sale": sale,
            "rent": rent,
            "last_update": max(update_candidates) if update_candidates else None,
        }
    )


@app.route("/api/analytics", methods=["GET"])
def analytics_api():
    category_key = request.args.get("category")
    deal_type = request.args.get("deal_type", "sale")
    property_type = request.args.get("property_type", "apartments")
    rooms = request.args.get("rooms", "all")
    location_scope = request.args.get("location_scope", "lutsk")
    requested_source = request.args.get("data_source", "auto")
    period = request.args.get("period", "30")
    days = PERIODS.get(period, 30)
    rows = fetch_snapshots(
        category_key=category_key,
        days=days,
        deal_type=deal_type,
        property_type=property_type,
        rooms=rooms,
        location_scope=location_scope,
    )
    availability = source_availability(rows)
    selected_source = requested_source if requested_source in (*SOURCE_ORDER, "all") else default_source(availability)

    if selected_source == "all":
        response = build_all_source_series(rows)
    else:
        response = build_single_source_series(
            [row for row in rows if source_key(row) == selected_source],
            {
                "deal_type": deal_type,
                "property_type": property_type,
                "rooms": rooms,
                "location_scope": location_scope,
            },
            selected_source,
        )
        if not response["labels"] and requested_source not in SOURCE_ORDER:
            selected_source = default_source(availability)
            response = build_single_source_series(
                [row for row in rows if source_key(row) == selected_source],
                {
                    "deal_type": deal_type,
                    "property_type": property_type,
                    "rooms": rooms,
                    "location_scope": location_scope,
                },
                selected_source,
            )

    response["selected_source"] = selected_source
    response["source_availability"] = availability
    return jsonify(response)


@app.route("/api/analytics/status", methods=["GET"])
def analytics_status_api():
    return jsonify(domria_status_snapshot([category.key for category in CATEGORIES]))


@app.route("/api/collection/status", methods=["GET"])
def collection_status_api():
    init_db()
    return jsonify(collection_status_summary([category.key for category in CATEGORIES]))


@app.route("/api/collection/run", methods=["POST"])
def collection_run_api():
    token_response = require_collection_token()
    if token_response is not None:
        return token_response

    result, status_code = run_collection_in_web_process()
    return jsonify(result), status_code


@app.route("/api/system/storage", methods=["GET"])
def system_storage_api():
    return jsonify(storage_diagnostics())


@app.route("/api/system/storage-detailed", methods=["GET"])
def system_storage_detailed_api():
    return jsonify(storage_detailed_diagnostics())


@app.route("/api/analytics/debug", methods=["GET"])
def analytics_debug_api():
    if not is_development():
        abort(404)

    init_db()
    return jsonify(analytics_debug_summary())


initialize_application()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
