from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    CATEGORIES,
    DATABASE_PATH,
    DEAL_TYPES,
    LOCATION_SCOPES,
    PROPERTY_TYPES,
    ROOMS,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    data_source TEXT,
    category_key TEXT NOT NULL,
    category_name TEXT NOT NULL,
    deal_type TEXT,
    property_type TEXT,
    rooms TEXT,
    location_scope TEXT,
    url TEXT NOT NULL,
    listings_count INTEGER NOT NULL,
    average_price REAL,
    average_price_per_m2 REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, source, data_source, deal_type, property_type, rooms, location_scope)
);

CREATE INDEX IF NOT EXISTS idx_daily_snapshots_category_date
ON daily_snapshots(category_key, date);

CREATE TABLE IF NOT EXISTS domria_request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    endpoint TEXT NOT NULL,
    category_key TEXT NOT NULL,
    status_code INTEGER,
    success INTEGER NOT NULL,
    error_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_domria_request_log_timestamp
ON domria_request_log(timestamp);

CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    success INTEGER NOT NULL,
    api_requests_made INTEGER NOT NULL DEFAULT 0,
    real_categories TEXT NOT NULL DEFAULT '[]',
    skipped_categories TEXT NOT NULL DEFAULT '[]',
    missing_today TEXT NOT NULL DEFAULT '[]',
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_collection_runs_finished_at
ON collection_runs(finished_at);
"""


def database_path() -> Path:
    return Path(DATABASE_PATH)


def database_absolute_path() -> Path:
    return database_path().expanduser().resolve()


def daily_snapshots_row_count() -> int:
    with get_connection() as connection:
        table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'daily_snapshots'
            LIMIT 1
            """
        ).fetchone()
        if not table_exists:
            return 0
        return int(
            connection.execute("SELECT COUNT(*) FROM daily_snapshots").fetchone()[0]
        )


def database_file_info() -> dict:
    absolute_path = database_absolute_path()
    file_exists = absolute_path.exists()
    stat_result = absolute_path.stat() if file_exists else None
    return {
        "database_path": str(database_path()),
        "absolute_database_path": str(absolute_path),
        "database_file_exists": file_exists,
        "database_file_inode": getattr(stat_result, "st_ino", None) if stat_result else None,
        "database_file_size": stat_result.st_size if stat_result else 0,
        "railway_service_name": os.getenv("RAILWAY_SERVICE_NAME"),
        "railway_volume_name": os.getenv("RAILWAY_VOLUME_NAME"),
        "railway_volume_mount_path": os.getenv("RAILWAY_VOLUME_MOUNT_PATH"),
    }


def storage_diagnostics() -> dict:
    raw_path = database_path()
    absolute_path = database_absolute_path()
    data_dir = Path("/data")
    data_dir_exists = data_dir.exists()
    data_dir_writable = data_dir_exists and data_dir.is_dir() and os.access(data_dir, os.W_OK)
    row_count = 0
    file_exists = False
    file_size = 0

    try:
        init_db()
        file_exists = absolute_path.exists()
        file_size = absolute_path.stat().st_size if file_exists else 0
        row_count = daily_snapshots_row_count()
    except sqlite3.Error:
        row_count = 0

    return {
        "database_path": str(raw_path),
        "absolute_database_path": str(absolute_path),
        "database_file_exists": file_exists,
        "database_file_size": file_size,
        "data_directory_exists": data_dir_exists,
        "data_directory_writable": data_dir_writable,
        "daily_snapshots_row_count": row_count,
    }


