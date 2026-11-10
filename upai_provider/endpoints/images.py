"""Image job handlers. No ComfyUI imports."""

import asyncio
import base64

from aiohttp import web

from ..job_service import wait_for_job
from ..protocol import (
    CreateJobResponse,
    Job,
    ProtocolError,
    SyncImageItem,
    SyncImageResponse,
    create_job_to_wire,
    sync_images_to_wire,
)
from ..routes import Handler
from ..runtime import Runtime
from ..uploads import content_type_for
from .content import _result_path
from .create import create_from_request
from .uploads import asset_path


def _encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def _mock_image_items(runtime: Runtime, count: int) -> tuple[SyncImageItem, ...]:
    path = await asset_path(runtime, "image")
    encoded = _encode(await asyncio.to_thread(path.read_bytes))
    return tuple(SyncImageItem(encoded, "image/png") for _ in range(count))


def _real_image_items(runtime: Runtime, job: Job) -> tuple[SyncImageItem, ...]:
    items: list[SyncImageItem] = []
    for name in job.files:
        path = _result_path(runtime, name)
        if path is None:
            raise ProtocolError(
                "internal",
                "job result is unavailable",
                details={"job_id": job.id},
                status=500,
            )
        items.append(SyncImageItem(_encode(path.read_bytes()), content_type_for(path)))

    return tuple(items)


def create_image(runtime: Runtime) -> Handler:
    async def handler(request: web.Request) -> web.StreamResponse:
        job, _ = await create_from_request(runtime, request, "image")
        response = CreateJobResponse(
            id=job.id,
            status="pending",
            polling_url=f"/upai/api/v1/images/jobs/{job.id}",
        )
        return web.json_response(create_job_to_wire(response), status=202)

    return handler


def sync_images(runtime: Runtime) -> Handler:
    async def handler(request: web.Request) -> web.StreamResponse:
        job, count = await create_from_request(runtime, request, "image")
        completed = await wait_for_job(runtime, job.id)

        if runtime.is_mock:
            items = await _mock_image_items(runtime, count)
        else:
            items = await asyncio.to_thread(_real_image_items, runtime, completed)

        response = SyncImageResponse(data=items, usage_cost=0.0)
        return web.json_response(sync_images_to_wire(response))

    return handler
