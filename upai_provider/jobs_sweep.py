"""Expire and trim stored jobs."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace

from .protocol import FINAL_JOB_STATUSES, Job


@dataclass(frozen=True)
class SweepResult:
    """Job ids changed by one sweep."""

    expired: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


class JobStoreSweep:
    """Expire old final jobs and trim final jobs beyond max_jobs."""

    _clock: Callable[[], float]
    _jobs: dict[str, Job]
    _max_jobs: int
    _lock: asyncio.Lock

    def _next_snapshot_locked(self) -> tuple[int, tuple[Job, ...]]:
        raise NotImplementedError

    async def _persist(self, version: int, jobs: tuple[Job, ...]) -> None:
        raise NotImplementedError

    def _notify_final(self, job_id: str) -> None:
        raise NotImplementedError

    async def sweep(self, now: float | None = None) -> SweepResult:
        """Expire old final jobs and trim final jobs beyond max_jobs."""
        async with self._lock:
            current = int(self._clock() if now is None else now)
            changed = False
            expired: list[str] = []
            removed: tuple[str, ...] = ()
            for job_id, job in list(self._jobs.items()):
                if job.status == "expired":
                    continue
                if job.status not in FINAL_JOB_STATUSES:
                    continue
                if job.expires_at is not None and job.expires_at <= current:
                    self._jobs[job_id] = replace(job, status="expired")
                    expired.append(job_id)
                    changed = True

            if len(self._jobs) > self._max_jobs:
                non_final = [
                    job for job in self._jobs.values() if job.status not in FINAL_JOB_STATUSES
                ]
                budget = max(0, self._max_jobs - len(non_final))
                final = sorted(
                    (job for job in self._jobs.values() if job.status in FINAL_JOB_STATUSES),
                    key=lambda job: job.sequence,
                    reverse=True,
                )
                keep = {job.id for job in non_final} | {job.id for job in final[:budget]}
                if len(keep) < len(self._jobs):
                    removed = tuple(job_id for job_id in self._jobs if job_id not in keep)
                    self._jobs = {
                        job_id: job for job_id, job in self._jobs.items() if job_id in keep
                    }
                    changed = True

            result = SweepResult(expired=tuple(expired), removed=removed)
            if not changed:
                return result

            version, snapshot = self._next_snapshot_locked()

        await self._persist(version, snapshot)
        for job_id in result.expired:
            self._notify_final(job_id)
        for job_id in result.removed:
            self._notify_final(job_id)
        return result
