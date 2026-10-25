"""Security and private-media infrastructure for public incident reports."""

from __future__ import annotations

import hashlib
import io
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet
from jaldrishti.domain.incidents import IncidentMediaInput
from PIL import Image, ImageOps, UnidentifiedImageError
from redis.asyncio import Redis


class InvalidIncidentImage(ValueError):
    """Raised when an upload cannot be safely normalised as a supported image."""


class FernetContactCipher:
    def __init__(self, key: str, key_id: str) -> None:
        self._fernet = Fernet(key.encode("ascii"))
        self.key_id = key_id

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode("utf-8"))


class RedisIncidentRateLimiter:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        redis_key = f"jaldrishti:incident-rate:{digest}"
        count = int(await self._client.incr(redis_key))
        if count == 1:
            await self._client.expire(redis_key, window_seconds)
        return count <= limit


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    content: bytes
    mime_type: str
    extension: str


def normalize_incident_image(data: bytes, *, maximum_bytes: int) -> NormalizedImage:
    """Decode and re-encode a bounded image, discarding EXIF and ancillary metadata."""

    if not data or len(data) > maximum_bytes:
        raise InvalidIncidentImage(f"Photo must be between 1 byte and {maximum_bytes} bytes")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise InvalidIncidentImage("Photo must be JPEG, PNG or WebP")
            if source.width * source.height > 20_000_000:
                raise InvalidIncidentImage("Photo dimensions are too large")
            oriented = ImageOps.exif_transpose(source)
            oriented.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
            if oriented.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", oriented.size, "white")
                alpha = oriented.getchannel("A")
                background.paste(oriented.convert("RGB"), mask=alpha)
                output_image = background
            else:
                output_image = oriented.convert("RGB")
            output = io.BytesIO()
            output_image.save(output, format="JPEG", quality=88, optimize=True)
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as exc:
        raise InvalidIncidentImage("Photo could not be decoded safely") from exc
    content = output.getvalue()
    if len(content) > maximum_bytes:
        raise InvalidIncidentImage("Normalised photo exceeds the upload limit")
    return NormalizedImage(content=content, mime_type="image/jpeg", extension="jpg")


class PrivateIncidentMediaStore:
    def __init__(self, directory: str, maximum_bytes: int) -> None:
        self._directory = Path(directory)
        self._maximum_bytes = maximum_bytes

    def store(self, *, report_id: str, media_id: str, content: bytes) -> IncidentMediaInput:
        normalized = normalize_incident_image(content, maximum_bytes=self._maximum_bytes)
        report_directory = self._directory / report_id
        report_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = report_directory / f"{media_id}.{normalized.extension}"
        path.write_bytes(normalized.content)
        path.chmod(0o600)
        digest = hashlib.sha256(normalized.content).hexdigest()
        return IncidentMediaInput(
            id=media_id,
            private_uri=str(path),
            mime_type=normalized.mime_type,
            size_bytes=len(normalized.content),
            sha256=digest,
            normalization_status="content_normalized_metadata_removed",
        )

    def discard(self, media: IncidentMediaInput) -> None:
        path = Path(media.private_uri)
        path.unlink(missing_ok=True)
        with suppress(OSError):
            path.parent.rmdir()
