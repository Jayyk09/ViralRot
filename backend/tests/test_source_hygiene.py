"""Repository-wide checks that keep removed provider paths from silently rotting."""

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_all_tracked_backend_python_sources_compile():
    failures = []
    for path in BACKEND_DIR.rglob("*.py"):
        if any(part in {"venv", "__pycache__", ".pytest_cache"} for part in path.parts):
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (SyntaxError, UnicodeError) as exc:
            failures.append(f"{path.relative_to(BACKEND_DIR)}: {exc}")

    assert not failures, "Backend source compilation failed:\n" + "\n".join(failures)


def test_removed_generation_providers_do_not_return():
    source_paths = [
        path
        for path in BACKEND_DIR.rglob("*.py")
        if "venv" not in path.parts and "tests" not in path.parts
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)

    assert "GEMINI_API_KEY" not in combined
    assert "google.genai" not in combined
    assert "ELEVENLABS_API_KEY" not in combined
    assert "elevenLabs" not in combined
    assert "collection_service" not in combined
    assert "get_collection_videos" not in combined
    assert "generate_video_from_dialogue" not in combined
    assert not (BACKEND_DIR / "services" / "account_service.py").exists()
    assert not (BACKEND_DIR / "services" / "collection_service.py").exists()
    assert not (BACKEND_DIR / "backend_pipeline" / "generate_video.py").exists()
    assert not (BACKEND_DIR / "sync_db.py").exists()
