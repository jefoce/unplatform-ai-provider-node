"""Video request validation route tests."""

from aiohttp.test_utils import TestClient
from helpers import assert_error, json_body


async def test_video_requires_first_frame(client: TestClient) -> None:
    response = await client.post("/upai/api/v1/videos", json={"model": "wan22-i2v", "prompt": "x"})
    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "frame_images"


async def test_video_rejects_negative_prompt_when_unsupported(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/videos",
        json={"model": "wan22-t2v", "prompt": "x", "negative_prompt": "blurry"},
    )

    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "negative_prompt"


async def test_resolution_outside_capabilities(client: TestClient) -> None:
    response = await client.post(
        "/upai/api/v1/videos",
        json={"model": "wan22-t2v", "prompt": "x", "resolution": "1080p"},
    )
    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "resolution"
