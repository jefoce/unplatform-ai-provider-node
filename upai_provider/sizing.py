"""Resolution, aspect ratio and size override math."""

from __future__ import annotations

from .constants import SHORT_SIDE

DEFAULT_ALIGN = 16


def round_to_align(value: float, align: int) -> int:
    """Round a dimension to the nearest multiple of align."""
    step = max(1, int(align))
    return max(step, int(value / step + 0.5) * step)


def parse_ratio(text: str) -> float:
    """Parse a width:height ratio into a float. Raises ValueError."""
    left, separator, right = text.partition(":")
    if not separator:
        raise ValueError("ratio needs width:height")

    width = float(left)
    height = float(right)
    if width <= 0 or height <= 0:
        raise ValueError("ratio parts must be positive")

    return width / height


def parse_size_overrides(text: str) -> dict[tuple[str, str], tuple[int, int]]:
    """Parse `resolution aspect = WxH` lines into a size table. Bad lines are skipped."""
    overrides: dict[tuple[str, str], tuple[int, int]] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue

        parts = key.split()
        size = value.strip().lower().replace(" ", "").split("x")
        if len(parts) != 2 or len(size) != 2:
            continue

        try:
            width = int(size[0])
            height = int(size[1])
        except ValueError:
            continue

        if width > 0 and height > 0:
            overrides[(parts[0], parts[1])] = (width, height)

    return overrides


def resolve_size(
    resolution: str,
    aspect_ratio: str,
    *,
    align: int,
    overrides: dict[tuple[str, str], tuple[int, int]],
) -> tuple[int, int]:
    """Return width and height for a resolution and aspect ratio. Overrides win."""
    override = overrides.get((resolution.strip(), aspect_ratio.strip()))
    if override is not None:
        return override

    short = _short_side(resolution)
    ratio = parse_ratio(aspect_ratio)
    if ratio >= 1.0:
        return round_to_align(short * ratio, align), round_to_align(short, align)

    return round_to_align(short, align), round_to_align(short / ratio, align)


def _short_side(resolution: str) -> int:
    key = resolution.strip()
    known = SHORT_SIDE.get(key)
    if known is not None:
        return known

    try:
        value = int(key)
    except ValueError as exc:
        raise ValueError(f"unknown resolution: {key}") from exc

    if value <= 0:
        raise ValueError("resolution must be positive")

    return value
