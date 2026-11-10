"""Materialize and cleanup tests. No real ComfyUI and no real HTTP."""

import base64
import os
import time
from pathlib import Path

import pytest
from test_exec_support import JOB_ID, SECOND_JOB_ID, FakeResponse, FakeSession, make_request

import upai_provider.materialize_store as materialize_store_module
from upai_provider.materialize import materialize_inputs
from upai_provider.materialize_cleanup import cleanup_job_files
from upai_provider.mock import image_models, video_models
from upai_provider.protocol import FrameImage, InputReference, ProtocolError, format_run_id
from upai_provider.uploads import UploadStore


def _data_url(data: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _uploads(tmp_path: Path) -> UploadStore:
    return UploadStore(tmp_path / "uploads", max_bytes=1024 * 1024, clock=lambda: 0.0)


async def test_data_url_writes_png(tmp_path: Path, png_bytes: bytes) -> None:
    request = make_request(
        refs=(InputReference("image", _data_url(png_bytes), 1),),
    )
    media = await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=image_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=_uploads(tmp_path),
    )

    path = media.reference_path("image", 1)
    assert path is not None
    assert path.parent == tmp_path / "uploads"
    assert path.suffix == ".png"
    assert path.read_bytes() == png_bytes
    assert not (tmp_path / "input" / JOB_ID).exists()


async def test_bad_image_magic_is_rejected_and_job_dir_removed(tmp_path: Path) -> None:
    request = make_request(
        refs=(InputReference("image", _data_url(b"GIF89a-not-allowed"), 1),),
    )

    with pytest.raises(ProtocolError) as raised:
        await materialize_inputs(
            job_id=JOB_ID,
            request=request,
            capabilities=image_models()[0].capabilities,
            input_root=tmp_path / "input",
            uploads=_uploads(tmp_path),
        )

    assert raised.value.code == "invalid_request"
    assert not (tmp_path / "input" / JOB_ID).exists()


async def test_data_url_over_limit_is_rejected(tmp_path: Path, png_bytes: bytes) -> None:
    request = make_request(refs=(InputReference("image", _data_url(png_bytes), 1),))

    with pytest.raises(ProtocolError) as raised:
        await materialize_inputs(
            job_id=JOB_ID,
            request=request,
            capabilities=image_models()[0].capabilities,
            input_root=tmp_path / "input",
            uploads=_uploads(tmp_path),
            max_bytes=10,
        )

    assert raised.value.code == "too_large"


async def test_upload_reference_is_not_copied(tmp_path: Path, png_bytes: bytes) -> None:
    uploads = _uploads(tmp_path)
    upload = await uploads.save("frame.png", "image/png", png_bytes)
    request = make_request(refs=(InputReference("image", upload.ref, 1),))

    media = await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=image_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=uploads,
    )

    stored = uploads.path(upload.sha256)
    assert stored is not None
    assert media.reference_path("image", 1) == stored
    assert stored.read_bytes() == png_bytes
    assert not (tmp_path / "input" / JOB_ID).exists()


async def test_url_fetch_disabled(tmp_path: Path, png_bytes: bytes) -> None:
    session = FakeSession()
    session.get_responses.append(FakeResponse(chunks=[png_bytes]))
    request = make_request(refs=(InputReference("image", "https://example.test/a.png", 1),))

    with pytest.raises(ProtocolError) as raised:
        await materialize_inputs(
            job_id=JOB_ID,
            request=request,
            capabilities=image_models()[0].capabilities,
            input_root=tmp_path / "input",
            uploads=_uploads(tmp_path),
            session=session,
        )

    assert raised.value.code == "invalid_request"
    assert session.get_calls == []


async def test_url_fetch_writes_file(tmp_path: Path, png_bytes: bytes) -> None:
    session = FakeSession()
    session.get_responses.append(
        FakeResponse(
            headers={
                "Content-Type": "image/png",
                "Content-Length": str(len(png_bytes)),
            },
            chunks=[png_bytes],
        )
    )
    request = make_request(refs=(InputReference("image", "https://example.test/a", 1),))

    media = await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=image_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=_uploads(tmp_path),
        allow_url_fetch=True,
        session=session,
    )

    path = media.reference_path("image", 1)
    assert path is not None
    assert path.name == "image_1.png"
    assert path.read_bytes() == png_bytes
    assert session.get_calls == [("https://example.test/a", False)]


