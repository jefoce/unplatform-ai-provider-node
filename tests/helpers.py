"""Shared helpers for the route, auth and guard tests."""

from typing import Any, cast

from aiohttp import ClientResponse, FormData
from aiohttp.test_utils import TestClient
from aiohttp.web import HTTPRequestEntityTooLarge, Request
from conftest import assert_schema
from multidict import CIMultiDict

TOKEN = "abc123"  # noqa: S105
HEALTH = "/upai/api/v1/health"


def assert_error(body: dict[str, Any], code: str) -> None:
    assert_schema(body, "error")
    assert body["error"]["code"] == code


async def json_body(response: ClientResponse) -> dict[str, Any]:
    return cast(dict[str, Any], await response.json())


async def upload(
    client: TestClient,
    data: bytes,
    *,
    filename: str = "frame.png",
    content_type: str = "image/png",
) -> ClientResponse:
    form = FormData()
    form.add_field("file", data, filename=filename, content_type=content_type)
    return await client.post("/upai/api/v1/uploads", data=form)


class FakeTransport:
    def __init__(self, sockname: tuple[str, int] | None) -> None:
        self.sockname = sockname

    def get_extra_info(self, name: str) -> object | None:
        return self.sockname if name == "sockname" else None


class FakeRequest:
    """Only the attributes guard and upload_head read."""

    def __init__(
        self,
        remote: str,
        headers: dict[str, str] | None = None,
        match_info: dict[str, str] | None = None,
        sockname: tuple[str, int] | None = None,
    ) -> None:
        self.headers = CIMultiDict(headers or {})
        self.remote = remote
        self.match_info = match_info or {}
        self.transport = FakeTransport(sockname)


class TooLargeRequest:
    """Unknown content length, multipart parsing hits the app cap."""

    content_length = None
    query: dict[str, str] = {}
    _client_max_size = 64

    async def multipart(self) -> None:
        raise HTTPRequestEntityTooLarge(64)


def guard_request(
    remote: str,
    headers: dict[str, str] | None = None,
    sockname: tuple[str, int] | None = None,
) -> Request:
    merged = {"Host": "127.0.0.1", **(headers or {})}
    return cast(Request, FakeRequest(remote, merged, sockname=sockname))
