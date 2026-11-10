"""Parsers for incoming job request bodies."""

from .parse_common import (
    _object,
    _optional_int,
    _optional_number,
    _optional_str,
    _parse_frame_images,
    _parse_input_references,
    _required_str,
)
from .shapes import ImageJobRequest, VideoJobRequest


def parse_video_job_request(raw: object) -> VideoJobRequest:
    """Parse a POST /videos body."""
    obj = _object(raw, "body")
    return VideoJobRequest(
        model=_required_str(obj, "model"),
        prompt=_required_str(obj, "prompt"),
        negative_prompt=_optional_str(obj, "negative_prompt"),
        duration=_optional_number(obj, "duration", positive=True),
        resolution=_optional_str(obj, "resolution"),
        aspect_ratio=_optional_str(obj, "aspect_ratio"),
        seed=_optional_int(obj, "seed", minimum=0, maximum=2**31 - 1),
        frame_images=_parse_frame_images(obj.get("frame_images")),
        input_references=_parse_input_references(obj.get("input_references")),
    )


def parse_image_job_request(raw: object) -> ImageJobRequest:
    """Parse a POST /images or /images/jobs body."""
    obj = _object(raw, "body")
    return ImageJobRequest(
        model=_required_str(obj, "model"),
        prompt=_required_str(obj, "prompt"),
        negative_prompt=_optional_str(obj, "negative_prompt"),
        n=_optional_int(obj, "n", minimum=0),
        resolution=_optional_str(obj, "resolution"),
        aspect_ratio=_optional_str(obj, "aspect_ratio"),
        seed=_optional_int(obj, "seed", minimum=0, maximum=2**31 - 1),
        input_references=_parse_input_references(obj.get("input_references"), images_only=True),
    )
