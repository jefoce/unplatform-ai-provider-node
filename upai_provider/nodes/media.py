"""Load user files and build tensors. Bad files return None, never raise at the node edge."""

from __future__ import annotations

import logging
from pathlib import Path, PurePath
from typing import Any

import av
import folder_paths  # pyright: ignore[reportMissingImports]
import numpy as np
import torch  # pyright: ignore[reportMissingImports]
from comfy_api.latest import InputImpl  # pyright: ignore[reportMissingImports]
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

PLACEHOLDER_SIZE = 64


def _lexical_path(name: str, root: PurePath) -> PurePath | None:
    """Join name to root and reject any path that leaves it."""
    candidate = type(root)(name)
    if not candidate.is_absolute():
        candidate = root / candidate

    if ".." in candidate.parts or not candidate.is_relative_to(root):
        return None

    return candidate


def resolve_file(value: str | None) -> Path | None:
    """Resolve a widget file value to an existing path inside the input directory."""
    if not value or value.strip().lower() in {"", "none"}:
        return None

    name = value.strip()
    try:
        root = Path(folder_paths.get_input_directory()).resolve()
        candidate = Path(name)
        if candidate.is_absolute():
            # Resolve before containment so a symlinked input root still matches.
            if ".." in candidate.parts:
                logger.warning("test file %r is outside the input directory", name)
                return None
        else:
            lexical = _lexical_path(name, root)
            if lexical is None:
                logger.warning("test file %r is outside the input directory", name)
                return None

            candidate = lexical

        resolved = Path(candidate).resolve()
    except (OSError, RuntimeError, ValueError):
        logger.warning("test file %r could not be resolved", name)
        return None

    if not resolved.is_relative_to(root):
        logger.warning("test file %r is outside the input directory", name)
        return None

    return resolved if resolved.is_file() else None


def input_files(suffixes: tuple[str, ...]) -> list[str]:
    """List input files matching the suffixes, for a test-file widget."""
    try:
        names = folder_paths.get_input_directory()
        entries = Path(names).iterdir()
    except OSError:
        return []

    allowed = {suffix.lower().lstrip(".") for suffix in suffixes}
    return sorted(
        entry.name
        for entry in entries
        if entry.is_file() and entry.suffix.lower().lstrip(".") in allowed
    )


def placeholder_image() -> tuple[Any, Any]:
    """Return a 64x64 black image and an empty mask."""
    image = torch.zeros((1, PLACEHOLDER_SIZE, PLACEHOLDER_SIZE, 3))
    mask = torch.zeros((1, PLACEHOLDER_SIZE, PLACEHOLDER_SIZE))
    return image, mask


def load_image(path: Path) -> tuple[Any, Any]:
    """Load an image file as a batch tensor and an alpha mask."""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        width, height = image.size
        if "A" in image.getbands():
            alpha = np.asarray(image.getchannel("A"), dtype=np.float32) / 255.0
            mask = torch.from_numpy(1.0 - alpha)[None,]
        else:
            mask = torch.zeros((1, height, width))

        pixels = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0

    return torch.from_numpy(pixels)[None,], mask


def load_video(path: Path) -> Any:
    """Open a video file lazily through the ComfyUI input implementation."""
    return InputImpl.VideoFromFile(str(path))


def load_audio(path: Path) -> dict[str, Any]:
    """Decode an audio file to a waveform batch and sample rate."""
    with av.open(str(path)) as container:
        if not container.streams.audio:
            raise ValueError("no audio stream")

        stream = container.streams.audio[0]
        sample_rate = int(stream.codec_context.sample_rate)
        channels = int(stream.channels)
        frames: list[Any] = []
        for frame in container.decode(streams=stream.index):
            buffer = torch.from_numpy(frame.to_ndarray())  # pyright: ignore[reportAttributeAccessIssue]
            if buffer.shape[0] != channels:
                buffer = buffer.view(-1, channels).t()
            frames.append(buffer)

        if not frames:
            raise ValueError("no audio frames")

        waveform = torch.cat(frames, dim=1)

    return {"waveform": _as_float(waveform).unsqueeze(0), "sample_rate": sample_rate}


def _as_float(waveform: Any) -> Any:
    if waveform.dtype.is_floating_point:
        return waveform
    if waveform.dtype == torch.int16:
        return waveform.float() / (2**15)
    if waveform.dtype == torch.int32:
        return waveform.float() / (2**31)

    return waveform.float()
