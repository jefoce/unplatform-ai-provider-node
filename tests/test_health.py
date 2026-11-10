"""Health, model listing and capability route tests."""

import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
from aiohttp.test_utils import TestClient
from conftest import assert_schema, make_client, make_runtime
from helpers import HEALTH, json_body

import upai_provider.diskutil as diskutil_module
from upai_provider.config import Config
from upai_provider.constants import INLINE_JSON_MARGIN
from upai_provider.runtime import Runtime


async def test_health(client: TestClient, runtime: Runtime) -> None:
    response = await client.get(HEALTH)
    assert response.status == 200
    body = await json_body(response)
    assert_schema(body, "health")
    assert body["protocol"] == 1
    assert body["server"] == "mock"
    assert body["auth_required"] is False
    assert body["lan_allowed"] is False
    assert body["upload_quota_bytes"] == runtime.uploads.max_total_bytes
    assert body["instance_id"] == ""
    assert body["max_running"] == 1
    assert body["max_pending"] == runtime.config.max_pending
    assert body["max_inline_bytes"] == (body["max_upload_bytes"] - INLINE_JSON_MARGIN) * 3 // 4
    assert body["disk_free_bytes"] > 0
    assert body["result_delete"] is True


async def test_health_reports_instance_and_max_running(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(max_running=3))
    runtime.instance_id = str(uuid.uuid4())
    client = await make_client(aiohttp_client, runtime)

    body = await json_body(await client.get(HEALTH))
    assert_schema(body, "health")
    assert body["instance_id"] == runtime.instance_id
    assert body["max_running"] == 3


async def test_health_reports_lan_allowed(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(allow_lan=True))
    client = await make_client(aiohttp_client, runtime)

    body = await json_body(await client.get(HEALTH))
    assert_schema(body, "health")
    assert body["lan_allowed"] is True


async def test_health_reports_tightest_pack_volume(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    free = {runtime.input_root: 900, runtime.result_root: 500, runtime.data_dir: 300}
    runtime.free_space = lambda path: free[path]
    runtime.refresh_disk_free()
    client = await make_client(aiohttp_client, runtime)

    body = await json_body(await client.get(HEALTH))
    assert body["disk_free_bytes"] == 300


async def test_health_reads_cache_without_disk_usage(
    aiohttp_client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(tmp_path)
    runtime.free_space = None
    runtime.disk_free_bytes = 123

    def fail(path: Path) -> Any:
        raise OSError("disk usage should not run on the event loop")

    monkeypatch.setattr(diskutil_module.shutil, "disk_usage", fail)
    client = await make_client(aiohttp_client, runtime)

    response = await client.get(HEALTH)
    body = await json_body(response)
    assert response.status == 200
    assert body["disk_free_bytes"] == 123


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/upai/api/v1/videos/models", ["wan22-i2v", "wan22-t2v"]),
        ("/upai/api/v1/images/models", ["sdxl-image"]),
    ],
)
async def test_models(client: TestClient, path: str, expected: list[str]) -> None:
    response = await client.get(path)
    assert response.status == 200
    body = await json_body(response)
    assert_schema(body, "models")
    assert [model["id"] for model in body["data"]] == expected


async def test_catalog_runs_off_event_loop(
    aiohttp_client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(tmp_path)
    original = runtime.catalog
    threads: list[threading.Thread] = []

    def recording(kind: Any) -> Any:
        threads.append(threading.current_thread())
        return original(kind)

    monkeypatch.setattr(runtime, "catalog", recording)
    client = await make_client(aiohttp_client, runtime)

    response = await client.get("/upai/api/v1/videos/models")
    assert response.status == 200
    assert threads
    assert threads[0] is not threading.main_thread()
