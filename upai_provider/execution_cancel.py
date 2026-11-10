"""Cancel and untrack submitted prompt runs."""

import logging
from collections.abc import Awaitable, Callable
from typing import cast

from .execution_patch import PromptRun
from .execution_types import _Tracker

logger = logging.getLogger(__name__)


def _mark_cancelling(tracker: _Tracker, prompt_id: str) -> None:
    mark = getattr(tracker, "mark_cancelling", None)
    if callable(mark):
        mark(prompt_id)


def _mark_submitted(tracker: _Tracker | None, prompt_id: str) -> None:
    mark = getattr(tracker, "mark_submitted", None)
    if callable(mark):
        mark(prompt_id)


def _is_running(tracker: _Tracker | None, prompt_id: str) -> bool:
    check = getattr(tracker, "is_running", None)
    return bool(check(prompt_id)) if callable(check) else False


async def _cancel_submitted(
    tracker: _Tracker | None,
    cancel_prompt: Callable[[str, bool], Awaitable[None]] | None,
    submitted: list[PromptRun],
) -> None:
    if tracker is None:
        return

    for run in submitted:
        _mark_cancelling(tracker, run.prompt_id)
        if cancel_prompt is None:
            continue

        try:
            await cancel_prompt(run.prompt_id, _is_running(tracker, run.prompt_id))
        except Exception as exc:
            logger.warning("cancel prompt %s failed: %s", run.prompt_id, type(exc).__name__)


async def _resolve_cancelling(tracker: _Tracker | None) -> None:
    """Poll once so a prompt ComfyUI never queued stops holding its slot."""
    poll = getattr(tracker, "poll_once", None)
    if not callable(poll):
        return

    try:
        await cast(Awaitable[None], poll(only_cancelling=True))
    except Exception as exc:
        logger.warning("cancel resolution failed: %s", type(exc).__name__)


def _untrack_from(tracker: _Tracker | None, runs: tuple[PromptRun, ...], *, start: int) -> None:
    if tracker is None:
        return

    for run in runs[start:]:
        tracker.untrack(run.prompt_id)
