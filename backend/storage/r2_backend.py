"""Cloudflare R2 storage backend implementation (S3-compatible API via boto3)."""
import os
from typing import BinaryIO, Dict, Any, List, Iterator

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .base import StorageBackend


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


class R2StorageBackend(StorageBackend):
    """Cloudflare R2 storage implementation for production use."""

    def __init__(
        self,
        bucket_name: str,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
    ):
        """
        Initialize R2 backend.

        Args:
            bucket_name: R2 bucket name
            account_id: Cloudflare account ID (forms the endpoint URL)
            access_key_id: R2 API token access key ID
            secret_access_key: R2 API token secret access key
        """
        # A dedicated background bucket usually stores clips at its root. Set
        # R2_BACKGROUND_PREFIX=backgrounds/ when using a shared bucket instead.
        self.background_prefix = os.getenv("R2_BACKGROUND_PREFIX", "").strip("/")
        if self.background_prefix:
            self.background_prefix += "/"
        self.bucket = bucket_name
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        self.s3 = boto3.client(
            "s3",
            region_name="auto",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                # R2 rejects boto3's default streaming CRC32 checksums
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                s3={"addressing_style": "path"},
            ),
        )
        print(f"📦 R2 Storage initialized: bucket='{bucket_name}'")

    @property
    def backend_name(self) -> str:
        return f"R2 ({self.bucket})"

    def upload(self, file_obj: BinaryIO, key: str, metadata: Dict[str, Any]) -> str:
        """Upload file to R2."""
        file_obj.seek(0)  # Ensure we're at start of file

        extra_args = {}
        if "content_type" in metadata:
            extra_args["ContentType"] = metadata["content_type"]

        self.s3.upload_fileobj(
            Fileobj=file_obj,
            Bucket=self.bucket,
            Key=key,
            ExtraArgs=extra_args if extra_args else None
        )

        return key

    def generate_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for R2 object."""
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in
        )

    def generate_background_urls(self):
        response = self.s3.list_objects_v2(
            Bucket=self.bucket,
            Prefix=self.background_prefix,
        )

        items = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/") or not key.lower().endswith(".mp4"):
                continue
            url = self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=3600
            )
            items.append({
                "id": key.split("/")[-1].replace(".mp4", ""),
                "url": url
                })
        return items

    def delete(self, key: str) -> bool:
        """Delete file from R2."""
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def exists(self, key: str) -> bool:
        """Check if file exists in R2."""
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def get_size(self, key: str) -> int:
        """Get file size from R2."""
        try:
            response = self.s3.head_object(Bucket=self.bucket, Key=key)
            return response["ContentLength"]
        except ClientError as e:
            raise FileNotFoundError(f"Key not found: {key}") from e

    def download(self, key: str, dest_path: str) -> str:
        """Download an object to a local file path."""
        self.s3.download_file(self.bucket, key, dest_path)
        return dest_path

    def iter_keys(self, prefix: str = "") -> Iterator[str]:
        """Yield all object keys under a prefix (handles pagination)."""
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                yield key

    def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """List files in R2 bucket."""
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=limit
            )

            files = []
            for obj in response.get("Contents", []):
                files.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"],
                })

            return files
        except ClientError:
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get R2 bucket statistics."""
        total_files = 0
        total_size = 0

        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket):
                for obj in page.get("Contents", []):
                    total_files += 1
                    total_size += obj["Size"]
        except ClientError as e:
            print(f"Warning: Could not get R2 stats: {e}")

        return {
            "backend": self.backend_name,
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_human": _format_size(total_size),
        }
