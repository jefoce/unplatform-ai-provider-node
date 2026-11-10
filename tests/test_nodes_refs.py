"""Tests for the UPAI reference and frame nodes."""

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
import test_nodes_support as support
from PIL import Image

from upai_provider.nodes.frames import UPaiEndFrame, UPaiStartFrame
from upai_provider.nodes.media import _lexical_path, input_files, resolve_file
from upai_provider.nodes.refs import UPaiAudioRef, UPaiImageRef, UPaiVideoRef

support.install()


def _png(path: Path, size: tuple[int, int] = (8, 4), mode: str = "RGB") -> str:
    Image.new(mode, size, (255, 0, 0)).save(path)
    return path.name


def test_image_ref_reads_the_test_file(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    name = _png(tmp_path / "ref.png")

    image, mask, present, width, height = UPaiImageRef.execute(1, False, name).args

    assert present is True
    assert (width, height) == (8, 4)
    assert image.shape == (1, 4, 8, 3)
    assert mask.shape == (1, 4, 8)
    assert float(mask.max()) == 0.0


def test_image_ref_missing_file_uses_placeholder(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)

    image, mask, present, width, height = UPaiImageRef.execute(1, False, "").args

    assert present is False
    assert (width, height) == (64, 64)
    assert image.shape == (1, 64, 64, 3)
    assert mask.shape == (1, 64, 64)


def test_image_ref_bad_file_uses_placeholder(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    (tmp_path / "broken.png").write_bytes(b"not an image")

    image, _, present, width, height = UPaiImageRef.execute(1, False, "broken.png").args

    assert present is False
    assert (width, height) == (64, 64)
    assert image.shape == (1, 64, 64, 3)


def test_image_ref_keeps_rgba_as_mask(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    name = _png(tmp_path / "alpha.png", mode="RGBA")

    _, mask, present, _, _ = UPaiImageRef.execute(1, False, name).args

    assert present is True
    assert float(mask.max()) == 0.0


def test_reference_index_is_validated() -> None:
    assert UPaiImageRef.validate_inputs(1) is True
    assert UPaiImageRef.validate_inputs(16) is True
    assert isinstance(UPaiImageRef.validate_inputs(0), str)
    assert isinstance(UPaiImageRef.validate_inputs(17), str)

    with pytest.raises(ValueError):
        UPaiImageRef.execute(0, False, "")


def test_start_and_end_frame(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    name = _png(tmp_path / "frame.png")

    start, start_present = UPaiStartFrame.execute(True, name).args
    end, end_present = UPaiEndFrame.execute(False, "").args

    assert start_present is True
    assert start.shape == (1, 4, 8, 3)
    assert end_present is False
    assert end.shape == (1, 64, 64, 3)


def test_optional_frame_blank_passes_validation_and_uses_placeholder(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)

    assert UPaiStartFrame.validate_inputs(required=False, image="") is True
    assert UPaiEndFrame.validate_inputs(required=False, image="   ") is True

    start, present = UPaiStartFrame.execute(False, "").args

    assert present is False
    assert start.shape == (1, 64, 64, 3)


def test_required_frame_blank_returns_an_error() -> None:
    start_error = UPaiStartFrame.validate_inputs(required=True, image="")
    end_error = UPaiEndFrame.validate_inputs(required=True, image="   ")

    assert isinstance(start_error, str)
    assert "required" in start_error
    assert isinstance(end_error, str)
    assert "required" in end_error


def test_required_frame_with_missing_file_returns_an_error(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)

    start_error = UPaiStartFrame.validate_inputs(required=True, image="missing.png")
    end_error = UPaiEndFrame.validate_inputs(required=True, image="missing.png")

    assert isinstance(start_error, str)
    assert "not found" in start_error
    assert isinstance(end_error, str)
    assert "not found" in end_error
    assert UPaiStartFrame.validate_inputs(required=False, image="missing.png") is True


def test_frame_with_real_file_passes_validation(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    name = _png(tmp_path / "frame.png")

    assert UPaiStartFrame.validate_inputs(required=True, image=name) is True
    assert UPaiEndFrame.validate_inputs(required=False, image=name) is True

    image, present = UPaiStartFrame.execute(True, name).args

    assert present is True
    assert image.shape == (1, 4, 8, 3)


def test_video_ref_reads_the_test_file(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    (tmp_path / "clip.mp4").write_bytes(b"video")

    video, present, fps, duration, frame_count = UPaiVideoRef.execute(1, False, "clip.mp4").args

    assert video is not None
    assert present is True
    assert (fps, duration, frame_count) == (24.0, 2.0, 48)


def test_video_and_audio_ref_missing_file(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)

    video, video_present, fps, duration, frame_count = UPaiVideoRef.execute(1, False, "").args
    audio, audio_present, audio_duration = UPaiAudioRef.execute(1, False, "").args

    assert video is None
    assert video_present is False
    assert (fps, duration, frame_count) == (0.0, 0.0, 0)
    assert audio is None
    assert audio_present is False
    assert audio_duration == 0.0


def test_audio_ref_schema_uses_a_text_input() -> None:
    schema = UPaiAudioRef.define_schema()
    inputs = {item.id: item for item in schema.inputs}

    assert inputs["audio"].io_type == "STRING"
    assert "upload" not in inputs["audio"].kwargs
    assert all(item.kwargs.get("upload") != support.UploadType.audio for item in schema.inputs)


def test_input_files_filters_by_suffix(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    _png(tmp_path / "one.png")
    (tmp_path / "two.webp").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")

    assert input_files(("png", "webp")) == ["one.png", "two.webp"]


def _input_dir(tmp_path: Path) -> Path:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    support.set_directories(input=input_dir, temp=tmp_path)
    return input_dir


def test_resolve_file_rejects_outside_absolute_path(tmp_path: Path) -> None:
    _input_dir(tmp_path)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"x")

    assert resolve_file(str(outside)) is None


def test_resolve_file_rejects_parent_traversal(tmp_path: Path) -> None:
    _input_dir(tmp_path)
    (tmp_path / "x.wav").write_bytes(b"x")

    assert resolve_file("../x.wav") is None


def test_resolve_file_rejects_escaping_symlink(tmp_path: Path) -> None:
    input_dir = _input_dir(tmp_path)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"x")
    try:
        os.symlink(outside, input_dir / "link.wav")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")

    assert resolve_file("link.wav") is None


def test_resolve_file_accepts_inside_file(tmp_path: Path) -> None:
    input_dir = _input_dir(tmp_path)
    inside = input_dir / "ok.wav"
    inside.write_bytes(b"x")

    assert resolve_file("ok.wav") == inside.resolve()
    assert resolve_file(str(inside)) == inside.resolve()


def test_resolve_file_accepts_pack_job_path(tmp_path: Path) -> None:
    input_dir = _input_dir(tmp_path)
    job_file = input_dir / "upai" / "job" / "audio_1.wav"
    job_file.parent.mkdir(parents=True)
    job_file.write_bytes(b"x")

    assert resolve_file(str(job_file)) == job_file.resolve()


def test_resolve_file_accepts_absolute_path_under_symlinked_root(tmp_path: Path) -> None:
    real_input = tmp_path / "real-input"
    real_input.mkdir()
    link = tmp_path / "input-link"
    try:
        link.symlink_to(real_input, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")

    support.set_directories(input=link, temp=tmp_path)
    job_file = real_input / "upai" / "job" / "audio_1.wav"
    job_file.parent.mkdir(parents=True)
    job_file.write_bytes(b"x")

    # Absolute path from the unresolved symlink root, as the live check builds it.
    assert resolve_file(str(link / "upai" / "job" / "audio_1.wav")) == job_file.resolve()


def test_resolve_file_blank_is_none(tmp_path: Path) -> None:
    _input_dir(tmp_path)

    assert resolve_file("") is None
    assert resolve_file("   ") is None
    assert resolve_file("none") is None


def test_audio_ref_validate_rejects_outside_path(tmp_path: Path) -> None:
    _input_dir(tmp_path)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"x")

    error = UPaiAudioRef.validate_inputs(1, required=True, audio=str(outside))

    assert isinstance(error, str)
    assert "outside" in error


def test_audio_ref_validate_accepts_inside_file(tmp_path: Path) -> None:
    input_dir = _input_dir(tmp_path)
    (input_dir / "ok.wav").write_bytes(b"x")

    assert UPaiAudioRef.validate_inputs(1, required=True, audio="ok.wav") is True


def test_audio_ref_validate_blank_optional_is_valid(tmp_path: Path) -> None:
    _input_dir(tmp_path)

    assert UPaiAudioRef.validate_inputs(1, required=False, audio="") is True
    assert UPaiAudioRef.validate_inputs(1, required=False, audio="   ") is True


def test_audio_ref_validate_blank_required_is_error(tmp_path: Path) -> None:
    _input_dir(tmp_path)

    error = UPaiAudioRef.validate_inputs(1, required=True, audio="")

    assert isinstance(error, str)
    assert "required" in error


def test_audio_ref_validate_checks_index(tmp_path: Path) -> None:
    _input_dir(tmp_path)

    assert isinstance(UPaiAudioRef.validate_inputs(0, required=False, audio=""), str)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.wav", PurePosixPath("/input/a.wav")),
        ("/input/a.wav", PurePosixPath("/input/a.wav")),
        ("../a.wav", None),
        ("sub/../a.wav", None),
        ("/etc/a.wav", None),
    ],
)
def test_lexical_path_posix(name: str, expected: PurePosixPath | None) -> None:
    assert _lexical_path(name, PurePosixPath("/input")) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.wav", PureWindowsPath("C:/input/a.wav")),
        ("C:\\input\\a.wav", PureWindowsPath("C:/input/a.wav")),
        ("..\\a.wav", None),
        ("C:\\input\\..\\a.wav", None),
        ("D:\\a.wav", None),
        ("\\\\server\\share\\a.wav", None),
    ],
)
def test_lexical_path_windows(name: str, expected: PureWindowsPath | None) -> None:
    assert _lexical_path(name, PureWindowsPath("C:/input")) == expected
