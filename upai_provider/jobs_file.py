"""Read and write the jobs file, including boot repair and quarantine."""

import asyncio
import contextlib
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, replace
from pathlib import Path

from .fileutil import replace_file
from .protocol import FINAL_JOB_STATUSES, Job, ProtocolError
from .protocol.parse_files import parse_jobs_records
from .timeutil import iso_now

logger = logging.getLogger(__name__)

_UNREADABLE = object()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".jobs-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(payload, file, separators=(",", ":"), sort_keys=True)
        replace_file(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise


def _read(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
        return _UNREADABLE

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _UNREADABLE


def _file_exists(path: Path, name: str) -> bool:
    file_path = Path(name)
    if not file_path.is_absolute():
        file_path = path.parent / file_path
    try:
        return file_path.exists()
    except OSError:
        return False


async def _quarantine(path: Path, clock: Callable[[], float]) -> bool:
    """Move an unreadable jobs file aside. False when it stays in place."""
    if not path.is_file():
        logger.warning("cannot move unreadable jobs path %s: not a file", path)
        return False

    target = path.with_name(f"{path.name}.corrupt-{int(clock())}")
    try:
        await asyncio.to_thread(replace_file, path, target)
    except OSError as exc:
        logger.warning("cannot move unreadable jobs file %s: %s", path, exc)
        return False

    logger.warning("moved unreadable jobs file %s to %s", path, target)
    return True


async def _copy_corrupt(path: Path, clock: Callable[[], float]) -> None:
    """Copy the original jobs file aside before saving the valid records."""
    target = path.with_name(f"{path.name}.corrupt-{int(clock())}")
    try:
        await asyncio.to_thread(shutil.copyfile, path, target)
    except OSError as exc:
        logger.warning("cannot copy invalid jobs file %s: %s", path, exc)
        return

    logger.warning("copied invalid jobs file %s to %s", path, target)


def _apply_boot_rules(
    jobs: dict[str, Job],
    *,
    path: Path,
    clock: Callable[[], float],
    ttl_seconds: float,
) -> None:
    now = clock()
    for job_id, job in list(jobs.items()):
        if job.status not in FINAL_JOB_STATUSES:
            jobs[job_id] = replace(
                job,
                status="failed",
                error="ComfyUI restarted",
                finished_at=iso_now(lambda: now),
                expires_at=int(now + ttl_seconds),
            )
            continue

        if job.status == "expired":
            continue

        expired_at = job.expires_at is not None and job.expires_at <= int(now)
        missing_file = any(not _file_exists(path, name) for name in job.files)
        if expired_at or missing_file:
            jobs[job_id] = replace(job, status="expired")


async def save_jobs(path: Path, jobs: Iterable[Job]) -> None:
    """Serialize jobs and write them atomically."""
    payload = {"jobs": [asdict(job) for job in jobs]}
    await asyncio.to_thread(_write_json, path, payload)


async def load_jobs(
    path: Path, *, clock: Callable[[], float], ttl_seconds: float
) -> dict[str, Job]:
    """Load stored jobs, repair boot state, then persist once."""
    raw = await asyncio.to_thread(_read, path)
    if raw is _UNREADABLE:
        if not await _quarantine(path, clock):
            return {}
        raw = None

    jobs: dict[str, Job] = {}
    if raw is not None:
        try:
            parsed, skipped = parse_jobs_records(raw)
        except ProtocolError as exc:
            logger.warning("ignoring invalid jobs file %s: %s", path, exc.message)
            if not await _quarantine(path, clock):
                return {}
        else:
            jobs = {job.id: job for job in parsed}
            if skipped:
                logger.warning("skipped %d invalid job records in %s", skipped, path)
                await _copy_corrupt(path, clock)

    _apply_boot_rules(jobs, path=path, clock=clock, ttl_seconds=ttl_seconds)
    await save_jobs(path, jobs.values())
    return jobs
