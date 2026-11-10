"""Data URL decoding, media extension helpers and image format checks."""

import base64
import binascii
from pathlib import Path

from .constants import CONTENT_TYPES
from .media_sniff import detect_image_format, normalize_image_format
from .protocol import ProtocolError, ReferenceLimit

_SNIFF_BYTES = 16
_CONTENT_TYPE_EXTENSION = {
    content_type: extension for extension, content_type in reversed(CONTENT_TYPES.items())
}


def extension_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None

    base = content_type.split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_EXTENSION.get(base)


def extension_from_path(path: Path) -> str | None:
    suffix = path.suffix.lower().lstrip(".")
    return suffix if suffix in CONTENT_TYPES else None


def decode_data_url(url: str) -> tuple[str | None, bytes]:
    header, separator, payload = url[5:].partition(",")
    if not separator or ";base64" not in header:
        raise ProtocolError("invalid_request", "data URL must carry base64", status=400)

    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProtocolError(
            "invalid_request", "data URL must carry valid base64", status=400
        ) from exc

    mime = header.split(";", 1)[0].strip().lower() or None
    return mime, data


def _allowed_formats(limit: ReferenceLimit) -> set[str]:
    return {normalize_image_format(item) for item in limit.formats}


def check_image_data(data: bytes, limit: ReferenceLimit, field: str) -> str:
    if len(data) > limit.max_bytes:
        raise ProtocolError(
            "too_large",
            f"image reference exceeds {limit.max_bytes} bytes",
            details={"field": field},
            status=413,
        )

    detected = detect_image_format(data)
    if detected is None or detected not in _allowed_formats(limit):
        raise ProtocolError(
            "invalid_request",
            "image reference format is not supported",
            details={"field": field},
        )

    return detected


def _read_prefix(path: Path) -> bytes:
    with path.open("rb") as file:
        return file.read(_SNIFF_BYTES)


def check_image_file(path: Path, limit: ReferenceLimit, field: str) -> str:
    if path.stat().st_size > limit.max_bytes:
        raise ProtocolError(
            "too_large",
            f"image reference exceeds {limit.max_bytes} bytes",
            details={"field": field},
            status=413,
        )

    detected = detect_image_format(_read_prefix(path))
    if detected is None or detected not in _allowed_formats(limit):
        raise ProtocolError(
            "invalid_request",
            "image reference format is not supported",
            details={"field": field},
        )

    return detected
