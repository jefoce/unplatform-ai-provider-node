"""Patch an exported prompt with job values."""

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from .materialize import MaterializedMedia
from .protocol import ExportModel, ImageJobRequest, VideoJobRequest

PROMPT_INPUT = "text"
NEGATIVE_INPUT = "negative"
FRAME_INPUT = "image"
OUTPUT_INPUT = "upai_job"
SETTINGS_RESOLUTION = "test_resolution"
SETTINGS_ASPECT = "test_aspect_ratio"
SETTINGS_DURATION = "test_duration"
SETTINGS_COUNT = "test_count"
SETTINGS_SEED = "test_seed"


@dataclass(frozen=True)
class PromptRun:
    """One prompt id and the patched prompt document sent for it."""

    prompt_id: str
    prompt: Mapping[str, object]
    seed: int
    count: int


def _node_inputs(document: dict[str, object], node_id: str) -> dict[str, object]:
    from .execution_errors import WorkflowInvalidError

    node = document.get(node_id)
    if not isinstance(node, dict):
        raise WorkflowInvalidError(
            f"bound node {node_id} is missing",
            {node_id: {"message": "bound node is missing"}},
        )

    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
        node["inputs"] = inputs

    return cast(dict[str, object], inputs)


def _patch_settings(
    inputs: dict[str, object],
    model: ExportModel,
    request: VideoJobRequest | ImageJobRequest,
    *,
    seed: int,
    count: int,
) -> None:
    capabilities = model.capabilities
    inputs[SETTINGS_RESOLUTION] = request.resolution or capabilities.default_resolution
    inputs[SETTINGS_ASPECT] = request.aspect_ratio or capabilities.default_aspect_ratio
    inputs[SETTINGS_COUNT] = count
    inputs[SETTINGS_SEED] = seed

    if capabilities.duration is not None:
        duration = request.duration if isinstance(request, VideoJobRequest) else None
        inputs[SETTINGS_DURATION] = capabilities.duration.default if duration is None else duration


def build_prompt(
    prompt: Mapping[str, object],
    model: ExportModel,
    request: VideoJobRequest | ImageJobRequest,
    media: MaterializedMedia,
    *,
    job_id: str,
    seed: int,
    count: int,
    run_id: str | None = None,
) -> dict[str, object]:
    """Deep-copy the export prompt and patch every bound job value."""
    document = copy.deepcopy(dict(prompt))
    bindings = model.bindings

    if bindings.prompt is not None:
        inputs = _node_inputs(document, bindings.prompt)
        inputs[PROMPT_INPUT] = request.prompt
        if request.negative_prompt is not None:
            inputs[NEGATIVE_INPUT] = request.negative_prompt

    if bindings.settings is not None:
        _patch_settings(
            _node_inputs(document, bindings.settings),
            model,
            request,
            seed=seed,
            count=count,
        )

    for kind, refs in bindings.refs.items():
        for binding in refs:
            inputs = _node_inputs(document, binding.node)
            path = media.reference_path(kind, binding.index)
            inputs[kind] = "" if path is None else str(path)

    frames = request.frame_images if isinstance(request, VideoJobRequest) else ()
    for frame_type, node_id in (("first_frame", bindings.start), ("last_frame", bindings.end)):
        if node_id is None:
            continue

        frame = next((item for item in frames if item.frame_type == frame_type), None)
        path = media.frame_path(frame_type, 1 if frame is None else frame.slot)
        _node_inputs(document, node_id)[FRAME_INPUT] = "" if path is None else str(path)

    _node_inputs(document, model.output_node)[OUTPUT_INPUT] = run_id or job_id
    return document
