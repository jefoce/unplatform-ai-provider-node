"""Internal workflow export handler. Same-origin browser calls only."""

import asyncio
import math
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from aiohttp import web

from ..export_file import write_export
from ..export_graph import derive_export, slugify
from ..protocol import ProtocolError
from ..routes import Handler
from ..runtime import Runtime
from ..timeutil import iso_now
from ..validation import read_json


def _object(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ProtocolError(
            "invalid_request", f"{field} must be an object", details={"field": field}
        )

    return value


def _source(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError("invalid_request", "source must be a path", details={"field": "source"})

    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
        or ":" in relative.parts[0]
        or relative.suffix != ".json"
        or "\\" in value
    ):
        raise ProtocolError(
            "invalid_request", "source must be a relative JSON path", details={"field": "source"}
        )

    return value


def _saved_at(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(
            "invalid_request", "saved_at must be epoch seconds", details={"field": "saved_at"}
        )

    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ProtocolError(
            "invalid_request", "saved_at must be epoch seconds", details={"field": "saved_at"}
        )

    return number


def _source_file(root: Path, source: str) -> Path | None:
    relative = PurePosixPath(source)
    path = root.joinpath(*relative.parts)
    return path if path.is_file() else None


def export_workflow(runtime: Runtime) -> Handler:
    """Return the handler for POST /upai/internal/export."""

    async def handler(request: web.Request) -> web.StreamResponse:
        body = _object(await read_json(request), "body")
        source = _source(body.get("source"))
        prompt = _object(body.get("prompt"), "prompt")
        saved_at = _saved_at(body.get("saved_at"))

        workflow_id = slugify(PurePosixPath(source).stem)
        source_file = _source_file(runtime.data_dir.parent, source)
        source_mtime = source_file.stat().st_mtime if source_file is not None else saved_at

        build = derive_export(
            source=source,
            prompt=prompt,
            source_mtime=source_mtime,
            exported_at=iso_now(runtime.clock),
            comfy_version=runtime.server_version,
        )

        # Only this workflow id is touched. A rename or save-as keeps the old export.
        path = runtime.data_dir / "exports" / f"{workflow_id}.json"
        if build.export.models:
            await asyncio.to_thread(
                write_export,
                path,
                build.export,
                build.invalid_reasons,
                build.warnings,
            )
        else:
            await asyncio.to_thread(path.unlink, missing_ok=True)

        reason = next(iter(build.invalid_reasons.values()), None)
        if reason is None and build.workflow_errors:
            reason = build.workflow_errors[0]

        is_invalid = bool(build.invalid_reasons or build.workflow_errors)
        return web.json_response(
            {
                "id": workflow_id,
                "status": "invalid" if is_invalid else "ready",
                "status_reason": reason,
                "warnings": list(build.warnings),
            }
        )

    return handler
