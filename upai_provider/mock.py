"""Deterministic mock timeline and local mock model catalog."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from .constants import (
    ALLOWED_IMAGE_FORMATS,
    IMAGE_ASPECT_RATIOS,
    IMAGE_RESOLUTIONS,
    MOCK_COMPLETE_SEC,
    MOCK_FAIL_SEC,
    MOCK_PENDING_SEC,
    MOCK_SLOW_SEC,
    MOCK_TICK_SEC,
    REFERENCE_MAX_BYTES,
    SHORT_SIDE,
)
from .protocol import (
    Capabilities,
    CountCapability,
    DurationCapability,
    FrameRule,
    FramesCapability,
    JobStatus,
    Model,
    Pricing,
    PromptCapability,
    ReferenceCapability,
    ReferenceLimit,
    ReferenceLimits,
    ReferencesCapability,
)

_UPDATED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class MockTimings:
    complete_sec: float = MOCK_COMPLETE_SEC
    fail_sec: float = MOCK_FAIL_SEC
    slow_sec: float = MOCK_SLOW_SEC
    pending_sec: float = MOCK_PENDING_SEC
    tick_sec: float = MOCK_TICK_SEC


@dataclass(frozen=True)
class MockState:
    status: JobStatus
    percent: int
    node: str
    value: int
    max_value: int
    queue_position: int | None
    error: str | None


def mock_state(elapsed_sec: float, prompt: str, timings: MockTimings) -> MockState:
    """Map elapsed time and prompt markers to one mock job state."""
    if elapsed_sec < timings.pending_sec:
        return MockState("pending", 0, "MockSampler", 0, 100, None, None)

    if "[fail]" in prompt:
        finish = timings.fail_sec
        fails = True
    elif "[slow]" in prompt:
        finish = timings.slow_sec
        fails = False
    else:
        finish = timings.complete_sec
        fails = False

    if elapsed_sec >= finish:
        if fails:
            return MockState(
                "failed", 0, "MockSampler", 0, 100, None, "MockSampler: simulated failure"
            )
        return MockState("completed", 100, "MockSampler", 100, 100, None, None)

    span = max(finish - timings.pending_sec, 0.001)
    percent = min(99, max(0, int((elapsed_sec - timings.pending_sec) / span * 99)))
    return MockState("in_progress", percent, "MockSampler", percent, 100, None, None)


def _reference_limits() -> ReferenceLimits:
    return ReferenceLimits(ReferenceLimit(REFERENCE_MAX_BYTES, ALLOWED_IMAGE_FORMATS))


def _video_capabilities(
    *,
    image_refs: int,
    image_required: int,
    use_frames: bool,
    reference_label: str | None = None,
    reference_labels: Mapping[str, str] | None = None,
) -> Capabilities:
    return Capabilities(
        prompt=PromptCapability(True, 4000, reference_label, reference_labels),
        negative_prompt=False,
        references=ReferencesCapability(
            image=ReferenceCapability(image_refs, image_required),
            video=ReferenceCapability(0, 0),
            audio=ReferenceCapability(0, 0),
        ),
        resolutions=("480p", "720p"),
        default_resolution="480p",
        aspect_ratios=("16:9", "9:16", "1:1"),
        default_aspect_ratio="16:9",
        sizes={
            "480p": {"16:9": "832x480", "9:16": "480x832", "1:1": "624x624"},
            "720p": {"16:9": "1280x720", "9:16": "720x1280", "1:1": "960x960"},
        },
        seed=True,
        reference_limits=_reference_limits(),
        frames=FramesCapability(use_frames, False, use_frames, False),
        duration=DurationCapability(2, 5, 5, 1),
        fps=16,
        frame_rule=FrameRule(4, 1),
        audio_output=False,
    )


_VIDEO_MODELS: tuple[Model, ...] = (
    Model(
        id="wan22-i2v",
        name="Wan 2.2 I2V (local)",
        description="",
        kind="video",
        status="ready",
        status_reason=None,
        updated_at=_UPDATED_AT,
        pricing=Pricing(0),
        capabilities=_video_capabilities(
            image_refs=2,
            image_required=0,
            use_frames=True,
            reference_label="<{kind}_{n}>",
            reference_labels={
                "image": "<Picture {n}>",
                "video": "<Video {n}>",
                "audio": "<Audio {n}>",
            },
        ),
    ),
    Model(
        id="wan22-t2v",
        name="Wan 2.2 T2V (local)",
        description="",
        kind="video",
        status="ready",
        status_reason=None,
        updated_at=_UPDATED_AT,
        pricing=Pricing(0),
        capabilities=_video_capabilities(image_refs=0, image_required=0, use_frames=False),
    ),
)


def video_models() -> tuple[Model, ...]:
    """Return the two local Wan mock models."""
    return _VIDEO_MODELS


def _even(value: float) -> int:
    return max(2, int(round(value / 2.0)) * 2)


def _size_for(resolution: str, aspect_ratio: str) -> str:
    short = SHORT_SIDE[resolution]
    width_part, height_part = aspect_ratio.split(":", maxsplit=1)
    ratio = float(width_part) / float(height_part)
    if ratio >= 1:
        width = _even(short * ratio)
        height = short
    else:
        width = short
        height = _even(short / ratio)

    return f"{width}x{height}"


_IMAGE_SIZES: Mapping[str, Mapping[str, str]] = {
    resolution: {
        aspect_ratio: _size_for(resolution, aspect_ratio) for aspect_ratio in IMAGE_ASPECT_RATIOS
    }
    for resolution in IMAGE_RESOLUTIONS
}

_IMAGE_CAPABILITIES = Capabilities(
    prompt=PromptCapability(True, 4000),
    negative_prompt=False,
    references=ReferencesCapability(
        image=ReferenceCapability(1, 0),
        video=ReferenceCapability(0, 0),
        audio=ReferenceCapability(0, 0),
    ),
    resolutions=IMAGE_RESOLUTIONS,
    default_resolution="1K",
    aspect_ratios=IMAGE_ASPECT_RATIOS,
    default_aspect_ratio="1:1",
    sizes=_IMAGE_SIZES,
    seed=True,
    reference_limits=_reference_limits(),
    count=CountCapability(4),
)

_IMAGE_MODELS: tuple[Model, ...] = (
    Model(
        id="sdxl-image",
        name="SDXL Image (local)",
        description="",
        kind="image",
        status="ready",
        status_reason=None,
        updated_at=_UPDATED_AT,
        pricing=Pricing(0),
        capabilities=_IMAGE_CAPABILITIES,
    ),
)


def image_models() -> tuple[Model, ...]:
    """Return the local SDXL mock model."""
    return _IMAGE_MODELS
