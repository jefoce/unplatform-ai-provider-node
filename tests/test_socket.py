"""Socket-level tests for Host and peer checks."""

import ipaddress
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from aiohttp import ClientSession, web
from conftest import make_runtime

from upai_provider.config import Config
from upai_provider.routes import add_routes
from upai_provider.runtime import Runtime

HEALTH = "/upai/api/v1/health"
TOKEN = "abc123"  # noqa: S105


def _lan_ip() -> str | None:
    """Return a non-loopback IPv4 address of this host, or None."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            address = sock.getsockname()[0]
        except OSError:
            return None

    if ipaddress.ip_address(address).is_loopback:
        return None

    return address


@asynccontextmanager
async def _serve(runtime: Runtime) -> AsyncIterator[int]:
    """Serve a runtime on an ephemeral port bound to all interfaces."""
    app = web.Application()
    add_routes(app, runtime)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 0)  # noqa: S104
    await site.start()
    addresses = runner.addresses
    assert addresses

    try:
        yield addresses[0][1]
    finally:
        await runner.cleanup()


async def _get(
    session: ClientSession,
    address: str,
    port: int,
    *,
    host: str | None = None,
    token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    headers: dict[str, str] = {}
    if host is not None:
        headers["Host"] = host
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    url = f"http://{address}:{port}{HEALTH}"
    async with session.get(url, headers=headers) as response:
        return response.status, cast(dict[str, Any], await response.json())


@pytest.fixture
async def session() -> AsyncIterator[ClientSession]:
    async with ClientSession() as client:
        yield client


async def test_socket_host_allowlist(tmp_path: Path, session: ClientSession) -> None:
    runtime = make_runtime(tmp_path)
    async with _serve(runtime) as port:
        status, _ = await _get(session, "127.0.0.1", port)
        assert status == 200

        status, body = await _get(session, "127.0.0.1", port, host="attacker.example")
        assert status == 403
        assert body["error"]["code"] == "forbidden"

        status, _ = await _get(session, "127.0.0.1", port, host=f"localhost:{port}")
        assert status == 200

    custom = make_runtime(tmp_path, config=Config(allowed_hosts=("custom.test",)))
    async with _serve(custom) as port:
        status, _ = await _get(session, "127.0.0.1", port, host="custom.test")
        assert status == 200


async def test_socket_same_host_lan_ip(tmp_path: Path, session: ClientSession) -> None:
    lan_ip = _lan_ip()
    if lan_ip is None:
        pytest.skip("no non-loopback IPv4 address")

    runtime = make_runtime(tmp_path)
    async with _serve(runtime) as port:
        status, _ = await _get(session, lan_ip, port)
        assert status == 200


async def test_socket_lan_token(tmp_path: Path, session: ClientSession) -> None:
    lan_ip = _lan_ip()
    if lan_ip is None:
        pytest.skip("no non-loopback IPv4 address")

    runtime = make_runtime(tmp_path, config=Config(token=TOKEN))
    async with _serve(runtime) as port:
        status, _ = await _get(session, lan_ip, port)
        assert status == 401

        status, _ = await _get(session, lan_ip, port, token=TOKEN)
        assert status == 200
