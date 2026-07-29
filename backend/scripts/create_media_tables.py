#!/usr/bin/env python3
"""Create the media asset and timeline clip tables in PostgreSQL.

Usage:
    python scripts/create_media_tables.py
    python scripts/create_media_tables.py --database-url postgresql://...

The command reads DATABASE_URL from backend/.env unless --database-url is
provided. The SQL script runs in a single transaction and is safe to rerun.
The editor tables (scripts/create_editor_tables.sql) must already exist.
"""

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
SQL_PATH = Path(__file__).with_name("create_media_tables.sql")


def main() -> None:
    load_dotenv(BACKEND_DIR / ".env")

    parser = argparse.ArgumentParser(
        description="Create media_assets and timeline_clips tables."
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL connection URL (defaults to DATABASE_URL).",
    )
    args = parser.parse_args()

    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is not set and --database-url was not provided")

    sql = SQL_PATH.read_text(encoding="utf-8")

    print(f"Applying {SQL_PATH.name}...")
    connection = psycopg2.connect(database_url)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
    finally:
        connection.close()

    print("Media overlay tables created successfully.")


if __name__ == "__main__":
    main()
