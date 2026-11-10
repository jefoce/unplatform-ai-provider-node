"""Job lifecycle and request error route tests."""

import asyncio
import importlib.util
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
import test_nodes_support as support
from aiohttp import web
from aiohttp.test_utils import TestClient
from conftest import assert_schema, make_client, make_runtime, wait_for_status
from helpers import assert_error, json_body
from test_exec_support import make_job

from upai_provider.config import Config
from upai_provider.mock import MockTimings, video_models


def _uuid(index: int) -> str:
    return str(uuid.UUID(int=index, version=4))


async def test_cross_kind_cancel_is_404(client: TestClient) -> None:
    image = await json_body(
        await client.post(
            "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "[slow]"}
        )
    )
    wrong = await client.post(f"/upai/api/v1/videos/{image['id']}/cancel")
    assert wrong.status == 404
    assert_error(await json_body(wrong), "job_not_found")
    unchanged = await json_body(await client.get(image["polling_url"]))
    assert unchanged["status"] != "cancelled"

    video = await json_body(
        await client.post("/upai/api/v1/videos", json={"model": "wan22-t2v", "prompt": "[slow]"})
    )
    wrong = await client.post(f"/upai/api/v1/images/jobs/{video['id']}/cancel")
    assert wrong.status == 404
    assert_error(await json_body(wrong), "job_not_found")
    unchanged = await json_body(await client.get(video["polling_url"]))
    assert unchanged["status"] != "cancelled"


async def test_delete_job_routes(client: TestClient) -> None:
    created = await json_body(
        await client.post("/upai/api/v1/videos", json={"model": "wan22-t2v", "prompt": "[slow]"})
    )
    job_id = created["id"]

    conflict = await client.delete(f"/upai/api/v1/videos/{job_id}")
    assert conflict.status == 409
    assert_error(await json_body(conflict), "invalid_request")

    wrong_kind = await client.delete(f"/upai/api/v1/images/jobs/{job_id}")
    assert wrong_kind.status == 404
    assert_error(await json_body(wrong_kind), "job_not_found")

    missing = await client.delete("/upai/api/v1/videos/11111111-1111-4111-8111-111111111111")
    assert missing.status == 404
    assert_error(await json_body(missing), "job_not_found")

    assert (await client.post(f"/upai/api/v1/videos/{job_id}/cancel")).status == 200

    deleted = await client.delete(f"/upai/api/v1/videos/{job_id}")
    assert deleted.status == 204
    assert await deleted.read() == b""

    gone = await client.get(f"/upai/api/v1/videos/{job_id}")
    assert gone.status == 404
    assert_error(await json_body(gone), "job_not_found")


async def test_video_job_lifecycle(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/videos", json={"model": "wan22-t2v", "prompt": "smoke"}
    )
    assert response.status == 202
    created = await json_body(response)
    assert_schema(created, "create-job")

    job = await wait_for_status(client, created["polling_url"], ("completed",))
    assert_schema(job, "job")
    assert len(job["urls"]) == 1
    assert job["urls"][0].endswith(f"/videos/{created['id']}/content?index=0")

    content = await client.get(f"/upai/api/v1/videos/{created['id']}/content?index=0")
    assert content.status == 200
    assert content.headers["Content-Type"] == "video/mp4"
    assert content.headers.get("Content-Length") is not None
    await content.read()

    cancelled = await client.post(f"/upai/api/v1/videos/{created['id']}/cancel")
    assert (await json_body(cancelled))["status"] == "completed"


async def test_urls_follow_request_host(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/videos", json={"model": "wan22-t2v", "prompt": "host"}
    )
    created = await json_body(response)
    job = await wait_for_status(client, created["polling_url"], ("completed",))

    origin = str(client.make_url("")).rstrip("/")
    assert origin != "http://127.0.0.1:8190"
    assert job["urls"][0].startswith(origin)


async def test_each_job_keeps_its_own_base_url(client: TestClient) -> None:
    first = await json_body(
        await client.post(
            "/upai/api/v1/videos",
            json={"model": "wan22-t2v", "prompt": "alpha"},
            headers={"Host": "alpha.local:9999"},
        )
    )
    second = await json_body(
        await client.post(
            "/upai/api/v1/videos",
            json={"model": "wan22-t2v", "prompt": "beta"},
            headers={"Host": "beta.local:8888"},
        )
    )

    first_job = await wait_for_status(client, first["polling_url"], ("completed",))
    second_job = await wait_for_status(client, second["polling_url"], ("completed",))

    real_host = str(client.make_url("")).rstrip("/")
    first_base = first_job["urls"][0].split("/upai")[0]
    second_base = second_job["urls"][0].split("/upai")[0]
    assert first_job["urls"][0].startswith("http://alpha.local:9999/upai/api/v1/videos/")
    assert second_job["urls"][0].startswith("http://beta.local:8888/upai/api/v1/videos/")
    assert real_host not in first_job["urls"][0]
    assert real_host not in second_job["urls"][0]
    assert first_base != second_base


