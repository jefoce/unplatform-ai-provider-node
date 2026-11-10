"""Minimal ComfyUI stubs so node tests run without ComfyUI or torch."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import numpy as np


class InputSpec:
    def __init__(
        self,
        id: str,
        io_type: str,
        optional: bool = False,
        **kwargs: Any,
    ) -> None:
        self.id = id
        self.io_type = io_type
        self.optional = optional
        self.kwargs = kwargs


class OutputSpec:
    def __init__(self, id: str | None, io_type: str, **kwargs: Any) -> None:
        self.id = id
        self.io_type = io_type
        self.kwargs = kwargs


class Leaf:
    """One fake ComfyType with Input and Output constructors."""

    def __init__(self, io_type: str) -> None:
        self.io_type = io_type

    def Input(self, id: str, optional: bool = False, **kwargs: Any) -> InputSpec:  # noqa: N802
        return InputSpec(id, self.io_type, optional, **kwargs)

    def Output(self, id: str | None = None, **kwargs: Any) -> OutputSpec:  # noqa: N802
        return OutputSpec(id, self.io_type, **kwargs)


class MultiTypeInput(InputSpec):
    def __init__(
        self,
        id: str,
        types: list[Leaf],
        optional: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(id, ",".join(item.io_type for item in types), optional, **kwargs)


class MultiType:
    Input = MultiTypeInput


class Schema:
    def __init__(
        self,
        node_id: str,
        display_name: str | None = None,
        category: str = "",
        inputs: list[InputSpec] | None = None,
        outputs: list[OutputSpec] | None = None,
        is_output_node: bool = False,
        **kwargs: Any,
    ) -> None:
        self.node_id = node_id
        self.display_name = display_name
        self.category = category
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.is_output_node = is_output_node
        self.kwargs = kwargs


class ComfyNode:
    pass


class ComfyExtension:
    async def get_node_list(self) -> list[type[ComfyNode]]:
        raise NotImplementedError


class NodeOutput:
    def __init__(self, *args: Any, ui: Any = None) -> None:
        self.args = args
        self.ui = ui


class FolderType:
    input = "input"
    output = "output"
    temp = "temp"


class UploadType:
    image = "image_upload"
    audio = "audio_upload"
    video = "video_upload"
    model = "file_upload"


class Hidden:
    prompt = "prompt"
    extra_pnginfo = "extra_pnginfo"


class SavedResult(dict[str, Any]):
    def __init__(self, filename: str, subfolder: str, type: str) -> None:
        super().__init__(filename=filename, subfolder=subfolder, type=type)


class PreviewImage:
    def __init__(self, image: Any, animated: bool = False, cls: Any = None, **kwargs: Any) -> None:
        self.image = image
        self.animated = animated


class PreviewVideo:
    def __init__(self, values: list[SavedResult], **kwargs: Any) -> None:
        self.values = values


class PreviewAudio:
    def __init__(self, audio: dict[str, Any], cls: Any = None, **kwargs: Any) -> None:
        self.audio = audio


class VideoFromFile:
    def __init__(self, path: str) -> None:
        self.path = path

    def get_frame_rate(self) -> float:
        return 24.0

    def get_duration(self) -> float:
        return 2.0

    def get_frame_count(self) -> int:
        return 48

    def save_to(self, path: str, **kwargs: Any) -> None:
        Path(path).write_bytes(b"video")


class VideoFromComponents:
    def __init__(self, components: VideoComponents, **kwargs: Any) -> None:
        self.components = components

    def save_to(self, path: str, **kwargs: Any) -> None:
        Path(path).write_bytes(b"video")


class VideoComponents:
    def __init__(
        self,
        images: Any,
        frame_rate: Any,
        audio: Any = None,
        metadata: Any = None,
        alpha: Any = None,
    ) -> None:
        self.images = images
        self.frame_rate = frame_rate
        self.audio = audio
        self.metadata = metadata
        self.alpha = alpha


class VideoCodec:
    H264 = "h264"


class VideoContainer:
    MP4 = "mp4"


class _Input:
    pass


class _InputImpl:
    VideoFromFile = VideoFromFile
    VideoFromComponents = VideoFromComponents


class _Types:
    VideoComponents = VideoComponents
    VideoCodec = VideoCodec
    VideoContainer = VideoContainer


def _make_io() -> ModuleType:
    module = ModuleType("comfy_api.latest.io")
    for name, value in (
        ("ComfyNode", ComfyNode),
        ("Schema", Schema),
        ("NodeOutput", NodeOutput),
        ("FolderType", FolderType),
        ("UploadType", UploadType),
        ("Hidden", Hidden),
        ("MultiType", MultiType),
        ("Custom", lambda io_type: Leaf(io_type)),
    ):
        setattr(module, name, value)
    for name in ("String", "Int", "Float", "Boolean", "Combo", "Image", "Video", "Audio", "Mask"):
        setattr(module, name, Leaf(name.upper()))
    return module


def _make_ui() -> ModuleType:
    module = ModuleType("comfy_api.latest.ui")
    for name, value in (
        ("SavedResult", SavedResult),
        ("PreviewImage", PreviewImage),
        ("PreviewVideo", PreviewVideo),
        ("PreviewAudio", PreviewAudio),
    ):
        setattr(module, name, value)
    return module


def _make_folder_paths() -> ModuleType:
    module = ModuleType("folder_paths")
    state = {"input": Path.cwd(), "temp": Path.cwd(), "user": Path.cwd()}

    def get_input_directory() -> str:
        return str(state["input"])

    def get_temp_directory() -> str:
        return str(state["temp"])

    def get_user_directory() -> str:
        return str(state["user"])

    def get_annotated_filepath(name: str, default_dir: str | None = None) -> str:
        base = Path(default_dir) if default_dir else state["input"]
        if name.endswith("[input]"):
            name = name[:-8]
            base = state["input"]
        elif name.endswith("[temp]"):
            name = name[:-7]
            base = state["temp"]
        elif name.endswith("[output]"):
            name = name[:-9]
            base = state["output"]

        path = Path(name)
        return str(path if path.is_absolute() else base / path)

    for name, value in (
        ("get_input_directory", get_input_directory),
        ("get_temp_directory", get_temp_directory),
        ("get_user_directory", get_user_directory),
        ("get_annotated_filepath", get_annotated_filepath),
        ("set_directories", lambda **kwargs: state.update(kwargs)),
    ):
        setattr(module, name, value)
    return module


def _make_torch() -> ModuleType:
    module = ModuleType("torch")
    for name, value in (
        ("from_numpy", np.asarray),
        ("zeros", lambda shape, dtype=None: np.zeros(shape, dtype=dtype or np.float32)),
        ("cat", lambda tensors, dim=0: np.concatenate(tensors, axis=dim)),
        ("float32", np.float32),
        ("int16", np.int16),
        ("int32", np.int32),
    ):
        setattr(module, name, value)
    return module


def install() -> None:
    """Install the fake modules once. Safe to call from several test modules."""
    if "comfy_api.latest" in sys.modules:
        return

    package = ModuleType("comfy_api")
    package.__path__ = []  # type: ignore[attr-defined]
    latest = ModuleType("comfy_api.latest")
    for name, value in (
        ("ComfyExtension", ComfyExtension),
        ("io", _make_io()),
        ("ui", _make_ui()),
        ("Input", _Input),
        ("InputImpl", _InputImpl),
        ("Types", _Types),
    ):
        setattr(latest, name, value)

    sys.modules["comfy_api"] = package
    sys.modules["comfy_api.latest"] = latest
    sys.modules["folder_paths"] = _make_folder_paths()
    sys.modules["torch"] = _make_torch()


install()


def set_directories(**paths: Path) -> None:
    """Point the fake folder_paths module at test directories."""
    module = cast(Any, sys.modules["folder_paths"])
    module.set_directories(**paths)
