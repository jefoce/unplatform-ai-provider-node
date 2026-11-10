"""Record job output files from the ComfyUI worker thread."""

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from .constants import REGISTER_OUTPUT_TIMEOUT
from .jobs import JobStore
from .protocol import FINAL_JOB_STATUSES, JOB_ID_PATTERN, parse_run_id

logger = logging.getLogger(__name__)

_active_store: JobStore | None = None
_active_loop: asyncio.AbstractEventLoop | None = None


def configure_output(store: JobStore, loop: asyncio.AbstractEventLoop) -> None:
    """Point the worker-thread output hook at the running store and loop."""
    global _active_store, _active_loop
    _active_store = store
    _active_loop = loop


def _output_sort_key(path: str) -> tuple[tuple[int, int, str], ...]:
    """Sort run-batch names numerically, so run 2 follows run 10."""
    parts = Path(path).stem.split("-")
    return tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in parts)


async def _register_output(job_id: str, files: Sequence[str]) -> None:
    if _active_store is None:
        return

    job = await _active_store.get(job_id)
    if job is None or job.status in FINAL_JOB_STATUSES:
        return

    merged = tuple(sorted(dict.fromkeys((*job.files, *files)), key=_output_sort_key))
    await _active_store.update(job_id, files=merged)


def register_output(job_id: str, files: Sequence[str]) -> None:
    """Record output files for a job run from the ComfyUI worker thread."""
    parsed = parse_run_id(job_id)
    base_id = parsed[0] if parsed is not None else job_id
    if not JOB_ID_PATTERN.match(base_id) or _active_loop is None or _active_store is None:
        return

    future = asyncio.run_coroutine_threadsafe(_register_output(base_id, files), _active_loop)
    try:
        future.result(timeout=REGISTER_OUTPUT_TIMEOUT)
    except Exception as exc:
        logger.warning("register_output failed for job %s: %s", base_id, exc)
