"""Upload route and upload store tests."""

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import av
import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient
from aiohttp.web import Request, Response
from conftest import assert_schema, make_client, make_runtime
from helpers import (
    HEALTH,
    FakeRequest,
    TooLargeRequest,
    assert_error,
    json_body,
    upload,
)
from PIL import Image

import upai_provider.mock_assets as mock_assets_module
import upai_provider.uploads as uploads_module
from upai_provider.endpoints.uploads import upload as upload_endpoint
from upai_provider.endpoints.uploads import upload_head
from upai_provider.job_service import validate_media_urls
from upai_provider.mock_assets import ensure_mock_assets
from upai_provider.protocol import InputReference, ProtocolError, Upload, VideoJobRequest
from upai_provider.routes import wrap_handler


async def test_upload_dedupes_and_head(
    client: TestClient, tmp_path: Path, png_bytes: bytes
) -> None:
    first = await upload(client, png_bytes)
    assert first.status == 201
    body = await json_body(first)
    assert_schema(body, "upload")
    assert len(body["sha256"]) == 64
    assert body["ref"].startswith("upai-upload:")
    assert body["size"] == len(png_bytes)

    second = await upload(client, png_bytes)
    assert second.status == 201
    duplicate = await json_body(second)
    assert duplicate["sha256"] == body["sha256"]
    assert len(list((tmp_path / "uploads").iterdir())) == 1

    known = await client.head(f"/upai/api/v1/uploads/{body['sha256']}")
    assert known.status == 200
    unknown = await client.head(f"/upai/api/v1/uploads/{'0' * 64}")
    assert unknown.status == 404
    malformed = await client.head("/upai/api/v1/uploads/not-a-hash")
    assert malformed.status == 404


async def test_upload_head_refreshes_mtime(
    client: TestClient, tmp_path: Path, png_bytes: bytes
) -> None:
    body = await json_body(await upload(client, png_bytes))
    path = next((tmp_path / "uploads").glob(f"{body['sha256']}.*"))
    os.utime(path, (1, 1))

    response = await client.head(f"/upai/api/v1/uploads/{body['sha256']}")
    assert response.status == 200
    assert path.stat().st_mtime > 1


async def test_upload_dedupe_refreshes_mtime(
    client: TestClient, tmp_path: Path, png_bytes: bytes
) -> None:
    body = await json_body(await upload(client, png_bytes))
    path = next((tmp_path / "uploads").glob(f"{body['sha256']}.*"))
    os.utime(path, (1, 1))

    response = await upload(client, png_bytes)
    assert response.status == 201
    assert path.stat().st_mtime > 1


async def test_sweep_after_head_keeps_upload(
    aiohttp_client: Any, tmp_path: Path, png_bytes: bytes
) -> None:
    runtime = make_runtime(tmp_path)
    client = await make_client(aiohttp_client, runtime)
    body = await json_body(await upload(client, png_bytes))
    path = next((tmp_path / "uploads").glob(f"{body['sha256']}.*"))
    os.utime(path, (1, 1))

    response = await client.head(f"/upai/api/v1/uploads/{body['sha256']}")
    assert response.status == 200

    runtime.uploads.sweep(max_age_sec=10, now=time.time())
    assert path.exists()


async def test_sweep_after_dedupe_keeps_upload(
    aiohttp_client: Any, tmp_path: Path, png_bytes: bytes
) -> None:
    runtime = make_runtime(tmp_path)
    client = await make_client(aiohttp_client, runtime)
    body = await json_body(await upload(client, png_bytes))
    path = next((tmp_path / "uploads").glob(f"{body['sha256']}.*"))
    os.utime(path, (1, 1))

    response = await upload(client, png_bytes)
    assert response.status == 201

    runtime.uploads.sweep(max_age_sec=10, now=time.time())
    assert path.exists()


async def test_upload_quota(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, max_total_bytes=100)
    client = await make_client(aiohttp_client, runtime)
    await runtime.uploads.save("a.bin", "application/octet-stream", b"a" * 60)

    response = await upload(client, b"b" * 60, filename="b.bin")
    assert response.status == 413
    body = await json_body(response)
    assert_error(body, "too_large")
    assert body["error"]["details"]["reason"] == "quota"
    assert not list((tmp_path / "uploads").glob(".upload-*.tmp"))


def _open_fd_count() -> int:
    for directory in (Path("/dev/fd"), Path("/proc/self/fd")):
        if directory.is_dir():
            return len(os.listdir(directory))

    raise AssertionError("no file descriptor directory")


