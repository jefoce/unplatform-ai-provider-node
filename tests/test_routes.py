"""Route table, internal guard and content mode selection tests."""

from pathlib import Path
from typing import Any, cast

import pytest
from conftest import make_client, make_runtime
from helpers import TOKEN, guard_request, json_body
from test_exec_support import JOB_ID, make_job

from upai_provider.config import Config
from upai_provider.protocol import ProtocolError
from upai_provider.routes import internal_guard, route_specs


def test_internal_guard_requires_same_origin() -> None:
    config = Config(token=TOKEN, allowed_origins=("http://allowed.test",))

    with pytest.raises(ProtocolError) as denied:
        internal_guard(
            guard_request(
                "127.0.0.1",
                {
                    "Origin": "http://evil.test",
                    "Host": "127.0.0.1",
                    "Content-Type": "application/json",
                },
            ),
            config,
        )

    assert denied.value.status == 403


def test_internal_guard_checks_config_and_host() -> None:
    with pytest.raises(ProtocolError) as invalid:
        internal_guard(guard_request("127.0.0.1"), Config(is_config_invalid=True))
    assert invalid.value.status == 503

    with pytest.raises(ProtocolError) as host:
        internal_guard(
            guard_request("127.0.0.1", {"Host": "evil.test"}),
            Config(allowed_hosts=("127.0.0.1",)),
        )
    assert host.value.status == 403


def test_export_route_is_internal(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    internal = [
        (method, path) for method, path, _, is_internal in route_specs(runtime) if is_internal
    ]

    assert internal == [("POST", "/internal/export")]


async def test_internal_export_route_bypasses_token(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(token=TOKEN))
    client = await make_client(aiohttp_client, runtime)
    payload = {"source": "workflows/demo.json", "prompt": {}, "saved_at": 1.0}

    no_origin = await client.post("/upai/internal/export", json=payload)
    assert no_origin.status == 403

    response = await client.post(
        "/upai/internal/export",
        json=payload,
        headers={"Origin": str(client.make_url("")).rstrip("/")},
    )
    body = await json_body(response)
    assert response.status == 200
    assert body["status"] == "invalid"


class _RecordingTracker:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def set_server_url(self, server_url: str) -> None:
        self.urls.append(server_url)


async def test_create_uses_comfy_base_url_not_client_host(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = make_runtime(tmp_path)
    runtime.comfy_base_url = lambda: "http://127.0.0.1:9999"
    tracker = _RecordingTracker()
    runtime.tracker = cast(Any, tracker)
    client = await make_client(aiohttp_client, runtime)

    assert tracker.urls == []
    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "real"}
    )

    assert response.status == 202
    assert tracker.urls == ["http://127.0.0.1:9999"]
    assert not hasattr(runtime, "server_url")


async def test_real_content_route_serves_registered_file(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = make_runtime(tmp_path)
    runtime.is_mock = False
    root = tmp_path / "temp"
    result = root / JOB_ID / "0.png"
    result.parent.mkdir(parents=True)
    result.write_bytes(b"real-bytes")
    runtime.result_root = root
    await runtime.store.create(make_job(status="completed", files=(str(result),)))
    client = await make_client(aiohttp_client, runtime)

    response = await client.get(f"/upai/api/v1/images/jobs/{JOB_ID}/content?index=0")

    assert response.status == 200
    assert response.headers["Content-Type"] == "image/png"
    assert await response.read() == b"real-bytes"
