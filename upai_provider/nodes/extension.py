"""V3 extension exposing every UPAI node."""

from comfy_api.latest import ComfyExtension, io  # pyright: ignore[reportMissingImports]

from .frames import UPaiEndFrame, UPaiStartFrame
from .limits import UPaiLimits
from .model import UPaiModel
from .output import UPaiOutput
from .prompt import UPaiPrompt
from .refs import UPaiAudioRef, UPaiImageRef, UPaiVideoRef
from .settings import UPaiSettings

NODE_CLASSES = (
    UPaiModel,
    UPaiLimits,
    UPaiPrompt,
    UPaiImageRef,
    UPaiVideoRef,
    UPaiAudioRef,
    UPaiStartFrame,
    UPaiEndFrame,
    UPaiSettings,
    UPaiOutput,
)


class UPaiExtension(ComfyExtension):
    """Register the UPAI nodes with ComfyUI."""

    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return list(NODE_CLASSES)
