"""Capability and request validation for the upai/1 protocol. No ComfyUI imports."""

import asyncio
import base64
import binascii
from pathlib import Path
from typing import Protocol

from aiohttp import web

from .media_sniff import detect_image_format, normalize_image_format
from .protocol import (
    Capabilities,
    FrameImage,
    InputReference,
    ProtocolError,
    ReferenceCapability,
    ReferenceLimit,
    Upload,
)

_SNIFF_BYTES = 16


class _UploadLookup(Protocol):
    """Minimal upload store surface used to read reference files."""

    def head(self, sha256: str) -> Upload | None: ...

    async def head_async(self, sha256: str) -> Upload | None: ...

    def path(self, sha256: str) -> Path | None: ...


async def read_json(request: web.Request) -> object:
    """Parse the request body as JSON or raise a protocol error."""
    try:
        return await request.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError(
            "invalid_request",
            "body must be valid JSON",
            details={"field": "body"},
        ) from exc


def validate_prompt(prompt: str, capabilities: Capabilities) -> None:
    """Check prompt presence and length against model capabilities."""
    if not prompt and capabilities.prompt.required:
        raise ProtocolError(
            "invalid_request",
            "prompt is required",
            details={"field": "prompt"},
        )

    if len(prompt) > capabilities.prompt.max_chars:
        raise ProtocolError(
            "invalid_request",
            f"prompt exceeds {capabilities.prompt.max_chars} characters",
            details={"field": "prompt"},
        )


def validate_negative_prompt(negative_prompt: str | None, capabilities: Capabilities) -> None:
    """Reject a negative prompt when the model has no wired negative input."""
    if negative_prompt and not capabilities.negative_prompt:
        raise ProtocolError(
            "invalid_request",
            "model does not accept a negative prompt",
            details={"field": "negative_prompt"},
        )


def validate_seed(seed: int | None, capabilities: Capabilities) -> None:
    """Reject a seed when the model does not accept one."""
    if seed is not None and not capabilities.seed:
        raise ProtocolError(
            "invalid_request",
            "model does not accept a seed",
            details={"field": "seed"},
        )


def validate_resolution_and_aspect(
    capabilities: Capabilities, *, resolution: str | None, aspect_ratio: str | None
) -> None:
    """Check requested resolution and aspect ratio against capabilities."""
    chosen_resolution = capabilities.default_resolution if resolution is None else resolution
    if chosen_resolution not in capabilities.resolutions:
        raise ProtocolError(
            "invalid_request",
            "resolution is not supported",
            details={"field": "resolution"},
        )

    chosen_aspect = capabilities.default_aspect_ratio if aspect_ratio is None else aspect_ratio
    if chosen_aspect not in capabilities.aspect_ratios:
        raise ProtocolError(
            "invalid_request",
            "aspect_ratio is not supported",
            details={"field": "aspect_ratio"},
        )


def reference_count(references: tuple[InputReference, ...], kind: str) -> int:
    """Count references of one kind."""
    return sum(1 for reference in references if reference.kind == kind)


def _check_reference_kind(
    references: tuple[InputReference, ...],
    kind: str,
    capability: ReferenceCapability,
    field: str,
) -> None:
    """Check one reference kind against its capability bounds."""
    count = reference_count(references, kind)
    if count < capability.required or count > capability.max:
        raise ProtocolError(
            "invalid_request",
            f"{kind} references must be between {capability.required} and {capability.max}",
            details={"field": field},
        )


def check_references(
    references: tuple[InputReference, ...],
    capabilities: Capabilities,
    field: str = "input_references",
) -> None:
    """Check every reference kind against its capability bounds."""
    for kind, capability in (
        ("image", capabilities.references.image),
        ("video", capabilities.references.video),
        ("audio", capabilities.references.audio),
    ):
        _check_reference_kind(references, kind, capability, field)


def check_invalid_prompt(prompt: str) -> None:
    """Raise the workflow error for the mock invalid marker."""
    if "[invalid]" in prompt:
        raise ProtocolError(
            "workflow_invalid",
            "workflow rejected by the backend",
            details={"node_errors": {}},
            status=422,
        )


def _read_prefix(path: Path) -> bytes:
    with path.open("rb") as file:
        return file.read(_SNIFF_BYTES)


def _decode_data_url(url: str, field: str) -> bytes:
    payload = url.partition(";base64,")[2]
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProtocolError(
            "invalid_request",
            "data URL must carry valid base64",
            details={"field": field},
        ) from exc


def _check_size(size: int, limit: ReferenceLimit, field: str) -> None:
    if size > limit.max_bytes:
        raise ProtocolError(
            "too_large",
            f"image reference exceeds {limit.max_bytes} bytes",
            details={"field": field},
            status=413,
        )


def _check_format(data: bytes, limit: ReferenceLimit, field: str) -> None:
    detected = detect_image_format(data)
    allowed = {normalize_image_format(item) for item in limit.formats}
    if detected is None or detected not in allowed:
        raise ProtocolError(
            "invalid_request",
            "image reference format is not supported",
            details={"field": field},
        )


async def _check_image_reference(
    url: str,
    limit: ReferenceLimit,
    uploads: _UploadLookup,
    field: str,
) -> None:
    if url.startswith("data:"):
        data = _decode_data_url(url, field)
        _check_size(len(data), limit, field)
        _check_format(data, limit, field)
        return

    if not url.startswith("upai-upload:"):
        return

    sha256 = url.removeprefix("upai-upload:")
    record = await uploads.head_async(sha256)
    path = await asyncio.to_thread(uploads.path, sha256)
    if record is None or path is None:
        raise ProtocolError(
            "upload_not_found",
            "upload not found",
            details={"field": field, "ref": url},
            status=404,
        )

    _check_size(record.size, limit, field)
    prefix = await asyncio.to_thread(_read_prefix, path)
    _check_format(prefix, limit, field)


async def check_image_reference_limits(
    *,
    references: tuple[InputReference, ...],
    frames: tuple[FrameImage, ...],
    limit: ReferenceLimit,
    uploads: _UploadLookup,
) -> None:
    """Check image reference size and magic-byte format before job creation."""
    for frame in frames:
        await _check_image_reference(frame.url, limit, uploads, "frame_images")

    for reference in references:
        if reference.kind == "image":
            await _check_image_reference(reference.url, limit, uploads, "input_references")
