"""Frame and count math for the UPAI Settings node."""

from __future__ import annotations


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value between minimum and maximum."""
    if maximum < minimum:
        return minimum

    return min(max(value, minimum), maximum)


def round_frames(seconds: float, *, fps: float, mod: int, add: int) -> int:
    """Round duration * fps to the nearest valid frame count."""
    step = max(1, int(mod))
    offset = max(0, int(add))
    target = max(0.0, seconds) * fps
    count = int((target - offset) / step + 0.5) * step + offset
    return max(offset, count)


def clamp_count(value: int, maximum: int) -> int:
    """Clamp an image count to at least 1 and at most maximum."""
    return max(1, min(int(value), max(1, int(maximum))))
