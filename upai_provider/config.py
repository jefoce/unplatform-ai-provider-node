"""Runtime config loaded from config.json with env overrides."""

import ipaddress
import json
import logging
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from .constants import LAN_NETWORKS, MIN_FREE_DISK_BYTES, RESULTS_QUOTA_BYTES
from .protocol import RawConfig
from .protocol.constants import MAX_RUNNING_DEFAULT, MAX_RUNNING_MAX, MAX_RUNNING_MIN
from .protocol.parse_files import parse_config_fields
from .protocol.shapes import (
    MAX_PENDING_DEFAULT,
    RESULT_TTL_HOURS_DEFAULT,
    SYNC_TIMEOUT_SEC_DEFAULT,
)

logger = logging.getLogger(__name__)

_TRUTHY = ("1", "true", "yes", "on")
_INVALID_HOST_CHARS = frozenset("@/\\")

PeerClass = Literal["local", "lan", "public"]
_Address = ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True)
class Config:
    token: str = ""
    allow_remote: bool = False
    allow_lan: bool = False
    allowed_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    allow_url_fetch: bool = False
    result_ttl_hours: float = RESULT_TTL_HOURS_DEFAULT
    max_pending: int = MAX_PENDING_DEFAULT
    sync_timeout_sec: float = SYNC_TIMEOUT_SEC_DEFAULT
    max_running: int = MAX_RUNNING_DEFAULT
    min_free_disk_bytes: int = MIN_FREE_DISK_BYTES
    results_quota_bytes: int = RESULTS_QUOTA_BYTES
    is_config_invalid: bool = False


def _valid_origin(origin: str) -> bool:
    if not origin:
        return False

    parts = urlsplit(origin)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _has_invalid_host_char(value: str) -> bool:
    return any(char in _INVALID_HOST_CHARS or char.isspace() for char in value)


def _host_name(value: str) -> str:
    """Strip a port and normalize a Host header or config entry. Empty when invalid."""
    host = value.strip().lower()
    if not host or _has_invalid_host_char(host):
        return ""

    if host.startswith("["):
        end = host.find("]")
        if end == -1:
            return ""

        rest = host[end + 1 :]
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return ""

        return host[1:end].rstrip(".")

    if host.count(":") > 1:
        return ""

    if host.count(":") == 1:
        host = host.split(":", 1)[0]

    return host.rstrip(".")


def _ip(value: str | None) -> _Address | None:
    if not value:
        return None

    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return None

    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped

    return address


def is_allowed_host(host_header: str | None, allowed_hosts: tuple[str, ...]) -> bool:
    """Return true for IP literals, localhost, .local names and allowed hosts."""
    if not host_header or host_header != host_header.strip():
        return False

    host = _host_name(host_header)
    if not host:
        return False

    if host == "localhost" or host.endswith(".local") or _ip(host) is not None:
        return True

    return any(_host_name(entry) == host for entry in allowed_hosts)


def classify_peer(remote: str | None, sockname: object | None) -> PeerClass:
    """Classify a request peer as local, lan or public."""
    peer = _ip(remote)
    if peer is None:
        return "public"

    if peer.is_loopback:
        return "local"

    if isinstance(sockname, tuple) and sockname and isinstance(sockname[0], str):
        own = _ip(sockname[0])
        if own is not None and not own.is_unspecified and peer == own:
            return "local"

    if any(peer in network for network in LAN_NETWORKS):
        return "lan"

    return "public"


def _normalize_hosts(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(host for item in values if (host := _host_name(item)))


def _env_int(source: Mapping[str, str], name: str, fallback: int) -> int:
    if name not in source:
        return fallback

    try:
        return max(0, int(source[name].strip()))
    except ValueError:
        return fallback


def _raw_config(path: Path | None) -> tuple[RawConfig, bool]:
    """Return the parsed config and whether it must fail closed."""
    if path is None or not path.is_file():
        return RawConfig(), False

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("config at %s is not readable", path)
        return RawConfig(), True

    try:
        raw = json.loads(text)
    except ValueError:
        logger.warning("config at %s is not a JSON object", path)
        return RawConfig(), True

    if not isinstance(raw, dict):
        logger.warning("config at %s is not a JSON object", path)
        return RawConfig(), True

    parsed, invalid_fields, is_config_invalid = parse_config_fields(raw)
    for field in invalid_fields:
        logger.warning("ignoring invalid config field %s", field)
    if is_config_invalid:
        logger.warning("config at %s is invalid; routes return config_invalid", path)

    return parsed, is_config_invalid


def load_config(path: Path | None, env: Mapping[str, str] | None = None) -> Config:
    """Load config.json, then apply env overrides."""
    raw, is_config_invalid = _raw_config(path)
    source = os.environ if env is None else env

    token = raw.token
    if "UPAI_TOKEN" in source:
        token = source["UPAI_TOKEN"].strip()

    allow_remote = raw.allow_remote
    if "UPAI_ALLOW_REMOTE" in source:
        allow_remote = source["UPAI_ALLOW_REMOTE"].strip().lower() in _TRUTHY

    allow_lan = raw.allow_lan
    if "UPAI_ALLOW_LAN" in source:
        allow_lan = source["UPAI_ALLOW_LAN"].strip().lower() in _TRUTHY

    allowed_hosts = _normalize_hosts(raw.allowed_hosts)
    if "UPAI_ALLOWED_HOSTS" in source:
        allowed_hosts = _normalize_hosts(source["UPAI_ALLOWED_HOSTS"].split(","))

    max_running = raw.max_running
    if "UPAI_MAX_RUNNING" in source:
        try:
            max_running = int(source["UPAI_MAX_RUNNING"].strip())
        except ValueError:
            max_running = raw.max_running
        max_running = min(MAX_RUNNING_MAX, max(MAX_RUNNING_MIN, max_running))

    origins = tuple(origin for origin in raw.allowed_origins if _valid_origin(origin))
    return Config(
        token=token,
        allow_remote=allow_remote,
        allow_lan=allow_lan,
        allowed_origins=origins,
        allowed_hosts=allowed_hosts,
        allow_url_fetch=raw.allow_url_fetch,
        result_ttl_hours=raw.result_ttl_hours,
        max_pending=raw.max_pending,
        sync_timeout_sec=raw.sync_timeout_sec,
        max_running=max_running,
        min_free_disk_bytes=_env_int(source, "UPAI_MIN_FREE_DISK", raw.min_free_disk_bytes),
        results_quota_bytes=_env_int(source, "UPAI_RESULTS_QUOTA", raw.results_quota_bytes),
        is_config_invalid=is_config_invalid,
    )