def storage_detailed_diagnostics() -> dict:
    init_db()
    details = database_file_info()
    details["daily_snapshots_row_count"] = daily_snapshots_row_count()

    with get_connection() as connection:
        details["latest_daily_snapshots_rows"] = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, date, source, data_source
                FROM daily_snapshots
                ORDER BY created_at DESC, id DESC
                LIMIT 20
                """
            ).fetchall()
        ]
        latest_domria = connection.execute(
            """
            SELECT id, date, source, data_source
            FROM daily_snapshots
            WHERE source = 'DOM.RIA' OR data_source = 'domria'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        latest_olx = connection.execute(
            """
            SELECT id, date, source, data_source
            FROM daily_snapshots
            WHERE lower(source) = 'olx'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    details["latest_domria_row"] = dict(latest_domria) if latest_domria else None
    details["latest_olx_row"] = dict(latest_olx) if latest_olx else None
    return details


def get_connection() -> sqlite3.Connection:
    database_absolute_path().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_absolute_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(SCHEMA)
        ensure_columns(connection)
        ensure_daily_snapshots_unique_key(connection)


def ensure_columns(connection: sqlite3.Connection) -> None:
    migrations = {
        "data_source": "ALTER TABLE daily_snapshots ADD COLUMN data_source TEXT",
        "deal_type": "ALTER TABLE daily_snapshots ADD COLUMN deal_type TEXT",
        "property_type": "ALTER TABLE daily_snapshots ADD COLUMN property_type TEXT",
        "rooms": "ALTER TABLE daily_snapshots ADD COLUMN rooms TEXT",
        "location_scope": "ALTER TABLE daily_snapshots ADD COLUMN location_scope TEXT",
    }
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(daily_snapshots)").fetchall()
    }
    for column, statement in migrations.items():
        if column not in columns:
            connection.execute(statement)
    connection.execute(
        """
        UPDATE daily_snapshots
        SET data_source = 'demo'
        WHERE data_source IS NULL OR data_source = ''
        """
    )
    connection.execute(
        """
        UPDATE daily_snapshots
        SET location_scope = 'lutsk'
        WHERE location_scope IS NULL OR location_scope = ''
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_daily_snapshots_filters_date
        ON daily_snapshots(deal_type, property_type, rooms, location_scope, date)
        """
    )


def ensure_daily_snapshots_unique_key(connection: sqlite3.Connection) -> None:
    columns = [
        row["name"]
        for row in connection.execute("PRAGMA table_info(daily_snapshots)").fetchall()
    ]
    desired_sql = """
        CREATE TABLE daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            source TEXT NOT NULL,
            data_source TEXT,
            category_key TEXT NOT NULL,
            category_name TEXT NOT NULL,
            deal_type TEXT,
            property_type TEXT,
            rooms TEXT,
            location_scope TEXT,
            url TEXT NOT NULL,
            listings_count INTEGER NOT NULL,
            average_price REAL,
            average_price_per_m2 REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, source, data_source, deal_type, property_type, rooms, location_scope)
        )
    """
    desired_columns = [
        "id",
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
        "created_at",
    ]
    if columns == desired_columns:
        indexes = connection.execute("PRAGMA index_list(daily_snapshots)").fetchall()
        for index in indexes:
            if index["origin"] != "u":
                continue
            index_columns = [
                row["name"]
                for row in connection.execute(f"PRAGMA index_info({index['name']})").fetchall()
            ]
            if index_columns == [
                "date",
                "source",
                "data_source",
                "deal_type",
                "property_type",
                "rooms",
                "location_scope",
            ]:
                return

    connection.execute("ALTER TABLE daily_snapshots RENAME TO daily_snapshots_old")
    connection.execute(desired_sql)
    insert_columns = ", ".join(desired_columns)
    connection.execute(
        f"""
        INSERT OR IGNORE INTO daily_snapshots ({insert_columns})
        SELECT {insert_columns}
        FROM daily_snapshots_old
        ORDER BY id
        """
    )
    connection.execute("DROP TABLE daily_snapshots_old")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_daily_snapshots_category_date
        ON daily_snapshots(category_key, date)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_daily_snapshots_filters_date
        ON daily_snapshots(deal_type, property_type, rooms, location_scope, date)
        """
    )


def save_snapshot(snapshot: dict) -> None:
    with get_connection() as connection:
        write_snapshots(connection, [snapshot])


def save_snapshots(snapshots: list[dict]) -> None:
    with get_connection() as connection:
        write_snapshots(connection, snapshots)


