"""Focused tests for timeline-native image overlays (assets, clips, export)."""

import os
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from services.media_service import (
    MAX_UPLOAD_BYTES,
    MediaAssetService,
    MediaValidationError,
    normalize_image,
)
from services.repositories.editor_repository import (
    EditorClipValidationError,
    EditorCompositionRequiredError,
    EditorProjectNotFoundError,
    EditorRevisionConflictError,
    MediaAssetInUseError,
    clamp_clip_window,
    validate_clip_geometry,
)

PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
ASSET_ID = UUID("55555555-5555-4555-8555-555555555555")
CLIP_ID = UUID("66666666-6666-4666-8666-666666666666")


@pytest.fixture
def client():
    from main import app

    return TestClient(app)


# ============ Image helpers ============

def _png_bytes(width=100, height=80):
    buf = BytesIO()
    Image.new("RGBA", (width, height), (255, 0, 0, 128)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes_with_orientation(width=120, height=60, orientation=6):
    image = Image.new("RGB", (width, height), "blue")
    exif = image.getexif()
    exif[274] = orientation  # EXIF Orientation tag
    buf = BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _gif_bytes():
    buf = BytesIO()
    Image.new("P", (10, 10)).save(buf, format="GIF")
    return buf.getvalue()


def _animated_webp_bytes():
    frames = [Image.new("RGB", (10, 10), color) for color in ("red", "blue")]
    buf = BytesIO()
    frames[0].save(
        buf, format="WEBP", save_all=True, append_images=frames[1:], duration=100
    )
    return buf.getvalue()


# ============ Normalization ============

def test_normalize_image_produces_single_webp_with_same_dimensions():
    webp_bytes, width, height = normalize_image(_png_bytes(100, 80))

    output = Image.open(BytesIO(webp_bytes))
    assert output.format == "WEBP"
    assert (width, height) == (100, 80)
    assert output.size == (100, 80)
    assert not getattr(output, "is_animated", False)


def test_normalize_image_applies_exif_orientation_and_strips_metadata():
    # Orientation 6 = rotate 90: a 120x60 source must become 60x120 pixels
    webp_bytes, width, height = normalize_image(
        _jpeg_bytes_with_orientation(120, 60, orientation=6)
    )

    assert (width, height) == (60, 120)
    output = Image.open(BytesIO(webp_bytes))
    assert output.size == (60, 120)
    assert dict(output.getexif()) == {}  # metadata discarded


def test_normalize_image_preserves_alpha():
    webp_bytes, _, _ = normalize_image(_png_bytes())
    assert Image.open(BytesIO(webp_bytes)).mode == "RGBA"


def test_normalize_image_rejects_unsupported_format():
    with pytest.raises(MediaValidationError, match="only PNG, JPEG, and WebP"):
        normalize_image(_gif_bytes())


def test_normalize_image_rejects_animated_webp():
    with pytest.raises(MediaValidationError, match="Animated"):
        normalize_image(_animated_webp_bytes())


def test_normalize_image_rejects_non_image_bytes():
    with pytest.raises(MediaValidationError, match="not a valid image"):
        normalize_image(b"definitely not an image")


def test_normalize_image_rejects_oversized_dimensions():
    with pytest.raises(MediaValidationError, match="4096x4096"):
        normalize_image(_png_bytes(1, 4097))


def test_normalize_image_rejects_oversized_payload():
    with pytest.raises(MediaValidationError, match="maximum size"):
        normalize_image(b"0" * (MAX_UPLOAD_BYTES + 1))


# ============ Upload lifecycle (asset row only after storage succeeds) ============

def test_upload_image_uploads_before_insert_and_returns_asset():
    storage = MagicMock()
    repository = MagicMock()
    repository.create_media_asset.return_value = {"id": str(ASSET_ID)}
    service = MediaAssetService(repository=repository, storage=storage)

    asset = service.upload_image(PROJECT_ID, 1, _png_bytes(), "a.png", "image/png")

    assert asset == {"id": str(ASSET_ID)}
    storage.upload.assert_called_once()
    _, storage_key, metadata = storage.upload.call_args.args
    assert storage_key.startswith(f"editor/1/{PROJECT_ID}/images/")
    assert storage_key.endswith(".webp")
    assert metadata == {"content_type": "image/webp"}
    kwargs = repository.create_media_asset.call_args.kwargs
    assert kwargs["storage_key"] == storage_key
    assert kwargs["content_type"] == "image/webp"
    assert (kwargs["width_px"], kwargs["height_px"]) == (100, 80)
    storage.delete.assert_not_called()


def test_upload_image_compensates_storage_when_db_insert_fails():
    storage = MagicMock()
    repository = MagicMock()
    repository.create_media_asset.side_effect = RuntimeError("db down")
    service = MediaAssetService(repository=repository, storage=storage)

    with pytest.raises(RuntimeError, match="db down"):
        service.upload_image(PROJECT_ID, 1, _png_bytes(), "a.png", "image/png")

    uploaded_key = storage.upload.call_args.args[1]
    storage.delete.assert_called_once_with(uploaded_key)


def test_upload_image_rejects_disallowed_declared_content_type():
    storage = MagicMock()
    service = MediaAssetService(repository=MagicMock(), storage=storage)

    with pytest.raises(MediaValidationError, match="content type"):
        service.upload_image(PROJECT_ID, 1, _png_bytes(), "a.svg", "image/svg+xml")

    storage.upload.assert_not_called()


# ============ Clip timing/geometry validation ============

def test_clamp_clip_window_clamps_end_to_composition_duration():
    assert clamp_clip_window(1000, 4000, 3500) == (1000, 3500)
    assert clamp_clip_window(0, 3000, 10000) == (0, 3000)


def test_clamp_clip_window_rejects_start_beyond_duration():
    with pytest.raises(EditorClipValidationError, match="beyond the narration"):
        clamp_clip_window(5000, 8000, 5000)


def test_clamp_clip_window_rejects_inverted_window():
    with pytest.raises(EditorClipValidationError, match="greater than start_ms"):
        clamp_clip_window(2000, 2000, 5000)


def test_clamp_clip_window_rejects_sub_half_second_window():
    with pytest.raises(EditorClipValidationError, match="0.5 seconds"):
        clamp_clip_window(4800, 5200, 5000)


def test_validate_clip_geometry():
    validate_clip_geometry(0.25, 0.25, 0.5)
    validate_clip_geometry(0.834, 0.0, 0.1666667)  # float rounding tolerance
    with pytest.raises(EditorClipValidationError):
        validate_clip_geometry(0.8, 0.2, 0.5)  # off-frame right
    with pytest.raises(EditorClipValidationError):
        validate_clip_geometry(0.2, 1.2, 0.5)
    with pytest.raises(EditorClipValidationError):
        validate_clip_geometry(0.2, 0.2, 0.0)
    with pytest.raises(EditorClipValidationError, match="vertically"):
        validate_clip_geometry(0.1, 0.8, 0.5, 500, 1000)


# ============ API contract ============

def test_upload_asset_endpoint_returns_created_asset(client):
    project = {"id": PROJECT_ID}
    with (
        patch("main.editor_repository.get_project", return_value=project),
        patch("main.MediaAssetService") as service_cls,
    ):
        service = service_cls.return_value
        service.upload_image.return_value = {
            "id": str(ASSET_ID),
            "storage_key": f"editor/1/{PROJECT_ID}/images/{ASSET_ID}.webp",
            "original_filename": "diagram.png",
            "content_type": "image/webp",
            "byte_size": 1234,
            "width_px": 100,
            "height_px": 80,
            "status": "ready",
        }
        service.storage.generate_url.return_value = "https://storage.example/a.webp"

        response = client.post(
            f"/editor/projects/{PROJECT_ID}/assets",
            files={"file": ("diagram.png", _png_bytes(), "image/png")},
        )

    assert response.status_code == 201
    asset = response.json()["asset"]
    assert asset["status"] == "ready"
    assert asset["access_url"] == (
        f"http://localhost:8000/editor/projects/{PROJECT_ID}/assets/{ASSET_ID}/content"
    )


def test_upload_asset_endpoint_rejects_oversized_file(client):
    with patch("main.editor_repository.get_project", return_value={"id": PROJECT_ID}):
        response = client.post(
            f"/editor/projects/{PROJECT_ID}/assets",
            files={"file": ("big.png", b"0" * (MAX_UPLOAD_BYTES + 1), "image/png")},
        )

    assert response.status_code == 413


def test_upload_asset_endpoint_rejects_invalid_image(client):
    with patch("main.editor_repository.get_project", return_value={"id": PROJECT_ID}):
        response = client.post(
            f"/editor/projects/{PROJECT_ID}/assets",
            files={"file": ("fake.png", b"not an image", "image/png")},
        )

    assert response.status_code == 422


def test_clip_create_requires_active_narration(client):
    with patch(
        "main.editor_repository.create_timeline_clip",
        side_effect=EditorCompositionRequiredError(
            "Regenerate narration before editing visuals"
        ),
    ):
        response = client.post(
            f"/editor/projects/{PROJECT_ID}/clips",
            json={
                "asset_id": str(ASSET_ID),
                "start_ms": 12400,
                "expected_project_revision": 3,
            },
        )

    assert response.status_code == 409
    assert "Regenerate narration" in response.json()["detail"]


def test_clip_create_defaults_three_second_window_and_returns_project(client):
    stored = {"id": PROJECT_ID, "revision": 4, "dialogue": [], "exports": []}
    with patch(
        "main.editor_repository.create_timeline_clip", return_value=stored
    ) as create:
        response = client.post(
            f"/editor/projects/{PROJECT_ID}/clips",
            json={
                "asset_id": str(ASSET_ID),
                "start_ms": 12400,
                "x": 0.3,
                "y": 0.2,
                "width": 0.4,
                "expected_project_revision": 3,
            },
        )

    assert response.status_code == 201
    assert response.json()["project"]["revision"] == 4
    args = create.call_args.args
    # (project_id, user_id, asset_id, start_ms, end_ms, x, y, width, z_index, rev)
    assert args[3] == 12400
    assert args[4] == 15400  # start + DEFAULT_CLIP_DURATION_MS
    assert args[9] == 3


def test_clip_patch_returns_clip_and_conflicts_are_409(client):
    clip = {"id": str(CLIP_ID), "revision": 2, "start_ms": 100, "end_ms": 3100}
    with patch(
        "main.editor_repository.update_timeline_clip", return_value=clip
    ) as update:
        response = client.patch(
            f"/editor/projects/{PROJECT_ID}/clips/{CLIP_ID}",
            json={"x": 0.1, "y": 0.2, "expected_revision": 1},
        )

    assert response.status_code == 200
    assert response.json()["clip"]["revision"] == 2
    # args: (project_id, clip_id, user_id, updates, expected_revision)
    assert update.call_args.args[3] == {"x": 0.1, "y": 0.2}  # only set fields
    assert update.call_args.args[4] == 1

    with patch(
        "main.editor_repository.update_timeline_clip",
        side_effect=EditorRevisionConflictError(
            "Expected clip revision 1, but current revision is 2"
        ),
    ):
        response = client.patch(
            f"/editor/projects/{PROJECT_ID}/clips/{CLIP_ID}",
            json={"x": 0.1, "expected_revision": 1},
        )

    assert response.status_code == 409


def test_clip_patch_can_replace_asset(client):
    clip = {"id": str(CLIP_ID), "revision": 5}
    with patch(
        "main.editor_repository.update_timeline_clip", return_value=clip
    ) as update:
        response = client.patch(
            f"/editor/projects/{PROJECT_ID}/clips/{CLIP_ID}",
            json={"asset_id": str(ASSET_ID), "expected_revision": 4},
        )

    assert response.status_code == 200
    assert update.call_args.args[3] == {"asset_id": ASSET_ID}


def test_clip_delete_returns_project_snapshot(client):
    stored = {"id": PROJECT_ID, "revision": 6, "dialogue": [], "exports": []}
    with patch(
        "main.editor_repository.delete_timeline_clip", return_value=stored
    ):
        response = client.request(
            "DELETE",
            f"/editor/projects/{PROJECT_ID}/clips/{CLIP_ID}",
            json={"expected_project_revision": 5},
        )

    assert response.status_code == 200
    assert response.json()["project"]["revision"] == 6


def test_asset_delete_conflicts_when_referenced(client):
    with patch(
        "main.MediaAssetService",
    ) as service_cls:
        service_cls.return_value.delete_asset.side_effect = MediaAssetInUseError(
            [CLIP_ID]
        )
        response = client.delete(
            f"/editor/projects/{PROJECT_ID}/assets/{ASSET_ID}"
        )

    assert response.status_code == 409
    assert response.json()["detail"]["referencing_clip_ids"] == [str(CLIP_ID)]


def test_asset_delete_missing_asset_is_404(client):
    with patch("main.MediaAssetService") as service_cls:
        service_cls.return_value.delete_asset.side_effect = (
            EditorProjectNotFoundError("Media asset not found")
        )
        response = client.delete(
            f"/editor/projects/{PROJECT_ID}/assets/{ASSET_ID}"
        )

    assert response.status_code == 404


def test_project_response_uses_proxied_asset_urls_and_includes_clips():
    from main import _editor_project_response

    project = {
        "id": PROJECT_ID,
        "active_composition_id": None,
        "dialogue": [],
        "exports": [],
        "media_assets": [
            {
                "id": str(ASSET_ID),
                "storage_key": f"editor/1/{PROJECT_ID}/images/{ASSET_ID}.webp",
                "content_type": "image/webp",
            }
        ],
        "timeline_clips": [
            {
                "id": str(CLIP_ID),
                "asset_id": str(ASSET_ID),
                "start_ms": 1000,
                "end_ms": 4000,
                "timing_status": "aligned",
            }
        ],
    }
    with patch("main.get_storage_backend") as storage_factory:
        storage_factory.return_value.generate_url.return_value = (
            "https://storage.example/fresh.webp"
        )
        response = _editor_project_response(project)

    assert response["media_assets"][0]["access_url"] == (
        f"http://localhost:8000/editor/projects/{PROJECT_ID}/assets/{ASSET_ID}/content"
    )
    assert response["timeline_clips"][0]["timing_status"] == "aligned"


def test_project_response_falls_back_to_content_route_for_local_storage():
    from main import _editor_project_response

    project = {
        "id": PROJECT_ID,
        "active_composition_id": None,
        "dialogue": [],
        "exports": [],
        "media_assets": [
            {
                "id": str(ASSET_ID),
                "project_id": str(PROJECT_ID),
                "storage_key": "k.webp",
                "content_type": "image/webp",
            }
        ],
        "timeline_clips": [],
    }
    with patch("main.get_storage_backend") as storage_factory:
        storage_factory.return_value.generate_url.return_value = "file:///tmp/k.webp"
        response = _editor_project_response(project)

    assert response["media_assets"][0]["access_url"] == (
        f"http://localhost:8000/editor/projects/{PROJECT_ID}/assets/{ASSET_ID}/content"
    )


def test_asset_content_passthrough_streams_bytes(client, temp_output_dir):
    asset = {
        "id": str(ASSET_ID),
        "project_id": str(PROJECT_ID),
        "storage_key": f"editor/1/{PROJECT_ID}/images/{ASSET_ID}.webp",
        "content_type": "image/webp",
    }

    def fake_download(key, dest_path):
        with open(dest_path, "wb") as f:
            f.write(b"webp-bytes")
        return dest_path

    with (
        patch("main.editor_repository.get_media_asset", return_value=asset),
        patch("main.get_storage_backend") as storage_factory,
    ):
        storage_factory.return_value.download.side_effect = fake_download
        response = client.get(
            f"/editor/projects/{PROJECT_ID}/assets/{ASSET_ID}/content"
        )

    assert response.status_code == 200
    assert response.content == b"webp-bytes"
    assert response.headers["content-type"] == "image/webp"


# ============ Export rendering (FFmpeg filtergraph) ============

def test_export_renders_overlay_clips_between_background_and_characters(
    temp_output_dir, temp_audio_file, mock_ffmpeg
):
    from backend_pipeline.video_assembly.ffMpeg import (
        create_video_with_audio_and_captions,
    )

    overlay_image = temp_output_dir / "overlay.webp"
    Image.new("RGB", (200, 100), "green").save(overlay_image, format="WEBP")

    create_video_with_audio_and_captions(
        background_video=str(temp_output_dir / "bg.mp4"),
        audio_file=str(temp_audio_file),
        caption_timings=[
            {
                "start": 0.0,
                "end": 5.0,
                "caption": "Hello",
                "speaker": "PETER",
                "emotion": "neutral",
            }
        ],
        output_file=str(temp_output_dir / "out.mp4"),
        overlay_clips=[
            {
                "path": str(overlay_image),
                "x": 0.25,
                "y": 0.25,
                "width": 0.5,
                "start": 1.0,
                "end": 4.0,
                "z_index": 0,
            }
        ],
    )

    # Second subprocess call is the actual ffmpeg render (first is ffprobe)
    ffmpeg_cmd = mock_ffmpeg.call_args_list[1].args[0]
    filter_complex = ffmpeg_cmd[ffmpeg_cmd.index("-filter_complex") + 1]

    # Normalized geometry converted to pixels for a 1080x1920 frame
    assert "scale=540:-1[clipimg_0]" in filter_complex
    clip_overlay = "overlay=x=270:y=480:enable='gte(t,1.0)*lt(t,4.0)'"
    assert clip_overlay in filter_complex

    # Painter order: background first, then overlay clips, then characters,
    # then captions on top.
    bg_pos = filter_complex.index("[bg]")
    clip_pos = filter_complex.index(clip_overlay)
    character_pos = filter_complex.index("overlay=0:H-h-0")
    caption_pos = filter_complex.index("drawtext")
    assert bg_pos < clip_pos < character_pos < caption_pos

    # The clip image is a real ffmpeg input, fed by key-downloaded local path
    assert str(overlay_image) in ffmpeg_cmd


def test_export_orders_overlay_clips_by_z_index(
    temp_output_dir, temp_audio_file, mock_ffmpeg
):
    from backend_pipeline.video_assembly.ffMpeg import (
        create_video_with_audio_and_captions,
    )

    low = temp_output_dir / "low.webp"
    high = temp_output_dir / "high.webp"
    for path in (low, high):
        Image.new("RGB", (50, 50), "red").save(path, format="WEBP")

    create_video_with_audio_and_captions(
        background_video=str(temp_output_dir / "bg.mp4"),
        audio_file=str(temp_audio_file),
        caption_timings=[
            {
                "start": 0.0,
                "end": 5.0,
                "caption": "Hi",
                "speaker": "PETER",
                "emotion": "neutral",
            }
        ],
        output_file=str(temp_output_dir / "out.mp4"),
        overlay_clips=[
            {
                "path": str(high),
                "x": 0.0,
                "y": 0.0,
                "width": 0.1,
                "start": 0.0,
                "end": 1.0,
                "z_index": 5,
            },
            {
                "path": str(low),
                "x": 0.0,
                "y": 0.0,
                "width": 0.1,
                "start": 0.0,
                "end": 1.0,
                "z_index": 1,
            },
        ],
    )

    ffmpeg_cmd = mock_ffmpeg.call_args_list[1].args[0]
    # Inputs follow paint order: lower z_index first (drawn underneath)
    assert ffmpeg_cmd.index(str(low)) < ffmpeg_cmd.index(str(high))
