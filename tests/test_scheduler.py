"""Scheduler tests: FIFO order, limits, foreign jobs, waiting state, cancel."""

import asyncio
import uuid
from collections.abc import Iterable
from pathlib import Path

from upai_provider.jobs import JobStore
from upai_provider.protocol import Job, JobProgress, JobStatus
from upai_provider.scheduler import Scheduler

CREATED = "2026-01-01T00:00:00Z"


def _uuid(index: int) -> str:
    return str(uuid.UUID(int=index, version=4))


def _job(job_id: str, *, status: JobStatus = "pending") -> Job:
    return Job(
        id=job_id,
        kind="video",
        model="wan22-t2v",
        status=status,
        progress=JobProgress(0, None, 0, 0, 0),
        seed=1,
        urls=None,
        error=None,
        usage_cost=0.0,
        created_at=CREATED,
        started_at=None,
        finished_at=None,
        expires_at=None,
    )


def _store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "jobs.json", clock=lambda: 1_800_000_000.0, ttl_seconds=3600)


async def _create(store: JobStore, index: int) -> Job:
    job = await store.create_pending(_job(_uuid(index)), 10)
    assert job is not None
    return job


class FakeActive:
    """Return queued ComfyUI prompt ids, repeating the last response."""

    def __init__(self, responses: Iterable[Iterable[str]] = ()) -> None:
        self.responses = [set(item) for item in responses] or [set()]
        self.calls = 0

    async def __call__(self) -> set[str]:
        self.calls += 1
        index = min(self.calls - 1, len(self.responses) - 1)
        return set(self.responses[index])


class RecordingDispatch:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, job_id: str) -> None:
        self.calls.append(job_id)


class FakeTracker:
    def __init__(self) -> None:
        self.ids: dict[str, tuple[str, ...]] = {}
        self.running: set[str] = set()
        self.cancelling: set[str] = set()

    def child_prompt_ids(self, job_id: str) -> tuple[str, ...]:
        return self.ids.get(job_id, ())

    def is_running(self, prompt_id: str) -> bool:
        return prompt_id in self.running

    def mark_cancelling(self, prompt_id: str) -> None:
        self.cancelling.add(prompt_id)


class RecordingCancel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    async def __call__(self, prompt_id: str, is_running: bool) -> None:
        self.calls.append((prompt_id, is_running))


def _scheduler(
    store: JobStore,
    active: FakeActive,
    dispatch: RecordingDispatch,
    *,
    max_running: int = 1,
    tracker: FakeTracker | None = None,
    cancel_prompt: RecordingCancel | None = None,
) -> Scheduler:
    return Scheduler(
        store,
        max_running=max_running,
        fetch_active_jobs=active,
        dispatch=dispatch,
        tracker=tracker,
        cancel_prompt=cancel_prompt,
    )


async def test_second_job_waits_for_max_running(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = await _create(store, 1)
    second = await _create(store, 2)
    active = FakeActive()
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch, max_running=1)
    await scheduler.start()

    await scheduler.tick()
    assert dispatch.calls == [first.id]

    await scheduler.tick()
    assert dispatch.calls == [first.id]
    waiting = await store.get(second.id)
    assert waiting is not None
    assert waiting.progress is not None
    assert waiting.progress.waiting_on == "pack_queue"
    assert waiting.progress.queue_position == 1

    await store.finalize(first.id, "completed", urls=())
    await scheduler.tick()
    assert dispatch.calls == [first.id, second.id]


async def test_fifo_order(tmp_path: Path) -> None:
    store = _store(tmp_path)
    jobs = [await _create(store, index) for index in (1, 2, 3)]
    active = FakeActive()
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch, max_running=3)
    await scheduler.start()

    await scheduler.tick()

    assert dispatch.calls == [job.id for job in jobs]


async def test_foreign_job_blocks_dispatch(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = await _create(store, 1)
    active = FakeActive([{"foreign"}])
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch)
    await scheduler.start()

    await scheduler.tick()
    assert dispatch.calls == []
    waiting = await store.get(job.id)
    assert waiting is not None
    assert waiting.progress is not None
    assert waiting.progress.waiting_on == "comfyui_busy"
    assert waiting.progress.queue_position == 1

    active.responses = [set()]
    await scheduler.tick()
    assert dispatch.calls == [job.id]


async def test_runs_child_prompts_are_not_foreign(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runs = await _create(store, 1)
    single = await _create(store, 2)
    third = await _create(store, 3)
    child_one = _uuid(11)
    child_two = _uuid(12)
    tracker = FakeTracker()
    tracker.ids[runs.id] = (child_one, child_two)
    await store.update(runs.id, status="in_progress")
    active = FakeActive([{child_one, child_two}])
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch, max_running=2, tracker=tracker)
    await scheduler.start()

    await scheduler.tick()

    assert dispatch.calls == [single.id]
    waiting = await store.get(third.id)
    assert waiting is not None
    assert waiting.progress is not None
    assert waiting.progress.waiting_on == "pack_queue"


