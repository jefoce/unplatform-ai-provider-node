"""Runs-mode E2E: a failing child fails the job, cancels siblings and frees the slot."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.comfy

FAIL_MODEL = "e2e-runs.e2e-runs"
IMAGE_MODEL = "image-single.image-single"


def _fail_prompt() -> dict[str, Any]:
    return {
        "1": {
            "class_type": "UPAIModel",
            "inputs": {
                "id": "e2e-runs",
                "name": "E2E Runs",
                "description": "",
                "kind": "image",
                "enabled": True,
                "price_per_run_usd": 0.0,
            },
        },
        "2": {
            "class_type": "UPAIPrompt",
            "inputs": {
                "text": "fail run",
                "negative": "",
                "required": True,
                "max_chars": 200,
            },
        },
        "3": {
            "class_type": "UPAISettings",
            "inputs": {
                "resolutions": "512",
                "aspect_ratios": "1:1",
                "default_resolution": "512",
                "default_aspect_ratio": "1:1",
                "align": 16,
                "size_overrides": "",
                "duration_min": 1.0,
                "duration_max": 4.0,
                "duration_default": 1.0,
                "duration_step": 0.25,
                "fps": 8.0,
                "frame_mod": 4,
                "frame_add": 1,
                "count_max": 4,
                "count_mode": "runs",
                "test_resolution": "512",
                "test_aspect_ratio": "1:1",
                "test_duration": 1.0,
                "test_count": 1,
                "test_seed": 0,
            },
        },
        "4": {
            "class_type": "EmptyImage",
            "inputs": {"width": 2048, "height": 2048, "batch_size": 1, "color": ["8", 0]},
        },
        "5": {
            "class_type": "UpaiFailNode",
            "inputs": {"image": ["4", 0], "seed": ["3", 6]},
        },
        "6": {"class_type": "ImageInvert", "inputs": {"image": ["5", 0]}},
        "7": {
            "class_type": "UPAIOutput",
            "inputs": {
                "format": "png",
                "crf": 0,
                "preview": False,
                "upai_job": "",
                "model": ["1", 0],
                "images": ["10", 0],
            },
        },
        "8": {"class_type": "StringLength", "inputs": {"string": ["2", 0]}},
        "9": {"class_type": "ImageInvert", "inputs": {"image": ["6", 0]}},
        "10": {"class_type": "ImageInvert", "inputs": {"image": ["9", 0]}},
    }


def _has_class(record: object, class_type: str) -> bool:
    if not isinstance(record, dict):
        return False

    prompt = record.get("prompt")
    if not isinstance(prompt, list) or len(prompt) < 3 or not isinstance(prompt[2], dict):
        return False

    return any(
        isinstance(node, dict) and node.get("class_type") == class_type
        for node in prompt[2].values()
    )


@pytest.fixture(scope="session")
def runs_models(
    comfy_server: Any,
    api_workflows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    image = comfy_server.export_workflow(
        "upai-e2e/image-single.json", api_workflows["image-single"]
    )
    assert image["status"] == "ready", image

    failed = comfy_server.export_workflow("upai-e2e/e2e-runs.json", _fail_prompt())
    assert failed["status"] == "ready", failed
    return failed


def test_child_failure_releases_slot(comfy_server: Any, runs_models: dict[str, Any]) -> None:
    assert runs_models["status"] == "ready"

    status, failing = comfy_server.json(
        "POST",
        "/upai/api/v1/images/jobs",
        payload={"model": FAIL_MODEL, "prompt": "runs", "n": 2, "seed": 0},
    )
    assert status == 202, failing

    status, following = comfy_server.json(
        "POST",
        "/upai/api/v1/images/jobs",
        payload={"model": IMAGE_MODEL, "prompt": "after failure", "n": 1},
    )
    assert status == 202

    failed = comfy_server.wait_job(failing["polling_url"])
    assert failed["status"] == "failed", failed
    assert "odd seed" in (failed["error"] or ""), failed

    completed = comfy_server.wait_job(following["polling_url"])
    assert completed["status"] == "completed", completed
    assert completed["started_at"] is not None

    records = comfy_server.history_records()
    fail_entries = [record for record in records.values() if _has_class(record, "UpaiFailNode")]
    statuses = [(record.get("status") or {}).get("status_str") for record in fail_entries]
    assert "error" in statuses, statuses

    assert comfy_server.active_jobs() == []
