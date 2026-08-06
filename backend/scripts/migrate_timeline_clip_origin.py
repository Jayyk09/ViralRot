#!/usr/bin/env python3
"""Add manual/generated origin tracking to timeline clips in PostgreSQL.

Usage:
    python scripts/migrate_timeline_clip_origin.py
    python scripts/migrate_timeline_clip_origin.py --database-url postgresql://...

The command reads DATABASE_URL from backend/.env unless --database-url is
provided. The SQL migration runs in a single transaction and is safe to rerun.
The media tables (scripts/create_media_tables.sql) must already exist.
"""

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
SQL_PATH = Path(__file__).with_name("migrate_timeline_clip_origin.sql")


def apply_migration(connection, sql_path: Path = SQL_PATH) -> None:
    """Apply the migration on an existing connection.

    Exposing this small seam lets integration tests select an isolated schema
    on a real PostgreSQL connection. The SQL owns its transaction so it remains
    directly runnable by local tooling as well.
    """
    sql = sql_path.read_text(encoding="utf-8")
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
    except BaseException:
        connection.rollback()
        raise


def main() -> None:
    load_dotenv(BACKEND_DIR / ".env")

    parser = argparse.ArgumentParser(
        description="Add origin tracking to timeline_clips."
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL connection URL (defaults to DATABASE_URL).",
    )
    args = parser.parse_args()

    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is not set and --database-url was not provided")

    print(f"Applying {SQL_PATH.name}...")
    connection = psycopg2.connect(database_url)
    try:
        apply_migration(connection)
    finally:
        connection.close()

    print("Timeline clip origin migration applied successfully.")


if __name__ == "__main__":
    main()