async def test_url_fetch_streams_response_content(tmp_path: Path, png_bytes: bytes) -> None:
    session = FakeSession()
    split = len(png_bytes) // 2
    session.get_responses.append(
        FakeResponse(
            headers={"Content-Type": "image/png"},
            chunks=[png_bytes[:split], png_bytes[split:]],
        )
    )
    request = make_request(refs=(InputReference("image", "https://example.test/a", 1),))

    media = await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=image_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=_uploads(tmp_path),
        allow_url_fetch=True,
        session=session,
    )

    path = media.reference_path("image", 1)
    assert path is not None
    assert path.read_bytes() == png_bytes


async def test_video_reference_is_not_sniffed_as_image(tmp_path: Path) -> None:
    payload = base64.b64encode(b"not-an-image").decode("ascii")
    request = make_request(
        kind="video",
        refs=(InputReference("video", f"data:video/mp4;base64,{payload}", 1),),
    )

    media = await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=video_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=_uploads(tmp_path),
    )

    path = media.reference_path("video", 1)
    assert path is not None
    assert path.suffix == ".mp4"
    assert path.read_bytes() == b"not-an-image"


async def test_frame_is_materialized(tmp_path: Path, png_bytes: bytes) -> None:
    request = make_request(
        kind="video",
        frames=(FrameImage("first_frame", _data_url(png_bytes), 1),),
    )

    media = await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=video_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=_uploads(tmp_path),
    )

    path = media.frame_path("first_frame")
    assert path is not None
    assert path.suffix == ".png"
    assert path.read_bytes() == png_bytes


async def test_cleanup_removes_job_files_not_shared_uploads(
    tmp_path: Path, png_bytes: bytes
) -> None:
    input_root = tmp_path / "input"
    result_root = tmp_path / "temp"
    uploads = _uploads(tmp_path)
    upload = await uploads.save("keep.png", "image/png", png_bytes)

    input_file = input_root / JOB_ID / "image_1.png"
    input_file.parent.mkdir(parents=True)
    input_file.write_bytes(png_bytes)
    result_file = result_root / JOB_ID / "0.png"
    result_file.parent.mkdir(parents=True)
    result_file.write_bytes(png_bytes)

    cleanup_job_files(
        JOB_ID,
        input_root=input_root,
        result_root=result_root,
        files=(str(result_file),),
    )

    assert not input_file.parent.exists()
    assert not result_file.parent.exists()
    assert uploads.path(upload.sha256) is not None


async def test_cleanup_removes_run_directories(tmp_path: Path, png_bytes: bytes) -> None:
    input_root = tmp_path / "input"
    result_root = tmp_path / "temp"
    job_file = input_root / JOB_ID / "image_1.png"
    job_file.parent.mkdir(parents=True)
    job_file.write_bytes(png_bytes)
    run_file = result_root / format_run_id(JOB_ID, 0) / "0-0.png"
    run_file.parent.mkdir(parents=True)
    run_file.write_bytes(png_bytes)
    shared = result_root / "uploads" / "keep.png"
    shared.parent.mkdir(parents=True)
    shared.write_bytes(png_bytes)

    cleanup_job_files(JOB_ID, input_root=input_root, result_root=result_root)

    assert not job_file.parent.exists()
    assert not run_file.parent.exists()
    assert shared.read_bytes() == png_bytes


async def test_cleanup_rejects_invalid_job_id(tmp_path: Path) -> None:
    root = tmp_path / "input"
    target = root / ".." / "elsewhere"
    target.mkdir(parents=True)

    cleanup_job_files("../elsewhere", input_root=root, result_root=tmp_path / "temp")

    assert target.exists()


def _record_replace(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, Path]]:
    calls: list[tuple[Path, Path]] = []
    original = materialize_store_module.replace_file

    def fake(source: Path, target: Path) -> None:
        calls.append((Path(source), Path(target)))
        original(source, target)

    monkeypatch.setattr(materialize_store_module, "replace_file", fake)
    return calls


