"""Tests for the video encoder selection and MP4 writer."""

import logging
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest

import upai_provider.encoder as encoder


def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(encoder, "_chosen", None)
    monkeypatch.setattr(encoder, "_supports_crf", None)


def test_select_encoder_picks_first_openable_and_caches(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _reset(monkeypatch)
    tried: list[str] = []

    def fake_open(name: str, crf: float | None) -> Any:
        tried.append(name)
        if name != "h264_videotoolbox":
            raise ValueError(name)
        return object()

    monkeypatch.setattr(encoder, "_open_encoder", fake_open)
    caplog.set_level(logging.INFO, logger=encoder.__name__)

    assert encoder.select_encoder() == "h264_videotoolbox"
    assert encoder.select_encoder() == "h264_videotoolbox"

    assert set(tried) == {"libx264", "h264_nvenc", "h264_videotoolbox"}
    messages = [record.getMessage() for record in caplog.records]
    assert messages.count("UPAI video encoder: h264_videotoolbox") == 1


def test_select_encoder_falls_through_a_failed_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset(monkeypatch)

    def fake_open(name: str, crf: float | None) -> Any:
        if name == "libx264":
            raise ValueError("cannot open libx264")
        return object()

    monkeypatch.setattr(encoder, "_open_encoder", fake_open)

    assert encoder.select_encoder() == "h264_nvenc"


def test_select_encoder_retries_without_crf(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset(monkeypatch)

    def fake_open(name: str, crf: float | None) -> Any:
        if name != "libx264":
            raise ValueError(name)
        if crf is not None:
            raise ValueError("crf unsupported")
        return object()

    monkeypatch.setattr(encoder, "_open_encoder", fake_open)

    assert encoder.select_encoder() == "libx264"
    assert encoder._supports_crf is False


def test_select_encoder_raises_with_the_last_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset(monkeypatch)

    def fake_open(name: str, crf: float | None) -> Any:
        raise ValueError(f"cannot open {name}")

    monkeypatch.setattr(encoder, "_open_encoder", fake_open)

    with pytest.raises(RuntimeError, match="cannot open mpeg4"):
        encoder.select_encoder()


def test_encode_mp4_writes_a_non_empty_file(tmp_path: Path) -> None:
    frames = np.random.default_rng(0).random((3, 64, 64, 3)).astype(np.float32)
    path = tmp_path / "clip.mp4"

    encoder.encode_mp4(path, frames, 24.0, None, 18)

    assert path.stat().st_size > 0
    with av.open(str(path)) as container:
        assert container.streams.video[0].codec_context.name == "h264"