async def test_real_foreign_prompt_still_blocks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runs = await _create(store, 1)
    single = await _create(store, 2)
    child_one = _uuid(11)
    tracker = FakeTracker()
    tracker.ids[runs.id] = (child_one,)
    await store.update(runs.id, status="in_progress")
    active = FakeActive([{child_one, "foreign"}])
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch, max_running=2, tracker=tracker)
    await scheduler.start()

    await scheduler.tick()

    assert dispatch.calls == []
    waiting = await store.get(single.id)
    assert waiting is not None
    assert waiting.progress is not None
    assert waiting.progress.waiting_on == "comfyui_busy"


async def test_without_tracker_child_prompts_stay_foreign(tmp_path: Path) -> None:
    store = _store(tmp_path)
    runs = await _create(store, 1)
    single = await _create(store, 2)
    child_one = _uuid(11)
    await store.update(runs.id, status="in_progress")
    active = FakeActive([{child_one}])
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch, max_running=2)
    await scheduler.start()

    await scheduler.tick()

    assert dispatch.calls == []
    waiting = await store.get(single.id)
    assert waiting is not None
    assert waiting.progress is not None
    assert waiting.progress.waiting_on == "comfyui_busy"


async def test_fetches_comfy_queue_before_each_dispatch(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = await _create(store, 1)
    active = FakeActive([set(), {"foreign"}])
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch)
    await scheduler.start()

    await scheduler.tick()

    assert active.calls == 2
    assert dispatch.calls == [job.id]


async def test_second_job_waits_when_refetch_sees_foreign_prompt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = await _create(store, 1)
    second = await _create(store, 2)
    active = FakeActive([set(), {"foreign"}])

    async def dispatch(job_id: str) -> None:
        await store.update(job_id, status="in_progress")

    scheduler = Scheduler(
        store,
        max_running=2,
        fetch_active_jobs=active,
        dispatch=dispatch,
    )
    await scheduler.start()

    await scheduler.tick()

    assert active.calls == 2
    waiting = await store.get(second.id)
    assert waiting is not None
    assert waiting.status == "pending"
    assert waiting.progress is not None
    assert waiting.progress.waiting_on == "comfyui_busy"
    started = await store.get(first.id)
    assert started is not None
    assert started.status == "in_progress"


async def test_queue_position_counts_running_and_foreign_jobs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = await _create(store, 1)
    second = await _create(store, 2)
    active = FakeActive([set()])
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch, max_running=1)
    await scheduler.start()
    await scheduler.tick()
    assert dispatch.calls == [first.id]

    active.responses.append({"foreign"})
    await scheduler.tick()

    waiting = await store.get(second.id)
    assert waiting is not None
    assert waiting.progress is not None
    assert waiting.progress.waiting_on == "comfyui_busy"
    assert waiting.progress.queue_position == 2


async def test_cancel_waiting_job_never_dispatches(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = await _create(store, 1)
    second = await _create(store, 2)
    active = FakeActive()
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch, max_running=1)
    await scheduler.start()
    await scheduler.tick()
    assert dispatch.calls == [first.id]

    cancelled = await scheduler.cancel(second.id)

    assert dispatch.calls == [first.id]
    assert cancelled is not None
    assert cancelled.id == second.id
    assert cancelled.status == "cancelled"


