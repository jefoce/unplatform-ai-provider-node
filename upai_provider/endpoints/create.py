"""Shared create flow for video and image requests. No ComfyUI imports."""

import asyncio
from collections.abc import Mapping
from typing import cast

from aiohttp import web

from ..job_service import Kind, create_job, validate_media_urls
from ..protocol import (
    ImageJobRequest,
    Job,
    ProtocolError,
    VideoJobRequest,
    parse_image_job_request,
    parse_video_job_request,
)
from ..registry import find_model
from ..runtime import Runtime
from ..validation import check_image_reference_limits, check_invalid_prompt, read_json
from ..validation_image import validate_image
from ..validation_video import validate_video


async def create_from_request(
    runtime: Runtime,
    request: web.Request,
    kind: Kind,
) -> tuple[Job, int]:
    """Parse, validate and create one job from a request body."""
    body = await read_json(request)
    payload: VideoJobRequest | ImageJobRequest = (
        parse_video_job_request(body) if kind == "video" else parse_image_job_request(body)
    )
    catalog = await asyncio.to_thread(runtime.catalog, kind)
    model = find_model(catalog, payload.model, kind)
    if model is None:
        raise ProtocolError(
            "model_not_found",
            "model not found",
            details={"model": payload.model},
            status=404,
        )

    if model.status == "invalid":
        raise ProtocolError(
            "invalid_request",
            f"model is invalid: {model.status_reason or 'unknown reason'}",
            details={"field": "model"},
        )

    if runtime.tracker is not None:
        runtime.tracker.set_server_url(runtime.comfy_base_url())

    await validate_media_urls(payload, runtime)
    if isinstance(payload, VideoJobRequest):
        validate_video(payload, model)
        count = 1
    else:
        count = validate_image(payload, model)

    if runtime.is_mock:
        check_invalid_prompt(payload.prompt)
    await check_image_reference_limits(
        references=payload.input_references,
        frames=payload.frame_images if isinstance(payload, VideoJobRequest) else (),
        limit=model.capabilities.reference_limits.image,
        uploads=runtime.uploads,
    )
    job = await create_job(
        runtime,
        kind=kind,
        model=payload.model,
        prompt=payload.prompt,
        seed=payload.seed,
        count=count,
        base_url=str(request.url.origin()),
        request=cast(Mapping[str, object], body),
    )
    if not runtime.is_mock and runtime.scheduler is not None:
        await runtime.scheduler.enqueue(job.id)

    return job, count