def snapshot_exists(connection: sqlite3.Connection, snapshot: dict) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM daily_snapshots
        WHERE date = ?
          AND source = ?
          AND data_source = ?
          AND deal_type = ?
          AND property_type = ?
          AND rooms = ?
          AND location_scope = ?
        LIMIT 1
        """,
        (
            snapshot["date"],
            snapshot["source"],
            snapshot.get("data_source"),
            snapshot.get("deal_type"),
            snapshot.get("property_type"),
            snapshot.get("rooms"),
            snapshot.get("location_scope", "lutsk"),
        ),
    ).fetchone()
    return row is not None


def save_snapshots_with_counts(snapshots: list[dict]) -> dict:
    if not snapshots:
        return {"created": 0, "updated": 0}
    with get_connection() as connection:
        updated = sum(1 for snapshot in snapshots if snapshot_exists(connection, snapshot))
        write_snapshots(connection, snapshots)
        return {"created": len(snapshots) - updated, "updated": updated}


def write_snapshots(connection: sqlite3.Connection, snapshots: list[dict]) -> None:
    connection.executemany(
        """
        INSERT INTO daily_snapshots (
            date,
            source,
            data_source,
            category_key,
            category_name,
            deal_type,
            property_type,
            rooms,
            location_scope,
            url,
            listings_count,
            average_price,
            average_price_per_m2
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, source, data_source, deal_type, property_type, rooms, location_scope)
        DO UPDATE SET
            category_name = excluded.category_name,
            category_key = excluded.category_key,
            url = excluded.url,
            listings_count = excluded.listings_count,
            average_price = excluded.average_price,
            average_price_per_m2 = excluded.average_price_per_m2,
            created_at = CURRENT_TIMESTAMP
        """,
        [
            (
                snapshot["date"],
                snapshot["source"],
                snapshot.get("data_source"),
                snapshot["category_key"],
                snapshot["category_name"],
                snapshot.get("deal_type"),
                snapshot.get("property_type"),
                snapshot.get("rooms"),
                snapshot.get("location_scope", "lutsk"),
                snapshot["url"],
                snapshot["listings_count"],
                snapshot.get("average_price"),
                snapshot.get("average_price_per_m2"),
            )
            for snapshot in snapshots
        ],
    )


def update_demo_counts(counts_by_scope: dict[tuple[str, str, str], int]) -> None:
    if not counts_by_scope:
        return
    with get_connection() as connection:
        connection.executemany(
            """
            UPDATE daily_snapshots
            SET listings_count = ?,
                created_at = CURRENT_TIMESTAMP
            WHERE category_key = ?
              AND date = ?
              AND location_scope = ?
              AND data_source = 'demo'
            """,
            [
                (count, category_key, snapshot_date, location_scope)
                for (category_key, snapshot_date, location_scope), count in counts_by_scope.items()
            ],
        )


def fetch_categories() -> list[dict]:
    return [
        {
            "key": category.key,
            "name": category.name,
            "deal_type": category.deal_type,
            "property_type": category.property_type,
            "rooms": category.rooms,
            "location_scope": category.location_scope,
        }
        for category in CATEGORIES
    ]


def fetch_filter_options() -> dict:
    return {
        "deal_types": [{"key": key, "name": value} for key, value in DEAL_TYPES.items()],
        "property_types": [{"key": key, "name": value} for key, value in PROPERTY_TYPES.items()],
        "rooms": [{"key": key, "name": value} for key, value in ROOMS.items()],
        "location_scopes": [
            {"key": key, "name": value} for key, value in LOCATION_SCOPES.items()
        ],
    }


def fetch_latest_manual_snapshots(limit: int = 50) -> list[dict]:
    query = """
        SELECT
            id,
            date,
            source,
            data_source,
            category_key,
            category_name,
            deal_type,
            property_type,
            rooms,
            location_scope,
            listings_count,
            created_at
        FROM daily_snapshots
        WHERE data_source = 'manual'
        ORDER BY date DESC, created_at DESC, id DESC
        LIMIT ?
    """
    with get_connection() as connection:
        rows = connection.execute(query, (limit,)).fetchall()
        return [dict(row) for row in rows]


def fetch_manual_snapshot_groups(limit: int = 20) -> list[dict]:
    query = """
        SELECT
            date,
            source,
            location_scope,
            COUNT(*) AS rows_count,
            MAX(created_at) AS latest_saved_at
        FROM daily_snapshots
        WHERE data_source = 'manual'
        GROUP BY date, source, location_scope
        ORDER BY date DESC, latest_saved_at DESC, source ASC, location_scope ASC
        LIMIT ?
    """
    with get_connection() as connection:
        rows = connection.execute(query, (limit,)).fetchall()
        return [dict(row) for row in rows]


def fetch_suspicious_manual_snapshots(limit: int = 50) -> list[dict]:
    query = """
        SELECT
            id,
            date,
            source,
            data_source,
            category_key,
            category_name,
            deal_type,
            property_type,
            rooms,
            location_scope,
            listings_count,
            created_at,
            CASE
                WHEN date = '2026-05-29' AND created_at >= '2026-05-31 20:10:00'
                    THEN 'Ймовірний тестовий bulk-знімок Codex'
                WHEN date < substr(created_at, 1, 10)
                    THEN 'Рядок внесено пізніше за дату знімка'
                ELSE 'Потрібна ручна перевірка'
            END AS suspicion_reason
        FROM daily_snapshots
        WHERE data_source = 'manual'
          AND lower(source) = 'olx'
          AND (
            (date = '2026-05-29' AND created_at >= '2026-05-31 20:10:00')
            OR date < substr(created_at, 1, 10)
          )
        ORDER BY date DESC, created_at DESC, id DESC
        LIMIT ?
    """
    with get_connection() as connection:
        rows = connection.execute(query, (limit,)).fetchall()
        return [dict(row) for row in rows]


def delete_manual_snapshot(snapshot_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM daily_snapshots
            WHERE id = ?
              AND data_source = 'manual'
            """,
            (snapshot_id,),
        )
        return cursor.rowcount > 0


