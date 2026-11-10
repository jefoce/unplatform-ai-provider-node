"""UPAI start and end frame nodes. Missing or bad test files fall back cleanly."""

from __future__ import annotations

from typing import Any

from comfy_api.latest import io  # pyright: ignore[reportMissingImports]

from ..constants import (
    ALLOWED_IMAGE_FORMATS,
    NODE_UPAI_END_FRAME,
    NODE_UPAI_START_FRAME,
)
from .io_types import CATEGORY
from .media import input_files
from .refs_common import _frame_result, _validate_frame


class UPaiStartFrame(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_START_FRAME,
            display_name="UPAI Start Frame",
            category=CATEGORY,
            inputs=[
                io.Boolean.Input("required", default=False),
                io.Combo.Input(
                    "image",
                    options=input_files(ALLOWED_IMAGE_FORMATS),
                    upload=io.UploadType.image,
                ),
            ],
            outputs=[io.Image.Output("image"), io.Boolean.Output("present")],
        )

    @classmethod
    def validate_inputs(cls, required: bool = False, **kwargs: Any) -> bool | str:
        return _validate_frame(kwargs.get("image"), required=required, label="UPAI Start Frame")

    @classmethod
    def execute(cls, required: bool, image: str) -> io.NodeOutput:
        return io.NodeOutput(*_frame_result(image, "UPAI Start Frame", required))


class UPaiEndFrame(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_END_FRAME,
            display_name="UPAI End Frame",
            category=CATEGORY,
            inputs=[
                io.Boolean.Input("required", default=False),
                io.Combo.Input(
                    "image",
                    options=input_files(ALLOWED_IMAGE_FORMATS),
                    upload=io.UploadType.image,
                ),
            ],
            outputs=[io.Image.Output("image"), io.Boolean.Output("present")],
        )

    @classmethod
    def validate_inputs(cls, required: bool = False, **kwargs: Any) -> bool | str:
        return _validate_frame(kwargs.get("image"), required=required, label="UPAI End Frame")

    @classmethod
    def execute(cls, required: bool, image: str) -> io.NodeOutput:
        return io.NodeOutput(*_frame_result(image, "UPAI End Frame", required))