async def test_failed_job(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "[fail]"}
    )
    assert response.status == 202
    created = await json_body(response)

    job = await wait_for_status(client, created["polling_url"], ("failed",))
    assert job["error"] == "MockSampler: simulated failure"


async def test_slow_job_cancel(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    runtime.timings = MockTimings(
        complete_sec=5.0,
        fail_sec=5.0,
        slow_sec=5.0,
        pending_sec=0.01,
        tick_sec=0.01,
    )
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "[slow]"}
    )
    assert response.status == 202
    created = await json_body(response)

    await asyncio.sleep(0.1)
    job = await json_body(await client.get(created["polling_url"]))
    assert job["status"] == "in_progress"

    first = await client.post(f"/upai/api/v1/images/jobs/{created['id']}/cancel")
    cancelled = await json_body(first)
    assert cancelled["status"] == "cancelled"
    assert cancelled["finished_at"] is not None

    second = await client.post(f"/upai/api/v1/images/jobs/{created['id']}/cancel")
    again = await json_body(second)
    assert again["status"] == "cancelled"
    assert again["finished_at"] == cancelled["finished_at"]


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/upai/api/v1/videos", {"model": "wan22-t2v", "prompt": "[invalid]"}),
        ("/upai/api/v1/images/jobs", {"model": "sdxl-image", "prompt": "[invalid]"}),
    ],
)
async def test_invalid_workflow(client: TestClient, path: str, payload: dict[str, str]) -> None:
    response = await client.post(path, json=payload)
    assert response.status == 422
    assert_error(await json_body(response), "workflow_invalid")


async def test_unknown_model(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/videos", json={"model": "unknown-model", "prompt": "x"}
    )
    assert response.status == 404
    assert_error(await json_body(response), "model_not_found")


@pytest.mark.parametrize(
    "path",
    [
        "/upai/api/v1/videos/22222222-2222-4222-8222-222222222222",
        "/upai/api/v1/images/jobs/33333333-3333-4333-8333-333333333333",
    ],
)
async def test_unknown_job(client: TestClient, path: str) -> None:
    response = await client.get(path)
    assert response.status == 404
    assert_error(await json_body(response), "job_not_found")


async def test_malformed_json(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/videos",
        data=b"{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status == 400
    assert_error(await json_body(response), "invalid_request")


async def test_missing_prompt(client: TestClient) -> None:
    response = await client.post("/upai/api/v1/videos", json={"model": "wan22-t2v"})
    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "prompt"


async def test_queue_full(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(max_pending=1))
    runtime.timings = MockTimings(
        complete_sec=5.0,
        fail_sec=5.0,
        slow_sec=5.0,
        pending_sec=5.0,
        tick_sec=0.01,
    )
    client = await make_client(aiohttp_client, runtime)

    first = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "one"}
    )
    assert first.status == 202
    second = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "two"}
    )
    assert second.status == 429
    assert_error(await json_body(second), "queue_full")


async def test_queue_full_counts_running_job(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(max_pending=2))
    runtime.timings = MockTimings(
        complete_sec=5.0,
        fail_sec=5.0,
        slow_sec=5.0,
        pending_sec=0.02,
        tick_sec=0.01,
    )
    client = await make_client(aiohttp_client, runtime)

    first = await json_body(
        await client.post("/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "one"})
    )
    await wait_for_status(client, first["polling_url"], ("in_progress",))

    second = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "two"}
    )
    assert second.status == 202

    third = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "three"}
    )
    assert third.status == 429
    assert_error(await json_body(third), "queue_full")


async def test_queue_cap_is_atomic(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(max_pending=1))
    runtime.timings = MockTimings(
        complete_sec=5.0,
        fail_sec=5.0,
        slow_sec=5.0,
        pending_sec=5.0,
        tick_sec=0.01,
    )
    client = await make_client(aiohttp_client, runtime)

    payload = {"model": "sdxl-image", "prompt": "race"}
    first, second = await asyncio.gather(
        client.post("/upai/api/v1/images/jobs", json=payload),
        client.post("/upai/api/v1/images/jobs", json=payload),
    )

    assert sorted((first.status, second.status)) == [202, 429]
    rejected = first if first.status == 429 else second
    assert_error(await json_body(rejected), "queue_full")


