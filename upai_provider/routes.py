"""HTTP routes for the upai/1 protocol. No ComfyUI imports."""

import hmac
import logging
from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import urlsplit

from aiohttp import web

from .config import Config, classify_peer, is_allowed_host
from .constants import PROTOCOL_HEADER, PROTOCOL_VERSION
from .protocol import ProtocolError, error_to_wire
from .runtime import Runtime

logger = logging.getLogger(__name__)

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

_UPAI_PREFIXES = ("/upai", "/api/upai")
_HTTP_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}
UPAI_CONFIG_KEY = web.AppKey("upai_config", Config)
_default_config: Config | None = None


def _json_error(
    status: int,
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> web.Response:
    return web.json_response(error_to_wire(code, message, details or {}), status=status)


def wrap_handler(handler: Handler, config: Config, *, internal: bool = False) -> Handler:
    async def wrapped(request: web.Request) -> web.StreamResponse:
        try:
            if internal:
                internal_guard(request, config)
            else:
                guard(request, config)
            response = await handler(request)
        except ProtocolError as exc:
            response = _json_error(exc.status, exc.code, exc.message, exc.details)
        except web.HTTPRequestEntityTooLarge:
            response = _json_error(
                413,
                "too_large",
                "request body is too large",
                {"field": "body"},
            )
        except web.HTTPException:
            raise
        except Exception:
            logger.exception("request failed")
            response = _json_error(500, "internal", "internal error")

        response.headers[PROTOCOL_HEADER] = str(PROTOCOL_VERSION)
        return response

    return wrapped


def _request_config(request: web.Request) -> Config:
    config = request.app.get(UPAI_CONFIG_KEY)
    if isinstance(config, Config):
        return config

    return _default_config or Config()


@web.middleware
async def upai_middleware(request: web.Request, handler: Handler) -> web.StreamResponse:
    """Add the protocol header and guard router 404/405 errors as JSON envelopes."""
    is_upai = request.path.startswith(_UPAI_PREFIXES)
    try:
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            if not is_upai:
                raise

            code = _HTTP_ERROR_CODES.get(exc.status)
            if code is None:
                raise

            guard(request, _request_config(request))
            response = _json_error(exc.status, code, exc.reason or "", {})
    except ProtocolError as exc:
        if not is_upai:
            raise

        response = _json_error(exc.status, exc.code, exc.message, exc.details)

    if is_upai:
        response.headers[PROTOCOL_HEADER] = str(PROTOCOL_VERSION)

    return response


def guard(request: web.Request, config: Config) -> None:
    """Check Origin, Host, peer class and bearer token before any route work."""
    if config.is_config_invalid:
        raise ProtocolError("config_invalid", "config.json is invalid", status=503)

    origin = request.headers.get("Origin")
    if origin:
        normalized = origin.strip().lower().rstrip("/")
        allowed = {item.strip().lower().rstrip("/") for item in config.allowed_origins}
        if normalized not in allowed:
            raise ProtocolError("forbidden", "origin is not allowed", status=403)

    if not is_allowed_host(request.headers.get("Host"), config.allowed_hosts):
        raise ProtocolError("forbidden", "host is not allowed", status=403)

    sockname = (
        request.transport.get_extra_info("sockname") if request.transport is not None else None
    )
    peer = classify_peer(request.remote, sockname)
    if peer == "lan" and not config.allow_lan and not (config.allow_remote and config.token):
        raise ProtocolError("forbidden", "lan access is disabled", status=403)

    if peer == "public" and not (config.allow_remote and config.token):
        raise ProtocolError("forbidden", "remote access is disabled", status=403)

    if config.token:
        scheme, _, supplied = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not supplied:
            raise ProtocolError("unauthorized", "missing bearer token", status=401)
        if not hmac.compare_digest(supplied.encode(), config.token.encode()):
            raise ProtocolError("unauthorized", "invalid bearer token", status=401)


def internal_guard(request: web.Request, config: Config) -> None:
    """Guard internal routes: same origin, JSON body and peer policy, no token."""
    if config.is_config_invalid:
        raise ProtocolError("config_invalid", "config.json is invalid", status=503)

    host = request.headers.get("Host")
    if not is_allowed_host(host, config.allowed_hosts):
        raise ProtocolError("forbidden", "host is not allowed", status=403)

    origin = request.headers.get("Origin")
    if not origin or host is None or urlsplit(origin).netloc.lower() != host.strip().lower():
        raise ProtocolError("forbidden", "export requires a same-origin request", status=403)

    media_type = request.headers.get("Content-Type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise ProtocolError("invalid_request", "content type must be application/json", status=415)

    sockname = (
        request.transport.get_extra_info("sockname") if request.transport is not None else None
    )
    peer = classify_peer(request.remote, sockname)
    if peer == "lan" and not config.allow_lan:
        raise ProtocolError("forbidden", "lan access is disabled", status=403)
    if peer == "public":
        raise ProtocolError("forbidden", "remote access is disabled", status=403)


def not_found(_: Runtime) -> Handler:
    """Catch unmatched /upai paths before ComfyUI's static catch-all."""

    async def handler(_: web.Request) -> web.StreamResponse:
        raise ProtocolError("not_found", "not found", status=404)

    return handler


def route_specs(runtime: Runtime) -> list[tuple[str, str, Handler, bool]]:
    """Return method, path relative to /upai, handler and internal flag."""
    from .endpoints.content import content as real_content
    from .endpoints.export import export_workflow
    from .endpoints.images import create_image, sync_images
    from .endpoints.jobs import cancel_job, delete_job, get_job
    from .endpoints.system import health, models
    from .endpoints.uploads import content as mock_content
    from .endpoints.uploads import upload, upload_head
    from .endpoints.videos import create_video

    content = mock_content if runtime.is_mock else real_content
    return [
        ("GET", "/api/v1/health", health(runtime), False),
        ("GET", "/api/v1/videos/models", models(runtime, "video"), False),
        ("GET", "/api/v1/images/models", models(runtime, "image"), False),
        ("POST", "/api/v1/uploads", upload(runtime), False),
        ("HEAD", "/api/v1/uploads/{sha256}", upload_head(runtime), False),
        ("POST", "/api/v1/videos", create_video(runtime), False),
        ("GET", "/api/v1/videos/{id}", get_job(runtime, "video"), False),
        ("DELETE", "/api/v1/videos/{id}", delete_job(runtime, "video"), False),
        ("GET", "/api/v1/videos/{id}/content", content(runtime, "video"), False),
        ("POST", "/api/v1/videos/{id}/cancel", cancel_job(runtime, "video"), False),
        ("POST", "/api/v1/images/jobs", create_image(runtime), False),
        ("GET", "/api/v1/images/jobs/{id}", get_job(runtime, "image"), False),
        ("DELETE", "/api/v1/images/jobs/{id}", delete_job(runtime, "image"), False),
        ("GET", "/api/v1/images/jobs/{id}/content", content(runtime, "image"), False),
        ("POST", "/api/v1/images/jobs/{id}/cancel", cancel_job(runtime, "image"), False),
        ("POST", "/api/v1/images", sync_images(runtime), False),
        ("POST", "/internal/export", export_workflow(runtime), True),
        ("GET", "", not_found(runtime), False),
        ("GET", "/{tail:.*}", not_found(runtime), False),
    ]


def register_routes(table: web.RouteTableDef, runtime: Runtime) -> None:
    """Add every route under the /upai prefix to a ComfyUI route table."""
    global _default_config
    _default_config = runtime.config
    for method, path, handler, is_internal in route_specs(runtime):
        table.route(method, f"/upai{path}")(
            wrap_handler(handler, runtime.config, internal=is_internal)
        )


def add_routes(app: web.Application, runtime: Runtime) -> None:
    """Add every route under the /upai prefix to an aiohttp app."""
    app[UPAI_CONFIG_KEY] = runtime.config
    app.middlewares.append(upai_middleware)
    for method, path, handler, is_internal in route_specs(runtime):
        app.router.add_route(
            method,
            f"/upai{path}",
            wrap_handler(handler, runtime.config, internal=is_internal),
        )
