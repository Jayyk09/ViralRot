"""Image validation, normalization, and storage lifecycle for editor overlays.

Uploads are proxied through FastAPI (multipart), validated server-side, and
normalized to a single WebP with EXIF orientation applied and all metadata
discarded. The original bytes are never retained. The permanent media_assets
row is only created after normalization and the storage upload succeed; if
the DB insert fails, the uploaded object is deleted (compensation), matching
the EditorAudioService pattern.
"""

from io import BytesIO
from typing import Dict, Optional, Tuple
from uuid import UUID, uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from services.repositories.editor_repository import EditorRepository
from storage import get_storage_backend

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_IMAGE_DIMENSION = 4096  # px, each axis
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
NORMALIZED_CONTENT_TYPE = "image/webp"
WEBP_QUALITY = 90

# Default clip length when the client only supplies the playhead position.
DEFAULT_CLIP_DURATION_MS = 3000

_PIL_FORMATS = {"PNG", "JPEG", "WEBP"}


class MediaValidationError(Exception):
    """Raised when an uploaded file fails image validation."""


def normalize_image(data: bytes) -> Tuple[bytes, int, int]:
    """Validate and normalize uploaded image bytes.

    - Accepts PNG/JPEG/WebP only (verified by decoding, not by declared type)
    - Enforces MAX_UPLOAD_BYTES and MAX_IMAGE_DIMENSION
    - Applies the EXIF orientation to the pixels
    - Re-encodes as a single (non-animated) WebP with all metadata discarded

    Returns (webp_bytes, width_px, height_px) where the dimensions describe
    the orientation-corrected image.
    """
    if not data:
        raise MediaValidationError("Uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise MediaValidationError(
            f"Image exceeds the maximum size of {MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
        )

    # First pass: integrity check on a throwaway handle (verify() invalidates it).
    try:
        probe = Image.open(BytesIO(data))
        probe.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MediaValidationError("File is not a valid image") from exc

    try:
        image = Image.open(BytesIO(data))
        # Reject hostile dimensions before decoding the full pixel buffer.
        encoded_width, encoded_height = image.size
        if (
            encoded_width < 1
            or encoded_height < 1
            or encoded_width > MAX_IMAGE_DIMENSION
            or encoded_height > MAX_IMAGE_DIMENSION
        ):
            raise MediaValidationError(
                f"Image dimensions exceed {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}"
            )
        image.load()
    except MediaValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MediaValidationError("File is not a valid image") from exc

    image_format = (image.format or "").upper()
    if image_format not in _PIL_FORMATS:
        raise MediaValidationError(
            "Unsupported image format: only PNG, JPEG, and WebP are accepted"
        )
    if getattr(image, "is_animated", False):
        raise MediaValidationError("Animated images are not supported")

    # Bake the EXIF orientation into the pixels so canvas and FFmpeg agree.
    image = ImageOps.exif_transpose(image)
    width, height = image.size
    if width < 1 or height < 1:
        raise MediaValidationError("Image has no pixels")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise MediaValidationError(
            f"Image dimensions exceed {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION}"
        )

    if image.mode not in ("RGB", "RGBA"):
        has_alpha = (
            "A" in image.mode
            or image.mode == "P"
            or "transparency" in image.info
        )
        image = image.convert("RGBA" if has_alpha else "RGB")

    # Discard metadata: Pillow's WebP encoder picks exif/icc/xmp back up from
    # image.info unless it is cleared before saving.
    for meta_key in ("exif", "icc_profile", "xmp"):
        image.info.pop(meta_key, None)

    output = BytesIO()
    image.save(output, format="WEBP", quality=WEBP_QUALITY, method=4)
    return output.getvalue(), width, height


class MediaAssetService:
    """Upload lifecycle for project-scoped image overlay assets."""

    def __init__(
        self,
        repository: Optional[EditorRepository] = None,
        storage=None,
    ) -> None:
        self.repository = repository or EditorRepository()
        self.storage = storage or get_storage_backend()

    def upload_image(
        self,
        project_id: UUID,
        user_id: int,
        data: bytes,
        original_filename: str,
        declared_content_type: Optional[str],
    ) -> Dict[str, object]:
        """Normalize, store, and persist an uploaded image.

        Order matters: bytes are uploaded first and the DB row second, with a
        compensating storage delete if the insert fails - so a media_assets
        row only ever exists for an object that is really in storage.
        """
        declared = (declared_content_type or "").split(";")[0].strip().lower()
        if declared and declared not in ALLOWED_CONTENT_TYPES:
            raise MediaValidationError(
                "Unsupported content type: only PNG, JPEG, and WebP are accepted"
            )

        webp_bytes, width_px, height_px = normalize_image(data)

        asset_id = uuid4()
        # Server-generated key (client filename is display metadata only),
        # following the editor narration key convention.
        storage_key = f"editor/{user_id}/{project_id}/images/{asset_id}.webp"

        self.storage.upload(
            BytesIO(webp_bytes),
            storage_key,
            {"content_type": NORMALIZED_CONTENT_TYPE},
        )
        try:
            return self.repository.create_media_asset(
                project_id=project_id,
                user_id=user_id,
                asset_id=asset_id,
                storage_key=storage_key,
                original_filename=(original_filename or "image").strip() or "image",
                content_type=NORMALIZED_CONTENT_TYPE,
                byte_size=len(webp_bytes),
                width_px=width_px,
                height_px=height_px,
            )
        except Exception:
            self.storage.delete(storage_key)
            raise

    def delete_asset(self, project_id: UUID, asset_id: UUID, user_id: int) -> None:
        """Delete an unreferenced asset: row first (guarded by the clip check
        inside the transaction), then best-effort storage delete."""
        storage_key = self.repository.delete_media_asset(project_id, asset_id, user_id)
        try:
            self.storage.delete(storage_key)
        except Exception as exc:  # orphaned bytes are recoverable; a broken row is not
            print(f"⚠️  Failed to delete asset object {storage_key}: {exc}")
