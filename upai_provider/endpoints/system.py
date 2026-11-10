"""Health and model catalog handlers. No ComfyUI imports."""

import asyncio

from aiohttp import web

from ..constants import IMPLEMENTATION_NAME, PROTOCOL_VERSION
from ..job_service import Kind
from ..protocol import Health, ModelList, health_to_wire, models_to_wire
from ..routes import Handler
from ..runtime import Runtime
from ..version import __version__
from .uploads import effective_inline_cap, effective_upload_cap


def health(runtime: Runtime) -> Handler:
    async def handler(request: web.Request) -> web.StreamResponse:
        health = Health(
            protocol=PROTOCOL_VERSION,
            server=runtime.server_name,
            server_version=runtime.server_version,
            implementation=IMPLEMENTATION_NAME,
            implementation_version=__version__,
            auth_required=bool(runtime.config.token),
            lan_allowed=runtime.config.allow_lan,
            max_upload_bytes=effective_upload_cap(request, runtime),
            upload_quota_bytes=runtime.uploads.max_total_bytes,
            instance_id=runtime.instance_id,
            max_running=runtime.config.max_running,
            max_pending=runtime.config.max_pending,
            max_inline_bytes=effective_inline_cap(request, runtime),
            disk_free_bytes=runtime.disk_free_bytes,
            result_delete=True,
        )
        return web.json_response(health_to_wire(health))

    return handler


def models(runtime: Runtime, kind: Kind) -> Handler:
    async def handler(request: web.Request) -> web.StreamResponse:
        model_list = ModelList(await asyncio.to_thread(runtime.catalog, kind))
        return web.json_response(models_to_wire(model_list.data))

    return handler
