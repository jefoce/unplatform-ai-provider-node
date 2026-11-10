"""ComfyUI entry point for the Unplatform AI Provider pack."""

import asyncio
import atexit
import logging
import os
import time
from pathlib import Path
from typing import cast

import aiohttp
import comfyui_version  # pyright: ignore[reportMissingImports]
import folder_paths  # pyright: ignore[reportMissingImports]
import nodes as comfy_nodes  # pyright: ignore[reportMissingImports]
from comfy_api.latest import ComfyExtension  # pyright: ignore[reportMissingImports]
from server import PromptServer  # pyright: ignore[reportMissingImports]

try:
    from comfy import cli_args  # pyright: ignore[reportMissingImports]
except ImportError:  # pragma: no cover - ComfyUI always ships comfy.cli_args
    cli_args = None

from .upai_provider import jobs_output
from .upai_provider.config import load_config
from .upai_provider.constants import MAX_UPLOAD_BYTES_DEFAULT, SCHEDULER_TICK_SEC
from .upai_provider.execution import execute_job
from .upai_provider.export_registry import ExportRegistry
from .upai_provider.instance import load_instance_id
from .upai_provider.jobs import JobStore
from .upai_provider.materialize import HttpSession
from .upai_provider.mock import MockTimings
from .upai_provider.nodes.extension import UPaiExtension
from .upai_provider.protocol import (
    FINAL_JOB_STATUSES,
    ProtocolError,
    parse_image_job_request,
    parse_video_job_request,
)
from .upai_provider.routes import register_routes, upai_middleware
from .upai_provider.runtime import Runtime
from .upai_provider.scheduler import Scheduler
from .upai_provider.tracker import Tracker
from .upai_provider.uploads import UploadStore

WEB_DIRECTORY = "./web"

logger = logging.getLogger(__name__)

runtime: Runtime | None = None
_is_registered = False


