"""Custom wire types and shared labels for the UPAI V3 nodes."""

from comfy_api.latest import io  # pyright: ignore[reportMissingImports]

from ..constants import WS_TYPE_UPAI_LIMITS, WS_TYPE_UPAI_MODEL

CATEGORY = "Unplatform AI"

UPAI_MODEL = io.Custom(WS_TYPE_UPAI_MODEL)
UPAI_LIMITS = io.Custom(WS_TYPE_UPAI_LIMITS)