@pytest.mark.skipif(os.name != "posix", reason="file descriptor directory is POSIX only")
async def test_quota_rejection_closes_temp_descriptor(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, max_total_bytes=100)
    store = runtime.uploads
    await store.save("a.bin", "application/octet-stream", b"a" * 60)

    async def stream() -> AsyncIterator[bytes]:
        yield b"b" * 60

    before = _open_fd_count()
    for _ in range(20):
        with pytest.raises(ProtocolError) as raised:
            await store.save_stream(
                "b.bin", "application/octet-stream", stream(), reserved_bytes=60
            )
        assert raised.value.status == 413

    assert _open_fd_count() == before
    assert not list((tmp_path / "uploads").glob(".upload-*.tmp"))


@pytest.mark.parametrize(
    ("filename", "content_type", "suffix"),
    [
        ("a.mp3", "audio/mpeg", ".mp3"),
        ("a.webm", "video/webm", ".webm"),
        ("a.mov", "video/quicktime", ".mov"),
    ],
)
async def test_upload_media_types(
    client: TestClient,
    tmp_path: Path,
    filename: str,
    content_type: str,
    suffix: str,
) -> None:
    response = await upload(client, b"media-bytes", filename=filename, content_type=content_type)
    assert response.status == 201
    body = await json_body(response)
    assert body["content_type"] == content_type
    path = next((tmp_path / "uploads").glob(f"{body['sha256']}.*"))
    assert path.suffix == suffix


async def test_head_returns_none_when_file_vanishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(tmp_path)
    stored = await runtime.uploads.save("a.bin", "application/octet-stream", b"gone")

    def missing_utime(path: Path, times: object) -> None:
        raise FileNotFoundError(path)

    monkeypatch.setattr("upai_provider.uploads.os.utime", missing_utime)
    assert runtime.uploads.head(stored.sha256) is None


@pytest.mark.parametrize("sha256", ["0" * 64, "not-a-hash"])
async def test_upload_head_missing_returns_code(tmp_path: Path, sha256: str) -> None:
    runtime = make_runtime(tmp_path)
    wrapped = wrap_handler(upload_head(runtime), runtime.config)
    request = cast(
        Request,
        FakeRequest("127.0.0.1", {"Host": "127.0.0.1"}, match_info={"sha256": sha256}),
    )

    response = cast(Response, await wrapped(request))
    assert response.status == 404
    assert_error(json.loads(cast(str, response.text)), "upload_not_found")


async def test_upload_requires_a_file_part(client: TestClient) -> None:
    form = FormData()
    form.add_field("note", "no file here", content_type="text/plain")

    response = await client.post("/upai/api/v1/uploads", data=form)

    assert response.status == 400
    assert_error(await json_body(response), "invalid_request")


async def test_upload_too_large(aiohttp_client: Any, tmp_path: Path, png_bytes: bytes) -> None:
    runtime = make_runtime(tmp_path, max_upload_bytes=32)
    client = await make_client(aiohttp_client, runtime)

    response = await upload(client, png_bytes)
    assert response.status == 413
    assert_error(await json_body(response), "too_large")


async def test_upload_stream_cap_cleans_temp(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, max_upload_bytes=32)
    uploads_dir = tmp_path / "uploads"

    async def stream() -> AsyncIterator[bytes]:
        yield b"x" * 20
        yield b"y" * 20

    with pytest.raises(ProtocolError) as raised:
        await runtime.uploads.save_stream("big.bin", "application/octet-stream", stream())

    assert raised.value.code == "too_large"
    assert raised.value.status == 413
    assert not list(uploads_dir.glob(".upload-*.tmp"))


