
#!/usr/bin/env python3
"""
Sync local `videos` table with objects in S3 for local dev.

- Lists all objects in the S3 bucket
- Extracts user_id from key prefix (format: "{user_id}/{uuid}{ext}")
- Inserts rows into `videos` for any s3_key that doesn't exist locally

Requires:
- AWS credentials configured (aws configure or env vars)
- .env with DATABASE_URL pointing to your local DB
"""

import os
from pathlib import Path
from typing import Optional

import boto3
import psycopg2
from dotenv import load_dotenv

BUCKET_NAME = "emory-hacks-video-bucket"

# ---- Load env (.env in project root) ----
BASE_DIR = Path(__file__).resolve().parent# HackEmory-backend/
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set in environment/.env")

s3 = boto3.client("s3")


def get_db_conn():
    return psycopg2.connect(DATABASE_URL)


def list_all_s3_keys(bucket: str):
    """Yield all object keys in the bucket (handles pagination)."""
    continuation_token: Optional[str] = None

    while True:
        kwargs = {"Bucket": bucket}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            # skip "folders"
            if key.endswith("/"):
                continue
            yield key

        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
        else:
            break


def parse_user_id_from_key(key: str) -> Optional[int]:
    """
    Expect keys like "1/uuid.mp4" or "42/somevideo.mov".
    Return user_id as int or None if it can't be parsed.
    """
    parts = key.split("/", 1)
    if not parts:
        return None
    try:
        return int(parts[0])
    except ValueError:
        return None


def sync_videos():
    conn = get_db_conn()
    conn.autocommit = True
    cur = conn.cursor()

    inserted = 0
    skipped_existing = 0
    skipped_bad = 0

    for key in list_all_s3_keys(BUCKET_NAME):
        user_id = parse_user_id_from_key(key)
        if user_id is None:
            print(f"⚠️  Skipping key without numeric user_id prefix: {key}")
            skipped_bad += 1
            continue

        # Check if this s3_key already exists locally
        cur.execute("SELECT 1 FROM videos WHERE s3_key = %s", (key,))
        if cur.fetchone():
            skipped_existing += 1
            continue

        # Insert minimal row; title/description can be NULL
        cur.execute(
            """
            INSERT INTO videos (user_id, s3_key, video_title, video_description)
            VALUES (%s, %s, NULL, NULL)
            """,
            (user_id, key),
        )
        inserted += 1
        print(f"✅ Inserted video for user_id={user_id}, s3_key={key}")

    cur.close()
    conn.close()

    print("\n=== Sync complete ===")
    print(f"Inserted:         {inserted}")
    print(f"Already existed:  {skipped_existing}")
    print(f"Skipped (bad key): {skipped_bad}")


if __name__ == "__main__":
    sync_videos()
