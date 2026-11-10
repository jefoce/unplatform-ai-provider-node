"""Job creation, queue cap and sync polling. No ComfyUI imports."""

import asyncio
import secrets
import uuid
from collections.abc import Mapping
from typing import Literal

from .protocol import (
    FINAL_JOB_STATUSES,
    ImageJobRequest,
    Job,
    JobProgress,
    ProtocolError,
    VideoJobRequest,
)
from .runtime import Runtime
from .timeutil import iso_now

Kind = Literal["video", "image"]
_SYNC_POLL_SEC = 0.1
_UPLOAD_PREFIX = "upai-upload:"


def _upload_refs(value: object) -> tuple[str, ...]:
    """Collect upload hashes from a parsed request body."""
    found: list[str] = []
    if isinstance(value, str):
        if value.startswith(_UPLOAD_PREFIX):
            found.append(value.removeprefix(_UPLOAD_PREFIX))
    elif isinstance(value, Mapping):
        for item in value.values():
            found.extend(_upload_refs(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_upload_refs(item))

    return tuple(found)


async def _check_media_url(url: str, field: str, runtime: Runtime) -> None:
    if url.startswith("upai-upload:"):
        if await runtime.uploads.head_async(url.removeprefix("upai-upload:")) is None:
            raise ProtocolError(
                "upload_not_found",
                "upload not found",
                details={"field": field, "ref": url},
                status=404,
            )
        return

    if url.startswith(("http://", "https://")) and not runtime.config.allow_url_fetch:
        raise ProtocolError(
            "invalid_request",
            "URL fetch is disabled",
            details={"field": field},
        )


async def validate_media_urls(request: VideoJobRequest | ImageJobRequest, runtime: Runtime) -> None:
    """Check that upload refs exist and URL fetch is enabled."""
    frames = request.frame_images if isinstance(request, VideoJobRequest) else ()
    for frame in frames:
        await _check_media_url(frame.url, "frame_images", runtime)

    for reference in request.input_references:
        await _check_media_url(reference.url, "input_references", runtime)


async def create_job(
    runtime: Runtime,
    *,
    kind: Kind,
    model: str,
    prompt: str,
    seed: int | None,
    count: int,
    base_url: str,
    request: Mapping[str, object],
) -> Job:
    """Create a pending job and start its mock driver."""
    await runtime.enforce_results_quota()
    runtime.ensure_free_space()
    if runtime.result_root is not None:
        runtime.ensure_free_space(runtime.result_root)

    job = Job(
        id=str(uuid.uuid4()),
        kind=kind,
        model=model,
        status="pending",
        progress=JobProgress(
            percent=0,
            node=None,
            value=0,
            max=0,
            queue_position=0,
        ),
        seed=secrets.randbelow(2**31) if seed is None else seed,
        urls=None,
        error=None,
        usage_cost=0.0,
        created_at=iso_now(runtime.clock),
        started_at=None,
        finished_at=None,
        expires_at=None,
        files=(),
        base_url=base_url,
    )
    runtime.remember_request(job.id, request)
    created = await runtime.store.create_pending(job, runtime.config.max_pending)
    if created is None:
        runtime.forget_request(job.id)
        raise ProtocolError("queue_full", "too many pending jobs", status=429)

    runtime.pin_uploads(created.id, _upload_refs(request))
    if runtime.is_mock:
        await runtime.start_mock_job(created, prompt, count=count)
    return created


async def wait_for_job(runtime: Runtime, job_id: str) -> Job:
    """Poll until the job completes or the sync timeout expires."""
    deadline = runtime.clock() + runtime.config.sync_timeout_sec
    while True:
        job = await runtime.store.get(job_id)
        if job is None:
            raise ProtocolError(
                "internal",
                "job disappeared",
                details={"job_id": job_id},
                status=500,
            )

        if job.status == "completed":
            return job

        if job.status in FINAL_JOB_STATUSES:
            raise ProtocolError(
                "job_failed",
                "job did not complete",
                details={"job_id": job.id, "status": job.status, "error": job.error},
                status=502,
            )

        remaining = deadline - runtime.clock()
        if remaining <= 0:
            raise ProtocolError(
                "timeout",
                "job timed out",
                details={"job_id": job_id},
                status=504,
            )

        await asyncio.sleep(min(_SYNC_POLL_SEC, remaining))
