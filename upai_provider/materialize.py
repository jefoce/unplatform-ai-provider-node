"""Materialize request media under the pack input directory."""

import asyncio
import shutil
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .materialize_store import job_dir, materialize_one
from .protocol import Capabilities, FrameImage, ImageJobRequest, VideoJobRequest
from .uploads import UploadStore


class HttpResponseContent(Protocol):
    def iter_chunked(self, size: int) -> AsyncIterator[bytes]: ...


class HttpResponse(Protocol):
    status: int
    headers: Mapping[str, str]
    content: HttpResponseContent

    async def __aenter__(self) -> "HttpResponse": ...

    async def __aexit__(self, *args: object) -> None: ...


class PostResponse(Protocol):
    status: int

    async def json(self, *, content_type: str | None = None) -> object: ...

    async def __aenter__(self) -> "PostResponse": ...

    async def __aexit__(self, *args: object) -> None: ...


class HttpSession(Protocol):
    def get(self, url: str, *, allow_redirects: bool = True) -> HttpResponse: ...

    def post(self, url: str, *, json: object) -> PostResponse: ...


@dataclass(frozen=True)
class MaterializedInput:
    """One file written for a job input slot."""

    kind: str
    slot: int
    path: Path


@dataclass(frozen=True)
class MaterializedMedia:
    """Files written for one job, addressed by reference kind and slot."""

    job_dir: Path
    inputs: tuple[MaterializedInput, ...]

    def reference_path(self, kind: str, slot: int) -> Path | None:
        """Return the file for one reference kind and slot."""
        return next(
            (item.path for item in self.inputs if item.kind == kind and item.slot == slot),
            None,
        )

    def frame_path(self, frame_type: str, slot: int = 1) -> Path | None:
        """Return the file for a start or end frame."""
        return self.reference_path(frame_type, slot)


async def materialize_inputs(
    *,
    job_id: str,
    request: VideoJobRequest | ImageJobRequest,
    capabilities: Capabilities,
    input_root: Path,
    uploads: UploadStore,
    allow_url_fetch: bool = False,
    session: HttpSession | None = None,
    max_bytes: int | None = None,
) -> MaterializedMedia:
    """Write every request media URL under input/upai/<job> and re-check it."""
    target = job_dir(input_root, job_id)
    inputs: list[MaterializedInput] = []
    try:
        for reference in request.input_references:
            inputs.append(
                await materialize_one(
                    job_id=job_id,
                    job_dir=target,
                    kind=reference.kind,
                    slot=reference.slot,
                    url=reference.url,
                    field="input_references",
                    capabilities=capabilities,
                    uploads=uploads,
                    allow_url_fetch=allow_url_fetch,
                    session=session,
                    max_bytes=max_bytes,
                )
            )

        frames: Sequence[FrameImage] = (
            request.frame_images if isinstance(request, VideoJobRequest) else ()
        )
        for frame in frames:
            inputs.append(
                await materialize_one(
                    job_id=job_id,
                    job_dir=target,
                    kind=frame.frame_type,
                    slot=frame.slot,
                    url=frame.url,
                    field="frame_images",
                    capabilities=capabilities,
                    uploads=uploads,
                    allow_url_fetch=allow_url_fetch,
                    session=session,
                    max_bytes=max_bytes,
                )
            )
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, target, True)
        raise

    return MaterializedMedia(job_dir=target, inputs=tuple(inputs))


__all__ = [
    "HttpResponse",
    "HttpSession",
    "MaterializedInput",
    "MaterializedMedia",
    "PostResponse",
    "materialize_inputs",
]
