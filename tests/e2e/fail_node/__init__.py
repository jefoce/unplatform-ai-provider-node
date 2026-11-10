"""Test-only ComfyUI node that fails when its seed input is odd."""

from __future__ import annotations

from typing import Any


class UpaiFailNode:
    """Raise on an odd seed so E2E runs mode can exercise a child failure."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:  # noqa: N802 - ComfyUI requires this name
        return {
            "required": {
                "image": ("IMAGE",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "run"
    CATEGORY = "upai-e2e"

    def run(self, image: Any, seed: int) -> tuple[Any]:
        if seed % 2 == 1:
            raise RuntimeError("upai e2e fail node: odd seed")

        return (image,)


NODE_CLASS_MAPPINGS = {"UpaiFailNode": UpaiFailNode}
NODE_DISPLAY_NAME_MAPPINGS = {"UpaiFailNode": "UPAI E2E Fail"}
