"""Job store, boot repair, sweep and mock timeline tests."""

import asyncio
import json
import logging
import uuid
from dataclasses import asdict
from pathlib import Path

import pytest
from conftest import FakeClock, make_runtime

import upai_provider.jobs as jobs_module
import upai_provider.jobs_file as jobs_file_module
import upai_provider.jobs_output as jobs_output
import upai_provider.runtime as runtime_module
from upai_provider.config import Config
from upai_provider.job_service import create_job
from upai_provider.jobs import JobStore
from upai_provider.jobs_sweep import SweepResult
from upai_provider.mock import MockTimings, mock_state
from upai_provider.protocol import Job, JobProgress, JobStatus, ProtocolError, format_run_id

CREATED = "2026-01-01T00:00:00Z"


def _uuid(index: int) -> str:
    return str(uuid.UUID(int=index, version=4))


def _job(
    job_id: str,
    *,
    status: JobStatus = "pending",
    created_at: str = CREATED,
    expires_at: int | None = None,
    urls: tuple[str, ...] | None = None,
    queue_position: int | None = None,
) -> Job:
    return Job(
        id=job_id,
        kind="video",
        model="wan22-t2v",
        status=status,
        progress=JobProgress(0, None, 0, 0, queue_position),
        seed=1,
        urls=urls,
        error=None,
        usage_cost=0.0,
        created_at=created_at,
        started_at=None,
        finished_at=None,
        expires_at=expires_at,
    )


def _store(tmp_path: Path, clock: FakeClock, *, max_jobs: int | None = None) -> JobStore:
    if max_jobs is None:
        return JobStore(tmp_path / "jobs.json", clock=clock, ttl_seconds=3600)

    return JobStore(
        tmp_path / "jobs.json",
        clock=clock,
        ttl_seconds=3600,
        max_jobs=max_jobs,
    )


async def test_register_output_from_thread_merges_files(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock)
    job = await store.create(_job(_uuid(1)))
    jobs_output.configure_output(store, asyncio.get_running_loop())

    await asyncio.to_thread(jobs_output.register_output, job.id, ("a.mp4",))
    await asyncio.to_thread(jobs_output.register_output, job.id, ("a.mp4", "b.mp4"))

    stored = await store.get(job.id)
    assert stored is not None
    assert stored.files == ("a.mp4", "b.mp4")


async def test_register_output_orders_run_then_batch(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock)
    job = await store.create(_job(_uuid(1)))
    jobs_output.configure_output(store, asyncio.get_running_loop())

    for run, names in (
        (2, ("2-0.mp4", "2-1.mp4")),
        (0, ("0-0.mp4", "0-1.mp4")),
        (1, ("1-0.mp4",)),
    ):
        await asyncio.to_thread(jobs_output.register_output, format_run_id(job.id, run), names)

    stored = await store.get(job.id)
    assert stored is not None
    assert stored.files == ("0-0.mp4", "0-1.mp4", "1-0.mp4", "2-0.mp4", "2-1.mp4")

    await store.finalize(job.id, "completed")
    await asyncio.to_thread(jobs_output.register_output, format_run_id(job.id, 3), ("3-0.mp4",))

    final = await store.get(job.id)
    assert final is not None
    assert final.files == stored.files


async def test_register_output_ignores_final_jobs(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock)
    job = await store.create(_job(_uuid(1)))
    jobs_output.configure_output(store, asyncio.get_running_loop())
    await store.finalize(job.id, "completed")

    await asyncio.to_thread(jobs_output.register_output, job.id, ("a.mp4",))

    stored = await store.get(job.id)
    assert stored is not None
    assert stored.files == ()