async def test_content_requires_completed(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    runtime.timings = MockTimings(
        complete_sec=5.0,
        fail_sec=5.0,
        slow_sec=5.0,
        pending_sec=5.0,
        tick_sec=0.01,
    )
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "pending"}
    )
    created = await json_body(response)
    content = await client.get(f"/upai/api/v1/images/jobs/{created['id']}/content?index=0")
    assert content.status == 400
    assert_error(await json_body(content), "invalid_request")


class _FakeExports:
    def catalog(self, kind: str) -> tuple[Any, ...]:
        return video_models() if kind == "video" else ()


class _FakeScheduler:
    def __init__(self, store: Any = None, runtime: Any = None) -> None:
        self.calls: list[str] = []
        self.cancelled: list[str] = []
        self.requests: list[Any] = []
        self.store = store
        self.runtime = runtime

    async def enqueue(self, job_id: str) -> None:
        self.calls.append(job_id)
        if self.runtime is not None:
            self.requests.append(self.runtime.request_for(job_id))

    async def cancel(self, job_id: str) -> Any:
        self.cancelled.append(job_id)
        return await self.store.cancel(job_id)


async def test_real_create_enqueues_scheduler(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    runtime.is_mock = False
    runtime.exports = cast(Any, _FakeExports())
    scheduler = _FakeScheduler(runtime=runtime)
    runtime.scheduler = cast(Any, scheduler)
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/videos", json={"model": "wan22-t2v", "prompt": "real"}
    )
    assert response.status == 202
    created = await json_body(response)

    assert scheduler.calls == [created["id"]]
    assert scheduler.requests == [{"model": "wan22-t2v", "prompt": "real"}]
    stored = await runtime.store.get(created["id"])
    assert stored is not None
    assert runtime.request_for(created["id"]) == {"model": "wan22-t2v", "prompt": "real"}


async def test_real_cancel_routes_through_scheduler(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    runtime.is_mock = False
    runtime.exports = cast(Any, _FakeExports())
    scheduler = _FakeScheduler(runtime.store)
    runtime.scheduler = cast(Any, scheduler)
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/videos", json={"model": "wan22-t2v", "prompt": "real"}
    )
    created = await json_body(response)

    cancelled = await client.post(f"/upai/api/v1/videos/{created['id']}/cancel")

    assert (await json_body(cancelled))["status"] == "cancelled"
    assert scheduler.cancelled == [created["id"]]


class _CancelResponse:
    status = 200

    async def __aenter__(self) -> "_CancelResponse":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _CancelSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> _CancelResponse:
        self.calls.append((url, kwargs))
        return _CancelResponse()


class _FakeApp:
    def __init__(self) -> None:
        self.middlewares: list[Any] = []


class _FakePromptServer:
    class _Instance:
        port = 8188
        routes = web.RouteTableDef()
        app = _FakeApp()

    instance = _Instance()


def _import_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, build: bool = True
) -> ModuleType:
    support.install()
    support.set_directories(
        input=tmp_path / "input",
        temp=tmp_path / "temp",
        user=tmp_path / "user",
    )
    _FakePromptServer._Instance.app = _FakeApp()
    _FakePromptServer._Instance.routes = web.RouteTableDef()
    version = ModuleType("comfyui_version")
    version.__version__ = "0.0.0"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "comfyui_version", version)
    comfy_nodes = ModuleType("nodes")
    comfy_nodes.NODE_CLASS_MAPPINGS = {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "nodes", comfy_nodes)
    server = ModuleType("server")
    server.PromptServer = _FakePromptServer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "server", server)

    root = Path(__file__).resolve().parents[1]
    name = "_upai_entry_test"
    spec = importlib.util.spec_from_file_location(
        name, root / "__init__.py", submodule_search_locations=[str(root)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    if build:
        cast(Any, module)._ensure_runtime()
    return module


def test_import_has_no_runtime_or_route_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = cast(Any, _import_entry(tmp_path, monkeypatch, build=False))

    assert entry.runtime is None
    assert _FakePromptServer._Instance.app.middlewares == []
    assert len(_FakePromptServer._Instance.routes) == 0

    built = entry._ensure_runtime()
    entry._ensure_runtime()

    assert built is entry.runtime
    assert _FakePromptServer._Instance.app.middlewares == [entry.upai_middleware]
    assert len(_FakePromptServer._Instance.routes) > 0


async def test_cancel_comfy_prompt_posts_to_comfy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = cast(Any, _import_entry(tmp_path, monkeypatch))
    session = _CancelSession()
    entry.runtime.session = session
    entry.runtime.comfy_base_url = lambda: "http://127.0.0.1:9999/"

    await entry._cancel_comfy_prompt("prompt-1", True)
    await entry._cancel_comfy_prompt("prompt-2", False)

    assert session.calls == [
        ("http://127.0.0.1:9999/interrupt", {"json": {"prompt_id": "prompt-1"}}),
        ("http://127.0.0.1:9999/api/jobs/prompt-2/cancel", {}),
    ]

    for name in list(sys.modules):
        if name.startswith("_upai_entry_test."):
            sys.modules.pop(name, None)


async def test_create_returns_507_when_free_space_low(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    runtime.free_space = lambda path: 0
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "disk"}
    )

    assert response.status == 507
    assert_error(await json_body(response), "insufficient_storage")


async def test_results_quota_removes_expired_oldest_results(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    result_root = tmp_path / "temp"
    runtime = make_runtime(tmp_path, config=Config(results_quota_bytes=100))
    runtime.result_root = result_root
    now = int(runtime.clock())
    created = []
    for index in range(3):
        job_id = _uuid(index + 1)
        result = result_root / job_id / "0.png"
        result.parent.mkdir(parents=True)
        result.write_bytes(b"x" * 80)
        job = await runtime.store.create(
            replace(
                make_job(job_id=job_id, status="completed", files=(str(result),)),
                expires_at=now - 1 if index < 2 else now + 3600,
            )
        )
        created.append(job)
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "quota"}
    )

    assert response.status == 202
    assert await runtime.store.get(created[0].id) is None
    assert await runtime.store.get(created[1].id) is None
    assert await runtime.store.get(created[2].id) is not None
    assert not (result_root / created[1].id).exists()
    assert (result_root / created[2].id / "0.png").exists()


