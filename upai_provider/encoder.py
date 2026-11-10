"""Pick an H.264 encoder that opens here and encode MP4 through it."""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

import av
import numpy as np
from av.error import FFmpegError

logger = logging.getLogger(__name__)

ENCODERS = ("libx264", "h264_nvenc", "h264_videotoolbox", "libopenh264", "mpeg4")
_PROBE_WIDTH = 64
_PROBE_HEIGHT = 64
_chosen: str | None = None
_supports_crf: bool | None = None


def _open_encoder(name: str, crf: float | None) -> Any:
    """Open an encoder context with a tiny config. Raises when it cannot open."""
    context = cast(Any, av.CodecContext.create(name, "w"))
    context.width = _PROBE_WIDTH
    context.height = _PROBE_HEIGHT
    context.pix_fmt = "yuv420p"
    context.time_base = Fraction(1, 24)
    if crf is not None:
        context.options = {"crf": str(crf)}
    context.open()

    return context


def select_encoder(crf: float = 18.0) -> str:
    """Return the first encoder that opens, cached per process."""
    global _chosen, _supports_crf
    if _chosen is not None:
        return _chosen

    last_error: Exception | None = None
    for name in ENCODERS:
        for supports_crf in (True, False):
            try:
                _open_encoder(name, crf if supports_crf else None)
            except (FFmpegError, ValueError) as error:
                last_error = error
                continue

            _chosen = name
            _supports_crf = supports_crf
            logger.info("UPAI video encoder: %s", name)
            return name

    raise RuntimeError(f"no usable H.264 encoder found, last failure: {last_error}")


def _add_audio_stream(container: Any, audio: tuple[np.ndarray, int]) -> tuple[Any, Any]:
    waveform, sample_rate = audio
    samples = np.ascontiguousarray(waveform, dtype=np.float32)
    layout = {1: "mono", 2: "stereo"}.get(samples.shape[0])
    if layout is None:
        raise ValueError("audio has more than 2 channels")

    stream = container.add_stream("aac", rate=sample_rate, layout=layout)
    frame = av.AudioFrame.from_ndarray(samples, format="fltp", layout=layout)
    frame.sample_rate = sample_rate
    frame.pts = 0
    frame.time_base = Fraction(1, sample_rate)

    return stream, frame


def encode_mp4(
    path: Path,
    frames: np.ndarray,
    frame_rate: Any,
    audio: tuple[np.ndarray, int] | None,
    crf: float,
) -> None:
    """Encode frames and optional audio to an MP4 with the chosen encoder."""
    encoder = select_encoder()
    rate = Fraction(round(float(frame_rate) * 1000), 1000)
    with av.open(str(path), mode="w", format="mp4") as container:
        stream = cast(Any, container.add_stream(encoder, rate=rate))
        stream.width = int(frames.shape[2])
        stream.height = int(frames.shape[1])
        stream.pix_fmt = "yuv420p"
        if _supports_crf:
            stream.options = {"crf": str(crf)}

        audio_parts = _add_audio_stream(container, audio) if audio is not None else None

        for index, frame in enumerate(frames):
            pixels = np.clip(np.asarray(frame) * 255.0, 0, 255).astype(np.uint8)[..., :3]
            video_frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            video_frame = video_frame.reformat(format="yuv420p")
            video_frame.pts = index
            video_frame.time_base = 1 / rate
            for packet in stream.encode(video_frame):
                container.mux(packet)

        for packet in stream.encode():
            container.mux(packet)

        if audio_parts is not None:
            audio_stream, audio_frame = audio_parts
            for packet in audio_stream.encode(audio_frame):
                container.mux(packet)

            for packet in audio_stream.encode():
                container.mux(packet)
