"""Shared fixtures and helpers for the upai/1 test suite."""

import asyncio
import io
import json
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from PIL import Image

from upai_provider.config import Config
from upai_provider.constants import UPLOAD_QUOTA_BYTES
from upai_provider.jobs import JobStore
from upai_provider.mock import MockTimings
from upai_provider.routes import add_routes
from upai_provider.runtime import Runtime
from upai_provider.uploads import UploadStore

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "protocol" / "schema"
FIXTURE_DIR = ROOT / "protocol" / "fixtures"

DEFAULT_TIMINGS = MockTimings(
    complete_sec=0.15,
    fail_sec=0.10,
    slow_sec=0.40,
    pending_sec=0.02,
    tick_sec=0.01,
)


class FakeClock:
    """Epoch clock the tests can advance by hand."""

    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_runtime(
    tmp_path: Path,
    *,
    config: Config | None = None,
    timings: MockTimings | None = None,
    max_upload_bytes: int = 1024 * 1024,
    max_total_bytes: int = UPLOAD_QUOTA_BYTES,
    clock: Callable[[], float] | None = None,
) -> Runtime:
    """Build a mock runtime rooted in tmp_path."""
    resolved_config = config or Config()
    resolved_clock = clock or time.time
    store = JobStore(
        tmp_path / "jobs.json",
        clock=resolved_clock,
        ttl_seconds=resolved_config.result_ttl_hours * 3600.0,
    )
    uploads = UploadStore(
        tmp_path / "uploads",
        max_bytes=max_upload_bytes,
        clock=resolved_clock,
        max_total_bytes=max_total_bytes,
    )
    return Runtime(
        config=resolved_config,
        store=store,
        uploads=uploads,
        data_dir=tmp_path,
        is_mock=True,
        server_name="mock",
        server_version="mock",
        timings=timings or DEFAULT_TIMINGS,
        clock=resolved_clock,
        free_space=lambda _: 10**12,
    )


async def make_client(
    aiohttp_client: Any,
    runtime: Runtime,
    *,
    client_max_size: int | None = None,
) -> TestClient:
    """Wrap a runtime in a minimal aiohttp app and a test client."""
    app = (
        web.Application()
        if client_max_size is None
        else web.Application(client_max_size=client_max_size)
    )
    add_routes(app, runtime)

    async def cancel_tasks(_: web.Application) -> None:
        tasks = list(runtime.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    app.on_cleanup.append(cancel_tasks)
    return await aiohttp_client(app)


async def wait_for_status(
    client: TestClient,
    url: str,
    statuses: tuple[str, ...],
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Poll a job url until its status is in statuses."""
    deadline = time.monotonic() + timeout
    while True:
        response = await client.get(url)
        body = cast(dict[str, Any], await response.json())
        if response.status != 200:
            raise AssertionError(f"job request failed: {response.status} {body}")

        if body.get("status") in statuses:
            return body

        if time.monotonic() >= deadline:
            raise AssertionError(f"job did not reach {statuses}: {body.get('status')}")

        await asyncio.sleep(0.01)


def load_schema(name: str) -> dict[str, Any]:
    """Load a schema by short name or file name."""
    filename = name if name.endswith(".json") else f"{name}.schema.json"
    return cast(dict[str, Any], json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8")))


def load_fixture(name: str) -> dict[str, Any]:
    """Load one protocol fixture."""
    return cast(dict[str, Any], json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8")))


def assert_schema(instance: object, schema_name: str) -> None:
    """Validate an instance against a protocol schema."""
    jsonschema.validate(instance, load_schema(schema_name))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def runtime(tmp_path: Path) -> Runtime:
    return make_runtime(tmp_path)


@pytest.fixture
async def client(aiohttp_client: Any, runtime: Runtime) -> AsyncIterator[TestClient]:
    yield await make_client(aiohttp_client, runtime)


@pytest.fixture
def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()
