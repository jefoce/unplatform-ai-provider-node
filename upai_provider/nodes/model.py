"""UPAI Model node: one metadata spec per served model."""

from comfy_api.latest import io  # pyright: ignore[reportMissingImports]

from ..constants import NODE_UPAI_MODEL
from ..protocol import validate_reference_label
from .io_types import CATEGORY, UPAI_LIMITS, UPAI_MODEL


class UPaiModel(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_MODEL,
            display_name="UPAI Model",
            category=CATEGORY,
            inputs=[
                io.String.Input(
                    "id", default="", tooltip="Model id. Empty falls back to the file name."
                ),
                io.String.Input("name", default=""),
                io.String.Input("description", default="", multiline=True),
                io.Combo.Input("kind", options=["video", "image"], default="video"),
                io.Boolean.Input("enabled", default=True),
                io.Float.Input("price_per_run_usd", default=0.0, min=0.0, max=1000.0, step=0.001),
                io.String.Input(
                    "prompt_reference_label",
                    default="",
                    optional=True,
                    tooltip=(
                        "Template for client reference labels. Placeholders: {kind} lowercase "
                        "kind, {Kind} capitalized, {n} 1-based slot, {i} 0-based slot. "
                        "Must contain {n} or {i}."
                    ),
                ),
                io.String.Input(
                    "prompt_reference_label_image",
                    default="",
                    optional=True,
                    tooltip=(
                        "Image reference label template. Placeholders: {kind} lowercase "
                        "kind, {Kind} capitalized, {n} 1-based slot, {i} 0-based slot. "
                        "Must contain {n} or {i}."
                    ),
                ),
                io.String.Input(
                    "prompt_reference_label_video",
                    default="",
                    optional=True,
                    tooltip=(
                        "Video reference label template. Placeholders: {kind} lowercase "
                        "kind, {Kind} capitalized, {n} 1-based slot, {i} 0-based slot. "
                        "Must contain {n} or {i}."
                    ),
                ),
                io.String.Input(
                    "prompt_reference_label_audio",
                    default="",
                    optional=True,
                    tooltip=(
                        "Audio reference label template. Placeholders: {kind} lowercase "
                        "kind, {Kind} capitalized, {n} 1-based slot, {i} 0-based slot. "
                        "Must contain {n} or {i}."
                    ),
                ),
                UPAI_LIMITS.Input("limits", optional=True),
            ],
            outputs=[UPAI_MODEL.Output("model")],
        )

    @classmethod
    def validate_inputs(
        cls,
        prompt_reference_label: str = "",
        prompt_reference_label_image: str = "",
        prompt_reference_label_video: str = "",
        prompt_reference_label_audio: str = "",
        **kwargs: object,
    ) -> bool | str:
        for kind, value in (
            ("image", prompt_reference_label_image),
            ("video", prompt_reference_label_video),
            ("audio", prompt_reference_label_audio),
        ):
            error = validate_reference_label(value)
            if error is not None:
                return f"{kind}: {error}"

        return validate_reference_label(prompt_reference_label) or True

    @classmethod
    def execute(
        cls,
        id: str,
        name: str,
        description: str,
        kind: str,
        enabled: bool,
        price_per_run_usd: float,
        prompt_reference_label: str = "",
        prompt_reference_label_image: str = "",
        prompt_reference_label_video: str = "",
        prompt_reference_label_audio: str = "",
        limits: object = None,
    ) -> io.NodeOutput:
        spec = {
            "id": (id or "").strip(),
            "name": (name or "").strip(),
            "description": description or "",
            "kind": kind,
            "enabled": bool(enabled),
            "price_per_run_usd": float(price_per_run_usd),
            "prompt_reference_label": (prompt_reference_label or "").strip(),
            "prompt_reference_label_image": (prompt_reference_label_image or "").strip(),
            "prompt_reference_label_video": (prompt_reference_label_video or "").strip(),
            "prompt_reference_label_audio": (prompt_reference_label_audio or "").strip(),
            "limits": dict(limits) if isinstance(limits, dict) else {},
        }
        return io.NodeOutput(spec)
