"""Remove one job's input and result files."""

import contextlib
import shutil
from collections.abc import Sequence
from pathlib import Path

from .protocol import JOB_ID_PATTERN, parse_run_id


def _is_job_dir(name: str, job_id: str) -> bool:
    """True for the job folder or one of its per-run folders."""
    if name == job_id:
        return True

    parsed = parse_run_id(name)
    return parsed is not None and parsed[0] == job_id


def _directory_job_id(name: str) -> str | None:
    """Return the base job id for a job or run directory name."""
    if JOB_ID_PATTERN.match(name):
        return name

    parsed = parse_run_id(name)
    return parsed[0] if parsed is not None else None


def list_job_dirs(root: Path) -> tuple[str, ...]:
    """Return base job ids for direct child directories, sorted."""
    try:
        entries = tuple(root.iterdir())
    except OSError:
        return ()

    found: set[str] = set()
    for entry in entries:
        if not entry.is_dir():
            continue
        job_id = _directory_job_id(entry.name)
        if job_id is not None:
            found.add(job_id)

    return tuple(sorted(found))


def orphan_job_ids(
    input_root: Path,
    result_root: Path,
    *,
    keep_ids: set[str],
) -> tuple[str, ...]:
    """Return job ids present under either root that are not kept. No deletion."""
    present = set(list_job_dirs(input_root)) | set(list_job_dirs(result_root))
    return tuple(sorted(present - keep_ids))


def cleanup_job_files(
    job_id: str,
    *,
    input_root: Path,
    result_root: Path,
    files: Sequence[str] = (),
) -> None:
    """Remove one job's input and result files. Shared uploads stay untouched."""
    if not JOB_ID_PATTERN.match(job_id):
        return

    removed: list[Path] = []
    for root in (input_root.resolve(), result_root.resolve()):
        try:
            entries = tuple(root.iterdir())
        except OSError:
            continue

        for entry in entries:
            try:
                target = entry.resolve()
            except OSError:
                continue
            if target.parent != root or not target.is_dir():
                continue
            if not _is_job_dir(target.name, job_id):
                continue

            removed.append(target)
            shutil.rmtree(target, ignore_errors=True)

    for name in files:
        path = Path(name)
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not any(resolved.is_relative_to(directory) for directory in removed):
            continue
        if not resolved.is_file():
            continue
        with contextlib.suppress(FileNotFoundError, OSError):
            resolved.unlink()
