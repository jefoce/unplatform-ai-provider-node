"""Job lookup and cancel handlers shared by both kinds. No ComfyUI imports."""

from aiohttp import web

from ..job_service import Kind
from ..protocol import FINAL_JOB_STATUSES, ProtocolError, job_to_wire
from ..routes import Handler
from ..runtime import Runtime


def get_job(runtime: Runtime, kind: Kind) -> Handler:
    """Return a handler that reads one job of a kind."""

    async def handler(request: web.Request) -> web.StreamResponse:
        job = await runtime.store.get(request.match_info["id"])
        if job is None or job.kind != kind:
            raise ProtocolError("job_not_found", "job not found", status=404)

        return web.json_response(job_to_wire(job))

    return handler


def delete_job(runtime: Runtime, kind: Kind) -> Handler:
    """Return a handler that deletes one final job of a kind."""

    async def handler(request: web.Request) -> web.StreamResponse:
        job = await runtime.store.get(request.match_info["id"])
        if job is None or job.kind != kind:
            raise ProtocolError("job_not_found", "job not found", status=404)

        if job.status not in FINAL_JOB_STATUSES:
            raise ProtocolError(
                "invalid_request",
                "job is not final",
                details={"field": "status"},
                status=409,
            )

        await runtime.delete_job(job.id)
        return web.Response(status=204)

    return handler


def cancel_job(runtime: Runtime, kind: Kind) -> Handler:
    """Return a handler that cancels one job of a kind."""

    async def handler(request: web.Request) -> web.StreamResponse:
        job_id = request.match_info["id"]
        found = await runtime.store.get(job_id)
        if found is None or found.kind != kind:
            raise ProtocolError("job_not_found", "job not found", status=404)

        if not runtime.is_mock and runtime.scheduler is not None:
            job = await runtime.scheduler.cancel(job_id)
        else:
            job = await runtime.store.cancel(job_id)
        if job is None:
            raise ProtocolError("job_not_found", "job not found", status=404)

        return web.json_response(job_to_wire(job))

    return handler
