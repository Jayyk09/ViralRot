#!/usr/bin/env python3
"""
Seed pipeline assets into the storage bucket.

Uploads:
- assets/videos/*.mp4      -> backgrounds/<name>.mp4
- assets/characters/*.png  -> assets/characters/<name>.png

Usage:
    python scripts/seed_assets.py [--dry-run]

Uses the storage backend from .env (STORAGE_BACKEND / R2_* vars).
"""
import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

from storage import get_storage_backend  # noqa: E402

SEED_MAP = [
    (BACKEND_DIR / "assets" / "videos", "*.mp4", "backgrounds", "video/mp4"),
    (BACKEND_DIR / "assets" / "characters", "*.png", "assets/characters", "image/png"),
]


def main():
    parser = argparse.ArgumentParser(description="Upload local pipeline assets to storage.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be uploaded")
    args = parser.parse_args()

    storage = get_storage_backend()
    print(f"Seeding assets to {storage.backend_name}\n")

    uploaded = 0
    skipped = 0

    for local_dir, pattern, key_prefix, content_type in SEED_MAP:
        if not local_dir.exists():
            print(f"⚠️  Skipping missing directory: {local_dir}")
            continue

        for file_path in sorted(local_dir.glob(pattern)):
            key = f"{key_prefix}/{file_path.name}"

            if storage.exists(key):
                print(f"⏭️  Exists, skipping: {key}")
                skipped += 1
                continue

            if args.dry_run:
                print(f"🔍 Would upload: {file_path} -> {key}")
                uploaded += 1
                continue

            print(f"⬆️  Uploading: {file_path.name} -> {key}")
            with open(file_path, "rb") as f:
                storage.upload(f, key, {"content_type": content_type})
            uploaded += 1

    print(f"\n=== Done ===")
    print(f"Uploaded: {uploaded}{' (dry run)' if args.dry_run else ''}")
    print(f"Skipped (already exist): {skipped}")


if __name__ == "__main__":
    main()
