"""Capability dataclasses attached to a model."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .constants import REFERENCE_LABEL_MAX_CHARS

REFERENCE_LABEL_KINDS = ("image", "video", "audio")

_PLACEHOLDERS = frozenset({"kind", "Kind", "n", "i"})
_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")


def validate_reference_label(value: str | None) -> str | None:
    """Return the validation error for a reference label, or None when valid."""
    if value is None:
        return None

    label = value.strip()
    if not label:
        return None

    if len(label) > REFERENCE_LABEL_MAX_CHARS:
        return f"reference_label must be at most {REFERENCE_LABEL_MAX_CHARS} characters"

    for match in _PLACEHOLDER_RE.finditer(label):
        if match.group(1) not in _PLACEHOLDERS:
            return f"reference_label has an unknown placeholder {match.group(0)}"

    rest = _PLACEHOLDER_RE.sub("", label)
    if "{" in rest or "}" in rest:
        return "reference_label has a stray brace"

    if "{n}" not in label and "{i}" not in label:
        return "reference_label must contain {n} or {i}"

    return None


def split_reference_labels(
    value: object,
) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]:
    """Split a raw reference label map into labels, warnings and errors."""
    if value is None:
        return {}, (), ()
    if not isinstance(value, Mapping):
        return {}, (), ("reference_labels must be an object",)

    labels: dict[str, str] = {}
    warnings: list[str] = []
    errors: list[str] = []
    for key, raw in value.items():
        if not isinstance(key, str) or key not in REFERENCE_LABEL_KINDS:
            warnings.append(f"reference_labels has unknown kind '{key}', dropped")
            continue
        if raw is None:
            continue
        if not isinstance(raw, str):
            errors.append(f"reference_labels.{key} must be a string")
            continue

        label = raw.strip()
        if not label:
            continue

        error = validate_reference_label(label)
        if error is not None:
            errors.append(f"reference_labels.{key}: {error}")
            continue

        labels[key] = label

    return labels, tuple(warnings), tuple(errors)


@dataclass(frozen=True)
class PromptCapability:
    required: bool
    max_chars: int
    reference_label: str | None = None
    reference_labels: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ReferenceCapability:
    max: int
    required: int


@dataclass(frozen=True)
class ReferencesCapability:
    image: ReferenceCapability
    video: ReferenceCapability
    audio: ReferenceCapability


@dataclass(frozen=True)
class FramesCapability:
    start: bool
    end: bool
    start_required: bool
    end_required: bool


@dataclass(frozen=True)
class DurationCapability:
    min: float
    max: float
    default: float
    step: float


@dataclass(frozen=True)
class FrameRule:
    mod: int
    add: int


@dataclass(frozen=True)
class ReferenceLimit:
    max_bytes: int
    formats: tuple[str, ...]


@dataclass(frozen=True)
class ReferenceLimits:
    image: ReferenceLimit


@dataclass(frozen=True)
class CountCapability:
    max: int


@dataclass(frozen=True)
class Capabilities:
    prompt: PromptCapability
    negative_prompt: bool
    references: ReferencesCapability
    resolutions: tuple[str, ...]
    default_resolution: str
    aspect_ratios: tuple[str, ...]
    default_aspect_ratio: str
    sizes: Mapping[str, Mapping[str, str]]
    seed: bool
    reference_limits: ReferenceLimits
    frames: FramesCapability | None = None
    duration: DurationCapability | None = None
    fps: float | None = None
    frame_rule: FrameRule | None = None
    audio_output: bool | None = None
    count: CountCapability | None = None
