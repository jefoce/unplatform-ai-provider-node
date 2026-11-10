"""Encode and decode capability objects in the stored export shape."""

import logging

from .constants import ALLOWED_IMAGE_FORMATS
from .export_fields import (
    _bool,
    _float,
    _int,
    _obj,
    _optional_str,
    _str,
    _string_map,
    _strings,
)
from .protocol import (
    Capabilities,
    CountCapability,
    DurationCapability,
    FrameRule,
    FramesCapability,
    PromptCapability,
    ReferenceCapability,
    ReferenceLimit,
    ReferenceLimits,
    ReferencesCapability,
    capabilities_to_wire,
    split_reference_labels,
)

logger = logging.getLogger(__name__)

_REF_KINDS = ("image", "video", "audio")


def capabilities_to_data(capabilities: Capabilities) -> dict[str, object]:
    """Encode capabilities in the stored export shape via the wire serializer."""
    return capabilities_to_wire(capabilities)


def capabilities_from_data(value: object) -> Capabilities:
    obj = _obj(value, "capabilities")
    prompt = _obj(obj.get("prompt"), "capabilities.prompt")
    refs = _obj(obj.get("references"), "capabilities.references")
    limits = _obj(obj.get("reference_limits"), "capabilities.reference_limits")
    image_limit = _obj(limits.get("image"), "capabilities.reference_limits.image")
    sizes = _obj(obj.get("sizes"), "capabilities.sizes")

    references = {
        name: ReferenceCapability(
            _int(_obj(refs.get(name), f"capabilities.references.{name}"), "max"),
            _int(_obj(refs.get(name), f"capabilities.references.{name}"), "required"),
        )
        for name in _REF_KINDS
    }

    frames = None
    if obj.get("frames") is not None:
        frames_obj = _obj(obj.get("frames"), "capabilities.frames")
        frames = FramesCapability(
            _bool(frames_obj, "start"),
            _bool(frames_obj, "end"),
            _bool(frames_obj, "start_required"),
            _bool(frames_obj, "end_required"),
        )

    duration = None
    if obj.get("duration") is not None:
        duration_obj = _obj(obj.get("duration"), "capabilities.duration")
        duration = DurationCapability(
            _float(duration_obj, "min"),
            _float(duration_obj, "max"),
            _float(duration_obj, "default"),
            _float(duration_obj, "step"),
        )

    frame_rule = None
    if obj.get("frame_rule") is not None:
        rule_obj = _obj(obj.get("frame_rule"), "capabilities.frame_rule")
        frame_rule = FrameRule(_int(rule_obj, "mod"), _int(rule_obj, "add"))

    count = None
    if obj.get("count") is not None:
        count = CountCapability(_int(_obj(obj.get("count"), "capabilities.count"), "max"))

    fps = _float(obj, "fps") if obj.get("fps") is not None else None
    audio_output = _bool(obj, "audio_output") if obj.get("audio_output") is not None else None

    reference_labels, label_warnings, label_errors = split_reference_labels(
        prompt.get("reference_labels")
    )
    for message in (*label_warnings, *label_errors):
        logger.warning(message)

    return Capabilities(
        prompt=PromptCapability(
            _bool(prompt, "required"),
            _int(prompt, "max_chars"),
            _optional_str(prompt, "reference_label"),
            reference_labels or None,
        ),
        negative_prompt=_bool(obj, "negative_prompt"),
        references=ReferencesCapability(
            image=references["image"], video=references["video"], audio=references["audio"]
        ),
        resolutions=_strings(obj.get("resolutions"), "capabilities.resolutions"),
        default_resolution=_str(obj, "default_resolution"),
        aspect_ratios=_strings(obj.get("aspect_ratios"), "capabilities.aspect_ratios"),
        default_aspect_ratio=_str(obj, "default_aspect_ratio"),
        sizes={key: _string_map(row, f"capabilities.sizes.{key}") for key, row in sizes.items()},
        seed=_bool(obj, "seed"),
        reference_limits=ReferenceLimits(
            ReferenceLimit(
                _int(image_limit, "max_bytes"),
                _strings(image_limit.get("formats"), "formats")
                if image_limit.get("formats") is not None
                else ALLOWED_IMAGE_FORMATS,
            )
        ),
        frames=frames,
        duration=duration,
        fps=fps,
        frame_rule=frame_rule,
        audio_output=audio_output,
        count=count,
    )
