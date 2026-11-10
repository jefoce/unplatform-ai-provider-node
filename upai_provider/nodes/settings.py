"""UPAI Settings node: resolution, frame, duration, count and seed defaults."""

from __future__ import annotations

import logging
from typing import Any

from comfy_api.latest import io  # pyright: ignore[reportMissingImports]

from ..constants import (
    IMAGE_ASPECT_RATIOS,
    IMAGE_RESOLUTIONS,
    NODE_UPAI_SETTINGS,
)
from ..sizing import DEFAULT_ALIGN, parse_size_overrides, resolve_size
from .io_types import CATEGORY
from .settings_math import clamp, clamp_count, round_frames

logger = logging.getLogger(__name__)

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024


def _labels(text: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in text.split(",") if item.strip())


class UPaiSettings(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_SETTINGS,
            display_name="UPAI Settings",
            category=CATEGORY,
            inputs=[
                io.String.Input(
                    "resolutions",
                    default=",".join(IMAGE_RESOLUTIONS),
                    multiline=True,
                    tooltip="Comma-separated resolutions offered to the client.",
                ),
                io.String.Input(
                    "aspect_ratios",
                    default=",".join(IMAGE_ASPECT_RATIOS),
                    multiline=True,
                    tooltip="Comma-separated aspect ratios offered to the client.",
                ),
                io.String.Input("default_resolution", default="1K"),
                io.String.Input("default_aspect_ratio", default="16:9"),
                io.Int.Input("align", default=DEFAULT_ALIGN, min=1, max=128),
                io.String.Input(
                    "size_overrides",
                    default="",
                    multiline=True,
                    tooltip="One `resolution aspect = WxH` size per line.",
                ),
                io.Float.Input("duration_min", default=1.0, min=0.0, max=3600.0, step=0.5),
                io.Float.Input("duration_max", default=10.0, min=0.0, max=3600.0, step=0.5),
                io.Float.Input("duration_default", default=5.0, min=0.0, max=3600.0, step=0.5),
                io.Float.Input("duration_step", default=0.5, min=0.01, max=3600.0, step=0.01),
                io.Float.Input("fps", default=16.0, min=0.01, max=240.0, step=0.01),
                io.Int.Input("frame_mod", default=4, min=1, max=64),
                io.Int.Input("frame_add", default=1, min=0, max=64),
                io.Int.Input("count_max", default=4, min=1, max=64),
                io.Combo.Input("count_mode", options=["batch", "runs"], default="batch"),
                io.String.Input("test_resolution", default="1K"),
                io.String.Input("test_aspect_ratio", default="16:9"),
                io.Float.Input("test_duration", default=5.0, min=0.0, max=3600.0, step=0.5),
                io.Int.Input("test_count", default=1, min=1, max=64),
                io.Int.Input("test_seed", default=0, min=0, max=0xFFFFFFFF),
            ],
            outputs=[
                io.Int.Output("width"),
                io.Int.Output("height"),
                io.Int.Output("frames"),
                io.Float.Output("fps"),
                io.Float.Output("duration"),
                io.Int.Output("count"),
                io.Int.Output("seed"),
            ],
        )

    @classmethod
    def validate_inputs(
        cls,
        resolutions: str,
        aspect_ratios: str,
        default_resolution: str,
        default_aspect_ratio: str,
        test_resolution: str,
        test_aspect_ratio: str,
        **kwargs: Any,
    ) -> bool | str:
        resolution_labels = _labels(resolutions)
        aspect_labels = _labels(aspect_ratios)
        if not resolution_labels:
            return "resolutions is empty"
        if not aspect_labels:
            return "aspect_ratios is empty"

        for field, value, allowed in (
            ("default_resolution", default_resolution, resolution_labels),
            ("default_aspect_ratio", default_aspect_ratio, aspect_labels),
            ("test_resolution", test_resolution, resolution_labels),
            ("test_aspect_ratio", test_aspect_ratio, aspect_labels),
        ):
            if value.strip() not in allowed:
                return f"{field} {value!r} is not one of {', '.join(allowed)}"

        return True

    @classmethod
    def execute(
        cls,
        resolutions: str,
        aspect_ratios: str,
        default_resolution: str,
        default_aspect_ratio: str,
        align: int,
        size_overrides: str,
        duration_min: float,
        duration_max: float,
        duration_default: float,
        duration_step: float,
        fps: float,
        frame_mod: int,
        frame_add: int,
        count_max: int,
        count_mode: str,
        test_resolution: str,
        test_aspect_ratio: str,
        test_duration: float,
        test_count: int,
        test_seed: int,
    ) -> io.NodeOutput:
        resolution = test_resolution or default_resolution
        aspect_ratio = test_aspect_ratio or default_aspect_ratio
        overrides = parse_size_overrides(size_overrides)
        try:
            width, height = resolve_size(resolution, aspect_ratio, align=align, overrides=overrides)
        except ValueError:
            logger.warning(
                "UPAI Settings: invalid size inputs, using %sx%s", DEFAULT_WIDTH, DEFAULT_HEIGHT
            )
            width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT

        requested = test_duration if test_duration > 0 else duration_default
        duration = clamp(requested, duration_min, duration_max)
        frame_rate = max(0.01, float(fps))
        frames = round_frames(duration, fps=frame_rate, mod=frame_mod, add=frame_add)
        count = clamp_count(test_count, count_max)

        return io.NodeOutput(width, height, frames, frame_rate, duration, count, int(test_seed))