async def test_register_output_times_out_safely(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = _store(tmp_path, clock)
    job = await store.create(_job(_uuid(1)))
    jobs_output.configure_output(store, asyncio.get_running_loop())
    monkeypatch.setattr(jobs_output, "REGISTER_OUTPUT_TIMEOUT", 0.01)

    with caplog.at_level(logging.WARNING):
        jobs_output.register_output(job.id, ("a.mp4",))

    assert "register_output failed" in caplog.text
    await asyncio.sleep(0)


async def test_sweep_expires_with_fake_clock(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock)
    job = _job(_uuid(1), status="completed", expires_at=int(clock.now) + 10)
    await store.create(job)

    clock.advance(11)
    result = await store.sweep()

    assert result.expired == (job.id,)
    assert result.removed == ()
    stored = await store.get(job.id)
    assert stored is not None
    assert stored.status == "expired"


async def test_boot_repair(tmp_path: Path, clock: FakeClock) -> None:
    pending = _job(_uuid(1))
    done = _job(_uuid(2), status="completed", expires_at=int(clock.now) - 1)
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [asdict(pending), asdict(done)]}), encoding="utf-8")

    store = _store(tmp_path, clock)
    await store.load()

    repaired = await store.get(pending.id)
    assert repaired is not None
    assert repaired.status == "failed"
    assert repaired.error == "ComfyUI restarted"

    expired = await store.get(done.id)
    assert expired is not None
    assert expired.status == "expired"