async def test_data_url_uses_upload_store(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_replace(monkeypatch)
    request = make_request(refs=(InputReference("image", _data_url(png_bytes), 1),))

    media = await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=image_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=_uploads(tmp_path),
    )

    path = media.reference_path("image", 1)
    assert path is not None
    assert calls == []
    assert path.parent == tmp_path / "uploads"
    assert not list((tmp_path / "uploads").glob(".upload-*.tmp"))


async def test_upload_reference_skips_replace_file(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_replace(monkeypatch)
    uploads = _uploads(tmp_path)
    upload = await uploads.save("frame.png", "image/png", png_bytes)
    request = make_request(refs=(InputReference("image", upload.ref, 1),))

    await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=image_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=uploads,
    )

    assert calls == []
    assert not (tmp_path / "input" / JOB_ID).exists()


async def test_url_fetch_uses_replace_file(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_replace(monkeypatch)
    session = FakeSession()
    session.get_responses.append(
        FakeResponse(
            headers={
                "Content-Type": "image/png",
                "Content-Length": str(len(png_bytes)),
            },
            chunks=[png_bytes],
        )
    )
    request = make_request(refs=(InputReference("image", "https://example.test/a", 1),))

    await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=image_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=_uploads(tmp_path),
        allow_url_fetch=True,
        session=session,
    )

    job_dir = tmp_path / "input" / JOB_ID
    assert len(calls) == 2
    assert calls[0][1] == job_dir / "image_1.bin"
    assert calls[1][1] == job_dir / "image_1.png"
    assert not list(job_dir.glob(".part-*"))


async def test_two_identical_data_urls_store_one_file(tmp_path: Path, png_bytes: bytes) -> None:
    uploads = _uploads(tmp_path)
    capabilities = image_models()[0].capabilities
    url = _data_url(png_bytes)
    request = make_request(refs=(InputReference("image", url, 1),))

    first = await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=capabilities,
        input_root=tmp_path / "input",
        uploads=uploads,
    )
    stored = first.reference_path("image", 1)
    assert stored is not None
    os.utime(stored, (1, 1))

    second = await materialize_inputs(
        job_id=SECOND_JOB_ID,
        request=request,
        capabilities=capabilities,
        input_root=tmp_path / "input",
        uploads=uploads,
    )

    files = list((tmp_path / "uploads").iterdir())
    assert len(files) == 1
    assert sum(path.stat().st_size for path in files) == len(png_bytes)
    assert second.reference_path("image", 1) == stored
    assert time.time() - stored.stat().st_mtime < 60


async def test_pinned_upload_survives_sweep_until_released(
    tmp_path: Path, png_bytes: bytes
) -> None:
    uploads = _uploads(tmp_path)
    upload = await uploads.save("frame.png", "image/png", png_bytes)
    stored = uploads.path(upload.sha256)
    assert stored is not None
    uploads.pin(JOB_ID, upload.sha256)
    os.utime(stored, (1, 1))

    uploads.sweep(max_age_sec=10, now=time.time())
    assert stored.exists()

    uploads.release(JOB_ID)
    uploads.sweep(max_age_sec=10, now=time.time())
    assert not stored.exists()


async def test_identical_data_url_slots_share_one_stored_file(
    tmp_path: Path, png_bytes: bytes
) -> None:
    uploads = _uploads(tmp_path)
    url = _data_url(png_bytes)
    request = make_request(
        refs=(
            InputReference("image", url, 1),
            InputReference("image", url, 2),
        )
    )

    media = await materialize_inputs(
        job_id=JOB_ID,
        request=request,
        capabilities=image_models()[0].capabilities,
        input_root=tmp_path / "input",
        uploads=uploads,
    )

    first = media.reference_path("image", 1)
    second = media.reference_path("image", 2)
    assert first is not None
    assert first == second
    files = list((tmp_path / "uploads").iterdir())
    assert len(files) == 1
    assert files[0].stat().st_size == len(png_bytes)
