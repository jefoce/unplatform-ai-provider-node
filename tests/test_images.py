"""Image generation route tests."""

import base64
import io
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from aiohttp.test_utils import TestClient
from conftest import assert_schema, make_client, make_runtime, wait_for_status
from helpers import assert_error, json_body, upload
from PIL import Image

from upai_provider.config import Config
from upai_provider.mock import image_models
from upai_provider.runtime import Runtime

_REAL_IMAGE_BYTES = b"\x89PNG\r\n\x1a\nreal-job-bytes"


def _image_models_with_reference_max(max_bytes: int) -> tuple[Any, ...]:
    base = image_models()[0]
    limits = replace(
        base.capabilities.reference_limits,
        image=replace(base.capabilities.reference_limits.image, max_bytes=max_bytes),
    )
    capabilities = replace(base.capabilities, reference_limits=limits)
    return (replace(base, capabilities=capabilities),)


class _FakeImageExports:
    def catalog(self, kind: str) -> tuple[Any, ...]:
        return image_models() if kind == "image" else ()


class _NoopScheduler:
    async def enqueue(self, job_id: str) -> None:
        pass


class _CompletingScheduler:
    def __init__(self, runtime: Runtime, *, inside_root: bool = True) -> None:
        self.runtime = runtime
        self.inside_root = inside_root

    async def enqueue(self, job_id: str) -> None:
        root = self.runtime.result_root
        assert root is not None
        base = root if self.inside_root else self.runtime.data_dir
        path = base / job_id / "0.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_REAL_IMAGE_BYTES)
        await self.runtime.store.update(job_id, files=(str(path),))
        await self.runtime.store.finalize(job_id, "completed", urls=())


def _real_runtime(tmp_path: Path) -> Runtime:
    runtime = make_runtime(tmp_path)
    runtime.is_mock = False
    runtime.exports = cast(Any, _FakeImageExports())
    runtime.result_root = tmp_path / "temp"
    return runtime


async def test_real_prompt_with_invalid_marker_is_accepted(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = _real_runtime(tmp_path)
    runtime.scheduler = cast(Any, _NoopScheduler())
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "[invalid]"}
    )

    assert response.status == 202


async def test_real_sync_images_returns_job_files(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = _real_runtime(tmp_path)
    runtime.scheduler = cast(Any, _CompletingScheduler(runtime))
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images", json={"model": "sdxl-image", "prompt": "real"}
    )

    assert response.status == 200
    body = await json_body(response)
    assert_schema(body, "sync-images")
    assert body["data"] == [
        {
            "b64_json": base64.b64encode(_REAL_IMAGE_BYTES).decode("ascii"),
            "media_type": "image/png",
        }
    ]
    assert runtime.assets is None


async def test_real_sync_images_rejects_file_outside_result_root(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = _real_runtime(tmp_path)
    runtime.scheduler = cast(Any, _CompletingScheduler(runtime, inside_root=False))
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images", json={"model": "sdxl-image", "prompt": "real"}
    )

    assert response.status == 500
    assert_error(await json_body(response), "internal")
    assert runtime.assets is None


async def test_image_rejects_negative_prompt_when_unsupported(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs",
        json={"model": "sdxl-image", "prompt": "x", "negative_prompt": "blurry"},
    )

    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "negative_prompt"


async def test_image_count_and_content(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "two", "n": 2}
    )
    assert response.status == 202
    created = await json_body(response)

    job = await wait_for_status(client, created["polling_url"], ("completed",))
    assert_schema(job, "job")
    assert len(job["urls"]) == 2

    for index in (0, 1):
        content = await client.get(
            f"/upai/api/v1/images/jobs/{created['id']}/content?index={index}"
        )
        assert content.status == 200
        assert content.headers["Content-Type"] == "image/png"
        await content.read()

    missing = await client.get(f"/upai/api/v1/images/jobs/{created['id']}/content?index=2")
    assert missing.status == 404


async def test_sync_images(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images", json={"model": "sdxl-image", "prompt": "sync", "n": 1}
    )
    assert response.status == 200
    body = await json_body(response)
    assert_schema(body, "sync-images")
    assert len(body["data"]) == 1
    assert body["data"][0]["media_type"] == "image/png"
    assert body["usage"]["cost"] == 0


async def test_sync_images_job_failed(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images", json={"model": "sdxl-image", "prompt": "[fail]"}
    )
    assert response.status == 502

    body = await json_body(response)
    assert_error(body, "job_failed")
    details = body["error"]["details"]
    assert details["status"] == "failed"
    assert details["error"] == "MockSampler: simulated failure"


async def test_image_rejects_video_reference(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs",
        json={
            "model": "sdxl-image",
            "prompt": "x",
            "input_references": [{"type": "video_url", "video_url": {"url": "ref"}}],
        },
    )
    assert response.status == 400
    assert_error(await json_body(response), "invalid_request")