async def _shutdown_async() -> None:
    """Stop background work and close the loopback sessions."""
    current = runtime
    if current is None:
        return

    if current.scheduler is not None:
        await current.scheduler.stop()
    if current.tracker is not None:
        await current.tracker.stop()

    tasks = list(current.tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            logger.warning("task shutdown failed", exc_info=True)

    session = current.session
    if session is not None:
        await session.close()
    fetch_session = current.fetch_session
    if fetch_session is not None and fetch_session is not session:
        await fetch_session.close()


def _shutdown() -> None:
    """Run shutdown from atexit without raising."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    try:
        if loop is None or loop.is_closed():
            asyncio.run(_shutdown_async())
        elif loop.is_running():
            loop.create_task(_shutdown_async())
        else:
            loop.run_until_complete(_shutdown_async())
    except Exception:
        logger.warning("runtime shutdown failed", exc_info=True)


def _is_tls() -> bool:
    args = getattr(cli_args, "args", None)
    return bool(getattr(args, "tls_keyfile", None) and getattr(args, "tls_certfile", None))


def _comfy_base_url() -> str:
    try:
        port = PromptServer.instance.port
    except (AttributeError, RuntimeError):
        port = 8188

    scheme = "https" if _is_tls() else "http"
    return f"{scheme}://127.0.0.1:{port or 8188}"


def _build_runtime() -> Runtime:
    user_root = Path(folder_paths.get_user_directory()) / "default"
    user_dir = user_root / "upai"
    input_root = Path(folder_paths.get_input_directory()) / "upai"
    result_root = Path(folder_paths.get_temp_directory()) / "upai"
    uploads_dir = input_root / "uploads"
    user_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(user_dir / "config.json")
    if config.allow_lan and not config.token:
        logger.warning(
            "allow_lan is on without a token; anyone on the local network can use the pack"
        )

    clock = time.time
    store = JobStore(
        user_dir / "jobs.json",
        clock=clock,
        ttl_seconds=config.result_ttl_hours * 3600.0,
    )
    uploads = UploadStore(uploads_dir, max_bytes=MAX_UPLOAD_BYTES_DEFAULT, clock=clock)
    exports = ExportRegistry(
        user_dir / "exports",
        source_root=user_root,
        known_classes=lambda: set(comfy_nodes.NODE_CLASS_MAPPINGS),
    )
    return Runtime(
        config=config,
        store=store,
        uploads=uploads,
        data_dir=user_dir,
        is_mock=os.environ.get("UPAI_MOCK") == "1",
        tls_enabled=_is_tls(),
        server_name="comfyui",
        server_version=comfyui_version.__version__,
        timings=MockTimings(),
        clock=clock,
        instance_id=load_instance_id(user_dir / "instance.json"),
        exports=exports,
        input_root=input_root,
        result_root=result_root,
        comfy_base_url=_comfy_base_url,
    )


async def _fetch_active_jobs(runtime: Runtime) -> tuple[str, ...]:
    if runtime.session is None:
        return ()

    url = f"{runtime.comfy_base_url().rstrip('/')}/api/jobs"
    try:
        async with runtime.session.get(url, params={"status": "pending,in_progress"}) as response:
            if response.status != 200:
                logger.warning("active job fetch failed: %s", response.status)
                return ()
            payload = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        logger.warning("active job fetch failed", exc_info=True)
        return ()

    if not isinstance(payload, dict):
        return ()

    entries = payload.get("jobs")
    if not isinstance(entries, list):
        return ()

    ids: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        job_id = entry.get("id")
        if isinstance(job_id, str):
            ids.append(job_id)

    return tuple(ids)


async def _cancel_comfy_prompt(prompt_id: str, is_running: bool) -> None:
    """Cancel one dispatched prompt in ComfyUI."""
    current = runtime
    if current is None or current.session is None:
        logger.warning("cancel prompt %s skipped: no session", prompt_id)
        return

    base = current.comfy_base_url().rstrip("/")
    try:
        if is_running:
            async with current.session.post(
                f"{base}/interrupt", json={"prompt_id": prompt_id}
            ) as response:
                status = response.status
        else:
            async with current.session.post(f"{base}/api/jobs/{prompt_id}/cancel") as response:
                status = response.status
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.warning("cancel prompt %s failed", prompt_id, exc_info=True)
        return

    if status >= 400:
        logger.warning("cancel prompt %s failed: %s", prompt_id, status)


async def _dispatch_job(runtime: Runtime, job_id: str) -> None:
    job = await runtime.store.get(job_id)
    if job is None or job.status in FINAL_JOB_STATUSES:
        return

    body = runtime.request_for(job_id)
    if body is None:
        await runtime.store.finalize(job_id, "failed", error="job request is missing")
        return

    exports = runtime.exports
    resolved = exports.find(job.model) if exports is not None else None
    if resolved is None:
        await runtime.store.finalize(job_id, "failed", error="model not found")
        return

    if resolved.status == "invalid":
        reason = resolved.status_reason or "unknown reason"
        await runtime.store.finalize(job_id, "failed", error=f"model is invalid: {reason}")
        return

    try:
        if resolved.model.kind == "video":
            request = parse_video_job_request(body)
            count = 1
        else:
            image_request = parse_image_job_request(body)
            request = image_request
            count = image_request.n or 1

        if runtime.session is None or runtime.input_root is None:
            await runtime.store.finalize(job_id, "failed", error="runtime is not ready")
            return

        await execute_job(
            job=job,
            model=resolved.model,
            prompt=resolved.export.prompt,
            request=request,
            store=runtime.store,
            uploads=runtime.uploads,
            session=cast(HttpSession, runtime.session),
            tracker=runtime.tracker,
            input_root=runtime.input_root,
            instance_id=runtime.instance_id,
            server_url=runtime.comfy_base_url(),
            count=count,
            allow_url_fetch=runtime.config.allow_url_fetch,
            fetch_session=cast(HttpSession | None, runtime.fetch_session),
            cancel_prompt=_cancel_comfy_prompt,
        )
    except ProtocolError as exc:
        await runtime.store.finalize(job_id, "failed", error=exc.message)
    except Exception:
        logger.exception("dispatch failed for job %s", job_id)
        await runtime.store.finalize(job_id, "failed", error="dispatch failed")


async def _scheduler_loop(runtime: Runtime) -> None:
    while True:
        await asyncio.sleep(SCHEDULER_TICK_SEC)
        try:
            if runtime.scheduler is not None:
                await runtime.scheduler.tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduler tick failed")


def _ensure_runtime() -> Runtime:
    """Build the runtime and register the protocol surface once."""
    global runtime, _is_registered

    if runtime is None:
        runtime = _build_runtime()

    if not _is_registered:
        _is_registered = True
        PromptServer.instance.app.middlewares.append(upai_middleware)
        register_routes(PromptServer.instance.routes, runtime)

    return runtime


class UPAIExtension(UPaiExtension):
    """Register the nodes and start the real execution loop."""

    async def on_load(self) -> None:
        current = _ensure_runtime()
        await current.store.load()
        jobs_output.configure_output(current.store, asyncio.get_running_loop())
        if current.tls_enabled:
            current.session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
            )
            current.fetch_session = aiohttp.ClientSession()
        else:
            current.session = aiohttp.ClientSession()
            current.fetch_session = current.session
        atexit.register(_shutdown)

        task = asyncio.create_task(current.sweep_loop())
        current.tasks.add(task)
        task.add_done_callback(current.tasks.discard)

        disk = asyncio.create_task(current.disk_free_loop())
        current.tasks.add(disk)
        disk.add_done_callback(current.tasks.discard)

        if current.is_mock:
            return

        current.tracker = Tracker(
            store=current.store,
            instance_id=current.instance_id,
            server_url=current.comfy_base_url(),
            session=current.session,
            cancel_prompt=_cancel_comfy_prompt,
        )
        await current.tracker.start()

        current.scheduler = Scheduler(
            current.store,
            max_running=current.config.max_running,
            fetch_active_jobs=lambda: _fetch_active_jobs(current),
            dispatch=lambda job_id: _dispatch_job(current, job_id),
            tracker=current.tracker,
            cancel_prompt=_cancel_comfy_prompt,
        )
        await current.scheduler.start()

        tick = asyncio.create_task(_scheduler_loop(current))
        current.tasks.add(tick)
        tick.add_done_callback(current.tasks.discard)


async def comfy_entrypoint() -> ComfyExtension:
    return UPAIExtension()
