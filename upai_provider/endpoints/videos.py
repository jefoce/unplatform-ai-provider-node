"""Video job handlers. No ComfyUI imports."""

from aiohttp import web

from ..protocol import CreateJobResponse, create_job_to_wire
from ..routes import Handler
from ..runtime import Runtime
from .create import create_from_request


def create_video(runtime: Runtime) -> Handler:
    async def handler(request: web.Request) -> web.StreamResponse:
        job, _ = await create_from_request(runtime, request, "video")
        response = CreateJobResponse(
            id=job.id,
            status="pending",
            polling_url=f"/upai/api/v1/videos/{job.id}",
        )
        return web.json_response(create_job_to_wire(response), status=202)

    return handler
