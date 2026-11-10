"""Build prompt runs for a job, including one child per run."""

import uuid
from collections.abc import Mapping
from typing import Literal

from .execution_patch import PromptRun, build_prompt
from .materialize import MaterializedMedia
from .protocol import ExportModel, ImageJobRequest, VideoJobRequest, format_run_id

CountMode = Literal["batch", "count", "runs"]
_SEED_LIMIT = 2**31


def count_mode_from_prompt(
    prompt: Mapping[str, object],
    model: ExportModel,
) -> CountMode:
    """Read count_mode from the export settings node, batch when absent."""
    if model.bindings.settings is None:
        return "batch"

    node = prompt.get(model.bindings.settings)
    if not isinstance(node, Mapping):
        return "batch"

    inputs = node.get("inputs")
    if not isinstance(inputs, Mapping):
        return "batch"

    return "runs" if inputs.get("count_mode") == "runs" else "batch"


def build_prompts(
    prompt: Mapping[str, object],
    model: ExportModel,
    request: VideoJobRequest | ImageJobRequest,
    media: MaterializedMedia,
    *,
    job_id: str,
    seed: int,
    count: int,
    count_mode: CountMode = "batch",
) -> tuple[PromptRun, ...]:
    """Build one prompt, or one child prompt per run for count_mode=runs."""
    if count_mode != "runs" or count <= 1:
        return (
            PromptRun(
                prompt_id=job_id,
                prompt=build_prompt(
                    prompt,
                    model,
                    request,
                    media,
                    job_id=job_id,
                    seed=seed,
                    count=count,
                ),
                seed=seed,
                count=count,
            ),
        )

    runs: list[PromptRun] = []
    for index in range(count):
        run_seed = (seed + index) % _SEED_LIMIT
        prompt_id = job_id if index == 0 else str(uuid.uuid4())
        runs.append(
            PromptRun(
                prompt_id=prompt_id,
                prompt=build_prompt(
                    prompt,
                    model,
                    request,
                    media,
                    job_id=job_id,
                    seed=run_seed,
                    count=1,
                    run_id=format_run_id(job_id, index),
                ),
                seed=run_seed,
                count=1,
            )
        )

    return tuple(runs)
