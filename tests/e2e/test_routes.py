"""Server-level E2E for the upai/1 routes against a real ComfyUI."""

from __future__ import annotations

from typing import Any, cast

import pytest

pytestmark = pytest.mark.comfy

IMAGE_MODEL = "image-single.image-single"


@pytest.fixture(scope="session")
def exported_image(
    comfy_server: Any,
    api_workflows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return comfy_server.export_workflow("upai-e2e/image-single.json", api_workflows["image-single"])


def test_health(comfy_server: Any) -> None:
    status, body = comfy_server.json("GET", "/upai/api/v1/health")
    assert status == 200
    assert body["protocol"] == 1
    assert body["server"] == "comfyui"
    assert body["implementation"] == "unplatform-ai-provider-node"
    assert body["max_running"] >= 1
    assert body["result_delete"] is True


def test_model_catalog_lists_exported_workflow(
    comfy_server: Any, exported_image: dict[str, Any]
) -> None:
    assert exported_image["status"] == "ready", exported_image
    status, body = comfy_server.json("GET", "/upai/api/v1/images/models")
    assert status == 200
    models = cast(list[dict[str, Any]], body["data"])
    model = next((item for item in models if item["id"] == IMAGE_MODEL), None)
    assert model is not None, models
    assert model["status"] == "ready"
    assert model["kind"] == "image"
    assert model["capabilities"]["count"]["max"] >= 1


def test_export_guard(comfy_server: Any, api_workflows: dict[str, dict[str, Any]]) -> None:
    payload = {
        "source": "upai-e2e/guard.json",
        "prompt": api_workflows["image-single"],
        "saved_at": 0.0,
    }

    status, _ = comfy_server.json(
        "POST",
        "/upai/internal/export",
        payload=payload,
        headers={"Origin": "http://evil.example", "Host": comfy_server.netloc},
    )
    assert status == 403

    status, body = comfy_server.json(
        "POST",
        "/upai/internal/export",
        payload=payload,
        headers={"Origin": "http://127.0.0.1", "Host": comfy_server.netloc},
    )
    assert status == 403
    assert body["error"]["code"] == "forbidden"

    status, body = comfy_server.json(
        "POST",
        "/upai/internal/export",
        payload=payload,
        headers={
            "Origin": comfy_server.url,
            "Host": comfy_server.netloc,
            "Content-Type": "text/plain",
        },
    )
    assert status == 415
    assert body["error"]["code"] == "invalid_request"

    status, body = comfy_server.json(
        "POST",
        "/upai/internal/export",
        payload=payload,
        headers={"Origin": comfy_server.url, "Host": comfy_server.netloc},
    )
    assert status == 200
    assert body["status"] == "ready"


def test_create_get_content_delete(comfy_server: Any, exported_image: dict[str, Any]) -> None:
    assert exported_image["status"] == "ready"
    status, created = comfy_server.json(
        "POST",
        "/upai/api/v1/images/jobs",
        payload={"model": IMAGE_MODEL, "prompt": "e2e image", "n": 1},
    )
    assert status == 202
    assert created["status"] == "pending"

    job = comfy_server.wait_job(created["polling_url"])
    assert job["status"] == "completed", job
    assert job["urls"]

    data = comfy_server.content(f"{created['polling_url']}/content?index=0")
    assert data.startswith(b"\x89PNG")

    status, _ = comfy_server.json("DELETE", created["polling_url"])
    assert status == 204
    status, body = comfy_server.json("GET", created["polling_url"])
    assert status == 404
    assert body["error"]["code"] == "job_not_found"


def test_cancel_pending_job(comfy_server: Any, exported_image: dict[str, Any]) -> None:
    assert exported_image["status"] == "ready"
    status, running = comfy_server.json(
        "POST",
        "/upai/api/v1/images/jobs",
        payload={"model": IMAGE_MODEL, "prompt": "e2e running", "n": 1},
    )
    assert status == 202

    status, pending = comfy_server.json(
        "POST",
        "/upai/api/v1/images/jobs",
        payload={"model": IMAGE_MODEL, "prompt": "e2e pending", "n": 1},
    )
    assert status == 202
    assert pending["status"] == "pending"

    status, cancelled = comfy_server.json("POST", f"{pending['polling_url']}/cancel")
    assert status == 200
    assert cancelled["status"] == "cancelled", cancelled

    first = comfy_server.wait_job(running["polling_url"])
    assert first["status"] == "completed", first


def test_tls_health(tls_server: Any) -> None:
    status, body = tls_server.json("GET", "/upai/api/v1/health")
    assert status == 200
    assert body["protocol"] == 1
