"""FIFO scheduler for pack jobs. Stdlib only, no ComfyUI imports."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import replace
from typing import Protocol

from .jobs import JobStore
from .protocol import FINAL_JOB_STATUSES, Job, JobProgress

logger = logging.getLogger(__name__)

FetchActiveJobs = Callable[[], Awaitable[Iterable[str]]]
Dispatch = Callable[[str], Awaitable[None]]
CancelPrompt = Callable[[str, bool], Awaitable[None]]


class _Tracker(Protocol):
    def child_prompt_ids(self, job_id: str) -> tuple[str, ...]: ...

    def is_running(self, prompt_id: str) -> bool: ...

    def mark_cancelling(self, prompt_id: str) -> None: ...


class Scheduler:
    """Dispatch pack jobs within the running and foreign-queue limits."""

    def __init__(
        self,
        store: JobStore,
        *,
        max_running: int,
        fetch_active_jobs: FetchActiveJobs,
        dispatch: Dispatch,
        tracker: _Tracker | None = None,
        cancel_prompt: CancelPrompt | None = None,
    ) -> None:
        self._store = store
        self._max_running = max_running
        self._fetch_active_jobs = fetch_active_jobs
        self._dispatch = dispatch
        self._tracker = tracker
        self._cancel_prompt = cancel_prompt
        self._running: set[str] = set()
        self._started = False
        self._lock = asyncio.Lock()
        self._ticks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Allow ticks to dispatch."""
        self._started = True

    async def stop(self) -> None:
        """Stop dispatching. Jobs already submitted keep running."""
        self._started = False
        ticks = list(self._ticks)
        for task in ticks:
            task.cancel()
        if ticks:
            await asyncio.gather(*ticks, return_exceptions=True)

    async def enqueue(self, job_id: str) -> None:
        """Wake the scheduler after a job enters the store."""
        task = asyncio.create_task(self.tick())
        self._ticks.add(task)
        task.add_done_callback(self._ticks.discard)

    async def cancel(self, job_id: str) -> Job | None:
        """Cancel a job. A dispatched prompt is cancelled in ComfyUI, slot held."""
        async with self._lock:
            job = await self._store.get(job_id)
            if job is None or job.status in FINAL_JOB_STATUSES:
                return job

            is_dispatched = job_id in self._running
            prompt_ids = self._prompt_ids(job_id) if is_dispatched else ()

        if not is_dispatched:
            cancelled = await self._store.cancel(job_id)
            await self.tick()
            return cancelled

        if self._cancel_prompt is None:
            logger.warning("cancel prompt is not wired, job %s keeps its slot", job_id)
        else:
            for prompt_id in prompt_ids:
                self._mark_cancelling(prompt_id)
                try:
                    await self._cancel_prompt(prompt_id, self._is_running(prompt_id))
                except Exception:
                    logger.exception("cancel failed for prompt %s", prompt_id)

        cancelled = await self._store.cancel(job_id)
        await self.tick()
        return cancelled

    async def tick(self) -> None:
        """Dispatch as many waiting jobs as the limits allow."""
        if not self._started:
            return

        while True:
            active = set(await self._fetch_active_jobs())
            async with self._lock:
                if not self._started:
                    return

                job = await self._prepare_next(active)
                if job is None:
                    return

            current = await self._store.get(job.id)
            if current is None or current.status != "pending":
                async with self._lock:
                    self._running.discard(job.id)
                continue

            try:
                await self._dispatch(job.id)
            except Exception:
                logger.exception("dispatch failed for job %s", job.id)
                async with self._lock:
                    self._running.discard(job.id)
                return

    async def _prepare_next(self, active: set[str]) -> Job | None:
        """Pick one candidate and mark it running. Caller holds the lock."""
        jobs = list(await self._store.list())
        by_id = {job.id: job for job in jobs}
        self._running = {
            job_id for job_id in self._running if not self._is_released(job_id, by_id.get(job_id))
        }
        self._running.update(job.id for job in jobs if job.status == "in_progress")

        pending = sorted(
            (job for job in jobs if job.status == "pending" and job.id not in self._running),
            key=lambda job: job.sequence,
        )
        if not pending:
            return None

        known = set(by_id)
        if self._tracker is not None:
            for job in jobs:
                known.update(self._tracker.child_prompt_ids(job.id))

        foreign_count = len(active - known)
        await self._set_waiting(jobs, pending, foreign_count)
        if foreign_count or len(self._running) >= self._max_running:
            return None

        job = pending[0]
        self._running.add(job.id)
        await self._clear_waiting(job)
        return job

    def _is_released(self, job_id: str, job: Job | None) -> bool:
        if job is None:
            return True
        if job.status not in FINAL_JOB_STATUSES:
            return False
        if self._tracker is None:
            return True

        return not self._tracker.child_prompt_ids(job_id)

    def _prompt_ids(self, job_id: str) -> tuple[str, ...]:
        if self._tracker is None:
            return (job_id,)

        return self._tracker.child_prompt_ids(job_id) or (job_id,)

    def _is_running(self, prompt_id: str) -> bool:
        return self._tracker is not None and self._tracker.is_running(prompt_id)

    def _mark_cancelling(self, prompt_id: str) -> None:
        if self._tracker is not None:
            self._tracker.mark_cancelling(prompt_id)

    async def _set_waiting(
        self,
        jobs: list[Job],
        pending: list[Job],
        foreign_count: int,
    ) -> None:
        non_final = sorted(
            (job for job in jobs if job.status not in FINAL_JOB_STATUSES),
            key=lambda job: job.sequence,
        )
        waiting_on = "comfyui_busy" if foreign_count else "pack_queue"
        for job in pending:
            ahead = sum(1 for other in non_final if other.sequence < job.sequence)
            await self._update_progress(job, ahead + foreign_count, waiting_on)

    async def _update_progress(self, job: Job, position: int, waiting_on: str) -> None:
        progress = job.progress or JobProgress(
            percent=0,
            node=None,
            value=0,
            max=0,
            queue_position=None,
        )
        await self._store.update(
            job.id,
            progress=replace(progress, queue_position=position, waiting_on=waiting_on),
        )

    async def _clear_waiting(self, job: Job) -> None:
        if job.progress is None:
            return

        await self._store.update(
            job.id,
            progress=replace(job.progress, queue_position=None, waiting_on=None),
        )
