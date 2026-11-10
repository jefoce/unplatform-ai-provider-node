"""UPAI Prompt node: positive and negative prompt text."""

from comfy_api.latest import io  # pyright: ignore[reportMissingImports]

from ..constants import NODE_UPAI_PROMPT
from .io_types import CATEGORY


class UPaiPrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_PROMPT,
            display_name="UPAI Prompt",
            category=CATEGORY,
            inputs=[
                io.String.Input("text", default="", multiline=True),
                io.String.Input("negative", default="", multiline=True),
                io.Boolean.Input("required", default=False),
                io.Int.Input("max_chars", default=2000, min=1, max=100_000),
            ],
            outputs=[
                io.String.Output("prompt"),
                io.String.Output("negative"),
            ],
        )

    @classmethod
    def execute(
        cls,
        text: str,
        negative: str,
        required: bool,
        max_chars: int,
    ) -> io.NodeOutput:
        return io.NodeOutput(text or "", negative or "")
