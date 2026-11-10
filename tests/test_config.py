"""Config loading and peer policy tests."""

import json
import logging
import math
from pathlib import Path
from typing import cast

import pytest
from aiohttp.web import Response
from conftest import make_runtime
from helpers import guard_request

from upai_provider.config import PeerClass, classify_peer, is_allowed_host, load_config
from upai_provider.constants import MIN_FREE_DISK_BYTES, RESULTS_QUOTA_BYTES
from upai_provider.protocol import ProtocolError
from upai_provider.protocol.constants import MAX_RUNNING_DEFAULT, MAX_RUNNING_MAX, MAX_RUNNING_MIN
from upai_provider.protocol.shapes import (
    MAX_PENDING_DEFAULT,
    RESULT_TTL_HOURS_DEFAULT,
    SYNC_TIMEOUT_SEC_DEFAULT,
)
from upai_provider.routes import guard, route_specs, wrap_handler


@pytest.mark.parametrize(
    ("remote", "sockname", "expected"),
    [
        ("127.0.0.1", None, "local"),
        ("::1", None, "local"),
        ("::ffff:127.0.0.1", None, "local"),
        ("192.168.1.10", None, "lan"),
        ("10.1.2.3", None, "lan"),
        ("172.16.5.5", None, "lan"),
        ("169.254.10.1", None, "lan"),
        ("fe80::1", None, "lan"),
        ("fd00::1", None, "lan"),
        ("100.64.0.1", None, "lan"),
        ("192.168.1.10", ("192.168.1.10", 8188), "local"),
        ("192.168.1.10", ("0.0.0.0", 8188), "lan"),  # noqa: S104
        ("8.8.8.8", None, "public"),
        ("::ffff:8.8.8.8", None, "public"),
        (None, None, "public"),
    ],
)
def test_classify_peer(
    remote: str | None, sockname: tuple[str, int] | None, expected: PeerClass
) -> None:
    assert classify_peer(remote, sockname) == expected


@pytest.mark.parametrize(
    ("host", "allowed_hosts", "expected"),
    [
        ("127.0.0.1:8189", (), True),
        ("[::1]:8189", (), True),
        ("[fe80::1]:8189", (), True),
        (None, (), False),
        ("localhost:8189", (), True),
        ("mac.local:8189", (), True),
        ("studio.example", ("studio.example",), True),
        ("Studio.Example.:8189", ("studio.example",), True),
        ("attacker.example", (), False),
        ("127.0.0.1:8188@evil.example", (), False),
        ("localhost:8189@evil.example", (), False),
        ("127.0.0.1:8188/path", (), False),
        ("127.0.0.1:8188\\path", (), False),
        ("127.0.0.1:8188 evil.example", (), False),
        ("127.0.0.1 :8188", (), False),
        ("127.0.0.1:8188 ", (), False),
        ("::1", (), False),
        ("127.0.0.1:8188:9090", (), False),
    ],
)
def test_is_allowed_host(host: str | None, allowed_hosts: tuple[str, ...], expected: bool) -> None:
    assert is_allowed_host(host, allowed_hosts) is expected


def test_load_config_allow_lan(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"allow_lan": True}), encoding="utf-8")

    assert load_config(path, env={}).allow_lan is True
    assert load_config(path, env={"UPAI_ALLOW_LAN": "0"}).allow_lan is False
    assert load_config(None, env={"UPAI_ALLOW_LAN": "1"}).allow_lan is True
    assert load_config(None, env={}).allow_lan is False


def test_load_config_max_running(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"max_running": 4}), encoding="utf-8")

    assert load_config(path, env={}).max_running == 4
    assert load_config(None, env={}).max_running == MAX_RUNNING_DEFAULT
    assert load_config(path, env={"UPAI_MAX_RUNNING": "2"}).max_running == 2
    assert load_config(path, env={"UPAI_MAX_RUNNING": "99"}).max_running == MAX_RUNNING_MAX
    assert load_config(path, env={"UPAI_MAX_RUNNING": "0"}).max_running == MAX_RUNNING_MIN
    assert load_config(path, env={"UPAI_MAX_RUNNING": "x"}).max_running == 4


