"""Derive per-model capabilities from the graph and UPAI Limits."""

from collections.abc import Mapping
from dataclasses import dataclass

from .constants import (
    ALLOWED_IMAGE_FORMATS,
    IMAGE_RESOLUTIONS,
    REFERENCE_MAX_BYTES,
    VIDEO_RESOLUTIONS,
)
from .export_capability_limits import (
    _bool,
    _count,
    _duration,
    _frames,
    _inputs,
    _int,
    _number,
    _reference,
    _text,
)
from .export_sizing import build_sizes, override_resolutions
from .export_types import ModelGraph
from .protocol import (
    Capabilities,
    CountCapability,
    DurationCapability,
    FrameRule,
    PromptCapability,
    ReferenceCapability,
    ReferenceLimit,
    ReferenceLimits,
    ReferencesCapability,
    split_reference_labels,
    validate_reference_label,
)

_RESOLUTION_LABELS = {"video": VIDEO_RESOLUTIONS, "image": IMAGE_RESOLUTIONS}
_REFERENCE_LABEL_PREFIX = "prompt_reference_label_"


@dataclass(frozen=True)
class CapabilityResult:
    capabilities: Capabilities
    invalid_reason: str | None
    warnings: tuple[str, ...]


def _filter_resolutions(
    kind: str,
    resolutions: tuple[str, ...],
    warnings: list[str],
    *,
    extra_labels: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    allowed = _RESOLUTION_LABELS.get(kind, ())
    kept: list[str] = []
    for label in resolutions:
        if label in allowed or label in extra_labels:
            kept.append(label)
        else:
            warnings.append(f"resolution {label} is not a {kind} label")
    return tuple(kept)


def _labels(inputs: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = inputs.get(name)
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())

    if isinstance(value, (list, tuple)):
        return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())

    return ()


def _reference_limits() -> ReferenceLimits:
    return ReferenceLimits(ReferenceLimit(REFERENCE_MAX_BYTES, ALLOWED_IMAGE_FORMATS))


def _has_link(inputs: Mapping[str, object], name: str) -> bool:
    value = inputs.get(name)
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
    )


def _prompt(graph: ModelGraph, invalid: list[str], warnings: list[str]) -> PromptCapability:
    inputs = _inputs(graph.nodes.get(graph.model_node))
    raw_label = _text(inputs, "prompt_reference_label").strip()
    reference_label: str | None = None
    if raw_label:
        error = validate_reference_label(raw_label)
        if error is not None:
            invalid.append(error)
        else:
            reference_label = raw_label

    raw_labels = {
        key[len(_REFERENCE_LABEL_PREFIX) :]: value.strip()
        for key, value in inputs.items()
        if isinstance(key, str)
        and key.startswith(_REFERENCE_LABEL_PREFIX)
        and isinstance(value, str)
        and value.strip()
    }
    labels, label_warnings, label_errors = split_reference_labels(raw_labels)
    warnings.extend(label_warnings)
    invalid.extend(label_errors)
    reference_labels = labels or None

    if graph.prompt_node is None:
        return PromptCapability(False, 0, reference_label, reference_labels)

    prompt_inputs = _inputs(graph.nodes.get(graph.prompt_node))
    required = _bool(prompt_inputs, "required")
    max_chars = _int(prompt_inputs, "max_chars", 0) or 0
    return PromptCapability(required, max(max_chars, 0), reference_label, reference_labels)


def _settings(
    graph: ModelGraph,
) -> tuple[Mapping[str, object], tuple[str, ...], tuple[str, ...], int, str]:
    if graph.settings_node is None:
        return {}, (), (), 16, ""

    inputs = _inputs(graph.nodes.get(graph.settings_node))
    resolutions = _labels(inputs, "resolutions")
    aspect_ratios = _labels(inputs, "aspect_ratios")
    align = _int(inputs, "align", 16) or 16
    overrides = _text(inputs, "size_overrides")
    return inputs, resolutions, aspect_ratios, max(1, align), overrides


