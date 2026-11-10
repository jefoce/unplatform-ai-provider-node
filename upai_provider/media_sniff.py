"""Detect image formats from magic bytes. No ComfyUI imports."""

_JPEG_ALIASES = ("jpg", "jpe", "jfif")


def normalize_image_format(label: str) -> str:
    """Map an extension or label to the canonical sniffed format name."""
    name = label.lower().removeprefix(".")
    return "jpeg" if name in _JPEG_ALIASES else name


def detect_image_format(data: bytes) -> str | None:
    """Return png, jpeg or webp from magic bytes, or None when unknown."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"

    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"

    return None
