"""UPAI Output node: writes the model result into the pack temp folder."""

from __future__ import annotations

import os
import re
import tempfile
import wave
from fractions import Fraction
from pathlib import Path
from typing import Any

import folder_paths  # pyright: ignore[reportMissingImports]
import numpy as np
from comfy_api.latest import io, ui  # pyright: ignore[reportMissingImports]
from PIL import Image

from ..constants import NODE_UPAI_OUTPUT
from ..encoder import encode_mp4, select_encoder
from ..fileutil import replace_file
from ..jobs_output import register_output
from ..protocol import parse_run_id
from .io_types import CATEGORY, UPAI_MODEL

DEFAULT_FPS = 24.0
IMAGE_FORMATS = {
    "png": ("png", "PNG"),
    "jpg": ("jpg", "JPEG"),
    "jpeg": ("jpeg", "JPEG"),
    "webp": ("webp", "WEBP"),
}
_SAFE_JOB_ID = re.compile(r"[a-z0-9-]{1,64}")


def _to_numpy(value: Any) -> np.ndarray:
    """Convert a torch tensor or array-like value to a numpy array."""
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()

    return np.asarray(value)


def _temp_path(path: Path) -> Path:
    """Create an empty temp file next to path, for an atomic replace."""
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=path.suffix)
    os.close(handle)

    return Path(name)


def _job_folder(upai_job: str) -> tuple[Path, str, str]:
    raw = (upai_job or "").strip()
    parsed = parse_run_id(raw)
    if parsed is not None:
        name = parsed[0]
        prefix = f"{parsed[1]}-"
    else:
        name = raw or "editor"
        prefix = ""
        if _SAFE_JOB_ID.fullmatch(name) is None:
            raise ValueError("invalid upai_job")

    folder = Path(folder_paths.get_temp_directory()) / "upai" / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder, name, prefix


