"""Types shared by the execution modules."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .protocol import Job, JobStatus


@dataclass(frozen=True)
class ExecutionOutcome:
    """What dispatch did, for the caller that still owns an HTTP response."""

    is_submitted: bool
    prompt_ids: tuple[str, ...] = ()
    node_errors: Mapping[str, object] | None = None
    error: str | None = None


class _JobStore(Protocol):
    async def get(self, job_id: str) -> Job | None: ...

    async def finalize(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        urls: tuple[str, ...] | None = None,
    ) -> Job | None: ...


class _Tracker(Protocol):
    def track(
        self,
        prompt_id: str,
        *,
        job_id: str,
        prompt: Mapping[str, object],
        output_node: str,
        count: int = 1,
    ) -> None: ...

    def untrack(self, prompt_id: str) -> None: ...
