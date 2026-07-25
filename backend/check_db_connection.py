#!/usr/bin/env python3
"""
Standalone script to verify DATABASE_URL in .env is reachable and working.

Usage:
    python check_db_connection.py

Exits 0 on success, 1 on failure.
"""
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def redact(url: str) -> str:
    """Hide credentials when printing the URL back for confirmation."""
    if "@" not in url:
        return url
    scheme_and_creds, rest = url.split("@", 1)
    if "//" not in scheme_and_creds:
        return url
    scheme, _creds = scheme_and_creds.split("//", 1)
    return f"{scheme}//<redacted>@{rest}"


def main() -> int:
    if not DATABASE_URL:
        print("FAIL: DATABASE_URL is not set in .env")
        return 1

    print(f"Testing connection to: {redact(DATABASE_URL)}")

    try:
        import psycopg2
    except ImportError:
        print("FAIL: psycopg2 is not installed. Run: pip install -r requirements.txt")
        return 1

    start = time.monotonic()
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except Exception as e:
        print(f"FAIL: could not connect - {type(e).__name__}: {e}")
        return 1

    elapsed = time.monotonic() - start

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]

            cur.execute("SELECT current_database(), current_user;")
            dbname, dbuser = cur.fetchone()

            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                LIMIT 20;
                """
            )
            tables = [row[0] for row in cur.fetchall()]

        print(f"OK: connected in {elapsed:.2f}s")
        print(f"  database: {dbname}")
        print(f"  user:     {dbuser}")
        print(f"  server:   {version.splitlines()[0]}")
        print(f"  tables ({len(tables)} shown, public schema): {', '.join(tables) if tables else '(none found)'}")
        return 0
    except Exception as e:
        print(f"FAIL: connected but query failed - {type(e).__name__}: {e}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
