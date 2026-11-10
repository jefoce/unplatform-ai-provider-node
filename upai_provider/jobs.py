"""Job store: one asyncio lock, atomic JSON persistence and boot repair."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .constants import MAX_JOBS_STORED
from .jobs_file import load_jobs, save_jobs
from .jobs_sweep import JobStoreSweep
from .protocol import (
    FINAL_JOB_STATUSES,
    JOB_ID_PATTERN,
    Job,
    JobProgress,
    JobStatus,
    is_job_status,
)
from .timeutil import iso_now

_MUTABLE_FIELDS = frozenset(
    {
        "status",
        "progress",
        "seed",
        "urls",
        "error",
        "usage_cost",
        "started_at",
        "finished_at",
        "expires_at",
        "files",
    }
)


class JobStore(JobStoreSweep):
    """Frozen job records with one lock around every read-modify-write."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], float],
        ttl_seconds: float,
        max_jobs: int = MAX_JOBS_STORED,
    ) -> None:
        self._path = path
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._max_jobs = max_jobs
        self._jobs: dict[str, Job] = {}
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._version = 0
        self._written_version = 0
        self.on_final: Callable[[str], None] | None = None

    @staticmethod
    def _valid_id(job_id: str) -> bool:
        return bool(JOB_ID_PATTERN.match(job_id))

    @staticmethod
    def _monotonic_progress(job: Job, changes: dict[str, object]) -> dict[str, object]:
        """Keep the stored percent from going backwards. 100 only on completion."""
        progress = changes.get("progress")
        if not isinstance(progress, JobProgress):
            return changes

        percent = progress.percent
        if job.progress is not None:
            percent = max(job.progress.percent, percent)

        status = changes.get("status", job.status)
        if not is_job_status(status) or status not in FINAL_JOB_STATUSES:
            percent = min(99, percent)

        if percent == progress.percent:
            return changes

        return {**changes, "progress": replace(progress, percent=percent)}

    def _notify_final(self, job_id: str) -> None:
        """Tell the owner that a job is final or was dropped."""
        if self.on_final is not None:
            self.on_final(job_id)

    def _next_snapshot_locked(self) -> tuple[int, tuple[Job, ...]]:
        self._version += 1
        return self._version, tuple(self._jobs.values())

    async def _persist(self, version: int, jobs: tuple[Job, ...]) -> None:
        """Write one snapshot without holding the state lock. Older versions lose."""
        async with self._write_lock:
            if version <= self._written_version:
                return

            await save_jobs(self._path, jobs)
            self._written_version = version

    async def load(self) -> None:
        """Load stored jobs, repair boot state, then persist once."""
        async with self._lock:
            self._jobs = await load_jobs(
                self._path, clock=self._clock, ttl_seconds=self._ttl_seconds
            )
            self._sequence = max((job.sequence for job in self._jobs.values()), default=0)
            self._version = 1
            self._written_version = 1

    async def create(self, job: Job) -> Job:
        """Insert a job. Raises on an invalid id."""
        if not self._valid_id(job.id):
            raise ValueError("job id must be a lowercase UUID4")

        async with self._lock:
            self._sequence += 1
            job = replace(job, sequence=self._sequence)
            self._jobs[job.id] = job
            version, snapshot = self._next_snapshot_locked()

        await self._persist(version, snapshot)
        return job

    async def create_pending(self, job: Job, max_pending: int) -> Job | None:
        """Insert a pending job when the non-final queue has room."""
        async with self._lock:
            if not self._valid_id(job.id):
                raise ValueError("job id must be a lowercase UUID4")

            non_final = sum(
                1 for item in self._jobs.values() if item.status not in FINAL_JOB_STATUSES
            )
            limit = min(max_pending, self._max_jobs)
            if non_final >= limit:
                return None

            self._sequence += 1
            job = replace(job, sequence=self._sequence)
            pending = sum(1 for item in self._jobs.values() if item.status == "pending")
            if job.progress is not None:
                job = replace(job, progress=replace(job.progress, queue_position=pending))

            self._jobs[job.id] = job
            version, snapshot = self._next_snapshot_locked()

        await self._persist(version, snapshot)
        return job

    async def get(self, job_id: str) -> Job | None:
        """Return one job, or None for an unknown or invalid id."""
        if not self._valid_id(job_id):
            return None

        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: str, **changes: object) -> Job | None:
        """Replace allowed job fields, or return None when unknown."""
        if not self._valid_id(job_id):
            return None

        unknown = set(changes) - _MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"job fields not writable: {', '.join(sorted(unknown))}")

        status = changes.get("status")
        if status is not None and not is_job_status(status):
            raise ValueError("status is not a known job status")

        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if job.status in FINAL_JOB_STATUSES:
                return job

            changes = self._monotonic_progress(job, changes)
            updated = replace(job, **changes)
            self._jobs[job_id] = updated
            if replace(job, progress=updated.progress) == updated:
                return updated

            version, snapshot = self._next_snapshot_locked()

        await self._persist(version, snapshot)
        return updated

    async def list(self) -> tuple[Job, ...]:
        """Return all stored jobs in insertion order."""
        async with self._lock:
            return tuple(self._jobs.values())

    def _finalize(
        self,
        job: Job,
        status: JobStatus,
        *,
        error: str | None,
        urls: tuple[str, ...] | None,
    ) -> Job:
        now = self._clock()
        progress = job.progress
        if progress is not None:
            percent = 100 if status == "completed" else progress.percent
            progress = replace(
                progress,
                percent=percent,
                queue_position=None,
                waiting_on=None,
            )
        elif status == "completed":
            progress = JobProgress(100, None, None, None, None)

        return replace(
            job,
            status=status,
            progress=progress,
            error=error,
            urls=urls,
            finished_at=iso_now(lambda: now),
            expires_at=int(now + self._ttl_seconds),
        )

    async def finalize(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        urls: tuple[str, ...] | None = None,
    ) -> Job | None:
        """Move a job to a final state and set its expiry."""
        if not self._valid_id(job_id):
            return None

        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if job.status in FINAL_JOB_STATUSES:
                return job

            updated = self._finalize(job, status, error=error, urls=urls)
            self._jobs[job_id] = updated
            version, snapshot = self._next_snapshot_locked()

        await self._persist(version, snapshot)
        self._notify_final(job_id)
        return updated

    async def remove(self, job_id: str) -> Job | None:
        """Delete one job record, persist the snapshot and notify the owner."""
        if not self._valid_id(job_id):
            return None

        async with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is None:
                return None

            version, snapshot = self._next_snapshot_locked()

        await self._persist(version, snapshot)
        self._notify_final(job_id)
        return job

    async def cancel(self, job_id: str) -> Job | None:
        """Cancel a pending or running job. Final jobs are unchanged."""
        if not self._valid_id(job_id):
            return None

        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            if job.status in FINAL_JOB_STATUSES:
                return job

            updated = self._finalize(job, "cancelled", error=None, urls=None)
            self._jobs[job_id] = updated
            version, snapshot = self._next_snapshot_locked()

        await self._persist(version, snapshot)
        self._notify_final(job_id)
        return updated
