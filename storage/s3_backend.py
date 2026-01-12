"""AWS S3 storage backend implementation."""
import os
from typing import BinaryIO, Dict, Any, List
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from .base import StorageBackend


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


class S3StorageBackend(StorageBackend):
    """AWS S3 storage implementation for production use."""
    
    def __init__(self, bucket_name: str, region: str = "us-east-2"):
        """
        Initialize S3 backend.
        
        Args:
            bucket_name: S3 bucket name
            region: AWS region (default: us-east-2)
        """
        self.bucket = bucket_name
        self.region = region
        self.s3 = boto3.client("s3", region_name=region)
        print(f"📦 S3 Storage initialized: bucket='{bucket_name}', region='{region}'")
    
    @property
    def backend_name(self) -> str:
        return f"S3 ({self.bucket})"
    
    def upload(self, file_obj: BinaryIO, key: str, metadata: Dict[str, Any]) -> str:
        """Upload file to S3."""
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
        """Generate presigned URL for S3 object."""
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in
        )
    
    def delete(self, key: str) -> bool:
        """Delete file from S3."""
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
    
    def exists(self, key: str) -> bool:
        """Check if file exists in S3."""
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
    
    def get_size(self, key: str) -> int:
        """Get file size from S3."""
        try:
            response = self.s3.head_object(Bucket=self.bucket, Key=key)
            return response["ContentLength"]
        except ClientError as e:
            raise FileNotFoundError(f"Key not found: {key}") from e
    
    def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """List files in S3 bucket."""
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
        """Get S3 bucket statistics."""
        total_files = 0
        total_size = 0
        
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket):
                for obj in page.get("Contents", []):
                    total_files += 1
                    total_size += obj["Size"]
        except ClientError as e:
            print(f"Warning: Could not get S3 stats: {e}")
        
        return {
            "backend": self.backend_name,
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_human": _format_size(total_size),
        }
