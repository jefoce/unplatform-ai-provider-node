"""Schema and fixture contract tests."""

import copy
import json
from pathlib import Path
from typing import Any, cast

import jsonschema
import pytest
from conftest import (
    SCHEMA_DIR,
    assert_schema,
    load_fixture,
    load_schema,
    make_client,
    make_runtime,
)

from upai_provider.mock import MockTimings, mock_state
from upai_provider.protocol import Job, JobProgress, job_to_wire

_FIXTURE_SCHEMAS = {
    "health.json": "health",
    "models-video.json": "models",
    "models-image.json": "models",
    "models-invalid.json": "models",
    "job-pending.json": "job",
    "job-in_progress.json": "job",
    "job-completed.json": "job",
    "job-failed.json": "job",
    "job-cancelled.json": "job",
    "job-expired.json": "job",
    "upload.json": "upload",
    "create-job-video.json": "create-job",
    "create-job-image.json": "create-job",
    "sync-images.json": "sync-images",
    "error-invalid_request.json": "error",
    "error-unauthorized.json": "error",
    "error-forbidden.json": "error",
    "error-config_invalid.json": "error",
    "error-model_not_found.json": "error",
    "error-job_not_found.json": "error",
    "error-upload_not_found.json": "error",
    "error-not_found.json": "error",
    "error-method_not_allowed.json": "error",
    "error-too_large.json": "error",
    "error-insufficient_storage.json": "error",
    "error-workflow_invalid.json": "error",
    "error-queue_full.json": "error",
    "error-comfy_unavailable.json": "error",
    "error-job_failed.json": "error",
    "error-internal.json": "error",
    "error-timeout.json": "error",
}


@pytest.mark.parametrize(("fixture", "schema"), _FIXTURE_SCHEMAS.items())
def test_fixture_validates(fixture: str, schema: str) -> None:
    assert_schema(load_fixture(fixture), schema)


def test_every_schema_file_is_draft_2020_12() -> None:
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        document = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_bad_job_fixture_fails() -> None:
    job = copy.deepcopy(load_fixture("job-completed.json"))
    job["status"] = "bogus"

    with pytest.raises(jsonschema.ValidationError):
        assert_schema(job, "job")


def test_bad_error_fixture_fails() -> None:
    error = copy.deepcopy(load_fixture("error-invalid_request.json"))
    error["error"]["code"] = "not_a_code"

    with pytest.raises(jsonschema.ValidationError):
        assert_schema(error, "error")


def test_bad_health_fixture_fails() -> None:
    health = copy.deepcopy(load_fixture("health.json"))
    health["protocol"] = 2

    with pytest.raises(jsonschema.ValidationError):
        assert_schema(health, "health")


def test_future_reference_label_kind_validates() -> None:
    model = copy.deepcopy(load_fixture("models-video.json"))
    labels = model["data"][0]["capabilities"]["prompt"]["reference_labels"]
    labels["future"] = "<{n}>"

    assert_schema(model, "models")


def test_live_mock_state_job_validates() -> None:
    timings = MockTimings()
    state = mock_state(timings.complete_sec + 0.1, "plain", timings)
    assert state.status == "completed"

    job = Job(
        id="11111111-1111-4111-8111-111111111111",
        kind="video",
        model="wan22-t2v",
        status=state.status,
        progress=JobProgress(
            state.percent,
            state.node,
            state.value,
            state.max_value,
            state.queue_position,
        ),
        seed=1,
        urls=(
            "http://127.0.0.1:8190/upai/api/v1/videos/"
            "11111111-1111-4111-8111-111111111111/content?index=0",
        ),
        error=state.error,
        usage_cost=0.0,
        created_at="2026-11-05T12:00:00Z",
        started_at="2026-11-05T12:00:01Z",
        finished_at="2026-11-05T12:00:06Z",
        expires_at=1793966400,
    )

    assert_schema(job_to_wire(job), "job")


async def test_live_route_response_validates(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    client = await make_client(aiohttp_client, runtime)

    response = await client.get("/upai/api/v1/health")
    assert response.status == 200
    assert_schema(cast(dict[str, Any], await response.json()), "health")


def test_schema_loader_accepts_file_name() -> None:
    assert load_schema("health.schema.json") == load_schema("health")
