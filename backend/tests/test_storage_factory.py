"""Tests for storage backend factory."""
import pytest

from storage.factory import (
    get_background_storage_backend,
    get_storage_backend,
    reset_storage_backend,
)
from storage.r2_backend import R2StorageBackend
from storage.local_backend import LocalStorageBackend


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset cached backend before and after each test."""
    reset_storage_backend()
    yield
    reset_storage_backend()


@pytest.fixture
def r2_env(monkeypatch):
    """Set all required R2 environment variables."""
    monkeypatch.setenv("R2_ACCOUNT_ID", "test-account-id")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret-key")
    monkeypatch.setenv("R2_BACKGROUND_BUCKET_NAME", "test-backgrounds")
    monkeypatch.setenv("R2_PROJECT_MEDIA_BUCKET_NAME", "test-projects")


class TestStorageFactory:
    def test_r2_backend_created_with_env_vars(self, r2_env):
        backend = get_storage_backend(backend_type="r2", force_new=True)
        assert isinstance(backend, R2StorageBackend)
        assert backend.bucket == "test-projects"
        assert backend.backend_name == "R2 (test-projects)"
        assert (
            backend.s3.meta.endpoint_url
            == "https://test-account-id.r2.cloudflarestorage.com"
        )

    def test_r2_backend_missing_vars_raises(self, r2_env, monkeypatch):
        monkeypatch.delenv("R2_ACCOUNT_ID")
        monkeypatch.delenv("R2_PROJECT_MEDIA_BUCKET_NAME")
        with pytest.raises(ValueError) as exc_info:
            get_storage_backend(backend_type="r2", force_new=True)
        assert "R2_ACCOUNT_ID" in str(exc_info.value)
        assert "R2_PROJECT_MEDIA_BUCKET_NAME" in str(exc_info.value)

    def test_default_backend_from_env(self, r2_env, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "r2")
        backend = get_storage_backend(force_new=True)
        assert isinstance(backend, R2StorageBackend)

    def test_background_backend_uses_dedicated_bucket(self, r2_env, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "r2")
        backend = get_background_storage_backend(force_new=True)
        assert isinstance(backend, R2StorageBackend)
        assert backend.bucket == "test-backgrounds"

    def test_background_and_project_buckets_must_be_different(self, r2_env, monkeypatch):
        monkeypatch.setenv("STORAGE_BACKEND", "r2")
        monkeypatch.setenv("R2_BACKGROUND_BUCKET_NAME", "same-bucket")
        monkeypatch.setenv("R2_PROJECT_MEDIA_BUCKET_NAME", "same-bucket")
        with pytest.raises(ValueError, match="must be different"):
            get_background_storage_backend(force_new=True)

    def test_local_backend(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOCAL_STORAGE_DIR", str(tmp_path / "videos"))
        backend = get_storage_backend(backend_type="local", force_new=True)
        assert isinstance(backend, LocalStorageBackend)

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown storage backend"):
            get_storage_backend(backend_type="s3", force_new=True)
