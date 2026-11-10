"""Tracker job progress and finalization."""

from .content_urls import content_urls
from .protocol import FINAL_JOB_STATUSES, Job, JobProgress
from .textutil import one_line
from .timeutil import iso_now
from .tracker_state import _Tracked, _TrackerBase


class TrackerMessages(_TrackerBase):
    """Update job progress and finalize tracked prompts."""

    async def _update_progress(
        self,
        tracked: _Tracked,
        *,
        status: str = "in_progress",
    ) -> None:
        job = await self._store.get(tracked.job_id)
        if job is None or job.status in FINAL_JOB_STATUSES:
            return

        if status == "in_progress":
            tracked.started = True

        node, value, maximum = self._job_current_progress(tracked.job_id)
        previous = job.progress
        percent = self._job_percent(tracked.job_id)
        if previous is not None:
            percent = max(previous.percent, percent)
        if status == "in_progress":
            percent = min(99, percent)

        progress = JobProgress(
            percent=percent,
            node=node,
            value=value,
            max=maximum,
            queue_position=None if previous is None else previous.queue_position,
            waiting_on=None,
        )
        changes: dict[str, object] = {"status": status, "progress": progress}
        if status == "in_progress" and job.started_at is None:
            changes["started_at"] = iso_now(self._clock)

        if job.status == status and previous == progress:
            return

        await self._store.update(tracked.job_id, **changes)

    async def _finish_prompt(self, tracked: _Tracked) -> None:
        tracked.is_done = True
        self._job_done[tracked.job_id] = self._job_done.get(tracked.job_id, 0) + 1
        job = await self._store.get(tracked.job_id)
        if job is None or job.status in FINAL_JOB_STATUSES:
            self.untrack(tracked.prompt_id)
            return

        others = [
            item
            for item in self._job_entries(tracked.job_id)
            if item.prompt_id != tracked.prompt_id and not item.is_done
        ]
        if others:
            await self._update_progress(tracked)
            self.untrack(tracked.prompt_id)
            return

        await self._store.finalize(
            tracked.job_id,
            "completed",
            urls=self._content_urls(job, tracked.job_id),
        )
        self.untrack(tracked.prompt_id)

    def _content_urls(self, job: Job, job_id: str) -> tuple[str, ...]:
        count = max(len(job.files), self._job_counts.get(job_id, 0)) or 1

        return content_urls(
            job.base_url or self._server_url,
            job_id=job_id,
            kind=job.kind,
            count=count,
        )

    async def _cancel_siblings(self, tracked: _Tracked) -> None:
        for item in self._job_entries(tracked.job_id):
            if item.prompt_id == tracked.prompt_id or item.is_done or item.is_cancelling:
                continue

            item.is_cancelling = True
            await self.cancel_prompt(item.prompt_id, item.started)

    async def _fail_prompt(self, tracked: _Tracked, message: str) -> None:
        tracked.is_done = True
        job = await self._store.get(tracked.job_id)
        if job is not None and job.status not in FINAL_JOB_STATUSES:
            await self._store.finalize(tracked.job_id, "failed", error=one_line(message))

        await self._cancel_siblings(tracked)
        self.untrack(tracked.prompt_id)

    async def _cancel_prompt(self, tracked: _Tracked) -> None:
        tracked.is_done = True
        job = await self._store.get(tracked.job_id)
        if job is not None and job.status not in FINAL_JOB_STATUSES:
            await self._store.finalize(tracked.job_id, "cancelled")

        await self._cancel_siblings(tracked)
        self.untrack(tracked.prompt_id)
