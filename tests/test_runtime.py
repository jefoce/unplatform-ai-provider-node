"""Runtime sweep cleanup."""

import os
import time
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import FakeClock, make_runtime
from test_exec_support import JOB_ID, SECOND_JOB_ID, make_job

from upai_provider.job_service import create_job
from upai_provider.protocol import Job


def _make_job_dirs(tmp_path: Path, roots: tuple[Path, Path], job_id: str) -> None:
    for root in roots:
        folder = root / job_id
        folder.mkdir(parents=True)
        (folder / "0.bin").write_bytes(b"x")


async def test_sweep_once_removes_dirs_after_store_sweep(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    roots = (runtime.input_root, runtime.result_root)
    job = replace(make_job(job_id=JOB_ID, status="completed"), expires_at=int(clock.now) + 10)
    await runtime.store.create(job)
    _make_job_dirs(tmp_path, roots, JOB_ID)
    shared = runtime.input_root / "uploads" / "keep.png"
    shared.parent.mkdir(parents=True)
    shared.write_bytes(b"keep")

    clock.advance(11)
    await runtime.store.sweep()
    await runtime.sweep_once()

    assert not (runtime.input_root / JOB_ID).exists()
    assert not (runtime.result_root / JOB_ID).exists()
    assert shared.read_bytes() == b"keep"


async def test_sweep_once_removes_dir_without_job(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    _make_job_dirs(tmp_path, (runtime.input_root, runtime.result_root), JOB_ID)

    await runtime.sweep_once()

    assert not (runtime.input_root / JOB_ID).exists()
    assert not (runtime.result_root / JOB_ID).exists()


async def test_sweep_once_keeps_unexpired_and_non_final_dirs(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    roots = (runtime.input_root, runtime.result_root)
    done = replace(
        make_job(job_id=JOB_ID, status="completed"),
        expires_at=int(clock.now) + 3600,
    )
    running = make_job(job_id=SECOND_JOB_ID, status="in_progress")
    for job in (done, running):
        await runtime.store.create(job)
        _make_job_dirs(tmp_path, roots, job.id)

    await runtime.sweep_once()

    assert (runtime.input_root / done.id).exists()
    assert (runtime.result_root / done.id).exists()
    assert (runtime.input_root / running.id).exists()
    assert (runtime.result_root / running.id).exists()


async def test_sweep_once_keeps_dir_for_job_created_after_snapshot(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    _make_job_dirs(tmp_path, (runtime.input_root, runtime.result_root), JOB_ID)
    job = make_job(job_id=JOB_ID, status="pending")
    original_list = runtime.store.list

    async def list_then_create() -> tuple[Job, ...]:
        jobs = await original_list()
        await runtime.store.create(job)
        return jobs

    monkeypatch.setattr(runtime.store, "list", list_then_create)
    await runtime.sweep_once()

    assert (runtime.input_root / JOB_ID).exists()
    assert (runtime.result_root / JOB_ID).exists()


async def test_job_pins_upload_until_final(tmp_path: Path, clock: FakeClock) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.is_mock = False
    upload = await runtime.uploads.save("frame.png", "image/png", b"png-bytes")
    stored = runtime.uploads.path(upload.sha256)
    assert stored is not None

    job = await create_job(
        runtime,
        kind="image",
        model="sdxl-image",
        prompt="pin",
        seed=1,
        count=1,
        base_url="http://client.local:8188",
        request={"input_references": [{"url": upload.ref}]},
    )
    os.utime(stored, (1, 1))
    runtime.uploads.sweep(max_age_sec=10, now=time.time())
    assert stored.exists()

    await runtime.store.finalize(job.id, "cancelled")
    runtime.uploads.sweep(max_age_sec=10, now=time.time())
    assert not stored.exists()
