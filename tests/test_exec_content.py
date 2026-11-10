"""Real result content route tests. Files live in a temp result root."""

import os
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from conftest import make_runtime
from test_exec_support import JOB_ID, make_job

from upai_provider.endpoints.content import content
from upai_provider.job_service import Kind
from upai_provider.routes import wrap_handler


async def _client(aiohttp_client: Any, runtime: Any, kind: Kind = "image") -> TestClient:
    app = web.Application()
    app.router.add_get("/content/{id}", wrap_handler(content(runtime, kind), runtime.config))
    return await aiohttp_client(app)


async def test_serves_registered_file_with_length_and_type(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    result = root / JOB_ID / "0.png"
    result.parent.mkdir(parents=True)
    result.write_bytes(b"png-bytes")
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(make_job(status="completed", files=(str(result),)))
    client = await _client(aiohttp_client, runtime)

    response = await client.get(f"/content/{JOB_ID}?index=0")

    assert response.status == 200
    assert response.headers["Content-Type"] == "image/png"
    assert response.headers["Content-Length"] == str(len(b"png-bytes"))
    assert await response.read() == b"png-bytes"


async def test_index_is_zero_based_and_checked(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    first = root / JOB_ID / "0.png"
    second = root / JOB_ID / "1.png"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(make_job(status="completed", files=(str(first), str(second))))
    client = await _client(aiohttp_client, runtime)

    first_response = await client.get(f"/content/{JOB_ID}?index=0")
    second_response = await client.get(f"/content/{JOB_ID}?index=1")
    missing = await client.get(f"/content/{JOB_ID}?index=2")
    negative = await client.get(f"/content/{JOB_ID}?index=-1")

    assert first_response.status == 200
    assert await first_response.read() == b"one"
    assert second_response.status == 200
    assert await second_response.read() == b"two"
    assert missing.status == 404
    assert negative.status == 400


async def test_path_outside_result_root_is_not_served(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(make_job(status="completed", files=(str(outside),)))
    client = await _client(aiohttp_client, runtime)

    response = await client.get(f"/content/{JOB_ID}?index=0")

    assert response.status == 404


async def test_missing_file_is_404(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    root.mkdir()
    missing = root / JOB_ID / "0.png"
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(make_job(status="completed", files=(str(missing),)))
    client = await _client(aiohttp_client, runtime)

    response = await client.get(f"/content/{JOB_ID}?index=0")

    assert response.status == 404


async def test_unfinished_job_is_rejected(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    result = root / JOB_ID / "0.png"
    result.parent.mkdir(parents=True)
    result.write_bytes(b"one")
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(make_job(status="in_progress", files=(str(result),)))
    client = await _client(aiohttp_client, runtime)

    response = await client.get(f"/content/{JOB_ID}?index=0")

    assert response.status == 400


async def test_kind_and_video_index_are_checked(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    first = root / JOB_ID / "0.mp4"
    second = root / JOB_ID / "1.mp4"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(
        make_job(kind="video", status="completed", files=(str(first), str(second)))
    )

    image_client = await _client(aiohttp_client, runtime, "image")
    video_client = await _client(aiohttp_client, runtime, "video")

    wrong_kind = await image_client.get(f"/content/{JOB_ID}?index=0")
    first_response = await video_client.get(f"/content/{JOB_ID}?index=0")
    second_response = await video_client.get(f"/content/{JOB_ID}?index=1")

    assert wrong_kind.status == 404
    assert first_response.status == 200
    assert first_response.headers["Content-Type"] == "video/mp4"
    assert second_response.status == 404


async def test_parent_traversal_is_not_served(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(make_job(status="completed", files=("../outside.png",)))
    client = await _client(aiohttp_client, runtime)

    response = await client.get(f"/content/{JOB_ID}?index=0")

    assert response.status == 404


def _resolved(name: str, root: PurePath) -> PurePath:
    path = type(root)(name)
    if not path.is_absolute():
        path = root / path

    parts: list[str] = []
    for part in path.parts:
        if part == "..":
            if len(parts) > 1:
                parts.pop()
            continue
        if part == ".":
            continue
        parts.append(part)

    return type(root)(*parts)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.png", True),
        ("../a.png", False),
        ("/root/a.png", True),
        ("/other/a.png", False),
        ("sub/../a.png", True),
    ],
)
def test_result_containment_posix(name: str, expected: bool) -> None:
    root = PurePosixPath("/root")

    assert _resolved(name, root).is_relative_to(root) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.png", True),
        ("..\\a.png", False),
        ("C:\\root\\a.png", True),
        ("D:\\a.png", False),
        ("\\\\server\\share\\a.png", False),
        ("sub\\..\\a.png", True),
    ],
)
def test_result_containment_windows(name: str, expected: bool) -> None:
    root = PureWindowsPath("C:/root")

    assert _resolved(name, root).is_relative_to(root) is expected


async def test_symlink_to_outside_file_is_not_served(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    link = root / JOB_ID / "0.png"
    link.parent.mkdir(parents=True)
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(make_job(status="completed", files=(str(link),)))
    client = await _client(aiohttp_client, runtime)

    response = await client.get(f"/content/{JOB_ID}?index=0")

    assert response.status == 404


async def test_symlinked_parent_outside_root_is_not_served(
    aiohttp_client: Any, tmp_path: Path
) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "0.png").write_bytes(b"secret")
    try:
        os.symlink(outside, root / JOB_ID)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(make_job(status="completed", files=(str(root / JOB_ID / "0.png"),)))
    client = await _client(aiohttp_client, runtime)

    response = await client.get(f"/content/{JOB_ID}?index=0")

    assert response.status == 404


async def test_symlinked_result_root_is_served(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    real_root = tmp_path / "real-temp"
    result = real_root / JOB_ID / "0.png"
    result.parent.mkdir(parents=True)
    result.write_bytes(b"png-bytes")
    link_root = tmp_path / "temp"
    try:
        os.symlink(real_root, link_root)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    runtime.result_root = link_root  # type: ignore[attr-defined]
    await runtime.store.create(
        make_job(status="completed", files=(str(link_root / JOB_ID / "0.png"),))
    )
    client = await _client(aiohttp_client, runtime)

    response = await client.get(f"/content/{JOB_ID}?index=0")

    assert response.status == 200
    assert await response.read() == b"png-bytes"


async def test_symlink_inside_root_is_not_served(aiohttp_client: Any, tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    root = tmp_path / "temp"
    target = root / "shared.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"inside")
    link = root / JOB_ID / "0.png"
    link.parent.mkdir(parents=True)
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    runtime.result_root = root  # type: ignore[attr-defined]
    await runtime.store.create(make_job(status="completed", files=(str(link),)))
    client = await _client(aiohttp_client, runtime)

    response = await client.get(f"/content/{JOB_ID}?index=0")

    assert response.status == 404
