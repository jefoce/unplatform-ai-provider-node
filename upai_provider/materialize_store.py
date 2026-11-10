"""Write job media files under the pack input directory."""

import asyncio
import contextlib
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .fileutil import replace_file
from .materialize_decode import (
    check_image_data,
    check_image_file,
    decode_data_url,
    extension_from_content_type,
    extension_from_path,
)
from .protocol import JOB_ID_PATTERN, Capabilities, ProtocolError, ReferenceLimit
from .uploads import UploadStore

if TYPE_CHECKING:
    from .materialize import HttpSession, MaterializedInput

_CHUNK_BYTES = 64 * 1024


def job_dir(input_root: Path, job_id: str) -> Path:
    if not JOB_ID_PATTERN.match(job_id):
        raise ProtocolError("invalid_request", "job id is invalid", status=500)

    root = input_root.resolve()
    target = (root / job_id).resolve()
    if target.parent != root:
        raise ProtocolError("internal", "job path escapes the input root", status=500)

    return target


def _temp_path(directory: Path) -> Path:
    handle, name = tempfile.mkstemp(dir=directory, prefix=".part-", suffix=".tmp")
    os.close(handle)
    return Path(name)


def _check_size(size: int, cap: int, field: str) -> None:
    if size > cap:
        raise ProtocolError(
            "too_large",
            f"media reference exceeds {cap} bytes",
            details={"field": field},
            status=413,
        )


async def _download(
    session: "HttpSession",
    url: str,
    target: Path,
    *,
    cap: int,
    field: str,
) -> str | None:
    temp_path = _temp_path(target.parent)
    total = 0
    content_type: str | None = None
    try:
        async with session.get(url, allow_redirects=False) as response:
            if not 200 <= response.status < 300:
                raise ProtocolError(
                    "invalid_request",
                    "media URL fetch failed",
                    details={"field": field, "status": response.status},
                )

            content_type = response.headers.get("Content-Type")
            declared = response.headers.get("Content-Length")
            if declared is not None:
                try:
                    _check_size(int(declared), cap, field)
                except ValueError as exc:
                    raise ProtocolError(
                        "invalid_request",
                        "media URL fetch returned an invalid length",
                        details={"field": field},
                    ) from exc

            handle = await asyncio.to_thread(temp_path.open, "wb")
            try:
                async for chunk in response.content.iter_chunked(_CHUNK_BYTES):
                    total += len(chunk)
                    _check_size(total, cap, field)
                    await asyncio.to_thread(handle.write, chunk)
            finally:
                await asyncio.to_thread(handle.close)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_path)
        raise

    try:
        await asyncio.to_thread(replace_file, temp_path, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_path)
        raise

    return content_type


def _input_limit(
    kind: str,
    capabilities: Capabilities,
    max_bytes: int | None,
) -> ReferenceLimit | None:
    if kind not in ("image", "first_frame", "last_frame"):
        return None

    limit = capabilities.reference_limits.image
    if max_bytes is None:
        return limit
    return ReferenceLimit(min(limit.max_bytes, max_bytes), limit.formats)


def _cap(
    kind: str,
    capabilities: Capabilities,
    uploads: UploadStore,
    max_bytes: int | None,
) -> int:
    limit = _input_limit(kind, capabilities, max_bytes)
    if limit is not None:
        return limit.max_bytes

    return uploads.max_bytes if max_bytes is None else max_bytes


async def materialize_one(
    *,
    job_id: str | None = None,
    job_dir: Path,
    kind: str,
    slot: int,
    url: str,
    field: str,
    capabilities: Capabilities,
    uploads: UploadStore,
    allow_url_fetch: bool,
    session: "HttpSession | None",
    max_bytes: int | None,
) -> "MaterializedInput":
    from .materialize import MaterializedInput

    name = f"{kind}_{slot}"
    limit = _input_limit(kind, capabilities, max_bytes)
    cap = _cap(kind, capabilities, uploads, max_bytes)

    if url.startswith("data:"):
        mime, data = decode_data_url(url)
        _check_size(len(data), cap, field)
        extension = extension_from_content_type(mime) or "bin"
        if limit is not None:
            extension = check_image_data(data, limit, field)

        content_type = mime or "application/octet-stream"
        upload = await uploads.save(f"{name}.{extension}", content_type, data)
        if job_id is not None:
            uploads.pin(job_id, upload.sha256)
        target = await asyncio.to_thread(uploads.path, upload.sha256)
        if target is None:
            raise ProtocolError("internal", "stored upload is missing", status=500)
        return MaterializedInput(kind, slot, target)

    if url.startswith("upai-upload:"):
        sha256 = url.removeprefix("upai-upload:")
        record = await uploads.head_async(sha256)
        source = await asyncio.to_thread(uploads.path, sha256)
        if record is None or source is None:
            raise ProtocolError(
                "upload_not_found",
                "upload not found",
                details={"field": field, "ref": url},
                status=404,
            )

        _check_size(record.size, cap, field)
        if limit is not None:
            check_image_file(source, limit, field)
        if job_id is not None:
            uploads.pin(job_id, sha256)
        return MaterializedInput(kind, slot, source)

    if not url.startswith(("http://", "https://")):
        raise ProtocolError("invalid_request", "unsupported media URL", details={"field": field})

    if not allow_url_fetch:
        raise ProtocolError("invalid_request", "URL fetch is disabled", details={"field": field})

    if session is None:
        raise ProtocolError("invalid_request", "URL fetch is unavailable", details={"field": field})

    await asyncio.to_thread(job_dir.mkdir, parents=True, exist_ok=True)
    temp_target = job_dir / f"{name}.bin"
    content_type = await _download(session, url, temp_target, cap=cap, field=field)
    try:
        extension = extension_from_content_type(content_type) or extension_from_path(
            Path(url.split("?", 1)[0])
        )
        if limit is not None:
            extension = check_image_file(temp_target, limit, field)

        target = job_dir / f"{name}.{extension or 'bin'}"
        await asyncio.to_thread(replace_file, temp_target, target)
        return MaterializedInput(kind, slot, target)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_target)
