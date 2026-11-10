"""Video request validation. No ComfyUI imports."""

from .protocol import Model, ProtocolError, VideoJobRequest
from .validation import (
    check_references,
    validate_negative_prompt,
    validate_prompt,
    validate_resolution_and_aspect,
    validate_seed,
)


def validate_video(request: VideoJobRequest, model: Model) -> None:
    """Validate a video request against model capabilities."""
    capabilities = model.capabilities
    validate_prompt(request.prompt, capabilities)
    validate_negative_prompt(request.negative_prompt, capabilities)
    validate_seed(request.seed, capabilities)

    duration = capabilities.duration
    if duration is not None:
        value = duration.default if request.duration is None else request.duration
        if not float(value).is_integer():
            raise ProtocolError(
                "invalid_request",
                "duration must be an integer",
                details={"field": "duration"},
            )

        if value < duration.min or value > duration.max:
            raise ProtocolError(
                "invalid_request",
                f"duration must be between {duration.min} and {duration.max}",
                details={"field": "duration"},
            )

        if duration.step > 0 and (value - duration.min) % duration.step != 0:
            raise ProtocolError(
                "invalid_request",
                f"duration must step by {duration.step}",
                details={"field": "duration"},
            )

    validate_resolution_and_aspect(
        capabilities,
        resolution=request.resolution,
        aspect_ratio=request.aspect_ratio,
    )

    check_references(request.input_references, capabilities)

    frames = capabilities.frames
    if request.frame_images and frames is None:
        raise ProtocolError(
            "invalid_request",
            "model does not accept frame images",
            details={"field": "frame_images"},
        )

    if frames is None:
        return

    first = sum(1 for frame in request.frame_images if frame.frame_type == "first_frame")
    last = sum(1 for frame in request.frame_images if frame.frame_type == "last_frame")
    if first > 1 or last > 1:
        raise ProtocolError(
            "invalid_request",
            "at most one first frame and one last frame",
            details={"field": "frame_images"},
        )

    if first and not frames.start:
        raise ProtocolError(
            "invalid_request",
            "model does not accept a first frame",
            details={"field": "frame_images"},
        )

    if last and not frames.end:
        raise ProtocolError(
            "invalid_request",
            "model does not accept a last frame",
            details={"field": "frame_images"},
        )

    if frames.start_required and not first:
        raise ProtocolError(
            "invalid_request",
            "first frame is required",
            details={"field": "frame_images"},
        )

    if frames.end_required and not last:
        raise ProtocolError(
            "invalid_request",
            "last frame is required",
            details={"field": "frame_images"},
        )

    if last and not first:
        raise ProtocolError(
            "invalid_request",
            "last frame requires a first frame",
            details={"field": "frame_images"},
        )
