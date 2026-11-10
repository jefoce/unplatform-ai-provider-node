"""UPAI image, video and audio reference nodes. Missing or bad test files fall back cleanly."""

from __future__ import annotations

from typing import Any

from comfy_api.latest import io  # pyright: ignore[reportMissingImports]

from ..constants import (
    ALLOWED_IMAGE_FORMATS,
    NODE_UPAI_AUDIO_REF,
    NODE_UPAI_IMAGE_REF,
    NODE_UPAI_VIDEO_REF,
)
from .io_types import CATEGORY
from .media import input_files
from .refs_common import (
    MAX_REFERENCE_INDEX,
    VIDEO_SUFFIXES,
    _audio_result,
    _check_index,
    _image_result,
    _validate_audio,
    _validate_index,
    _video_result,
)


class UPaiImageRef(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_IMAGE_REF,
            display_name="UPAI Image Ref",
            category=CATEGORY,
            inputs=[
                io.Int.Input("index", default=1, min=1, max=MAX_REFERENCE_INDEX, step=1),
                io.Boolean.Input("required", default=False),
                io.Combo.Input(
                    "image",
                    options=input_files(ALLOWED_IMAGE_FORMATS),
                    upload=io.UploadType.image,
                ),
            ],
            outputs=[
                io.Image.Output("image"),
                io.Mask.Output("mask"),
                io.Boolean.Output("present"),
                io.Int.Output("width"),
                io.Int.Output("height"),
            ],
        )

    @classmethod
    def validate_inputs(cls, index: int, **kwargs: Any) -> bool | str:
        return _validate_index(index)

    @classmethod
    def execute(cls, index: int, required: bool, image: str) -> io.NodeOutput:
        slot = _check_index(index)
        result, mask, present, width, height = _image_result(
            image, f"UPAI Image Ref {slot}", required
        )
        return io.NodeOutput(result, mask, present, width, height)


class UPaiVideoRef(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_VIDEO_REF,
            display_name="UPAI Video Ref",
            category=CATEGORY,
            inputs=[
                io.Int.Input("index", default=1, min=1, max=MAX_REFERENCE_INDEX, step=1),
                io.Boolean.Input("required", default=False),
                io.Combo.Input(
                    "video",
                    options=input_files(VIDEO_SUFFIXES),
                    upload=io.UploadType.video,
                ),
            ],
            outputs=[
                io.Video.Output("video"),
                io.Boolean.Output("present"),
                io.Float.Output("fps"),
                io.Float.Output("duration"),
                io.Int.Output("frame_count"),
            ],
        )

    @classmethod
    def validate_inputs(cls, index: int, **kwargs: Any) -> bool | str:
        return _validate_index(index)

    @classmethod
    def execute(cls, index: int, required: bool, video: str) -> io.NodeOutput:
        slot = _check_index(index)
        return io.NodeOutput(*_video_result(video, f"UPAI Video Ref {slot}", required))


class UPaiAudioRef(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_AUDIO_REF,
            display_name="UPAI Audio Ref",
            category=CATEGORY,
            inputs=[
                io.Int.Input("index", default=1, min=1, max=MAX_REFERENCE_INDEX, step=1),
                io.Boolean.Input("required", default=False),
                io.String.Input(
                    "audio",
                    default="",
                    tooltip="Audio file name under the ComfyUI input directory.",
                ),
            ],
            outputs=[
                io.Audio.Output("audio"),
                io.Boolean.Output("present"),
                io.Float.Output("duration"),
            ],
        )

    @classmethod
    def validate_inputs(cls, index: int, required: bool = False, **kwargs: Any) -> bool | str:
        return _validate_audio(index, kwargs.get("audio"), required=required)

    @classmethod
    def execute(cls, index: int, required: bool, audio: str) -> io.NodeOutput:
        slot = _check_index(index)
        return io.NodeOutput(*_audio_result(audio, f"UPAI Audio Ref {slot}", required))
