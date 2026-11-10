"""Compute model sizes from resolutions, aspect ratios and overrides."""

from collections.abc import Mapping

from .sizing import parse_size_overrides, resolve_size


def _size_for(
    resolution: str,
    aspect_ratio: str,
    align: int,
    overrides: dict[tuple[str, str], tuple[int, int]],
) -> str | None:
    try:
        width, height = resolve_size(resolution, aspect_ratio, align=align, overrides=overrides)
    except ValueError:
        return None

    return f"{width}x{height}"


def override_resolutions(text: str) -> frozenset[str]:
    """Resolution labels present in parsed size overrides."""
    return frozenset(resolution for resolution, _ in parse_size_overrides(text))


def build_sizes(
    resolutions: tuple[str, ...],
    aspect_ratios: tuple[str, ...],
    align: int,
    text: str,
) -> Mapping[str, Mapping[str, str]]:
    """Build the resolution to aspect ratio size table."""
    overrides = parse_size_overrides(text)
    table: dict[str, dict[str, str]] = {}
    for resolution in resolutions:
        row: dict[str, str] = {}
        for aspect in aspect_ratios:
            size = _size_for(resolution, aspect, align, overrides)
            if size is not None:
                row[aspect] = size

        table[resolution] = row

    return table
