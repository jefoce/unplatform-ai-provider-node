"""Internal export route tests."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from conftest import make_runtime
from helpers import TOKEN, guard_request
from test_export_support import copy_prompt, video_prompt

from upai_provider.config import Config
from upai_provider.endpoints.export import _source, export_workflow
from upai_provider.export_registry import ExportRegistry
from upai_provider.protocol import ProtocolError
from upai_provider.routes import internal_guard, upai_middleware, wrap_handler


async def make_export_client(aiohttp_client: Any, tmp_path: Path) -> tuple[TestClient, Path]:
    runtime = make_runtime(tmp_path)
    data_dir = tmp_path / "user"
    data_dir.mkdir()
    runtime.data_dir = data_dir
    app = web.Application()
    app.middlewares.append(upai_middleware)
    handler = export_workflow(runtime)
    app.router.add_post(
        "/upai/internal/export", wrap_handler(handler, runtime.config, internal=True)
    )
    return await aiohttp_client(app), data_dir


def payload(prompt: dict[str, Any], *, source: str = "workflows/demo.json") -> dict[str, Any]:
    return {"source": source, "prompt": prompt, "saved_at": 100.0}


async def test_export_route_rejects_missing_origin(aiohttp_client: Any, tmp_path: Path) -> None:
    client, _ = await make_export_client(aiohttp_client, tmp_path)
    response = await client.post("/upai/internal/export", json=payload(video_prompt()))
    assert response.status == 403


async def test_export_route_rejects_cross_origin(aiohttp_client: Any, tmp_path: Path) -> None:
    client, _ = await make_export_client(aiohttp_client, tmp_path)
    response = await client.post(
        "/upai/internal/export",
        json=payload(video_prompt()),
        headers={"Origin": "http://evil.test"},
    )
    assert response.status == 403


async def test_export_route_writes_export_file(aiohttp_client: Any, tmp_path: Path) -> None:
    client, data_dir = await make_export_client(aiohttp_client, tmp_path)
    origin = str(client.make_url("/")).rstrip("/")
    (tmp_path / "workflows").mkdir()
    (tmp_path / "workflows" / "demo.json").write_text("{}", encoding="utf-8")
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["price_per_run_usd"] = 1.5

    response = await client.post(
        "/upai/internal/export",
        json=payload(prompt),
        headers={"Origin": origin},
    )
    body = cast(dict[str, Any], await response.json())

    assert response.status == 200
    assert body["id"] == "demo"
    assert body["status"] == "ready"
    assert body["status_reason"] is None
    path = data_dir / "exports" / "demo.json"
    assert path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["models"][0]["model_id"] == "wan"
    assert saved["models"][0]["price_per_run_usd"] == 1.5
    assert saved["source_mtime"] == (tmp_path / "workflows" / "demo.json").stat().st_mtime


async def test_export_route_returns_invalid_reason(aiohttp_client: Any, tmp_path: Path) -> None:
    client, data_dir = await make_export_client(aiohttp_client, tmp_path)
    origin = str(client.make_url("/")).rstrip("/")
    prompt = copy_prompt(video_prompt())
    prompt["6"]["inputs"]["index"] = 3

    response = await client.post(
        "/upai/internal/export",
        json=payload(prompt),
        headers={"Origin": origin},
    )
    body = cast(dict[str, Any], await response.json())

    assert response.status == 200
    assert body["status"] == "invalid"
    assert "contiguous" in body["status_reason"]
    assert (data_dir / "exports" / "demo.json").is_file()


async def test_export_route_writes_no_file_without_models(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    client, data_dir = await make_export_client(aiohttp_client, tmp_path)
    origin = str(client.make_url("/")).rstrip("/")

    response = await client.post(
        "/upai/internal/export",
        json=payload({"1": {"class_type": "UPAIOutput", "inputs": {}}}),
        headers={"Origin": origin},
    )
    body = cast(dict[str, Any], await response.json())

    assert body["status"] == "invalid"
    assert body["status_reason"] == "no UPAI Model node found"
    assert not (data_dir / "exports").exists()


async def test_export_route_rejects_unsafe_source(aiohttp_client: Any, tmp_path: Path) -> None:
    client, _ = await make_export_client(aiohttp_client, tmp_path)
    origin = str(client.make_url("/")).rstrip("/")

    response = await client.post(
        "/upai/internal/export",
        json=payload(video_prompt(), source="../outside.json"),
        headers={"Origin": origin},
    )
    assert response.status == 400


@pytest.mark.parametrize(
    "source",
    ["C:/workflows/demo.json", "C:\\workflows\\demo.json", "c:demo.json"],
)
def test_export_source_rejects_windows_drive(source: str) -> None:
    with pytest.raises(ProtocolError):
        _source(source)


def test_export_source_accepts_relative_json() -> None:
    assert _source("workflows/demo.json") == "workflows/demo.json"


async def test_export_route_rejects_bad_saved_at(aiohttp_client: Any, tmp_path: Path) -> None:
    client, _ = await make_export_client(aiohttp_client, tmp_path)
    origin = str(client.make_url("/")).rstrip("/")

    response = await client.post(
        "/upai/internal/export",
        json={"source": "workflows/demo.json", "prompt": {}, "saved_at": "now"},
        headers={"Origin": origin},
    )
    assert response.status == 400


async def test_export_route_rejects_non_json(aiohttp_client: Any, tmp_path: Path) -> None:
    client, _ = await make_export_client(aiohttp_client, tmp_path)
    origin = str(client.make_url("/")).rstrip("/")

    response = await client.post(
        "/upai/internal/export",
        data=json.dumps(payload(video_prompt())),
        headers={"Origin": origin, "Content-Type": "text/plain"},
    )
    assert response.status == 415


async def test_export_route_deletes_file_when_all_models_are_removed(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    client, data_dir = await make_export_client(aiohttp_client, tmp_path)
    origin = str(client.make_url("/")).rstrip("/")
    path = data_dir / "exports" / "demo.json"

    first = await client.post(
        "/upai/internal/export",
        json=payload(video_prompt()),
        headers={"Origin": origin},
    )
    assert first.status == 200
    assert path.is_file()

    second = await client.post(
        "/upai/internal/export",
        json=payload({"1": {"class_type": "UPAIOutput", "inputs": {}}}),
        headers={"Origin": origin},
    )
    assert second.status == 200
    assert not path.exists()
    assert ExportRegistry(data_dir / "exports", source_root=tmp_path).catalog("video") == ()


async def test_export_route_keeps_old_export_after_rename(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    client, data_dir = await make_export_client(aiohttp_client, tmp_path)
    origin = str(client.make_url("/")).rstrip("/")
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "old.json").write_text("{}", encoding="utf-8")
    (workflows / "new.json").write_text("{}", encoding="utf-8")

    for source in ("workflows/old.json", "workflows/new.json"):
        response = await client.post(
            "/upai/internal/export",
            json=payload(video_prompt(), source=source),
            headers={"Origin": origin},
        )
        assert response.status == 200

    (workflows / "old.json").unlink()
    registry = ExportRegistry(data_dir / "exports", source_root=tmp_path)
    models = {model.id: model for model in registry.catalog("video")}

    assert (data_dir / "exports" / "old.json").is_file()
    assert models["old.wan"].status == "invalid"
    assert models["old.wan"].status_reason == "source workflow was deleted"
    assert models["new.wan"].status == "ready"


def _same_origin_headers(host: str) -> dict[str, str]:
    return {
        "Host": host,
        "Origin": f"http://{host}",
        "Content-Type": "application/json",
    }


def test_internal_guard_allows_loopback() -> None:
    internal_guard(guard_request("127.0.0.1", _same_origin_headers("127.0.0.1")), Config())


def test_internal_guard_rejects_public_peer() -> None:
    config = Config(allow_remote=True, token=TOKEN)
    with pytest.raises(ProtocolError) as denied:
        internal_guard(guard_request("8.8.8.8", _same_origin_headers("8.8.8.8")), config)

    assert denied.value.status == 403
    assert denied.value.message == "remote access is disabled"


def test_internal_guard_allows_lan_with_allow_lan() -> None:
    headers = _same_origin_headers("192.168.1.10:8188")
    internal_guard(guard_request("192.168.1.10", headers), Config(allow_lan=True))


def test_internal_guard_rejects_lan_without_allow_lan() -> None:
    headers = _same_origin_headers("192.168.1.10:8188")
    with pytest.raises(ProtocolError) as denied:
        internal_guard(guard_request("192.168.1.10", headers), Config())

    assert denied.value.status == 403
    assert denied.value.message == "lan access is disabled"


def test_internal_guard_rejects_lan_with_remote_and_token() -> None:
    headers = _same_origin_headers("192.168.1.10:8188")
    config = Config(allow_remote=True, token=TOKEN)
    with pytest.raises(ProtocolError) as denied:
        internal_guard(guard_request("192.168.1.10", headers), config)

    assert denied.value.status == 403
    assert denied.value.message == "lan access is disabled"
