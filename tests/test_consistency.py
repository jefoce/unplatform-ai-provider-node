"""Consistency checks across protocol enums, fixtures, docs and constants."""

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from conftest import FIXTURE_DIR, SCHEMA_DIR, assert_schema, load_fixture
from test_schema import _FIXTURE_SCHEMAS

import upai_provider.protocol.constants as protocol_constants
from upai_provider.config import Config
from upai_provider.constants import (
    DISK_FREE_REFRESH_SEC,
    ERROR_TEXT_MAX_CHARS,
    INLINE_JSON_MARGIN,
    MAX_JOBS_STORED,
    MAX_UPLOAD_BYTES_DEFAULT,
    MIN_FREE_DISK_BYTES,
    MISSING_POLL_LIMIT,
    MOCK_COMPLETE_SEC,
    MOCK_FAIL_SEC,
    MOCK_PENDING_SEC,
    MOCK_SLOW_SEC,
    MOCK_TICK_SEC,
    REFERENCE_MAX_BYTES,
    REGISTER_OUTPUT_TIMEOUT,
    RESULTS_QUOTA_BYTES,
    SCHEDULER_TICK_SEC,
    SWEEP_INTERVAL_SEC,
    UPLOAD_QUOTA_BYTES,
)
from upai_provider.protocol import (
    ERROR_CODES,
    REFERENCE_LABEL_KINDS,
    REFERENCE_LABEL_MAX_CHARS,
)
from upai_provider.protocol.shapes import (
    MAX_PENDING_DEFAULT,
    RESULT_TTL_HOURS_DEFAULT,
    SYNC_TIMEOUT_SEC_DEFAULT,
)

ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"

_BOUND_ROWS: dict[str, float] = {
    "Max pending jobs": MAX_PENDING_DEFAULT,
    "Max running": protocol_constants.MAX_RUNNING_DEFAULT,
    "Result TTL": RESULT_TTL_HOURS_DEFAULT,
    "Sync wait": SYNC_TIMEOUT_SEC_DEFAULT,
    "Max upload": MAX_UPLOAD_BYTES_DEFAULT,
    "Upload quota": UPLOAD_QUOTA_BYTES,
    "Min free disk": MIN_FREE_DISK_BYTES,
    "Results quota": RESULTS_QUOTA_BYTES,
    "Inline JSON margin": INLINE_JSON_MARGIN,
    "Stored jobs": MAX_JOBS_STORED,
    "Sweep interval": SWEEP_INTERVAL_SEC,
    "Disk free refresh": DISK_FREE_REFRESH_SEC,
    "Scheduler tick": SCHEDULER_TICK_SEC,
    "Register output timeout": REGISTER_OUTPUT_TIMEOUT,
    "Error text": ERROR_TEXT_MAX_CHARS,
    "Missing poll": MISSING_POLL_LIMIT,
    "Reference max": REFERENCE_MAX_BYTES,
    "Mock complete": MOCK_COMPLETE_SEC,
    "Mock fail": MOCK_FAIL_SEC,
    "Mock slow": MOCK_SLOW_SEC,
    "Mock pending": MOCK_PENDING_SEC,
    "Mock tick": MOCK_TICK_SEC,
}


def _leading_number(value: str) -> float:
    """Extract the leading number from a Bounds value cell."""
    match = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", value)
    if match is None:
        raise AssertionError(f"no leading number in bounds value: {value!r}")

    return float(match.group(1))


def _bounds_rows() -> dict[str, str]:
    """Map Bounds row labels to their raw value cells."""
    text = ARCHITECTURE.read_text(encoding="utf-8")
    section = text.split("## Bounds", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, str] = {}
    for line in section.splitlines():
        match = re.match(r"\| ([^|]+?) \| ([^|]+?) \|$", line)
        if match is None:
            continue

        label = match.group(1).strip()
        value = match.group(2).strip()
        if label == "Name" or value in {"Value", "---"}:
            continue

        rows[label] = value

    return rows


def test_error_codes_match_schema_and_fixtures() -> None:
    schema = cast(
        dict[str, Any],
        json.loads((SCHEMA_DIR / "error.schema.json").read_text(encoding="utf-8")),
    )
    enum = set(schema["properties"]["error"]["properties"]["code"]["enum"])
    assert enum == set(ERROR_CODES), f"schema enum differs from ERROR_CODES: {enum!r}"

    for code in ERROR_CODES:
        fixture = f"error-{code}.json"
        assert (FIXTURE_DIR / fixture).is_file(), f"missing fixture: {fixture}"
        assert_schema(load_fixture(fixture), "error")

    for path in sorted(FIXTURE_DIR.glob("error-*.json")):
        assert path.stem.removeprefix("error-") in ERROR_CODES, f"orphan fixture: {path.name}"


