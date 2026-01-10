# db.py
import os
from typing import Optional

from dotenv import load_dotenv
import psycopg2
from psycopg2.extensions import connection as PGConnection

load_dotenv()

DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

def get_db_conn() -> PGConnection:
    """
    Return a psycopg2 connection to the Neon Postgres DB.
    Uses DATABASE_URL env var.
    """
    # psycopg2 understands a full postgres:// URL DSN
    conn = psycopg2.connect(DATABASE_URL)
    return conn