async def test_cancel_pending_job_before_first_dispatch(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = await _create(store, 1)
    active = FakeActive()
    dispatch = RecordingDispatch()
    cancel = RecordingCancel()
    scheduler = _scheduler(
        store,
        active,
        dispatch,
        tracker=FakeTracker(),
        cancel_prompt=cancel,
    )
    await scheduler.start()

    cancelled = await scheduler.cancel(job.id)
    await scheduler.tick()

    assert dispatch.calls == []
    assert cancel.calls == []
    assert cancelled is not None
    assert cancelled.status == "cancelled"


async def test_restarted_store_fails_pending_jobs_instead_of_dispatching(
    tmp_path: Path,
) -> None:
    path = tmp_path / "jobs.json"
    first_store = JobStore(path, clock=lambda: 1.0, ttl_seconds=3600)
    job = await _create(first_store, 1)

    store = JobStore(path, clock=lambda: 2.0, ttl_seconds=3600)
    await store.load()
    active = FakeActive()
    dispatch = RecordingDispatch()
    scheduler = _scheduler(store, active, dispatch)
    await scheduler.start()
    await scheduler.tick()

    assert dispatch.calls == []
    repaired = await store.get(job.id)
    assert repaired is not None
    assert repaired.status == "failed"
    assert repaired.error == "ComfyUI restarted"


async def test_cancel_dispatched_queue_keeps_slot_until_tracker_releases(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    first = await _create(store, 1)
    second = await _create(store, 2)
    active = FakeActive()
    dispatch = RecordingDispatch()
    tracker = FakeTracker()
    cancel = RecordingCancel()
    scheduler = _scheduler(
        store,
        active,
        dispatch,
        tracker=tracker,
        cancel_prompt=cancel,
    )
    await scheduler.start()
    await scheduler.tick()
    assert dispatch.calls == [first.id]
    tracker.ids[first.id] = (first.id,)

    cancelled = await scheduler.cancel(first.id)

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancel.calls == [(first.id, False)]

    await scheduler.tick()
    assert dispatch.calls == [first.id]

    tracker.ids.pop(first.id)
    await scheduler.tick()
    assert dispatch.calls == [first.id, second.id]


async def test_cancel_running_uses_targeted_interrupt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = await _create(store, 1)
    active = FakeActive()
    dispatch = RecordingDispatch()
    tracker = FakeTracker()
    cancel = RecordingCancel()
    scheduler = _scheduler(
        store,
        active,
        dispatch,
        tracker=tracker,
        cancel_prompt=cancel,
    )
    await scheduler.start()
    await scheduler.tick()
    tracker.ids[job.id] = (job.id,)
    tracker.running.add(job.id)

    await scheduler.cancel(job.id)

    assert cancel.calls == [(job.id, True)]


async def test_cancel_runs_cancels_every_child_prompt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = await _create(store, 1)
    child_one = _uuid(11)
    child_two = _uuid(12)
    active = FakeActive()
    dispatch = RecordingDispatch()
    tracker = FakeTracker()
    cancel = RecordingCancel()
    scheduler = _scheduler(
        store,
        active,
        dispatch,
        tracker=tracker,
        cancel_prompt=cancel,
    )
    await scheduler.start()
    await scheduler.tick()
    tracker.ids[job.id] = (job.id, child_one, child_two)

    await scheduler.cancel(job.id)

    assert cancel.calls == [(job.id, False), (child_one, False), (child_two, False)]


async def test_enqueue_returns_before_dispatch_finishes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = await _create(store, 1)
    active = FakeActive()
    entered = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def dispatch(job_id: str) -> None:
        calls.append(job_id)
        entered.set()
        await release.wait()

    scheduler = Scheduler(
        store,
        max_running=1,
        fetch_active_jobs=active,
        dispatch=dispatch,
    )
    await scheduler.start()

    await asyncio.wait_for(scheduler.enqueue(job.id), timeout=0.2)
    await asyncio.wait_for(entered.wait(), timeout=1.0)

    assert calls == [job.id]
    assert not release.is_set()

    release.set()
    await asyncio.gather(*scheduler._ticks)


async def test_dispatch_does_not_hold_the_lock(tmp_path: Path) -> None:
    store = _store(tmp_path)
    await _create(store, 1)
    active = FakeActive()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(job_id: str) -> None:
        entered.set()
        await release.wait()

    scheduler = Scheduler(
        store,
        max_running=1,
        fetch_active_jobs=active,
        dispatch=dispatch,
    )
    await scheduler.start()
    task = asyncio.create_task(scheduler.tick())
    await entered.wait()

    assert not scheduler._lock.locked()
    release.set()
    await task


async def test_overlapping_ticks_do_not_dispatch_twice(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = await _create(store, 1)
    active = FakeActive()
    entered = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def dispatch(job_id: str) -> None:
        calls.append(job_id)
        entered.set()
        await release.wait()

    scheduler = Scheduler(
        store,
        max_running=2,
        fetch_active_jobs=active,
        dispatch=dispatch,
    )
    await scheduler.start()
    first = asyncio.create_task(scheduler.tick())
    await entered.wait()
    second = asyncio.create_task(scheduler.tick())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)

    assert calls == [job.id]


async def test_stop_cancels_spawned_ticks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = await _create(store, 1)
    active = FakeActive()
    entered = asyncio.Event()

    async def dispatch(job_id: str) -> None:
        entered.set()
        await asyncio.Event().wait()

    scheduler = Scheduler(
        store,
        max_running=1,
        fetch_active_jobs=active,
        dispatch=dispatch,
    )
    await scheduler.start()
    await scheduler.enqueue(job.id)
    await asyncio.wait_for(entered.wait(), timeout=1.0)
    tick = next(iter(scheduler._ticks))

    await scheduler.stop()

    assert tick.cancelled()
