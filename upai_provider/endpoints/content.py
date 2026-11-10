"""Serve real job result files with a containment check."""

import asyncio
import os
import stat
from collections.abc import Mapping
from pathlib import Path

from aiohttp import web

from ..job_service import Kind
from ..protocol import ProtocolError
from ..routes import Handler
from ..runtime import Runtime
from ..uploads import content_type_for
from .uploads import _parse_index

_READ_BYTES = 64 * 1024
_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


def _result_root(runtime: Runtime) -> Path:
    root = getattr(runtime, "result_root", None)
    return root if isinstance(root, Path) else runtime.data_dir


def _result_path(runtime: Runtime, name: str) -> Path | None:
    root = _result_root(runtime)
    path = Path(name)
    if not path.is_absolute():
        path = root / path

    try:
        resolved_root = root.resolve()
        normalized = Path(os.path.normpath(os.path.abspath(path)))
        candidate = normalized.parent.resolve() / normalized.name
        info = candidate.lstat()
    except OSError:
        return None

    if candidate == resolved_root or not candidate.is_relative_to(resolved_root):
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return None

    return candidate


def _safe_filename(path: Path) -> str:
    return path.name.replace("\r", "").replace("\n", "").replace('"', "_")


async def _open_result(path: Path) -> int:
    """Open a regular file without following a symlink in the final component."""
    try:
        info = await asyncio.to_thread(path.lstat)
    except OSError as exc:
        raise ProtocolError("job_not_found", "content not found", status=404) from exc

    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ProtocolError("job_not_found", "content not found", status=404)

    try:
        fd = await asyncio.to_thread(os.open, path, _OPEN_FLAGS)
    except OSError as exc:
        raise ProtocolError("job_not_found", "content not found", status=404) from exc

    try:
        opened = await asyncio.to_thread(os.fstat, fd)
    except OSError as exc:
        os.close(fd)
        raise ProtocolError("job_not_found", "content not found", status=404) from exc

    if not stat.S_ISREG(opened.st_mode):
        os.close(fd)
        raise ProtocolError("job_not_found", "content not found", status=404)

    return fd


async def stream_result(
    request: web.Request,
    path: Path,
    headers: Mapping[str, str],
) -> web.StreamResponse:
    """Stream one result file from an already checked descriptor."""
    fd = await _open_result(path)
    try:
        size = (await asyncio.to_thread(os.fstat, fd)).st_size
        response = web.StreamResponse(
            status=200,
            headers={**headers, "Content-Length": str(size)},
        )
        await response.prepare(request)
        while True:
            chunk = await asyncio.to_thread(os.read, fd, _READ_BYTES)
            if not chunk:
                break
            await response.write(chunk)
        await response.write_eof()
        return response
    finally:
        await asyncio.to_thread(os.close, fd)


def content(runtime: Runtime, kind: Kind) -> Handler:
    """Return a handler that serves one registered result file."""

    async def handler(request: web.Request) -> web.StreamResponse:
        index = _parse_index(request)
        job = await runtime.store.get(request.match_info["id"])
        if job is None or job.kind != kind:
            raise ProtocolError("job_not_found", "job not found", status=404)

        if job.status != "completed":
            raise ProtocolError("invalid_request", "job is not completed", status=400)

        if index >= len(job.files):
            raise ProtocolError("job_not_found", "content not found", status=404)

        if kind == "video" and index != 0:
            raise ProtocolError("job_not_found", "content not found", status=404)

        path = _result_path(runtime, job.files[index])
        if path is None:
            raise ProtocolError("job_not_found", "content not found", status=404)

        return await stream_result(
            request,
            path,
            {
                "Content-Type": content_type_for(path),
                "Content-Disposition": f'inline; filename="{_safe_filename(path)}"',
            },
        )

    return handler


__all__ = ["content", "stream_result"]