def test_every_fixture_is_mapped() -> None:
    fixtures = {path.name for path in FIXTURE_DIR.glob("*.json")}
    mapped = set(_FIXTURE_SCHEMAS)

    unmapped = sorted(fixtures - mapped)
    assert not unmapped, f"fixtures without a schema mapping: {unmapped}"

    missing = sorted(mapped - fixtures)
    assert not missing, f"schema mappings without a fixture: {missing}"


def test_architecture_bounds_match_constants() -> None:
    rows = _bounds_rows()

    for label, expected in _BOUND_ROWS.items():
        assert label in rows, f"missing Bounds row: {label}"
        actual = _leading_number(rows[label])
        assert actual == expected, (
            f"Bounds row {label!r} says {rows[label]!r} ({actual}), constant is {expected}"
        )


def test_protocol_disk_bounds_match_pack_constants() -> None:
    assert protocol_constants.MIN_FREE_DISK_BYTES == MIN_FREE_DISK_BYTES
    assert protocol_constants.RESULTS_QUOTA_BYTES == RESULTS_QUOTA_BYTES


_SPEC_BOUND_RE = re.compile(r"reference_label[^\n]*at most (\d+) characters")

_CONFIG_ENV: dict[str, str] = {
    "token": "UPAI_TOKEN",
    "allow_remote": "UPAI_ALLOW_REMOTE",
    "allow_lan": "UPAI_ALLOW_LAN",
    "allowed_origins": "",
    "allowed_hosts": "UPAI_ALLOWED_HOSTS",
    "allow_url_fetch": "",
    "result_ttl_hours": "",
    "max_pending": "",
    "sync_timeout_sec": "",
    "max_running": "UPAI_MAX_RUNNING",
    "min_free_disk_bytes": "UPAI_MIN_FREE_DISK",
    "results_quota_bytes": "UPAI_RESULTS_QUOTA",
}


def _config_rows() -> dict[str, tuple[str, str]]:
    """Map Config table keys to their Env and Default cells."""
    text = ARCHITECTURE.read_text(encoding="utf-8")
    section = text.split("## Config", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, tuple[str, str]] = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue

        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not cells[0].startswith("`"):
            continue

        rows[cells[0].strip("`")] = (cells[1].strip("`"), cells[2])

    return rows


def _config_default_matches(cell: str, value: object) -> bool:
    """Compare a Default cell with a Config field value."""
    if cell == "empty":
        return value == "" or value == ()

    if cell in ("true", "false"):
        return isinstance(value, bool) and value is (cell == "true")

    match = re.match(r"([0-9]+(?:\.[0-9]+)?)", cell)
    if match is None:
        return cell == str(value)

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False

    return float(match.group(1)) == float(value)


def test_reference_label_bound_matches_schema_and_spec() -> None:
    schema = cast(
        dict[str, Any],
        json.loads((SCHEMA_DIR / "models.schema.json").read_text(encoding="utf-8")),
    )
    max_length = schema["$defs"]["prompt"]["properties"]["reference_label"]["maxLength"]
    assert max_length == REFERENCE_LABEL_MAX_CHARS

    spec = (ROOT / "protocol" / "spec.md").read_text(encoding="utf-8")
    match = _SPEC_BOUND_RE.search(spec)
    assert match is not None, "spec does not state the reference_label bound"
    assert int(match.group(1)) == REFERENCE_LABEL_MAX_CHARS


def test_reference_label_kinds_match_schema() -> None:
    schema = cast(
        dict[str, Any],
        json.loads((SCHEMA_DIR / "models.schema.json").read_text(encoding="utf-8")),
    )
    labels = schema["$defs"]["prompt"]["properties"]["reference_labels"]

    extra = labels["additionalProperties"]
    assert extra["type"] == ["string", "null"]
    assert extra["maxLength"] == REFERENCE_LABEL_MAX_CHARS
    assert tuple(labels["properties"]) == REFERENCE_LABEL_KINDS
    for kind in REFERENCE_LABEL_KINDS:
        assert labels["properties"][kind]["maxLength"] == REFERENCE_LABEL_MAX_CHARS


def test_architecture_config_matches_config_fields() -> None:
    rows = _config_rows()
    defaults = asdict(Config())
    config_source = (ROOT / "upai_provider" / "config.py").read_text(encoding="utf-8")

    expected = set(defaults) - {"is_config_invalid"}
    assert set(rows) == expected, f"Config table drift: {set(rows) ^ expected}"

    for key, value in defaults.items():
        if key == "is_config_invalid":
            continue

        env, default_cell = rows[key]
        assert env == _CONFIG_ENV[key], f"{key} env {env!r} != {_CONFIG_ENV[key]!r}"
        if env:
            assert f'"{env}"' in config_source, f"{key} env {env} not read in config.py"

        assert _config_default_matches(default_cell, value), (
            f"{key} default {default_cell!r} does not match {value!r}"
        )