async def test_invalid_jobs_file_is_ignored(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "jobs.json"
    path.write_text("{not json", encoding="utf-8")

    store = _store(tmp_path, clock)
    await store.load()

    assert await store.list() == ()
    corrupt = list(tmp_path.glob("jobs.json.corrupt-*"))
    assert len(corrupt) == 1
    assert corrupt[0].read_text(encoding="utf-8") == "{not json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"jobs": []}


async def test_bad_record_keeps_valid_jobs(
    tmp_path: Path,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "jobs.json"
    first = _job(_uuid(1), status="completed", expires_at=int(clock.now) + 3600)
    second = _job(_uuid(2), status="completed", expires_at=int(clock.now) + 3600)
    bad = asdict(_job(_uuid(3)))
    bad["status"] = "bogus"
    original = json.dumps({"jobs": [asdict(first), bad, asdict(second)]})
    path.write_text(original, encoding="utf-8")

    store = _store(tmp_path, clock)
    with caplog.at_level(logging.WARNING):
        await store.load()

    remaining = await store.list()
    assert {job.id for job in remaining} == {first.id, second.id}
    corrupt = list(tmp_path.glob("jobs.json.corrupt-*"))
    assert len(corrupt) == 1
    assert corrupt[0].read_text(encoding="utf-8") == original
    assert "skipped 1 invalid job records" in caplog.text


async def test_non_utf8_jobs_file_is_quarantined(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "jobs.json"
    path.write_bytes(b"\xff\xfe")

    store = _store(tmp_path, clock)
    await store.load()

    assert await store.list() == ()
    corrupt = list(tmp_path.glob("jobs.json.corrupt-*"))
    assert len(corrupt) == 1
    assert corrupt[0].read_bytes() == b"\xff\xfe"
    assert json.loads(path.read_text(encoding="utf-8")) == {"jobs": []}


async def test_non_object_jobs_file_is_quarantined(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    path = tmp_path / "jobs.json"
    path.write_text("[]", encoding="utf-8")

    store = _store(tmp_path, clock)
    await store.load()

    assert await store.list() == ()
    corrupt = list(tmp_path.glob("jobs.json.corrupt-*"))
    assert len(corrupt) == 1
    assert corrupt[0].read_text(encoding="utf-8") == "[]"
    assert json.loads(path.read_text(encoding="utf-8")) == {"jobs": []}


async def test_unreadable_jobs_path_is_left_untouched(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "jobs.json"
    path.mkdir()

    store = _store(tmp_path, clock)
    await store.load()

    assert await store.list() == ()
    assert path.is_dir()


async def test_sweep_trims_to_max_jobs(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock, max_jobs=3)
    ids = []
    for index in range(1, 6):
        job = _job(
            _uuid(index),
            status="completed",
            created_at=f"2026-01-01T00:00:0{index}Z",
            expires_at=int(clock.now) + 3600,
        )
        await store.create(job)
        ids.append(job.id)

    result = await store.sweep()

    assert result.expired == ()
    assert set(result.removed) == set(ids[:2])
    remaining = await store.list()
    assert len(remaining) == 3
    assert {job.id for job in remaining} == set(ids[2:])


async def test_update_cannot_revive_cancelled_job(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock)
    job = _job(_uuid(1))
    await store.create(job)
    assert await store.get(job.id) is not None

    cancelled = await store.cancel(job.id)
    assert cancelled is not None
    finished_at = cancelled.finished_at

    updated = await store.update(
        job.id,
        status="in_progress",
        progress=JobProgress(50, "MockSampler", 50, 100, None),
    )
    stored = await store.get(job.id)

    assert updated is not None
    assert updated.status == "cancelled"
    assert updated.finished_at == finished_at
    assert stored == cancelled


async def test_progress_only_update_stays_in_memory(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path, clock)
    saves = 0
    original = store._persist

    async def counting_persist(version: int, jobs: tuple[Job, ...]) -> None:
        nonlocal saves
        saves += 1
        await original(version, jobs)

    monkeypatch.setattr(store, "_persist", counting_persist)
    job = _job(_uuid(1))
    await store.create(job)
    assert saves == 1

    await store.update(job.id, progress=JobProgress(10, "MockSampler", 10, 100, None))
    assert saves == 1

    await store.update(job.id, status="in_progress")
    assert saves == 2


async def test_final_job_rejects_every_write(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock)
    job = _job(_uuid(1))
    await store.create(job)

    done = await store.finalize(job.id, "completed", urls=("http://example.test/out",))
    assert done is not None

    updated = await store.update(
        job.id,
        urls=("http://example.test/other",),
        progress=JobProgress(50, "MockSampler", 50, 100, None),
        status="expired",
    )

    assert updated == done
    assert await store.get(job.id) == done


async def test_sweep_saves_only_on_change(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saves = 0
    original = jobs_module.save_jobs

    async def counting_save(path: Path, jobs: object) -> None:
        nonlocal saves
        saves += 1
        await original(path, jobs)  # type: ignore[arg-type]

    monkeypatch.setattr(jobs_module, "save_jobs", counting_save)
    store = _store(tmp_path, clock)
    await store.create(_job(_uuid(1), status="pending"))

    saves = 0
    await store.sweep()
    assert saves == 0

    expiring = _job(
        _uuid(2),
        status="completed",
        expires_at=int(clock.now) - 1,
    )
    await store.create(expiring)
    saves = 0
    await store.sweep()
    assert saves == 1


async def test_sweep_trim_uses_insertion_sequence(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock, max_jobs=2)
    ids = []
    for index in (4, 3, 2, 1):
        job = _job(
            _uuid(index),
            status="completed",
            created_at=CREATED,
            expires_at=int(clock.now) + 3600,
        )
        await store.create(job)
        ids.append(job.id)

    await store.sweep()

    remaining = await store.list()
    assert {job.id for job in remaining} == set(ids[-2:])


async def test_max_pending_is_capped_by_max_jobs(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_save(path: Path, jobs: object) -> None:
        return None

    monkeypatch.setattr(jobs_module, "save_jobs", no_save)
    store = _store(tmp_path, clock, max_jobs=500)
    for index in range(1, 501):
        accepted = await store.create_pending(_job(_uuid(index)), max_pending=600)
        assert accepted is not None

    rejected = await store.create_pending(_job(_uuid(501)), max_pending=600)
    assert rejected is None


async def test_sweep_keeps_non_final_jobs(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock, max_jobs=1)
    running = _job(_uuid(1), status="in_progress")
    done = _job(_uuid(2), status="completed", expires_at=int(clock.now) + 3600)
    await store.create(running)
    await store.create(done)

    await store.sweep()

    remaining = await store.list()
    assert [job.id for job in remaining] == [running.id]


async def test_runtime_keeps_requests_in_memory(tmp_path: Path, clock: FakeClock) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    body = {"model": "wan22-t2v", "prompt": "in-memory"}

    assert runtime.request_for("missing") is None
    runtime.remember_request(_uuid(1), body)
    assert runtime.request_for(_uuid(1)) == body

    runtime.forget_request(_uuid(1))
    assert runtime.request_for(_uuid(1)) is None


@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_request_forgotten_when_job_final(
    tmp_path: Path,
    clock: FakeClock,
    status: JobStatus,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    job = await runtime.store.create(_job(_uuid(1)))
    runtime.remember_request(job.id, {"prompt": "kept"})

    await runtime.store.finalize(job.id, status)

    assert runtime.request_for(job.id) is None


async def test_request_forgotten_when_job_cancelled(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    job = await runtime.store.create(_job(_uuid(1)))
    runtime.remember_request(job.id, {"prompt": "kept"})

    await runtime.store.cancel(job.id)

    assert runtime.request_for(job.id) is None


async def test_request_forgotten_when_job_expired(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    job = _job(_uuid(1), status="completed", expires_at=int(clock.now) + 10)
    await runtime.store.create(job)
    runtime.remember_request(job.id, {"prompt": "kept"})

    clock.advance(11)
    await runtime.sweep_once()

    assert runtime.request_for(job.id) is None


async def test_request_forgotten_when_job_trimmed(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.store = _store(tmp_path, clock, max_jobs=1)
    runtime.store.on_final = runtime.forget_request
    old = _job(_uuid(1), status="completed", expires_at=int(clock.now) + 3600)
    new = _job(_uuid(2), status="completed", expires_at=int(clock.now) + 3600)
    await runtime.store.create(old)
    await runtime.store.create(new)
    runtime.remember_request(old.id, {"prompt": "old"})
    runtime.remember_request(new.id, {"prompt": "new"})

    await runtime.sweep_once()

    assert runtime.request_for(old.id) is None
    assert runtime.request_for(new.id) == {"prompt": "new"}


async def test_sweep_once_removes_expired_job_files(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    job = _job(_uuid(1), status="completed", expires_at=int(clock.now) + 10)
    await runtime.store.create(job)

    shared = runtime.input_root / "uploads" / "keep.png"
    shared.parent.mkdir(parents=True)
    shared.write_bytes(b"keep")
    for root in (runtime.input_root, runtime.result_root):
        folder = root / job.id
        folder.mkdir(parents=True)
        (folder / "0.bin").write_bytes(b"x")

    clock.advance(11)
    await runtime.sweep_once()

    assert not (runtime.input_root / job.id).exists()
    assert not (runtime.result_root / job.id).exists()
    assert shared.read_bytes() == b"keep"


async def test_sweep_once_removes_trimmed_job_files(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.store = _store(tmp_path, clock, max_jobs=1)
    runtime.store.on_final = runtime.forget_request
    runtime.input_root = tmp_path / "input"
    runtime.result_root = tmp_path / "temp"
    old = _job(_uuid(1), status="completed", expires_at=int(clock.now) + 3600)
    new = _job(_uuid(2), status="completed", expires_at=int(clock.now) + 3600)
    for job in (old, new):
        await runtime.store.create(job)
        (runtime.input_root / job.id).mkdir(parents=True)
        (runtime.result_root / job.id).mkdir(parents=True)

    await runtime.sweep_once()

    assert not (runtime.input_root / old.id).exists()
    assert not (runtime.result_root / old.id).exists()
    assert (runtime.input_root / new.id).exists()
    assert (runtime.result_root / new.id).exists()


async def test_large_data_url_stays_out_of_jobs_file(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.timings = MockTimings(
        complete_sec=99.0,
        fail_sec=99.0,
        slow_sec=99.0,
        pending_sec=99.0,
        tick_sec=1.0,
    )
    data_url = "data:image/png;base64," + "A" * (5 * 1024 * 1024)
    body = {
        "model": "sdxl-image",
        "prompt": "big",
        "input_references": [{"kind": "image", "slot": 1, "url": data_url}],
    }

    try:
        job = await create_job(
            runtime,
            kind="image",
            model="sdxl-image",
            prompt="big",
            seed=1,
            count=1,
            base_url="http://127.0.0.1:8188",
            request=body,
        )
        assert runtime.request_for(job.id) == body

        path = tmp_path / "jobs.json"
        size = path.stat().st_size
        assert size < 100 * 1024, f"jobs.json grew to {size} bytes"
        assert "base64" not in path.read_text(encoding="utf-8")
    finally:
        for task in list(runtime.tasks):
            task.cancel()
        await asyncio.gather(*runtime.tasks, return_exceptions=True)


async def test_request_is_stored_before_create_pending(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.is_mock = False
    seen: list[object] = []
    original = runtime.store.create_pending

    async def create_pending(job: Job, max_pending: int) -> Job | None:
        seen.append(runtime.request_for(job.id))
        return await original(job, max_pending)

    monkeypatch.setattr(runtime.store, "create_pending", create_pending)
    body = {"model": "sdxl-image", "prompt": "stored first"}

    job = await create_job(
        runtime,
        kind="image",
        model="sdxl-image",
        prompt="stored first",
        seed=1,
        count=1,
        base_url="http://127.0.0.1:8188",
        request=body,
    )

    assert seen == [body]
    assert runtime.request_for(job.id) == body


async def test_queue_full_leaves_no_request(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock, config=Config(max_pending=1))
    runtime.is_mock = False
    first = await create_job(
        runtime,
        kind="image",
        model="sdxl-image",
        prompt="one",
        seed=1,
        count=1,
        base_url="http://127.0.0.1:8188",
        request={"model": "sdxl-image", "prompt": "one"},
    )
    attempted: list[str] = []
    original = runtime.store.create_pending

    async def create_pending(job: Job, max_pending: int) -> Job | None:
        attempted.append(job.id)
        return await original(job, max_pending)

    monkeypatch.setattr(runtime.store, "create_pending", create_pending)
    with pytest.raises(ProtocolError) as raised:
        await create_job(
            runtime,
            kind="image",
            model="sdxl-image",
            prompt="two",
            seed=1,
            count=1,
            base_url="http://127.0.0.1:8188",
            request={"model": "sdxl-image", "prompt": "two"},
        )

    assert raised.value.code == "queue_full"
    assert attempted
    assert runtime.request_for(attempted[0]) is None
    assert runtime.request_for(first.id) is not None


async def test_sequence_survives_reload(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock)
    await store.create(_job(_uuid(1), status="completed", expires_at=int(clock.now) + 3600))
    await store.create(_job(_uuid(2), status="completed", expires_at=int(clock.now) + 3600))

    reloaded = _store(tmp_path, clock)
    await reloaded.load()
    created = await reloaded.create(
        _job(_uuid(3), status="completed", expires_at=int(clock.now) + 3600)
    )

    assert created.sequence == 3


async def test_driver_error_finalizes_failed(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    job = _job(_uuid(1))
    await runtime.store.create(job)

    def boom(*_: object) -> None:
        raise RuntimeError("driver exploded")

    monkeypatch.setattr(runtime_module, "mock_state", boom)
    with caplog.at_level(logging.ERROR):
        await runtime._run_mock_job(job, "plain", clock(), 1)

    stored = await runtime.store.get(job.id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error == "driver exploded"
    assert job.id in caplog.text


async def test_sweep_loop_survives_exception(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    calls = 0
    done = asyncio.Event()

    async def flaky_sweep() -> SweepResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("sweep exploded")
        if calls >= 2:
            done.set()
        return SweepResult()

    monkeypatch.setattr(runtime.store, "sweep", flaky_sweep)
    monkeypatch.setattr(runtime_module, "SWEEP_INTERVAL_SEC", 0.0)
    task = asyncio.create_task(runtime.sweep_loop())
    await asyncio.wait_for(done.wait(), 1.0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert calls >= 2


async def test_mock_pending_keeps_queue_position(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.timings = MockTimings(
        complete_sec=20.0,
        fail_sec=20.0,
        slow_sec=20.0,
        pending_sec=10.0,
        tick_sec=0.01,
    )
    job = _job(_uuid(1), queue_position=2)
    await runtime.store.create(job)

    task = asyncio.create_task(runtime._run_mock_job(job, "plain", clock(), 1))
    await asyncio.sleep(0.03)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    stored = await runtime.store.get(job.id)
    assert stored is not None
    assert stored.status == "pending"
    assert stored.progress is not None
    assert stored.progress.queue_position == 2


async def test_get_does_not_wait_for_disk_write(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_save(path: Path, jobs: object) -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(jobs_module, "save_jobs", slow_save)
    store = _store(tmp_path, clock)
    job = _job(_uuid(1))

    creating = asyncio.create_task(store.create(job))
    await asyncio.wait_for(started.wait(), 1.0)

    fetched = await asyncio.wait_for(store.get(job.id), 0.2)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.sequence == 1

    release.set()
    created = await asyncio.wait_for(creating, 1.0)
    assert created.id == job.id
    assert created.sequence == 1


async def test_stale_snapshot_does_not_overwrite_newer(
    tmp_path: Path,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[tuple[str, ...]] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def ordered_save(path: Path, jobs: object) -> None:
        snapshot = tuple(job.id for job in jobs)  # type: ignore[union-attr]
        writes.append(snapshot)
        if len(writes) == 1:
            first_started.set()
            await release_first.wait()

    monkeypatch.setattr(jobs_module, "save_jobs", ordered_save)
    store = _store(tmp_path, clock)
    first = _job(_uuid(1))
    second = _job(_uuid(2))

    task = asyncio.create_task(store.create(first))
    await asyncio.wait_for(first_started.wait(), 1.0)
    second_task = asyncio.create_task(store.create(second))
    await asyncio.sleep(0.01)
    release_first.set()
    await task
    await second_task

    assert writes[-1] == (first.id, second.id)


async def test_cancel_pending_is_idempotent(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock)
    job = _job(_uuid(1))
    await store.create(job)

    cancelled = await store.cancel(job.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None
    assert cancelled.expires_at is not None

    again = await store.cancel(job.id)
    assert again == cancelled


async def test_remove_deletes_record_and_notifies(tmp_path: Path, clock: FakeClock) -> None:
    store = _store(tmp_path, clock)
    job = _job(_uuid(1))
    await store.create(job)
    notified: list[str] = []
    store.on_final = notified.append

    removed = await store.remove(job.id)
    assert removed is not None
    assert removed.id == job.id
    assert await store.get(job.id) is None
    assert notified == [job.id]
    assert await store.remove(job.id) is None
    assert await store.remove("not-an-id") is None

    reloaded = _store(tmp_path, clock)
    await reloaded.load()
    assert await reloaded.get(job.id) is None


def test_mock_timeline_defaults() -> None:
    timings = MockTimings()

    assert mock_state(0.0, "plain", timings).status == "pending"
    assert mock_state(1.0, "plain", timings).status == "in_progress"
    assert mock_state(6.1, "plain", timings).status == "completed"
    assert mock_state(timings.complete_sec + 0.1, "plain", timings).status == "completed"

    failed = mock_state(3.1, "[fail]", timings)
    assert failed.status == "failed"
    assert failed.error == "MockSampler: simulated failure"

    assert mock_state(10.0, "[slow]", timings).status == "in_progress"
    assert mock_state(60.1, "[slow]", timings).status == "completed"


def test_mock_percent_rises() -> None:
    timings = MockTimings()
    early = mock_state(1.0, "plain", timings)
    later = mock_state(3.0, "plain", timings)

    assert early.status == "in_progress"
    assert later.status == "in_progress"
    assert early.percent < later.percent


async def test_store_percent_is_monotonic_until_completed(
    tmp_path: Path,
    clock: FakeClock,
) -> None:
    runtime = make_runtime(tmp_path, clock=clock)
    runtime.timings = MockTimings(
        complete_sec=0.08,
        fail_sec=0.08,
        slow_sec=0.2,
        pending_sec=0.01,
        tick_sec=0.005,
    )
    job = await runtime.store.create(_job(_uuid(1)))
    task = asyncio.create_task(runtime._run_mock_job(job, "plain", clock(), 1))
    percents: list[int] = []
    current = job
    try:
        for _ in range(200):
            clock.advance(0.01)
            await asyncio.sleep(0.002)
            stored = await runtime.store.get(job.id)
            assert stored is not None
            current = stored
            if stored.progress is not None:
                percent = stored.progress.percent
                percents.append(percent)
                if percent == 100:
                    assert stored.status == "completed"
            if stored.status in ("completed", "failed", "cancelled", "expired"):
                break
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert percents == sorted(percents)
    assert percents[-1] == 100
    assert current.status == "completed"


async def test_jobs_save_uses_replace_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []
    original = jobs_file_module.replace_file

    def fake(source: Path, target: Path) -> None:
        calls.append((Path(source), Path(target)))
        original(source, target)

    monkeypatch.setattr(jobs_file_module, "replace_file", fake)
    path = tmp_path / "jobs.json"

    await jobs_file_module.save_jobs(path, ())

    assert len(calls) == 1
    assert calls[0][1] == path
    assert list(tmp_path.glob(".jobs-*")) == []


async def test_jobs_quarantine_uses_replace_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, Path]] = []
    original = jobs_file_module.replace_file

    def fake(source: Path, target: Path) -> None:
        calls.append((Path(source), Path(target)))
        original(source, target)

    monkeypatch.setattr(jobs_file_module, "replace_file", fake)
    path = tmp_path / "jobs.json"
    path.write_text("{not json", encoding="utf-8")

    await jobs_file_module.load_jobs(path, clock=lambda: 123.0, ttl_seconds=3600)

    assert any(target.name == "jobs.json.corrupt-123" for _, target in calls)
    assert list(tmp_path.glob(".jobs-*")) == []
