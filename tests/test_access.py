"""Auth, origin and remote-peer guard route tests."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from aiohttp.test_utils import TestClient
from aiohttp.web import Response
from conftest import assert_schema, make_client, make_runtime
from helpers import HEALTH, TOKEN, assert_error, guard_request, json_body

from upai_provider.config import Config, load_config
from upai_provider.protocol import ProtocolError
from upai_provider.routes import guard, route_specs, wrap_handler


async def test_unknown_upai_path_is_json_envelope(client: TestClient) -> None:
    response = await client.get("/upai/api/v1/unknown")
    assert response.status == 404
    assert response.headers["X-UPAI-Protocol"] == "1"
    assert_error(await json_body(response), "not_found")


async def test_method_not_allowed_is_json_envelope(client: TestClient) -> None:
    response = await client.post(HEALTH)
    assert response.status == 405
    assert response.headers["X-UPAI-Protocol"] == "1"
    assert_error(await json_body(response), "method_not_allowed")


async def test_method_not_allowed_runs_guard(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(token=TOKEN))
    client = await make_client(aiohttp_client, runtime)

    missing = await client.post(HEALTH)
    assert missing.status == 401
    assert missing.headers["X-UPAI-Protocol"] == "1"
    assert_error(await json_body(missing), "unauthorized")

    allowed = await client.post(HEALTH, headers={"Authorization": f"Bearer {TOKEN}"})
    assert allowed.status == 405
    assert allowed.headers["X-UPAI-Protocol"] == "1"
    assert_error(await json_body(allowed), "method_not_allowed")


@pytest.mark.parametrize(
    "text",
    [json.dumps({"token": 3}), "[]", "{not json"],
)
async def test_invalid_config_blocks_every_route(tmp_path: Path, text: str) -> None:
    path = tmp_path / "config.json"
    path.write_text(text, encoding="utf-8")
    config = load_config(path, env={})
    runtime = make_runtime(tmp_path, config=config)

    for _, _, handler, _ in route_specs(runtime):
        response = cast(Response, await wrap_handler(handler, config)(guard_request("127.0.0.1")))
        assert response.status == 503
        assert response.text is not None
        assert json.loads(response.text)["error"]["code"] == "config_invalid"


def test_guard_config_invalid_before_token() -> None:
    config = Config(token=TOKEN, is_config_invalid=True)

    with pytest.raises(ProtocolError) as denied:
        guard(guard_request("127.0.0.1"), config)

    assert denied.value.status == 503
    assert denied.value.code == "config_invalid"


async def test_oversized_json_body_returns_envelope(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    client = await make_client(aiohttp_client, runtime, client_max_size=64)

    response = await client.post(
        "/upai/api/v1/videos",
        data=b'{"prompt": "' + b"x" * 200 + b'"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status == 413
    assert response.headers["X-UPAI-Protocol"] == "1"
    assert_error(await json_body(response), "too_large")


async def test_auth(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(token=TOKEN))
    client = await make_client(aiohttp_client, runtime)

    missing = await client.get(HEALTH)
    assert missing.status == 401
    assert_error(await json_body(missing), "unauthorized")

    wrong = await client.get(HEALTH, headers={"Authorization": "Bearer nope"})
    assert wrong.status == 401
    assert_error(await json_body(wrong), "unauthorized")

    ok = await client.get(HEALTH, headers={"Authorization": f"Bearer {TOKEN}"})
    assert ok.status == 200
    body = await json_body(ok)
    assert_schema(body, "health")
    assert body["auth_required"] is True


async def test_origin_guard(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(allowed_origins=("http://localhost:3000",)))
    client = await make_client(aiohttp_client, runtime)

    allowed = await client.get(HEALTH, headers={"Origin": "http://localhost:3000"})
    assert allowed.status == 200

    evil = await client.get(HEALTH, headers={"Origin": "http://evil.example"})
    assert evil.status == 403
    assert_error(await json_body(evil), "forbidden")

    absent = await client.get(HEALTH)
    assert absent.status == 200


async def test_every_route_runs_guard(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(token=TOKEN))

    for _, _, handler, is_internal in route_specs(runtime):
        wrapped = wrap_handler(handler, runtime.config, internal=is_internal)

        remote = cast(Response, await wrapped(guard_request("203.0.113.5")))
        assert remote.status == 403
        assert remote.text is not None
        assert_error(json.loads(remote.text), "forbidden")

        loopback = cast(Response, await wrapped(guard_request("127.0.0.1")))
        assert loopback.status == (403 if is_internal else 401)
        assert loopback.text is not None
        if not is_internal:
            assert_error(json.loads(loopback.text), "unauthorized")


def test_guard_remote_peer() -> None:
    with pytest.raises(ProtocolError) as denied:
        guard(guard_request("203.0.113.5"), Config())
    assert denied.value.status == 403
    assert denied.value.code == "forbidden"

    with pytest.raises(ProtocolError):
        guard(guard_request("203.0.113.5"), Config(allow_remote=True))

    remote = Config(allow_remote=True, token=TOKEN)
    assert (
        guard(
            guard_request("203.0.113.5", {"Authorization": f"Bearer {TOKEN}"}),
            remote,
        )
        is None
    )

    assert guard(guard_request("127.0.0.1"), Config()) is None


def test_guard_rejects_unknown_host() -> None:
    with pytest.raises(ProtocolError) as denied:
        guard(guard_request("127.0.0.1", {"Host": "attacker.example"}), Config())

    assert denied.value.status == 403
    assert denied.value.code == "forbidden"
    assert denied.value.message == "host is not allowed"


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1:8189@evil.example",
        "localhost:8189@evil.example",
        "127.0.0.1:8189/path",
        "127.0.0.1:8189\\path",
        "127.0.0.1:8189 evil.example",
        "127.0.0.1 :8189",
        "127.0.0.1:8189:9090",
        "::1:8189",
    ],
)
def test_guard_rejects_malformed_host(host: str) -> None:
    with pytest.raises(ProtocolError) as denied:
        guard(guard_request("127.0.0.1", {"Host": host}), Config())

    assert denied.value.status == 403
    assert denied.value.code == "forbidden"


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1:8189", "localhost:8189", "mac.local:8189"],
)
def test_guard_allows_local_hosts(host: str) -> None:
    assert guard(guard_request("127.0.0.1", {"Host": host}), Config()) is None


def test_guard_allows_configured_host() -> None:
    config = Config(allowed_hosts=("studio.example",))
    request = guard_request("127.0.0.1", {"Host": "studio.example:8189"})
    assert guard(request, config) is None


async def test_create_rejects_userinfo_host(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/videos",
        json={"model": "wan22-t2v", "prompt": "host"},
        headers={"Host": "127.0.0.1:8190@evil.example"},
    )

    assert response.status == 403
    assert_error(await json_body(response), "forbidden")


def test_guard_lan_peer_needs_allow_lan() -> None:
    with pytest.raises(ProtocolError) as denied:
        guard(guard_request("192.168.1.10"), Config())
    assert denied.value.status == 403
    assert denied.value.message == "lan access is disabled"

    assert guard(guard_request("192.168.1.10"), Config(allow_lan=True)) is None


def test_guard_lan_peer_with_token() -> None:
    config = Config(allow_lan=True, token=TOKEN)
    with pytest.raises(ProtocolError) as denied:
        guard(guard_request("192.168.1.10"), config)
    assert denied.value.status == 401

    request = guard_request("192.168.1.10", {"Authorization": f"Bearer {TOKEN}"})
    assert guard(request, config) is None


def test_guard_lan_peer_allowed_by_remote_and_token() -> None:
    config = Config(allow_remote=True, token=TOKEN)
    request = guard_request("192.168.1.10", {"Authorization": f"Bearer {TOKEN}"})
    assert guard(request, config) is None


def test_guard_public_peer_needs_remote_and_token() -> None:
    with pytest.raises(ProtocolError) as denied:
        guard(guard_request("8.8.8.8"), Config(allow_lan=True))
    assert denied.value.status == 403
    assert denied.value.message == "remote access is disabled"

    config = Config(allow_remote=True, token=TOKEN)
    request = guard_request("8.8.8.8", {"Authorization": f"Bearer {TOKEN}"})
    assert guard(request, config) is None


def test_guard_same_host_lan_ip_is_local() -> None:
    request = guard_request("192.168.1.10", sockname=("192.168.1.10", 8188))
    assert guard(request, Config()) is None