def fetch_snapshots(
    category_key: str | None = None,
    days: int | None = None,
    deal_type: str | None = None,
    property_type: str | None = None,
    rooms: str | None = None,
    location_scope: str | None = None,
    source_filter: str | None = None,
) -> list[dict]:
    filters = []
    params = []

    if category_key and category_key != "all":
        filters.append("category_key = ?")
        params.append(category_key)
    else:
        if deal_type and deal_type != "all":
            filters.append("deal_type = ?")
            params.append(deal_type)

        if property_type and property_type != "all":
            filters.append("property_type = ?")
            params.append(property_type)

        if rooms and rooms != "all":
            filters.append("rooms = ?")
            params.append(rooms)
        elif property_type == "apartments":
            filters.append("rooms = ?")
            params.append("all")
        else:
            filters.append("rooms = ?")
            params.append("all")

        if location_scope and location_scope != "all":
            filters.append("location_scope = ?")
            params.append(location_scope)
        else:
            filters.append("location_scope = ?")
            params.append("lutsk")

    if source_filter == "olx":
        filters.append("data_source = ?")
        params.append("manual")
        filters.append("lower(source) = ?")
        params.append("olx")
    elif source_filter == "domria":
        filters.append("data_source = ?")
        params.append("domria")
    elif source_filter == "demo":
        filters.append("data_source = ?")
        params.append("demo")

    if days:
        filters.append("date >= date('now', ?)")
        params.append(f"-{days - 1} days")

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT
            date,
            source,
            data_source,
            category_key,
            category_name,
            deal_type,
            property_type,
            rooms,
            location_scope,
            url,
            listings_count,
            average_price,
            average_price_per_m2,
            created_at
        FROM daily_snapshots
        {where_clause}
        ORDER BY date ASC, category_name ASC, source ASC, created_at DESC
    """

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def latest_snapshot(category_key: str | None = None) -> dict | None:
    filters = []
    params = []

    if category_key and category_key != "all":
        filters.append("category_key = ?")
        params.append(category_key)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = f"""
        SELECT *
        FROM daily_snapshots
        {where_clause}
        ORDER BY date DESC, created_at DESC
        LIMIT 1
    """

    with get_connection() as connection:
        row = connection.execute(query, params).fetchone()
        return dict(row) if row else None


def latest_real_snapshot_for_category(category_key: str) -> dict | None:
    query = """
        SELECT *
        FROM daily_snapshots
        WHERE category_key = ?
          AND source = 'DOM.RIA'
          AND data_source = 'domria'
        ORDER BY date DESC, created_at DESC
        LIMIT 1
    """
    with get_connection() as connection:
        row = connection.execute(query, (category_key,)).fetchone()
        return dict(row) if row else None


def real_snapshot_dates_for_category(category_key: str) -> set[str]:
    query = """
        SELECT date
        FROM daily_snapshots
        WHERE category_key = ?
          AND source = 'DOM.RIA'
          AND data_source = 'domria'
    """
    with get_connection() as connection:
        rows = connection.execute(query, (category_key,)).fetchall()
        return {row["date"] for row in rows}


def find_today_domria_snapshot(
    *,
    deal_type: str,
    property_type: str,
    rooms: str,
    location_scope: str = "lutsk",
) -> dict | None:
    query = """
        SELECT *
        FROM daily_snapshots
        WHERE date = date('now')
          AND source = 'DOM.RIA'
          AND data_source = 'domria'
          AND deal_type = ?
          AND property_type = ?
          AND rooms = ?
          AND location_scope = ?
        ORDER BY created_at DESC
        LIMIT 1
    """
    with get_connection() as connection:
        row = connection.execute(
            query, (deal_type, property_type, rooms, location_scope)
        ).fetchone()
        return dict(row) if row else None


def log_domria_request(
    *,
    endpoint: str,
    category_key: str,
    status_code: int | None,
    success: bool,
    error_reason: str | None = None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO domria_request_log (
                endpoint,
                category_key,
                status_code,
                success,
                error_reason
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                endpoint,
                category_key,
                status_code,
                1 if success else 0,
                error_reason,
            ),
        )


def count_domria_requests_last_hour() -> int:
    query = """
        SELECT COUNT(*)
        FROM domria_request_log
        WHERE timestamp >= datetime('now', '-60 minutes')
    """
    with get_connection() as connection:
        return int(connection.execute(query).fetchone()[0])


def categories_collected_today(category_keys: list[str]) -> list[str]:
    if not category_keys:
        return []
    placeholders = ",".join("?" for _ in category_keys)
    query = f"""
        SELECT DISTINCT category_key
        FROM daily_snapshots
        WHERE date = date('now')
          AND source = 'DOM.RIA'
          AND data_source = 'domria'
          AND category_key IN ({placeholders})
        ORDER BY category_key
    """
    with get_connection() as connection:
        rows = connection.execute(query, category_keys).fetchall()
        return [row[0] for row in rows]


def domria_status_snapshot(category_keys: list[str]) -> dict:
    collected = categories_collected_today(category_keys)
    missing = [key for key in category_keys if key not in collected]
    with get_connection() as connection:
        domria_row = connection.execute(
            """
            SELECT created_at
            FROM daily_snapshots
            WHERE source = 'DOM.RIA'
              AND data_source = 'domria'
            ORDER BY date DESC, created_at DESC
            LIMIT 1
            """
        ).fetchone()
        olx_row = connection.execute(
            """
            SELECT created_at
            FROM daily_snapshots
            WHERE lower(source) = 'olx'
              AND data_source = 'manual'
            ORDER BY date DESC, created_at DESC
            LIMIT 1
            """
        ).fetchone()
    return {
        "collected_today": collected,
        "missing_today": missing,
        "last_successful_update": domria_row["created_at"] if domria_row else None,
        "olx_last_successful_update": olx_row["created_at"] if olx_row else None,
    }


def log_collection_run(
    *,
    started_at: str,
    finished_at: str,
    success: bool,
    api_requests_made: int,
    real_categories: list[str] | None = None,
    skipped_categories: list[str] | None = None,
    missing_today: list[str] | None = None,
    last_error: str | None = None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO collection_runs (
                started_at,
                finished_at,
                success,
                api_requests_made,
                real_categories,
                skipped_categories,
                missing_today,
                last_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                started_at,
                finished_at,
                1 if success else 0,
                api_requests_made,
                json.dumps(real_categories or [], ensure_ascii=False),
                json.dumps(skipped_categories or [], ensure_ascii=False),
                json.dumps(missing_today or [], ensure_ascii=False),
                last_error,
            ),
        )


def latest_collection_run() -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM collection_runs
            ORDER BY finished_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    for key in ("real_categories", "skipped_categories", "missing_today"):
        try:
            result[key] = json.loads(result.get(key) or "[]")
        except json.JSONDecodeError:
            result[key] = []
    result["success"] = bool(result["success"])
    return result


def collection_status_summary(category_keys: list[str]) -> dict:
    collected = categories_collected_today(category_keys)
    missing = [key for key in category_keys if key not in collected]
    latest_run = latest_collection_run()
    with get_connection() as connection:
        latest_real_row = connection.execute(
            """
            SELECT created_at
            FROM daily_snapshots
            WHERE source = 'DOM.RIA'
              AND data_source = 'domria'
            ORDER BY date DESC, created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    return {
        "last_domria_run_time": latest_run["finished_at"] if latest_run else None,
        "last_successful_update": latest_real_row["created_at"] if latest_real_row else None,
        "categories_collected_today": collected,
        "categories_missing_today": missing,
        "last_error": latest_run["last_error"] if latest_run else None,
        "requests_used_last_hour": count_domria_requests_last_hour(),
        "last_run": latest_run,
    }


