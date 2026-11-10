"""Parsers for files and stored records."""

from collections.abc import Mapping
from dataclasses import fields
from typing import cast

from .constants import MAX_RUNNING_MAX, MAX_RUNNING_MIN
from .errors import ProtocolError
from .ids import JOB_ID_PATTERN
from .parse_common import (
    _object,
    _optional_bool,
    _optional_int,
    _optional_number,
    _optional_str,
    _optional_timestamp,
    _parse_progress,
    _raise,
    _required_str,
    _required_timestamp,
    _string_tuple,
)
from .shapes import Job, ModelKind, RawConfig
from .status import is_job_status


def parse_job(raw: object) -> Job:
    """Parse one stored or serialized job record."""
    obj = _object(raw, "job")
    job_id = _required_str(obj, "id")
    if not JOB_ID_PATTERN.match(job_id):
        _raise("id", "id must be a lowercase UUID4")

    kind = obj.get("kind")
    if kind not in ("video", "image"):
        _raise("kind", "kind must be video or image")

    status = obj.get("status")
    if not is_job_status(status):
        _raise("status", "status is not a known job status")

    usage_cost = _optional_number(obj, "usage_cost")
    return Job(
        id=job_id,
        kind=cast(ModelKind, kind),
        model=_required_str(obj, "model"),
        status=status,
        progress=_parse_progress(obj.get("progress")),
        seed=_optional_int(obj, "seed", minimum=0, maximum=2**31 - 1),
        urls=_string_tuple(obj.get("urls"), "urls"),
        error=_optional_str(obj, "error"),
        usage_cost=0.0 if usage_cost is None else usage_cost,
        created_at=_required_timestamp(obj, "created_at"),
        started_at=_optional_timestamp(obj, "started_at"),
        finished_at=_optional_timestamp(obj, "finished_at"),
        expires_at=_optional_int(obj, "expires_at"),
        files=_string_tuple(obj.get("files"), "files") or (),
        base_url=_optional_str(obj, "base_url") or "",
        sequence=_optional_int(obj, "sequence", minimum=0) or 0,
    )


def parse_jobs_records(raw: object) -> tuple[tuple[Job, ...], int]:
    """Parse job records one by one. Returns the valid jobs and the skip count."""
    obj = _object(raw, "jobs_file")
    jobs = obj.get("jobs")
    if not isinstance(jobs, list):
        _raise("jobs", "jobs must be a list")

    parsed: list[Job] = []
    skipped = 0
    for item in jobs:
        try:
            parsed.append(parse_job(item))
        except ProtocolError:
            skipped += 1

    return tuple(parsed), skipped


def parse_config_file(raw: object) -> RawConfig:
    """Parse config.json. Unknown keys are ignored."""
    obj = _object(raw, "config")
    max_pending = _optional_int(obj, "max_pending", minimum=1)
    max_running = _optional_int(
        obj, "max_running", minimum=MAX_RUNNING_MIN, maximum=MAX_RUNNING_MAX
    )
    min_free_disk_bytes = _optional_int(obj, "min_free_disk_bytes", minimum=0)
    results_quota_bytes = _optional_int(obj, "results_quota_bytes", minimum=0)
    return RawConfig(
        token=_optional_str(obj, "token") or "",
        allow_remote=_optional_bool(obj, "allow_remote") or False,
        allow_lan=_optional_bool(obj, "allow_lan") or False,
        allowed_origins=_string_tuple(obj.get("allowed_origins"), "allowed_origins") or (),
        allowed_hosts=_string_tuple(obj.get("allowed_hosts"), "allowed_hosts") or (),
        allow_url_fetch=_optional_bool(obj, "allow_url_fetch") or False,
        result_ttl_hours=_optional_number(obj, "result_ttl_hours", positive=True)
        or RawConfig.result_ttl_hours,
        max_pending=max_pending or RawConfig.max_pending,
        sync_timeout_sec=_optional_number(obj, "sync_timeout_sec", positive=True)
        or RawConfig.sync_timeout_sec,
        max_running=max_running or RawConfig.max_running,
        min_free_disk_bytes=(
            RawConfig.min_free_disk_bytes if min_free_disk_bytes is None else min_free_disk_bytes
        ),
        results_quota_bytes=(
            RawConfig.results_quota_bytes if results_quota_bytes is None else results_quota_bytes
        ),
    )


def parse_config_fields(raw: object) -> tuple[RawConfig, tuple[str, ...], bool]:
    """Parse config.json one field at a time. Bad fields fall back to defaults.

    Returns the config, the invalid field names, and whether the file must fail
    closed (a bad token field or a file that is not a JSON object).
    """
    if not isinstance(raw, dict):
        return RawConfig(), (), True

    obj = cast(Mapping[str, object], raw)
    values: dict[str, object] = {}
    invalid: list[str] = []
    for field in fields(RawConfig):
        name = field.name
        if name not in obj:
            continue

        value = obj[name]
        if name == "token":
            if isinstance(value, str):
                values[name] = value
            else:
                invalid.append(name)
            continue

        try:
            parsed = parse_config_file({name: value})
        except ProtocolError:
            invalid.append(name)
            continue

        values[name] = getattr(parsed, name)

    config = RawConfig(
        token=cast(str, values.get("token", "")),
        allow_remote=cast(bool, values.get("allow_remote", False)),
        allow_lan=cast(bool, values.get("allow_lan", False)),
        allowed_origins=cast(tuple[str, ...], values.get("allowed_origins", ())),
        allowed_hosts=cast(tuple[str, ...], values.get("allowed_hosts", ())),
        allow_url_fetch=cast(bool, values.get("allow_url_fetch", False)),
        result_ttl_hours=cast(float, values.get("result_ttl_hours", RawConfig.result_ttl_hours)),
        max_pending=cast(int, values.get("max_pending", RawConfig.max_pending)),
        sync_timeout_sec=cast(float, values.get("sync_timeout_sec", RawConfig.sync_timeout_sec)),
        max_running=cast(int, values.get("max_running", RawConfig.max_running)),
        min_free_disk_bytes=cast(
            int, values.get("min_free_disk_bytes", RawConfig.min_free_disk_bytes)
        ),
        results_quota_bytes=cast(
            int, values.get("results_quota_bytes", RawConfig.results_quota_bytes)
        ),
    )
    return config, tuple(invalid), "token" in invalid