async def test_upload_stream_dedupes_and_cleans_temp(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    uploads_dir = tmp_path / "uploads"

    async def stream() -> AsyncIterator[bytes]:
        yield b"same-bytes"

    first = await runtime.uploads.save_stream("a.bin", "application/octet-stream", stream())
    second = await runtime.uploads.save_stream("a.bin", "application/octet-stream", stream())

    assert second.ref == first.ref
    assert len(list(uploads_dir.iterdir())) == 1
    assert not list(uploads_dir.glob(".upload-*.tmp"))


async def test_upload_app_cap_below_store_cap(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    client = await make_client(aiohttp_client, runtime, client_max_size=64)

    response = await upload(client, b"x" * 1024, filename="big.bin")
    assert response.status == 413
    assert response.headers["X-UPAI-Protocol"] == "1"
    assert_error(await json_body(response), "too_large")

    health = await json_body(await client.get(HEALTH))
    assert health["max_upload_bytes"] == 64


async def test_upload_413_uses_effective_cap(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, max_upload_bytes=1024 * 1024)
    request = cast(Request, TooLargeRequest())

    with pytest.raises(ProtocolError) as raised:
        await upload_endpoint(runtime)(request)

    assert raised.value.status == 413
    assert raised.value.message == "upload exceeds 64 bytes"
    assert str(runtime.uploads.max_bytes) not in raised.value.message


async def test_upload_dedupes_by_hash_only(
    client: TestClient, tmp_path: Path, png_bytes: bytes
) -> None:
    first = await upload(client, png_bytes, filename="a.png")
    first_body = await json_body(first)

    second = await upload(client, png_bytes, filename="a.jpg", content_type="image/jpeg")
    second_body = await json_body(second)
    assert second_body["sha256"] == first_body["sha256"]
    assert second_body["ref"] == first_body["ref"]
    assert second_body["filename"] == "a.jpg"
    assert second_body["content_type"] == "image/png"

    files = list((tmp_path / "uploads").iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".png"

    known = await client.head(f"/upai/api/v1/uploads/{first_body['sha256']}")
    assert known.status == 200


async def test_parallel_uploads_near_quota(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, max_upload_bytes=4_000_000, max_total_bytes=2_000_000)
    client = await make_client(aiohttp_client, runtime, client_max_size=4_000_000)

    first, second = await asyncio.gather(
        upload(client, b"a" * 1_100_000, filename="a.bin", content_type="application/octet-stream"),
        upload(client, b"b" * 1_100_000, filename="b.bin", content_type="application/octet-stream"),
    )

    assert sorted([first.status, second.status]) == [201, 413]
    failed = first if first.status == 413 else second
    body = await json_body(failed)
    assert_error(body, "too_large")
    assert body["error"]["details"]["reason"] == "quota"


async def test_parallel_uploads_below_quota_both_succeed(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = make_runtime(tmp_path, max_upload_bytes=4_000_000, max_total_bytes=2_000_000)
    client = await make_client(aiohttp_client, runtime, client_max_size=4_000_000)

    first, second = await asyncio.gather(
        upload(client, b"a" * 700_000, filename="a.bin", content_type="application/octet-stream"),
        upload(client, b"b" * 700_000, filename="b.bin", content_type="application/octet-stream"),
    )

    assert first.status == 201
    assert second.status == 201
    assert runtime.uploads.remaining_bytes() == 600_000


async def test_stale_temp_file_is_not_counted_as_stored(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = make_runtime(tmp_path, max_upload_bytes=4_000_000, max_total_bytes=2_000_000)
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    stale = uploads_dir / ".upload-stale.tmp"
    stale.write_bytes(b"x" * 1_900_000)
    client = await make_client(aiohttp_client, runtime, client_max_size=4_000_000)

    response = await upload(
        client, b"y" * 1_500_000, filename="y.bin", content_type="application/octet-stream"
    )

    assert response.status == 201
    assert runtime.uploads.remaining_bytes() == 500_000
    assert stale.exists()


async def test_reservation_released_on_client_failure(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, max_total_bytes=1000)
    uploads_dir = tmp_path / "uploads"

    async def stream() -> AsyncIterator[bytes]:
        yield b"x" * 100
        raise RuntimeError("client disconnected")

    with pytest.raises(RuntimeError):
        await runtime.uploads.save_stream("a.bin", "application/octet-stream", stream())

    assert runtime.uploads.remaining_bytes() == 1000
    assert not list(uploads_dir.glob(".upload-*.tmp"))


async def test_reservation_released_on_over_cap_stream(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, max_upload_bytes=32, max_total_bytes=1000)

    async def stream() -> AsyncIterator[bytes]:
        yield b"x" * 20
        yield b"y" * 20

    with pytest.raises(ProtocolError):
        await runtime.uploads.save_stream("a.bin", "application/octet-stream", stream())

    assert runtime.uploads.remaining_bytes() == 1000


async def test_upload_head_awaits_off_loop_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(tmp_path)
    calls: list[str] = []

    async def fake_head_async(sha256: str) -> None:
        calls.append(sha256)
        return None

    monkeypatch.setattr(runtime.uploads, "head_async", fake_head_async)
    wrapped = wrap_handler(upload_head(runtime), runtime.config)
    request = cast(
        Request,
        FakeRequest("127.0.0.1", {"Host": "127.0.0.1"}, match_info={"sha256": "0" * 64}),
    )

    response = cast(Response, await wrapped(request))
    assert response.status == 404
    assert calls == ["0" * 64]


async def test_media_url_check_uses_async_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(tmp_path)
    calls: list[str] = []

    async def fake_head_async(sha256: str) -> None:
        calls.append(sha256)
        return None

    monkeypatch.setattr(runtime.uploads, "head_async", fake_head_async)
    sha256 = "a" * 64
    request = VideoJobRequest(
        model="m",
        prompt="p",
        input_references=(InputReference("image", f"upai-upload:{sha256}", 1),),
    )

    with pytest.raises(ProtocolError) as raised:
        await validate_media_urls(request, runtime)

    assert raised.value.code == "upload_not_found"
    assert calls == [sha256]


async def test_quota_cache_updates_on_save_dedupe_and_sweep(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, max_total_bytes=1000)
    store = runtime.uploads

    await store.save("a.bin", "application/octet-stream", b"a" * 100)
    assert store.remaining_bytes() == 900

    await store.save("a.bin", "application/octet-stream", b"a" * 100)
    assert store.remaining_bytes() == 900

    await store.save("b.bin", "application/octet-stream", b"b" * 200)
    assert store.remaining_bytes() == 700

    store.sweep(max_age_sec=0, now=time.time() + 10)
    assert store.remaining_bytes() == 1000


async def test_mock_assets_regenerate_zero_byte_and_partial(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "mock.png").write_bytes(b"\x89PNG\r\n\x1a\npartial")
    (assets_dir / "mock.mp4").write_bytes(b"")

    assets = await ensure_mock_assets(tmp_path)

    assert assets.png.stat().st_size > 0
    assert assets.mp4.stat().st_size > 0
    with Image.open(assets.png) as image:
        image.verify()


async def test_upload_store_uses_replace_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, Path]] = []
    original = uploads_module.replace_file

    def fake(source: Path, target: Path) -> None:
        calls.append((Path(source), Path(target)))
        original(source, target)

    monkeypatch.setattr(uploads_module, "replace_file", fake)
    runtime = make_runtime(tmp_path)

    await runtime.uploads.save("a.bin", "application/octet-stream", b"bytes")

    assert len(calls) == 1
    assert calls[0][1].parent == tmp_path / "uploads"
    assert not list((tmp_path / "uploads").glob(".upload-*.tmp"))


async def test_mock_assets_use_replace_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, Path]] = []
    original = mock_assets_module.replace_file

    def fake(source: Path, target: Path) -> None:
        calls.append((Path(source), Path(target)))
        original(source, target)

    monkeypatch.setattr(mock_assets_module, "replace_file", fake)

    assets = await ensure_mock_assets(tmp_path)

    assert {target.name for _, target in calls} == {"mock.png", "mock.mp4"}
    assert assets.png.is_file()
    assert not list((tmp_path / "assets").glob(".mock-*"))


async def test_save_stream_honours_request_cap(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, max_upload_bytes=1024)

    async def stream() -> AsyncIterator[bytes]:
        yield b"x" * 20
        yield b"y" * 20

    with pytest.raises(ProtocolError) as raised:
        await runtime.uploads.save_stream(
            "big.bin",
            "application/octet-stream",
            stream(),
            max_bytes=32,
        )

    assert raised.value.status == 413
    assert raised.value.message == "upload exceeds 32 bytes"
    assert not list((tmp_path / "uploads").glob(".upload-*.tmp"))


async def test_upload_passes_effective_cap_to_store(
    aiohttp_client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = make_runtime(tmp_path)
    client = await make_client(aiohttp_client, runtime, client_max_size=200)
    seen: dict[str, int | None] = {}

    async def fake_save_stream(
        filename: str,
        content_type: str,
        chunks: AsyncIterator[bytes],
        *,
        reserved_bytes: int = 0,
        max_bytes: int | None = None,
    ) -> Upload:
        async for _ in chunks:
            pass
        seen["cap"] = max_bytes
        return Upload(
            sha256="a" * 64,
            ref=f"upai-upload:{'a' * 64}",
            size=4,
            content_type="image/png",
            filename=filename,
        )

    monkeypatch.setattr(runtime.uploads, "save_stream", fake_save_stream)

    response = await upload(client, b"tiny")

    assert response.status == 201
    assert seen["cap"] == 200


async def test_upload_returns_507_when_free_space_low(
    aiohttp_client: Any, tmp_path: Path, png_bytes: bytes
) -> None:
    runtime = make_runtime(tmp_path)
    runtime.free_space = lambda path: 0
    client = await make_client(aiohttp_client, runtime)

    response = await upload(client, png_bytes)

    assert response.status == 507
    assert_error(await json_body(response), "insufficient_storage")


async def test_mock_mp4_uses_selected_encoder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mock_assets_module, "select_encoder", lambda: "mpeg4")

    assets = await ensure_mock_assets(tmp_path)

    with av.open(str(assets.mp4)) as container:
        assert container.streams.video[0].codec_context.name == "mpeg4"
