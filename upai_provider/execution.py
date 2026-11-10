"""Patch an exported prompt and submit it to ComfyUI over loopback HTTP."""

import logging
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from .execution_cancel import (
    _cancel_submitted,
    _mark_submitted,
    _resolve_cancelling,
    _untrack_from,
)
from .execution_errors import ComfyUnavailableError, PromptRejectedError, WorkflowInvalidError
from .execution_patch import PromptRun
from .execution_runs import CountMode, build_prompts, count_mode_from_prompt
from .execution_submit import _first_node_error, submit_prompt
from .execution_types import ExecutionOutcome, _JobStore, _Tracker
from .materialize import HttpSession, materialize_inputs
from .protocol import (
    FINAL_JOB_STATUSES,
    ExportModel,
    ImageJobRequest,
    Job,
    ProtocolError,
    VideoJobRequest,
)
from .textutil import one_line
from .uploads import UploadStore

logger = logging.getLogger(__name__)


async def _fail(store: _JobStore, job_id: str, message: str, *, uploads: UploadStore) -> None:
    try:
        await store.finalize(job_id, "failed", error=one_line(message))
    finally:
        uploads.release(job_id)


def _client_id(instance_id: str) -> str:
    return f"upai-{instance_id}"


async def execute_job(
    *,
    job: Job,
    model: ExportModel,
    prompt: Mapping[str, object],
    request: VideoJobRequest | ImageJobRequest,
    store: _JobStore,
    uploads: UploadStore,
    session: HttpSession,
    tracker: _Tracker | None,
    input_root: Path,
    instance_id: str,
    server_url: str,
    count: int,
    count_mode: CountMode | None = None,
    allow_url_fetch: bool = False,
    fetch_session: HttpSession | None = None,
    cancel_prompt: Callable[[str, bool], Awaitable[None]] | None = None,
) -> ExecutionOutcome:
    """Materialize, patch and submit one prepared job."""
    try:
        media = await materialize_inputs(
            job_id=job.id,
            request=request,
            capabilities=model.capabilities,
            input_root=input_root,
            uploads=uploads,
            allow_url_fetch=allow_url_fetch,
            session=fetch_session or session,
        )
    except ProtocolError as exc:
        await _fail(store, job.id, exc.message, uploads=uploads)
        return ExecutionOutcome(False, error=exc.message)
    except Exception:
        logger.exception("job %s failed while materializing media", job.id)
        await _fail(store, job.id, "media materialize failed", uploads=uploads)
        return ExecutionOutcome(False, error="media materialize failed")

    seed = job.seed if job.seed is not None else 0
    resolved_mode = count_mode if count_mode is not None else count_mode_from_prompt(prompt, model)
    try:
        runs = build_prompts(
            prompt,
            model,
            request,
            media,
            job_id=job.id,
            seed=seed,
            count=count,
            count_mode=resolved_mode,
        )
    except WorkflowInvalidError as exc:
        await _fail(store, job.id, str(exc), uploads=uploads)
        return ExecutionOutcome(False, node_errors=exc.node_errors, error=str(exc))

    client_id = _client_id(instance_id)
    if tracker is not None:
        for run in runs:
            tracker.track(
                run.prompt_id,
                job_id=job.id,
                prompt=run.prompt,
                output_node=str(model.output_node),
                count=run.count,
            )

    submitted: list[PromptRun] = []
    try:
        for index, run in enumerate(runs):
            current = await store.get(job.id)
            if current is None or current.status in FINAL_JOB_STATUSES:
                uploads.release(job.id)
                _untrack_from(tracker, runs, start=index)
                return ExecutionOutcome(False, error="job is no longer active")

            await submit_prompt(
                session,
                server_url=server_url,
                run=run,
                client_id=client_id,
                output_node=str(model.output_node),
            )
            submitted.append(run)
            _mark_submitted(tracker, run.prompt_id)

            current = await store.get(job.id)
            if current is None or current.status in FINAL_JOB_STATUSES:
                uploads.release(job.id)
                _untrack_from(tracker, runs, start=index + 1)
                await _cancel_submitted(tracker, cancel_prompt, [run])
                return ExecutionOutcome(False, error="job is no longer active")
    except (PromptRejectedError, ComfyUnavailableError) as exc:
        failed_index = len(submitted)
        cancelled = [*submitted, runs[failed_index]] if exc.is_queued else list(submitted)
        await _cancel_submitted(tracker, cancel_prompt, cancelled)
        start = failed_index + 1 if exc.is_queued else failed_index
        _untrack_from(tracker, runs, start=start)

        node_errors: Mapping[str, object] | None = None
        if isinstance(exc, PromptRejectedError):
            node_errors = exc.node_errors
            message = _first_node_error(exc.node_errors)
        else:
            message = str(exc)

        await _fail(store, job.id, message, uploads=uploads)
        if exc.is_queued:
            await _resolve_cancelling(tracker)
        return ExecutionOutcome(False, node_errors=node_errors, error=message)

    return ExecutionOutcome(True, prompt_ids=tuple(run.prompt_id for run in runs))


__all__ = ["execute_job"]
