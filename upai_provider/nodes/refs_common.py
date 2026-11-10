"""Shared reference and frame helpers. Missing or bad test files fall back cleanly."""

import logging
from typing import Any

from .media import (
    PLACEHOLDER_SIZE,
    load_audio,
    load_image,
    load_video,
    placeholder_image,
    resolve_file,
)

logger = logging.getLogger(__name__)

MAX_REFERENCE_INDEX = 16
VIDEO_SUFFIXES = ("mp4", "webm", "mov", "mkv")


def _check_index(index: int) -> int:
    value = int(index)
    if value < 1 or value > MAX_REFERENCE_INDEX:
        raise ValueError(f"index must be between 1 and {MAX_REFERENCE_INDEX}")
    return value


def _validate_index(index: int) -> bool | str:
    if int(index) < 1 or int(index) > MAX_REFERENCE_INDEX:
        return f"index must be between 1 and {MAX_REFERENCE_INDEX}"
    return True


def _blank(value: str | None) -> bool:
    return not value or value.strip().lower() in {"", "none"}


def _missing(value: str | None, label: str, required: bool) -> bool:
    if _blank(value):
        if required:
            logger.warning("%s: required test file is missing", label)
        return True
    return False


def _validate_frame(image: str | None, *, required: bool, label: str) -> bool | str:
    if not required:
        return True

    if _blank(image):
        return f"{label}: required test file is missing"

    if resolve_file(image) is None:
        return f"{label}: required test file is not found"

    return True


def _validate_audio(index: int, audio: str | None, *, required: bool) -> bool | str:
    index_error = _validate_index(index)
    if index_error is not True:
        return index_error

    if _blank(audio):
        if required:
            return "UPAI Audio Ref: required test file is missing"
        return True

    if resolve_file(audio) is None:
        return "UPAI Audio Ref: test file is outside the input directory or not found"

    return True


def _image_result(value: str | None, label: str, required: bool) -> tuple[Any, Any, bool, int, int]:
    path = resolve_file(value)
    if path is None:
        if not _missing(value, label, required):
            logger.warning("%s: test file not found", label)
        image, mask = placeholder_image()
        return image, mask, False, PLACEHOLDER_SIZE, PLACEHOLDER_SIZE

    try:
        image, mask = load_image(path)
    except (OSError, ValueError):
        logger.warning("%s: test file could not be read", label)
        image, mask = placeholder_image()
        return image, mask, False, PLACEHOLDER_SIZE, PLACEHOLDER_SIZE

    return image, mask, True, int(image.shape[2]), int(image.shape[1])


def _frame_result(value: str | None, label: str, required: bool) -> tuple[Any, bool]:
    path = resolve_file(value)
    if path is None:
        if not _missing(value, label, required):
            logger.warning("%s: test file not found", label)
        image, _ = placeholder_image()
        return image, False

    try:
        image, _ = load_image(path)
    except (OSError, ValueError):
        logger.warning("%s: test file could not be read", label)
        image, _ = placeholder_image()
        return image, False

    return image, True


def _video_result(
    value: str | None,
    label: str,
    required: bool,
) -> tuple[Any, bool, float, float, int]:
    path = resolve_file(value)
    if path is None:
        if not _missing(value, label, required):
            logger.warning("%s: test file not found", label)
        return None, False, 0.0, 0.0, 0

    try:
        video = load_video(path)
        fps = float(video.get_frame_rate())
        duration = float(video.get_duration())
        frame_count = int(video.get_frame_count())
    except Exception:  # noqa: BLE001 - a bad media file must not crash the workflow
        logger.warning("%s: test file could not be read", label)
        return None, False, 0.0, 0.0, 0

    return video, True, fps, duration, frame_count


def _audio_result(value: str | None, label: str, required: bool) -> tuple[Any, bool, float]:
    path = resolve_file(value)
    if path is None:
        if not _missing(value, label, required):
            logger.warning("%s: test file not found", label)
        return None, False, 0.0

    try:
        audio = load_audio(path)
        sample_rate = int(audio["sample_rate"])
        duration = float(audio["waveform"].shape[-1]) / sample_rate
    except Exception:  # noqa: BLE001 - a bad media file must not crash the workflow
        logger.warning("%s: test file could not be read", label)
        return None, False, 0.0

    return audio, True, duration