def analytics_debug_summary() -> dict:
    with get_connection() as connection:
        return {
            "available_sources": [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT data_source, source, COUNT(*) AS row_count
                    FROM daily_snapshots
                    GROUP BY data_source, source
                    ORDER BY data_source, source
                    """
                ).fetchall()
            ],
            "available_dates": [
                row["date"]
                for row in connection.execute(
                    """
                    SELECT DISTINCT date
                    FROM daily_snapshots
                    ORDER BY date
                    """
                ).fetchall()
            ],
            "row_counts_by_source": [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT data_source, source, COUNT(*) AS row_count
                    FROM daily_snapshots
                    GROUP BY data_source, source
                    ORDER BY data_source, source
                    """
                ).fetchall()
            ],
            "row_counts_by_date": [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT date, COUNT(*) AS row_count
                    FROM daily_snapshots
                    GROUP BY date
                    ORDER BY date
                    """
                ).fetchall()
            ],
            "manual_row_count": connection.execute(
                """
                SELECT COUNT(*)
                FROM daily_snapshots
                WHERE data_source = 'manual'
                """
            ).fetchone()[0],
            "domria_row_count": connection.execute(
                """
                SELECT COUNT(*)
                FROM daily_snapshots
                WHERE data_source = 'domria'
                """
            ).fetchone()[0],
        }


def print_rows(title: str, rows: list[sqlite3.Row]) -> None:
    print(title)
    if not rows:
        print("- (none)")
        return
    for row in rows:
        print("- " + " | ".join(f"{key}={row[key]}" for key in row.keys()))


def audit_database() -> None:
    init_db()
    with get_connection() as connection:
        print_rows(
            "Total rows by date:",
            connection.execute(
                """
                SELECT date, COUNT(*) AS row_count
                FROM daily_snapshots
                GROUP BY date
                ORDER BY date DESC
                """
            ).fetchall(),
        )
        print_rows(
            "Total rows by source/data_source:",
            connection.execute(
                """
                SELECT source, data_source, COUNT(*) AS row_count, MIN(date) AS first_date, MAX(date) AS latest_date
                FROM daily_snapshots
                GROUP BY source, data_source
                ORDER BY source, data_source
                """
            ).fetchall(),
        )
        print_rows(
            "Total rows by source_name:",
            connection.execute(
                """
                SELECT source AS source_name, COUNT(*) AS row_count, MIN(date) AS first_date, MAX(date) AS latest_date
                FROM daily_snapshots
                GROUP BY source
                ORDER BY source
                """
            ).fetchall(),
        )
        print_rows(
            "Total rows by location_scope:",
            connection.execute(
                """
                SELECT location_scope, COUNT(*) AS row_count, MIN(date) AS first_date, MAX(date) AS latest_date
                FROM daily_snapshots
                GROUP BY location_scope
                ORDER BY location_scope
                """
            ).fetchall(),
        )
        print_rows(
            "Latest 5 rows for DOM.RIA:",
            connection.execute(
                """
                SELECT date, source, data_source, category_key, deal_type, property_type, rooms, location_scope, listings_count, created_at
                FROM daily_snapshots
                WHERE source = 'DOM.RIA' AND data_source = 'domria'
                ORDER BY date DESC, created_at DESC, id DESC
                LIMIT 5
                """
            ).fetchall(),
        )
        print_rows(
            "Latest 5 rows for OLX/manual:",
            connection.execute(
                """
                SELECT date, source, data_source, category_key, deal_type, property_type, rooms, location_scope, listings_count, created_at
                FROM daily_snapshots
                WHERE lower(source) = 'olx' AND data_source = 'manual'
                ORDER BY date DESC, created_at DESC, id DESC
                LIMIT 5
                """
            ).fetchall(),
        )
        print("Dates available for each active category:")
        for category in CATEGORIES:
            rows = connection.execute(
                """
                SELECT data_source, source, GROUP_CONCAT(date, ', ') AS dates, COUNT(*) AS row_count
                FROM (
                    SELECT DISTINCT data_source, source, date
                    FROM daily_snapshots
                    WHERE deal_type = ?
                      AND property_type = ?
                      AND rooms = ?
                      AND location_scope = ?
                    ORDER BY date
                )
                GROUP BY data_source, source
                ORDER BY data_source, source
                """,
                (
                    category.deal_type,
                    category.property_type,
                    category.rooms,
                    category.location_scope,
                ),
            ).fetchall()
            print(f"- {category.key} ({category.location_scope}):")
            if not rows:
                print("  - (none)")
            for row in rows:
                print(
                    f"  - source={row['source']} | data_source={row['data_source']} | "
                    f"row_count={row['row_count']} | dates={row['dates']}"
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize or audit the SQLite database.")
    parser.add_argument("--audit", action="store_true", help="Print analytics database diagnostics.")
    args = parser.parse_args()

    if args.audit:
        audit_database()
    else:
        init_db()
        print(f"Database initialized at {DATABASE_PATH}")
