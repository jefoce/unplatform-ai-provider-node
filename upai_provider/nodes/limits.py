"""UPAI Limits node: optional per-model capability overrides."""

from comfy_api.latest import io  # pyright: ignore[reportMissingImports]

from ..constants import NODE_UPAI_LIMITS
from .io_types import CATEGORY, UPAI_LIMITS

MAX_REFERENCE = 16
MAX_COUNT = 64


class UPaiLimits(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_LIMITS,
            display_name="UPAI Limits",
            category=CATEGORY,
            inputs=[
                io.Int.Input("image_max", default=-1, min=-1, max=MAX_REFERENCE),
                io.Int.Input("image_required", default=0, min=0, max=MAX_REFERENCE),
                io.Int.Input("video_max", default=-1, min=-1, max=MAX_REFERENCE),
                io.Int.Input("video_required", default=0, min=0, max=MAX_REFERENCE),
                io.Int.Input("audio_max", default=-1, min=-1, max=MAX_REFERENCE),
                io.Int.Input("audio_required", default=0, min=0, max=MAX_REFERENCE),
                io.Combo.Input(
                    "start_frame", options=["off", "optional", "required"], default="off"
                ),
                io.Combo.Input("end_frame", options=["off", "optional", "required"], default="off"),
                io.Float.Input("duration_min", default=0.0, min=0.0, max=3600.0, step=0.5),
                io.Float.Input("duration_max", default=0.0, min=0.0, max=3600.0, step=0.5),
                io.Int.Input("count_max", default=0, min=0, max=MAX_COUNT),
            ],
            outputs=[UPAI_LIMITS.Output("limits")],
        )

    @classmethod
    def execute(
        cls,
        image_max: int,
        image_required: int,
        video_max: int,
        video_required: int,
        audio_max: int,
        audio_required: int,
        start_frame: str,
        end_frame: str,
        duration_min: float,
        duration_max: float,
        count_max: int,
    ) -> io.NodeOutput:
        limits = {
            "image_max": int(image_max),
            "image_required": int(image_required),
            "video_max": int(video_max),
            "video_required": int(video_required),
            "audio_max": int(audio_max),
            "audio_required": int(audio_required),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "duration_min": float(duration_min),
            "duration_max": float(duration_max),
            "count_max": int(count_max),
        }
        return io.NodeOutput(limits)
