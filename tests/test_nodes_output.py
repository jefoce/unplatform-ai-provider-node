"""Tests for the UPAI Output node."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import test_nodes_support as support

import upai_provider.nodes.output as output_module
from upai_provider.constants import NODE_UPAI_OUTPUT
from upai_provider.nodes.output import UPaiOutput
from upai_provider.protocol import format_run_id

support.install()

JOB_ID = "123e4567-e89b-42d3-a456-426614174000"


class _FakeVideo:
    def __init__(self, frames: Any, audio: Any = None, frame_rate: Any = 24.0) -> None:
        self._components = support.VideoComponents(
            images=frames, frame_rate=frame_rate, audio=audio
        )

    def get_components(self) -> Any:
        return self._components

    def save_to(self, path: str, **kwargs: Any) -> None:
        Path(path).write_bytes(b"video")


def _stub_encoder(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    calls: list[tuple[Any, ...]] = []

    def fake_encode(path: Path, frames: Any, frame_rate: Any, audio: Any, crf: float) -> None:
        calls.append((frames.shape, frame_rate, audio, crf))
        Path(path).write_bytes(b"video")

    monkeypatch.setattr(output_module, "select_encoder", lambda *args, **kwargs: "fake")
    monkeypatch.setattr(output_module, "encode_mp4", fake_encode)
    return calls


def _params(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "model": {"kind": "image"},
        "upai_job": JOB_ID,
        "format": "png",
        "crf": 18,
        "preview": False,
        "images": np.zeros((2, 4, 8, 3), dtype=np.float32),
        "video": None,
        "audio": None,
        "fps": None,
    }
    values.update(changes)
    return values


def test_output_schema_uses_contract_id_and_model_input() -> None:
    schema = UPaiOutput.define_schema()

    assert schema.node_id == NODE_UPAI_OUTPUT
    assert schema.is_output_node is True
    assert schema.inputs[0].id == "model"
    assert schema.inputs[0].optional is False
    assert schema.inputs[1].id == "images"
    assert schema.inputs[1].io_type == "IMAGE,VIDEO"


def test_output_writes_image_batch_and_registers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    captured: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        output_module,
        "register_output",
        lambda job_id, files: captured.append((job_id, list(files))),
    )

    UPaiOutput.execute(**_params())

    folder = tmp_path / "upai" / JOB_ID
    assert sorted(path.name for path in folder.iterdir()) == ["0.png", "1.png"]
    assert captured == [(JOB_ID, [str(folder / "0.png"), str(folder / "1.png")])]


def test_output_run_ids_write_distinct_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    captured: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        output_module,
        "register_output",
        lambda job_id, files: captured.append((job_id, list(files))),
    )

    run_ids = [format_run_id(JOB_ID, index) for index in range(3)]
    for run_id in run_ids:
        UPaiOutput.execute(
            **_params(upai_job=run_id, images=np.zeros((1, 4, 8, 3), dtype=np.float32))
        )

    files = [path for _, paths in captured for path in paths]
    assert [item[0] for item in captured] == run_ids
    assert [Path(path).name for path in files] == ["0-0.png", "1-0.png", "2-0.png"]
    assert len(files) == len(set(files)) == 3


def test_output_run_prefix_keeps_batch_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    monkeypatch.setattr(output_module, "register_output", lambda job_id, files: None)

    UPaiOutput.execute(**_params(upai_job=format_run_id(JOB_ID, 2)))

    names = sorted(path.name for path in (tmp_path / "upai" / JOB_ID).iterdir())
    assert names == ["2-0.png", "2-1.png"]


def test_runs_mode_output_paths_are_windows_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    monkeypatch.setattr(output_module, "register_output", lambda job_id, files: None)

    for index in range(3):
        UPaiOutput.execute(**_params(upai_job=format_run_id(JOB_ID, index)))

    forbidden = set('<>:"|?*')
    for path in tmp_path.rglob("*"):
        assert not set(path.name) & forbidden, path.name


def test_output_video_kind_builds_an_mp4(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    captured: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        output_module,
        "register_output",
        lambda job_id, files: captured.append((job_id, list(files))),
    )
    calls = _stub_encoder(monkeypatch)

    UPaiOutput.execute(**_params(model={"kind": "video"}, images=np.zeros((2, 4, 8, 3)), fps=24.0))

    path = tmp_path / "upai" / JOB_ID / "0.mp4"
    assert path.read_bytes() == b"video"
    assert captured == [(JOB_ID, [str(path)])]
    assert calls[0][0] == (2, 4, 8, 3)


def test_output_accepts_a_video_on_the_images_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    monkeypatch.setattr(output_module, "register_output", lambda job_id, files: None)
    _stub_encoder(monkeypatch)

    UPaiOutput.execute(
        **_params(model={"kind": "video"}, images=_FakeVideo(np.zeros((2, 4, 8, 3))))
    )

    assert (tmp_path / "upai" / JOB_ID / "0.mp4").read_bytes() == b"video"


def test_output_uses_a_video_input_directly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    monkeypatch.setattr(output_module, "register_output", lambda job_id, files: None)
    _stub_encoder(monkeypatch)

    UPaiOutput.execute(
        **_params(model={"kind": "video"}, images=None, video=_FakeVideo(np.zeros((2, 4, 8, 3))))
    )

    assert (tmp_path / "upai" / JOB_ID / "0.mp4").read_bytes() == b"video"


def test_output_video_uses_encoder_and_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    replaced: list[tuple[Path, Path]] = []

    def fake_replace(source: Path, target: Path) -> None:
        replaced.append((Path(source), Path(target)))
        Path(source).replace(target)

    monkeypatch.setattr(output_module, "replace_file", fake_replace)
    monkeypatch.setattr(output_module, "register_output", lambda job_id, files: None)
    calls = _stub_encoder(monkeypatch)

    UPaiOutput.execute(
        **_params(model={"kind": "video"}, images=np.zeros((3, 64, 64, 3)), fps=24.0)
    )

    final = tmp_path / "upai" / JOB_ID / "0.mp4"
    assert final.read_bytes() == b"video"
    assert replaced[-1][1] == final
    assert replaced[-1][0].name.startswith(".0-")
    assert calls[0][0] == (3, 64, 64, 3)


def test_output_editor_run_uses_editor_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    called: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        output_module, "register_output", lambda job_id, files: called.append((job_id, list(files)))
    )

    UPaiOutput.execute(**_params(upai_job=""))

    assert (tmp_path / "upai" / "editor" / "0.png").is_file()
    assert called == []


def test_output_preview_adds_a_ui_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)
    monkeypatch.setattr(output_module, "register_output", lambda job_id, files: None)

    output = UPaiOutput.execute(**_params(preview=True))

    assert isinstance(output.ui, support.PreviewImage)


def test_output_rejects_an_unsafe_job_id(tmp_path: Path) -> None:
    support.set_directories(input=tmp_path, temp=tmp_path)

    with pytest.raises(ValueError):
        UPaiOutput.execute(**_params(upai_job="../../escape"))


def test_output_fingerprint_is_the_job_id() -> None:
    assert UPaiOutput.fingerprint_inputs(JOB_ID) == JOB_ID
    assert UPaiOutput.fingerprint_inputs("") == ""