def _image_payload(url: str) -> dict[str, Any]:
    return {
        "model": "sdxl-image",
        "prompt": "x",
        "input_references": [{"type": "image_url", "image_url": {"url": url}}],
    }


async def test_image_url_fetch_disabled(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs", json=_image_payload("http://example.com/x")
    )
    assert response.status == 400
    assert_error(await json_body(response), "invalid_request")


async def test_image_url_fetch_allowed(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, config=Config(allow_url_fetch=True))
    client = await make_client(aiohttp_client, runtime)

    response = await client.post(
        "/upai/api/v1/images/jobs", json=_image_payload("http://example.com/x")
    )
    assert response.status == 202


async def test_image_unknown_upload_ref(client: TestClient) -> None:
    ref = f"upai-upload:{'0' * 64}"
    response = await client.post("/upai/api/v1/images/jobs", json=_image_payload(ref))
    assert response.status == 404

    body = await json_body(response)
    assert_error(body, "upload_not_found")
    assert body["error"]["details"] == {"field": "input_references", "ref": ref}


async def test_image_known_upload_ref(client: TestClient, png_bytes: bytes) -> None:
    stored = await json_body(await upload(client, png_bytes))
    response = await client.post("/upai/api/v1/images/jobs", json=_image_payload(stored["ref"]))
    assert response.status == 202


async def test_count_above_capability(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs", json={"model": "sdxl-image", "prompt": "x", "n": 5}
    )
    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "n"


async def test_image_resolution_outside_capabilities(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs",
        json={"model": "sdxl-image", "prompt": "x", "resolution": "1080p"},
    )
    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "resolution"


async def test_image_aspect_ratio_outside_capabilities(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs",
        json={"model": "sdxl-image", "prompt": "x", "aspect_ratio": "7:3"},
    )
    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "aspect_ratio"


async def test_image_accepts_configured_resolution_and_aspect(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs",
        json={
            "model": "sdxl-image",
            "prompt": "x",
            "resolution": "1K",
            "aspect_ratio": "16:9",
        },
    )
    assert response.status == 202


def _image_bytes(image_format: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (0, 128, 0)).save(buffer, format=image_format)
    return buffer.getvalue()


def _data_url(data: bytes, media_type: str = "image/png") -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
async def test_image_accepts_known_ref_formats(client: TestClient, image_format: str) -> None:
    response = await client.post(
        "/upai/api/v1/images/jobs",
        json=_image_payload(_data_url(_image_bytes(image_format))),
    )
    assert response.status == 202


async def test_image_ref_rejects_magic_bytes_when_extension_lies(
    client: TestClient,
) -> None:
    stored = await json_body(
        await upload(client, _image_bytes("GIF"), filename="frame.png", content_type="image/png")
    )
    response = await client.post("/upai/api/v1/images/jobs", json=_image_payload(stored["ref"]))
    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "input_references"


async def test_image_upload_ref_checks_file_bytes(client: TestClient) -> None:
    stored = await json_body(
        await upload(client, _image_bytes("PNG"), filename="frame.gif", content_type="image/png")
    )
    response = await client.post("/upai/api/v1/images/jobs", json=_image_payload(stored["ref"]))
    assert response.status == 202


async def test_image_data_ref_uses_decoded_bytes_not_declared_mime(
    client: TestClient,
) -> None:
    url = _data_url(_image_bytes("PNG"), "image/gif")
    response = await client.post("/upai/api/v1/images/jobs", json=_image_payload(url))
    assert response.status == 202


async def test_image_data_ref_rejects_mismatched_bytes(client: TestClient) -> None:
    url = _data_url(_image_bytes("GIF"), "image/png")
    response = await client.post("/upai/api/v1/images/jobs", json=_image_payload(url))
    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "input_references"


async def test_image_ref_over_max_bytes_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "upai_provider.runtime.image_models", lambda: _image_models_with_reference_max(8)
    )
    response = await client.post(
        "/upai/api/v1/images/jobs",
        json=_image_payload(_data_url(_image_bytes("PNG"))),
    )
    assert response.status == 413
    body = await json_body(response)
    assert_error(body, "too_large")
    assert body["error"]["details"]["field"] == "input_references"


async def test_image_upload_ref_over_max_bytes_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "upai_provider.runtime.image_models", lambda: _image_models_with_reference_max(8)
    )
    stored = await json_body(await upload(client, _image_bytes("PNG")))
    response = await client.post("/upai/api/v1/images/jobs", json=_image_payload(stored["ref"]))
    assert response.status == 413
    body = await json_body(response)
    assert_error(body, "too_large")
    assert body["error"]["details"]["field"] == "input_references"
