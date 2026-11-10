"""Shared parsing helpers used by the request and file parsers."""

import math
from collections.abc import Mapping
from datetime import datetime
from typing import NoReturn, cast

from .errors import ProtocolError
from .ids import SHA256_PATTERN
from .shapes import FrameImage, FrameType, InputReference, JobProgress, ReferenceKind


def _raise(field: str, message: str) -> NoReturn:
    raise ProtocolError("invalid_request", message, details={"field": field})


def _object(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        _raise(field, f"{field} must be an object")

    return cast(Mapping[str, object], value)


def _str(value: object, field: str) -> str:
    if not isinstance(value, str):
        _raise(field, f"{field} must be a string")

    return value


def _required_str(obj: Mapping[str, object], field: str) -> str:
    if field not in obj:
        _raise(field, f"{field} is required")

    return _str(obj.get(field), field)


def _media_url(value: object, field: str) -> str:
    url = _str(value, field)
    if url.startswith("data:"):
        if not url.partition(";base64,")[2]:
            _raise(field, "unsupported media URL")
        return url

    if url.startswith("upai-upload:"):
        if not SHA256_PATTERN.match(url.removeprefix("upai-upload:")):
            _raise(field, "unsupported media URL")
        return url

    if url.startswith(("http://", "https://")):
        return url

    _raise(field, "unsupported media URL")


def _optional_str(obj: Mapping[str, object], field: str) -> str | None:
    value = obj.get(field)
    if value is None:
        return None

    return _str(value, field)


def _int(
    value: object, field: str, *, minimum: int | None = None, maximum: int | None = None
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _raise(field, f"{field} must be an integer")

    if minimum is not None and value < minimum:
        _raise(field, f"{field} must be at least {minimum}")

    if maximum is not None and value > maximum:
        _raise(field, f"{field} must be at most {maximum}")

    return value


def _optional_int(
    obj: Mapping[str, object],
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    value = obj.get(field)
    if value is None:
        return None

    return _int(value, field, minimum=minimum, maximum=maximum)


def _optional_number(
    obj: Mapping[str, object], field: str, *, positive: bool = False
) -> float | None:
    value = obj.get(field)
    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise(field, f"{field} must be a number")

    number = float(value)
    if not math.isfinite(number):
        _raise(field, f"{field} must be finite")

    if positive and number <= 0:
        _raise(field, f"{field} must be positive")

    return number


def _optional_bool(obj: Mapping[str, object], field: str) -> bool | None:
    value = obj.get(field)
    if value is None:
        return None

    if not isinstance(value, bool):
        _raise(field, f"{field} must be a boolean")

    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...] | None:
    if value is None:
        return None

    if not isinstance(value, (list, tuple)):
        _raise(field, f"{field} must be a list")

    return tuple(_str(item, f"{field}[{index}]") for index, item in enumerate(value))


def _timestamp(value: object, field: str) -> str:
    text = _str(value, field)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _raise(field, f"{field} must be an ISO 8601 timestamp")

    return text


def _required_timestamp(obj: Mapping[str, object], field: str) -> str:
    if field not in obj:
        _raise(field, f"{field} is required")

    return _timestamp(obj.get(field), field)


def _optional_timestamp(obj: Mapping[str, object], field: str) -> str | None:
    value = obj.get(field)
    if value is None:
        return None

    return _timestamp(value, field)


def _parse_progress(value: object) -> JobProgress | None:
    if value is None:
        return None

    obj = _object(value, "progress")
    if "percent" not in obj:
        _raise("progress.percent", "progress.percent is required")

    return JobProgress(
        percent=_int(obj.get("percent"), "progress.percent", minimum=0, maximum=100),
        node=_optional_str(obj, "node"),
        value=_optional_int(obj, "value"),
        max=_optional_int(obj, "max"),
        queue_position=_optional_int(obj, "queue_position"),
        waiting_on=_optional_str(obj, "waiting_on"),
    )


def _parse_frame_images(value: object) -> tuple[FrameImage, ...]:
    if value is None:
        return ()

    if not isinstance(value, list):
        _raise("frame_images", "frame_images must be a list")

    slots = {"first_frame": 0, "last_frame": 0}
    items: list[FrameImage] = []
    for index, item in enumerate(value):
        field = f"frame_images[{index}]"
        obj = _object(item, field)
        if obj.get("type") != "image_url":
            _raise(f"{field}.type", "frame type must be image_url")

        image_url = _object(obj.get("image_url"), f"{field}.image_url")
        url = _media_url(_required_str(image_url, "url"), f"{field}.image_url.url")
        frame_type = obj.get("frame_type")
        if frame_type == "first_frame":
            kind = cast(FrameType, "first_frame")
        elif frame_type == "last_frame":
            kind = cast(FrameType, "last_frame")
        else:
            _raise(f"{field}.frame_type", "frame_type must be first_frame or last_frame")

        slots[kind] += 1
        items.append(FrameImage(kind, url, slots[kind]))

    return tuple(items)


_REFERENCE_KINDS = {"image_url": "image", "video_url": "video", "audio_url": "audio"}


def _parse_input_references(
    value: object, *, images_only: bool = False
) -> tuple[InputReference, ...]:
    if value is None:
        return ()

    if not isinstance(value, list):
        _raise("input_references", "input_references must be a list")

    slots = {"image": 0, "video": 0, "audio": 0}
    items: list[InputReference] = []
    for index, item in enumerate(value):
        field = f"input_references[{index}]"
        obj = _object(item, field)
        ref_type = obj.get("type")
        if not isinstance(ref_type, str) or ref_type not in _REFERENCE_KINDS:
            _raise(f"{field}.type", "type must be image_url, video_url or audio_url")

        kind = cast(ReferenceKind, _REFERENCE_KINDS[ref_type])
        if images_only and kind != "image":
            _raise(f"{field}.type", "image jobs accept image references only")

        url_obj = _object(obj.get(f"{kind}_url"), f"{field}.{kind}_url")
        url = _media_url(_required_str(url_obj, "url"), f"{field}.{kind}_url.url")
        slots[kind] += 1
        items.append(InputReference(kind, url, slots[kind]))

    return tuple(items)