def _write_images(images: Any, folder: Path, image_format: str, prefix: str) -> list[Path]:
    data = _to_numpy(images)
    if data.ndim == 3:
        data = data[None, ...]

    extension, pil_format = IMAGE_FORMATS.get(
        (image_format or "").strip().lower(), IMAGE_FORMATS["png"]
    )
    files: list[Path] = []
    for index, frame in enumerate(data):
        pixels = np.clip(frame * 255.0, 0, 255).astype(np.uint8)
        image = Image.fromarray(pixels)
        if pil_format == "JPEG":
            image = image.convert("RGB")

        path = folder / f"{prefix}{index}.{extension}"
        temp = _temp_path(path)
        try:
            image.save(temp, format=pil_format)
            replace_file(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        files.append(path)

    return files


def _audio_pcm(audio: Any) -> tuple[np.ndarray, int] | None:
    if audio is None:
        return None

    waveform = _to_numpy(audio["waveform"])
    if waveform.ndim == 3:
        waveform = waveform[0]

    return waveform, int(audio["sample_rate"])


def _write_video(
    video: Any,
    images: Any,
    audio: Any,
    fps: float | None,
    folder: Path,
    crf: float,
    prefix: str,
) -> Path:
    if video is not None and hasattr(video, "get_components"):
        components = video.get_components()
        images = components.images
        audio = components.audio
        rate = components.frame_rate
    else:
        rate = Fraction(float(fps or DEFAULT_FPS))

    frames = _to_numpy(images)
    if frames.ndim == 3:
        frames = frames[None, ...]
    if frames.size == 0:
        raise ValueError("UPAI Output needs video frames")

    path = folder / f"{prefix}0.mp4"
    temp = _temp_path(path)
    try:
        select_encoder()
        encode_mp4(temp, frames, rate, _audio_pcm(audio), crf)
        replace_file(temp, path)
    finally:
        temp.unlink(missing_ok=True)

    return path


def _write_audio(audio: dict[str, Any], folder: Path, prefix: str) -> list[Path]:
    waveform = _to_numpy(audio["waveform"])
    sample_rate = int(audio["sample_rate"])
    if waveform.ndim == 2:
        waveform = waveform[None, ...]

    files: list[Path] = []
    for index, item in enumerate(waveform):
        channels = int(item.shape[0]) if item.ndim > 1 else 1
        if channels > 2:
            raise ValueError("audio has more than 2 channels")

        samples = item.T if item.ndim > 1 else item
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
        path = folder / f"{prefix}{index}.wav"
        temp = _temp_path(path)
        try:
            with wave.open(str(temp), "wb") as handle:
                handle.setnchannels(channels)
                handle.setsampwidth(2)
                handle.setframerate(sample_rate)
                handle.writeframes(pcm.tobytes())
            replace_file(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        files.append(path)

    return files


def _is_video(value: Any) -> bool:
    """True for a ComfyUI VIDEO value, false for an image tensor."""
    return value is not None and hasattr(value, "save_to")


def _preview(
    images: Any,
    video_path: Path | None,
    audio: Any,
    job_name: str,
) -> Any:
    if video_path is not None:
        return ui.PreviewVideo(
            [ui.SavedResult(video_path.name, f"upai/{job_name}", io.FolderType.temp)]
        )
    if images is not None:
        return ui.PreviewImage(images)
    if audio is not None:
        return ui.PreviewAudio(audio)

    return None


class UPaiOutput(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id=NODE_UPAI_OUTPUT,
            display_name="UPAI Output",
            category=CATEGORY,
            is_output_node=True,
            inputs=[
                UPAI_MODEL.Input("model"),
                io.MultiType.Input("images", [io.Image, io.Video], optional=True),
                io.Video.Input("video", optional=True),
                io.Audio.Input("audio", optional=True),
                io.Float.Input("fps", default=DEFAULT_FPS, min=0.01, max=240.0, optional=True),
                io.Combo.Input(
                    "format",
                    options=["auto", "mp4", "png", "webp", "jpeg"],
                    default="auto",
                ),
                io.Int.Input("crf", default=18, min=0, max=51, step=1),
                io.Boolean.Input("preview", default=False),
                io.String.Input("upai_job", default="", tooltip="Set by the job route."),
            ],
        )

    @classmethod
    def fingerprint_inputs(cls, upai_job: str, **kwargs: Any) -> str:
        return upai_job or ""

    @classmethod
    def execute(
        cls,
        model: Any,
        upai_job: str,
        format: str,
        crf: float,
        preview: bool,
        images: Any = None,
        video: Any = None,
        audio: Any = None,
        fps: float | None = None,
    ) -> io.NodeOutput:
        folder, job_name, prefix = _job_folder(upai_job)
        kind = model.get("kind") if isinstance(model, dict) else None
        files: list[Path] = []
        video_path: Path | None = None

        if kind == "video":
            if video is not None:
                video_path = _write_video(video, None, None, fps, folder, crf, prefix)
            elif _is_video(images):
                video_path = _write_video(images, None, None, fps, folder, crf, prefix)
            elif images is not None:
                video_path = _write_video(None, images, audio, fps, folder, crf, prefix)
            elif audio is not None:
                files = _write_audio(audio, folder, prefix)
            else:
                raise ValueError("UPAI Output needs images, video or audio")
        elif kind == "image":
            if images is not None:
                files = _write_images(images, folder, format, prefix)
            elif audio is not None:
                files = _write_audio(audio, folder, prefix)
            else:
                raise ValueError("UPAI Output needs images or audio")
        elif video is not None:
            video_path = _write_video(video, None, None, fps, folder, crf, prefix)
        elif _is_video(images):
            video_path = _write_video(images, None, None, fps, folder, crf, prefix)
        elif images is not None:
            files = _write_images(images, folder, format, prefix)
        elif audio is not None:
            files = _write_audio(audio, folder, prefix)
        else:
            raise ValueError("UPAI Output needs images, video or audio")

        if video_path is not None:
            files = [video_path]

        if job_name != "editor" and upai_job.strip():
            register_output(upai_job.strip(), [str(path) for path in files])

        preview_ui = _preview(images, video_path, audio, job_name) if preview else None
        return io.NodeOutput(ui=preview_ui)
