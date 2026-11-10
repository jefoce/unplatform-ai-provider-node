"""Poll the jobs route while the tracker websocket is down."""

import asyncio
from collections.abc import Mapping
from typing import Protocol, cast

import aiohttp

from .constants import MISSING_POLL_LIMIT
from .textutil import one_line
from .tracker_state import _TrackerBase


class _PollResponse(Protocol):
    status: int

    async def json(self, *, content_type: str | None = None) -> object: ...

    async def __aenter__(self) -> "_PollResponse": ...

    async def __aexit__(self, *args: object) -> None: ...


class _PollGet(Protocol):
    def __call__(self, url: str) -> _PollResponse: ...


class TrackerPoll(_TrackerBase):
    """Read job state over HTTP when the websocket is unavailable."""

    async def poll_once(self, *, only_cancelling: bool = False) -> None:
        """Read status from /api/jobs/{id} for every tracked prompt."""
        get = getattr(self._session, "get", None)
        if not callable(get):
            return

        get = cast(_PollGet, get)
        for tracked in list(self._tracked.values()):
            if tracked.is_done or (only_cancelling and not tracked.is_cancelling):
                continue

            url = f"{self._server_url}/api/jobs/{tracked.prompt_id}"
            try:
                async with get(url) as response:
                    if response.status == 404:
                        if tracked.is_cancelling:
                            await self._cancel_prompt(tracked)
                            continue

                        if not tracked.is_submitted:
                            continue

                        job = await self._store.get(tracked.job_id)
                        if (
                            job is not None
                            and job.files
                            and len(job.files) >= self._job_counts.get(tracked.job_id, 0)
                            and len(self._job_entries(tracked.job_id)) == 1
                        ):
                            await self._finish_prompt(tracked)
                            continue

                        tracked.missing_polls += 1
                        if tracked.missing_polls >= MISSING_POLL_LIMIT:
                            await self._fail_prompt(tracked, "prompt lost by ComfyUI")
                        continue

                    if response.status == 200:
                        tracked.missing_polls = 0

                    try:
                        body = await response.json(content_type=None)
                    except (ValueError, TypeError):
                        continue

                    if not isinstance(body, Mapping):
                        continue

                    status = body.get("status")
                    if status == "completed":
                        await self._finish_prompt(tracked)
                    elif status == "failed":
                        error = body.get("execution_error")
                        message = "workflow execution failed"
                        if isinstance(error, Mapping):
                            text = error.get("exception_message") or error.get("message")
                            if isinstance(text, str) and text:
                                message = text
                        elif isinstance(error, str):
                            message = error
                        await self._fail_prompt(tracked, one_line(message))
                    elif status == "cancelled":
                        await self._cancel_prompt(tracked)
                    elif status == "in_progress":
                        await self._update_progress(tracked)
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                continue

    async def _sleep_with_poll(self, delay: float) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + delay
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(self._poll_interval, remaining))
            await self.poll_once()
