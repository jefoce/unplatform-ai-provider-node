"""Runtime state shared by routes and the mock driver."""

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

from . import diskutil
from .config import Config
from .constants import DISK_FREE_REFRESH_SEC, SWEEP_INTERVAL_SEC
from .content_urls import content_urls
from .export_registry import ExportRegistry
from .jobs import JobStore
from .materialize_cleanup import cleanup_job_files, orphan_job_ids
from .mock import MockTimings, image_models, mock_state, video_models
from .mock_assets import MockAssets, ensure_mock_assets
from .protocol import FINAL_JOB_STATUSES, Job, JobProgress, Model, ProtocolError
from .protocol.shapes import ModelKind
from .scheduler import Scheduler
from .textutil import one_line
from .timeutil import iso_now
from .tracker import Tracker
from .uploads import UploadStore

logger = logging.getLogger(__name__)


def free_bytes(path: Path) -> int:
    """Read free bytes through the diskutil module, for test injection."""
    return diskutil.free_bytes(path)


def _default_comfy_base_url() -> str:
    return "http://127.0.0.1:8188"


@dataclass
class Runtime:
    """Owns config, store, uploads, mock assets and background tasks."""

    config: Config
    store: JobStore
    uploads: UploadStore
    data_dir: Path
    is_mock: bool
    server_name: str
    server_version: str
    timings: MockTimings
    clock: Callable[[], float]
    tls_enabled: bool = False
    instance_id: str = ""
    assets: MockAssets | None = None
    exports: ExportRegistry | None = None
    input_root: Path | None = None
    result_root: Path | None = None
    comfy_base_url: Callable[[], str] = _default_comfy_base_url
    session: aiohttp.ClientSession | None = None
    fetch_session: aiohttp.ClientSession | None = None
    scheduler: Scheduler | None = None
    tracker: Tracker | None = None
    requests: dict[str, Mapping[str, object]] = field(default_factory=dict)
    tasks: set[asyncio.Task[None]] = field(default_factory=set)
    free_space: Callable[[Path], int] | None = None
    disk_free_bytes: int = 0

    def __post_init__(self) -> None:
        self.store.on_final = self._handle_final
        self.disk_free_bytes = self.refresh_disk_free()

    def refresh_disk_free(self) -> int:
        """Read the tightest pack volume free space once."""
        reader = self.free_space or free_bytes
        upload_root = self.input_root or self.data_dir
        result_root = self.result_root or self.data_dir
        self.disk_free_bytes = min(reader(upload_root), reader(result_root), reader(self.data_dir))
        return self.disk_free_bytes

    async def disk_free_loop(self) -> None:
        """Refresh the cached disk free value off the event loop."""
        while True:
            try:
                await asyncio.to_thread(self.refresh_disk_free)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("disk free refresh failed")
                self.disk_free_bytes = 0
            await asyncio.sleep(DISK_FREE_REFRESH_SEC)

    def _handle_final(self, job_id: str) -> None:
        self.forget_request(job_id)
        self.uploads.release(job_id)

    def pin_uploads(self, job_id: str, refs: tuple[str, ...]) -> None:
        """Pin upload hashes used by a non-final job."""
        for sha256 in refs:
            self.uploads.pin(job_id, sha256)

    def release_uploads(self, job_id: str) -> None:
        """Release every upload pinned by a job."""
        self.uploads.release(job_id)

    def ensure_free_space(self, path: Path | None = None) -> None:
        """Reject new work when the volume has too little free space."""
        minimum = self.config.min_free_disk_bytes
        if minimum <= 0:
            return

        reader = self.free_space or free_bytes
        if reader(self.data_dir if path is None else path) >= minimum:
            return

        raise ProtocolError(
            "insufficient_storage",
            "not enough free disk space",
            status=507,
        )

    def _job_result_bytes(self, job: Job) -> int:
        total = 0
        for name in job.files:
            path = Path(name)
            if not path.is_absolute() and self.result_root is not None:
                path = self.result_root / path
            try:
                total += path.stat().st_size
            except OSError:
                continue

        return total

    def _results_bytes(self, jobs: tuple[Job, ...]) -> int:
        return sum(self._job_result_bytes(job) for job in jobs)

    @staticmethod
    def _is_expired(job: Job, now: int) -> bool:
        if job.status == "expired":
            return True

        return job.expires_at is not None and job.expires_at <= now

    async def enforce_results_quota(self) -> None:
        """Remove expired final results until the quota fits, then reject."""
        quota = self.config.results_quota_bytes
        if quota <= 0:
            return

        jobs = await self.store.list()
        total = await asyncio.to_thread(self._results_bytes, jobs)
        if total <= quota:
            return

        now = int(self.clock())
        expired = sorted(
            (
                job
                for job in jobs
                if job.status in FINAL_JOB_STATUSES and job.files and self._is_expired(job, now)
            ),
            key=lambda job: job.sequence,
        )
        for job in expired:
            if total <= quota:
                break

            total -= await asyncio.to_thread(self._job_result_bytes, job)
            await self.delete_job(job.id)

        if total > quota:
            raise ProtocolError(
                "insufficient_storage",
                "results quota exceeded",
                status=507,
            )

    def remember_request(self, job_id: str, body: Mapping[str, object]) -> None:
        """Keep a request body in memory only."""
        self.requests[job_id] = body

    def request_for(self, job_id: str) -> Mapping[str, object] | None:
        """Return the in-memory request body for a job."""
        return self.requests.get(job_id)

    def forget_request(self, job_id: str) -> None:
        """Drop a request body no longer needed for dispatch."""
        self.requests.pop(job_id, None)

    async def ensure_assets(self) -> None:
        """Generate mock media assets once."""
        if self.assets is None:
            self.assets = await ensure_mock_assets(self.data_dir)

    def catalog(self, kind: ModelKind) -> tuple[Model, ...]:
        """Return the model catalog for a kind."""
        if self.is_mock:
            return video_models() if kind == "video" else image_models()

        if self.exports is not None:
            return self.exports.catalog(kind)

        return ()

    def _content_urls(self, job: Job, count: int) -> tuple[str, ...]:
        return content_urls(job.base_url, job_id=job.id, kind=job.kind, count=count)

    async def _run_mock_job(
        self,
        job: Job,
        prompt: str,
        started: float,
        count: int,
    ) -> None:
        try:
            while True:
                current = await self.store.get(job.id)
                if current is None or current.status in FINAL_JOB_STATUSES:
                    return

                state = mock_state(self.clock() - started, prompt, self.timings)
                if state.status == "failed":
                    await self.store.finalize(
                        job.id,
                        "failed",
                        error=one_line(state.error or "Mock failure"),
                    )
                    return

                if state.status == "completed":
                    await self.store.update(
                        job.id,
                        progress=JobProgress(
                            percent=100,
                            node="MockSampler",
                            value=100,
                            max=100,
                            queue_position=None,
                        ),
                    )
                    await self.store.finalize(
                        job.id,
                        "completed",
                        urls=self._content_urls(job, count),
                    )
                    return

                queue_position = (
                    current.progress.queue_position
                    if state.status == "pending" and current.progress is not None
                    else state.queue_position
                )
                progress = JobProgress(
                    percent=state.percent,
                    node=state.node,
                    value=state.value,
                    max=state.max_value,
                    queue_position=queue_position,
                )
                changes: dict[str, object] = {"status": state.status, "progress": progress}
                if state.status == "in_progress" and current.started_at is None:
                    changes["started_at"] = iso_now(self.clock)

                await self.store.update(job.id, **changes)
                await asyncio.sleep(self.timings.tick_sec)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.exception("mock job %s failed", job.id)
            await self.store.finalize(
                job.id,
                "failed",
                error=one_line(str(exc) or type(exc).__name__),
            )

    async def start_mock_job(self, job: Job, prompt: str, *, count: int = 1) -> None:
        """Drive one mock job to a final state in the background."""
        started = self.clock()
        task = asyncio.create_task(self._run_mock_job(job, prompt, started, count))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _cleanup_job(self, job_id: str, files: tuple[str, ...] = ()) -> None:
        if self.input_root is None and self.result_root is None:
            return

        await asyncio.to_thread(
            cleanup_job_files,
            job_id,
            input_root=self.input_root or self.data_dir,
            result_root=self.result_root or self.data_dir,
            files=files,
        )

    async def delete_job(self, job_id: str) -> bool:
        """Remove a job's files and record. Shared uploads stay untouched."""
        removed = await self.store.remove(job_id)
        if removed is None:
            return False

        await self._cleanup_job(job_id, removed.files)
        return True

    async def sweep_once(self) -> None:
        """Expire jobs, remove their files, then sweep old uploads."""
        result = await self.store.sweep()
        cleanup = set(result.expired) | set(result.removed)

        if self.input_root is not None and self.result_root is not None:
            now = int(self.clock())
            keep = {
                job.id
                for job in await self.store.list()
                if job.status not in FINAL_JOB_STATUSES
                or job.expires_at is None
                or job.expires_at > now
            }
            cleanup.update(
                await asyncio.to_thread(
                    orphan_job_ids,
                    self.input_root,
                    self.result_root,
                    keep_ids=keep,
                )
            )

        for job_id in cleanup:
            current = await self.store.get(job_id)
            if current is not None and (
                current.status not in FINAL_JOB_STATUSES
                or current.expires_at is None
                or current.expires_at > int(self.clock())
            ):
                continue

            await self._cleanup_job(job_id)

        await asyncio.to_thread(
            self.uploads.sweep,
            self.config.result_ttl_hours * 3600.0,
            self.clock(),
        )

    async def sweep_loop(self) -> None:
        """Expire job records and old uploads every sweep interval."""
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_SEC)
            try:
                await self.sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("job sweep failed")