def test_load_config_disk_limits(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"min_free_disk_bytes": 1024, "results_quota_bytes": 2048}),
        encoding="utf-8",
    )

    config = load_config(path, env={})
    assert config.min_free_disk_bytes == 1024
    assert config.results_quota_bytes == 2048
    assert load_config(None, env={}).min_free_disk_bytes == MIN_FREE_DISK_BYTES
    assert load_config(None, env={}).results_quota_bytes == RESULTS_QUOTA_BYTES
    assert load_config(path, env={"UPAI_MIN_FREE_DISK": "4096"}).min_free_disk_bytes == 4096
    assert load_config(path, env={"UPAI_RESULTS_QUOTA": "8192"}).results_quota_bytes == 8192
    assert load_config(path, env={"UPAI_MIN_FREE_DISK": "x"}).min_free_disk_bytes == 1024
    assert load_config(path, env={"UPAI_RESULTS_QUOTA": "x"}).results_quota_bytes == 2048

    zero = tmp_path / "zero.json"
    zero.write_text(json.dumps({"min_free_disk_bytes": 0}), encoding="utf-8")
    assert load_config(zero, env={}).min_free_disk_bytes == 0


def test_load_config_bad_max_running_falls_back(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"max_running": 9}), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="upai_provider.config"):
        config = load_config(path, env={})

    assert config.max_running == MAX_RUNNING_DEFAULT
    assert config.is_config_invalid is False
    assert any("max_running" in record.getMessage() for record in caplog.records)


def test_load_config_allowed_hosts(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"allowed_hosts": ["Studio.Example."]}), encoding="utf-8")

    assert load_config(path, env={}).allowed_hosts == ("studio.example",)
    assert load_config(None, env={}).allowed_hosts == ()

    env = {"UPAI_ALLOWED_HOSTS": " a.example, ,B.Example. "}
    assert load_config(path, env=env).allowed_hosts == ("a.example", "b.example")


def test_load_config_drops_malformed_allowed_hosts(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"allowed_hosts": ["good.example", "bad@host"]}), encoding="utf-8")

    assert load_config(path, env={}).allowed_hosts == ("good.example",)

    env = {"UPAI_ALLOWED_HOSTS": "good.example,bad/host,bad host,bad\\host"}
    assert load_config(None, env=env).allowed_hosts == ("good.example",)


def test_load_config_bad_field_keeps_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"token": "secret", "max_pending": "many"}),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="upai_provider.config"):
        config = load_config(path, env={})

    assert config.token == "secret"  # noqa: S105
    assert config.max_pending == MAX_PENDING_DEFAULT
    assert config.is_config_invalid is False
    assert any("max_pending" in record.getMessage() for record in caplog.records)

    with pytest.raises(ProtocolError) as denied:
        guard(guard_request("127.0.0.1"), config)
    assert denied.value.status == 401


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({"token": 3}),
        json.dumps({"token": None}),
        "[]",
        '"a string"',
        "{not json",
    ],
)
def test_load_config_invalid_file_fails_closed(tmp_path: Path, text: str) -> None:
    path = tmp_path / "config.json"
    path.write_text(text, encoding="utf-8")

    assert load_config(path, env={}).is_config_invalid is True


def test_load_config_missing_file_is_valid(tmp_path: Path) -> None:
    assert load_config(tmp_path / "missing.json", env={}).is_config_invalid is False


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
@pytest.mark.parametrize(
    ("field", "default"),
    [
        ("result_ttl_hours", RESULT_TTL_HOURS_DEFAULT),
        ("sync_timeout_sec", SYNC_TIMEOUT_SEC_DEFAULT),
    ],
)
def test_load_config_rejects_non_finite_numbers(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    literal: str,
    field: str,
    default: float,
) -> None:
    path = tmp_path / "config.json"
    path.write_text(f'{{"{field}": {literal}}}', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="upai_provider.config"):
        config = load_config(path, env={})

    actual = getattr(config, field)
    assert actual == default
    assert math.isfinite(actual)
    assert config.is_config_invalid is False
    assert any(field in record.getMessage() for record in caplog.records)


async def test_non_utf8_config_blocks_every_route(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_bytes(b"\xff\xfe")
    config = load_config(path, env={})
    assert config.is_config_invalid is True

    runtime = make_runtime(tmp_path, config=config)
    for _, _, handler, _ in route_specs(runtime):
        response = cast(Response, await wrap_handler(handler, config)(guard_request("127.0.0.1")))
        assert response.status == 503
        assert json.loads(cast(str, response.text))["error"]["code"] == "config_invalid"
