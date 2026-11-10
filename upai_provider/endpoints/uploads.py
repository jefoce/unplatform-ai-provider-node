"""Upload, upload HEAD and job content handlers. No ComfyUI imports."""

from collections.abc import AsyncIterator
from pathlib import Path

from aiohttp import web
from aiohttp.multipart import BodyPartReader

from ..constants import INLINE_JSON_MARGIN
from ..job_service import Kind
from ..protocol import SHA256_PATTERN, ProtocolError, upload_to_wire
from ..routes import Handler
from ..runtime import Runtime


def _parse_index(request: web.Request) -> int:
    raw = request.query.get("index", "0")
    try:
        index = int(raw)
    except ValueError as exc:
        raise ProtocolError(
            "invalid_request",
            "index must be an integer",
            details={"field": "index"},
        ) from exc

    if index < 0:
        raise ProtocolError(
            "invalid_request",
            "index must be non-negative",
            details={"field": "index"},
        )

    return index


async def asset_path(runtime: Runtime, kind: Kind) -> Path:
    await runtime.ensure_assets()
    assets = runtime.assets
    if assets is None:
        raise ProtocolError("internal", "mock assets are unavailable", status=500)

    return assets.mp4 if kind == "video" else assets.png


def effective_upload_cap(request: web.Request, runtime: Runtime) -> int:
    """Return the smallest byte cap applied to an upload request."""
    limit = runtime.uploads.max_bytes
    return min(limit, int(getattr(request, "_client_max_size", limit)))


def effective_inline_cap(request: web.Request, runtime: Runtime) -> int:
    """Return the largest data URL payload accepted in a JSON body."""
    return max(0, (effective_upload_cap(request, runtime) - INLINE_JSON_MARGIN) * 3 // 4)


def upload(runtime: Runtime) -> Handler:
    async def handler(request: web.Request) -> web.StreamResponse:
        runtime.ensure_free_space(runtime.uploads.root)
        cap = effective_upload_cap(request, runtime)
        if request.content_length is not None and request.content_length > cap:
            raise ProtocolError(
                "too_large",
                f"upload exceeds {cap} bytes",
                details={"field": "file"},
                status=413,
            )

        try:
            reader = await request.multipart()
            part: BodyPartReader | None = None
            while (candidate := await reader.next()) is not None:
                if isinstance(candidate, BodyPartReader) and candidate.filename is not None:
                    part = candidate
                    break
            if part is None:
                raise ProtocolError(
                    "invalid_request",
                    "file is required",
                    details={"field": "file"},
                )

            filename = part.filename or "upload.bin"
            content_type = part.headers.get("Content-Type", "application/octet-stream")

            async def chunks() -> AsyncIterator[bytes]:
                chunk = await part.read_chunk(64 * 1024)
                while chunk:
                    yield chunk
                    chunk = await part.read_chunk(64 * 1024)

            upload = await runtime.uploads.save_stream(
                filename,
                content_type,
                chunks(),
                reserved_bytes=request.content_length or 0,
                max_bytes=cap,
            )
        except web.HTTPRequestEntityTooLarge as exc:
            raise ProtocolError(
                "too_large",
                f"upload exceeds {cap} bytes",
                details={"field": "file"},
                status=413,
            ) from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProtocolError(
                "invalid_request",
                "body must be multipart form data",
                details={"field": "body"},
            ) from exc

        return web.json_response(upload_to_wire(upload), status=201)

    return handler


def upload_head(runtime: Runtime) -> Handler:
    async def handler(request: web.Request) -> web.StreamResponse:
        sha256 = request.match_info["sha256"]
        if not SHA256_PATTERN.match(sha256):
            raise ProtocolError("upload_not_found", "upload not found", status=404)
        if await runtime.uploads.head_async(sha256) is None:
            raise ProtocolError("upload_not_found", "upload not found", status=404)

        return web.Response(status=200)

    return handler


def content(runtime: Runtime, kind: Kind) -> Handler:
    async def handler(request: web.Request) -> web.StreamResponse:
        index = _parse_index(request)
        job = await runtime.store.get(request.match_info["id"])
        if job is None or job.kind != kind:
            raise ProtocolError("job_not_found", "job not found", status=404)

        if job.status != "completed":
            raise ProtocolError(
                "invalid_request",
                "job is not completed",
                status=400,
            )

        if kind == "video":
            if index != 0:
                raise ProtocolError("job_not_found", "content not found", status=404)
            extension = "mp4"
            content_type = "video/mp4"
        else:
            urls = job.urls or ()
            if index >= len(urls):
                raise ProtocolError("job_not_found", "content not found", status=404)
            extension = "png"
            content_type = "image/png"

        from .content import stream_result

        path = await asset_path(runtime, kind)
        return await stream_result(
            request,
            path,
            {
                "Content-Type": content_type,
                "Content-Disposition": f'inline; filename="result.{extension}"',
            },
        )

    return handler