async def test_results_quota_returns_507_without_deleting_unexpired(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    result_root = tmp_path / "temp"
    runtime = make_runtime(tmp_path, config=Config(results_quota_bytes=50))
    runtime.result_root = result_root
    result = result_root / "run" / "0.png"
    result.parent.mkdir(parents=True)
    result.write_bytes(b"x" * 80)
    now = int(runtime.clock())
    job = await runtime.store.create(
        replace(
            make_job(job_id=_uuid(1), status="completed", files=(str(result),)),
            expires_at=now + 3600,
        )
    )
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "quota"}
    )

    assert response.status == 507
    assert_error(await json_body(response), "insufficient_storage")
    assert await runtime.store.get(job.id) is not None
    assert result.exists()


async def test_create_returns_507_when_result_volume_free_space_low(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = make_runtime(tmp_path)
    runtime.result_root = tmp_path / "temp"
    runtime.free_space = lambda path: 0 if path == runtime.result_root else 10**12
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "disk"}
    )

    assert response.status == 507
    assert_error(await json_body(response), "insufficient_storage")


async def test_delete_removes_job_files_not_shared_uploads(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = make_runtime(tmp_path)
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    job_id = _uuid(1)
    input_file = runtime.input_root / job_id / "image_1.png"
    input_file.parent.mkdir(parents=True)
    input_file.write_bytes(b"job-input")
    result = runtime.result_root / job_id / "0.png"
    result.parent.mkdir(parents=True)
    result.write_bytes(b"result")
    shared = runtime.input_root / "uploads" / "shared.png"
    shared.parent.mkdir(parents=True)
    shared.write_bytes(b"shared")
    await runtime.store.create(make_job(job_id=job_id, status="completed", files=(str(result),)))
    client = await make_client(aiohttp_client, runtime)

    response = await client.delete(f"/upai/api/v1/images/jobs/{job_id}")

    assert response.status == 204
    assert not input_file.exists()
    assert not result.exists()
    assert shared.read_bytes() == b"shared"


async def test_delete_non_final_job_keeps_files(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    job_id = _uuid(1)
    input_file = runtime.input_root / job_id / "image_1.png"
    input_file.parent.mkdir(parents=True)
    input_file.write_bytes(b"job-input")
    await runtime.store.create(make_job(job_id=job_id, status="in_progress"))
    client = await make_client(aiohttp_client, runtime)

    response = await client.delete(f"/upai/api/v1/images/jobs/{job_id}")

    assert response.status == 409
    assert_error(await json_body(response), "invalid_request")
    assert input_file.exists()


async def test_delete_releases_upload_pins(aiohttp_client: Any, tmp_path: Path) -> None:
    import os
    import time

    runtime = make_runtime(tmp_path)
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    job_id = _uuid(1)
    upload = await runtime.uploads.save("frame.png", "image/png", b"png")
    stored = runtime.uploads.path(upload.sha256)
    assert stored is not None
    runtime.pin_uploads(job_id, (upload.sha256,))
    await runtime.store.create(make_job(job_id=job_id, status="cancelled"))
    client = await make_client(aiohttp_client, runtime)

    response = await client.delete(f"/upai/api/v1/images/jobs/{job_id}")

    assert response.status == 204
    os.utime(stored, (1, 1))
    runtime.uploads.sweep(max_age_sec=10, now=time.time())
    assert not stored.exists()
