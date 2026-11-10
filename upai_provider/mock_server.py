"""Standalone mock server for the upai/1 protocol. Imports no ComfyUI module."""

import argparse
import asyncio
import contextlib
import logging
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from aiohttp import web

from .config import load_config
from .constants import MAX_UPLOAD_BYTES_DEFAULT
from .jobs import JobStore
from .mock import MockTimings
from .routes import add_routes
from .runtime import Runtime
from .uploads import UploadStore

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the upai/1 mock server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8190)
    parser.add_argument("--data-dir")
    parser.add_argument("--token")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--allow-lan", action="store_true")
    parser.add_argument("--max-upload-bytes", type=int)
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    data_dir = Path(args.data_dir) if args.data_dir else Path(tempfile.gettempdir()) / "upai-mock"
    data_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(data_dir / "config.json")
    if args.token is not None:
        config = replace(config, token=args.token)
    if args.allow_remote:
        config = replace(config, allow_remote=True)
    if args.allow_lan:
        config = replace(config, allow_lan=True)

    if config.allow_lan and not config.token:
        logger.warning(
            "allow_lan is on without a token; anyone on the local network can use the pack"
        )

    max_bytes = MAX_UPLOAD_BYTES_DEFAULT if args.max_upload_bytes is None else args.max_upload_bytes
    host_for_url = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host  # noqa: S104
    public_base_url = f"http://{host_for_url}:{args.port}"

    clock = time.time
    store = JobStore(
        data_dir / "jobs.json",
        clock=clock,
        ttl_seconds=config.result_ttl_hours * 3600.0,
    )
    uploads = UploadStore(data_dir / "uploads", max_bytes=max_bytes, clock=clock)
    runtime = Runtime(
        config=config,
        store=store,
        uploads=uploads,
        data_dir=data_dir,
        is_mock=True,
        server_name="mock",
        server_version="mock",
        timings=MockTimings(),
        clock=clock,
    )

    await store.load()
    app = web.Application(client_max_size=max_bytes)
    add_routes(app, runtime)

    sweep_task: asyncio.Task[None] | None = None
    disk_task: asyncio.Task[None] | None = None

    async def on_startup(_: web.Application) -> None:
        nonlocal sweep_task, disk_task
        sweep_task = asyncio.create_task(runtime.sweep_loop())
        disk_task = asyncio.create_task(runtime.disk_free_loop())

    async def on_cleanup(_: web.Application) -> None:
        nonlocal sweep_task, disk_task
        if sweep_task is not None:
            sweep_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweep_task
            sweep_task = None
        if disk_task is not None:
            disk_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await disk_task
            disk_task = None

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    await site.start()
    logger.info("mock server on %s/upai", public_base_url)

    stop = asyncio.Event()
    try:
        await stop.wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