def derive_capabilities(graph: ModelGraph) -> CapabilityResult:
    """Build capabilities for one model, applying UPAI Limits when wired."""
    invalid: list[str] = []
    warnings: list[str] = []
    limits = _inputs(graph.nodes.get(graph.limits_node)) if graph.limits_node else {}

    settings, resolutions, aspect_ratios, align, overrides = _settings(graph)
    if graph.settings_node is None:
        invalid.append("model has no UPAI Settings node")

    resolutions = _filter_resolutions(
        graph.kind, resolutions, warnings, extra_labels=override_resolutions(overrides)
    )
    if graph.settings_node is not None and not resolutions:
        invalid.append(f"model has no valid {graph.kind} resolution labels")

    if graph.settings_node is not None and not aspect_ratios:
        invalid.append("model has no aspect ratio labels")

    default_resolution = _text(settings, "default_resolution")
    if default_resolution not in resolutions:
        default_resolution = resolutions[0] if resolutions else ""

    default_aspect = _text(settings, "default_aspect_ratio")
    if default_aspect not in aspect_ratios:
        default_aspect = aspect_ratios[0] if aspect_ratios else ""

    refs = graph.refs
    image = _reference(
        "image",
        ReferenceCapability(
            len(refs.get("image", ())), sum(1 for r in refs.get("image", ()) if r.required)
        ),
        limits,
        invalid,
        warnings,
    )
    video = _reference(
        "video",
        ReferenceCapability(
            len(refs.get("video", ())), sum(1 for r in refs.get("video", ()) if r.required)
        ),
        limits,
        invalid,
        warnings,
    )
    audio = _reference(
        "audio",
        ReferenceCapability(
            len(refs.get("audio", ())), sum(1 for r in refs.get("audio", ()) if r.required)
        ),
        limits,
        invalid,
        warnings,
    )

    frames = _frames(graph, limits, invalid)
    seed = graph.settings_node is not None
    duration: DurationCapability | None = None
    fps: float | None = None
    frame_rule: FrameRule | None = None
    count: CountCapability | None = None
    audio_output: bool | None = None

    if graph.kind == "video":
        duration = _duration(
            DurationCapability(
                min=max(_number(settings, "duration_min", 0.0) or 0.0, 0.0),
                max=max(_number(settings, "duration_max", 0.0) or 0.0, 0.0),
                default=max(_number(settings, "duration_default", 0.0) or 0.0, 0.0),
                step=max(_number(settings, "duration_step", 0.0) or 0.0, 0.0),
            ),
            limits,
            invalid,
            warnings,
        )
        raw_fps = _number(settings, "fps")
        fps = raw_fps if raw_fps and raw_fps > 0 else None
        mod = _int(settings, "frame_mod")
        add = _int(settings, "frame_add")
        if mod is not None and mod > 0:
            frame_rule = FrameRule(mod, max(add or 0, 0))
        output = _inputs(graph.nodes.get(graph.output_node))
        audio_output = _has_link(output, "audio")
        frames = frames if graph.start_node or graph.end_node or limits else None
    else:
        count = CountCapability(max(_int(settings, "count_max", 1) or 1, 1))
        count = _count(count, limits, warnings)
        frames = None

    capabilities = Capabilities(
        prompt=_prompt(graph, invalid, warnings),
        negative_prompt=graph.prompt_negative_used,
        references=ReferencesCapability(image=image, video=video, audio=audio),
        resolutions=resolutions,
        default_resolution=default_resolution,
        aspect_ratios=aspect_ratios,
        default_aspect_ratio=default_aspect,
        sizes=build_sizes(resolutions, aspect_ratios, align, overrides),
        seed=seed,
        reference_limits=_reference_limits(),
        frames=frames,
        duration=duration,
        fps=fps,
        frame_rule=frame_rule,
        audio_output=audio_output,
        count=count,
    )
    reason = "; ".join(invalid) if invalid else None
    return CapabilityResult(capabilities, reason, tuple(warnings))
