"""Stable instance identity tests."""

import json
import uuid
from pathlib import Path

import pytest

import upai_provider.instance as instance_module
from upai_provider.instance import load_instance_id


def _path(tmp_path: Path) -> Path:
    return tmp_path / "user" / "default" / "upai" / "instance.json"


def test_creates_and_reuses_instance_id(tmp_path: Path) -> None:
    path = _path(tmp_path)

    first = load_instance_id(path)
    second = load_instance_id(path)

    assert first == second
    assert uuid.UUID(first).version == 4
    assert str(uuid.UUID(first)) == first


def test_stores_instance_id_in_json(tmp_path: Path) -> None:
    path = _path(tmp_path)

    instance_id = load_instance_id(path)

    assert json.loads(path.read_text(encoding="utf-8")) == {"instance_id": instance_id}


def test_keeps_existing_instance_id(tmp_path: Path) -> None:
    path = _path(tmp_path)
    existing = str(uuid.uuid4())
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"instance_id": existing}), encoding="utf-8")

    assert load_instance_id(path) == existing


def test_replaces_invalid_instance_id(tmp_path: Path) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    instance_id = load_instance_id(path)

    assert uuid.UUID(instance_id).version == 4
    assert json.loads(path.read_text(encoding="utf-8")) == {"instance_id": instance_id}
    assert list(path.parent.glob(".instance-*")) == []


def test_replaces_non_uuid4_instance_id(tmp_path: Path) -> None:
    path = _path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"instance_id": str(uuid.uuid1())}), encoding="utf-8")

    instance_id = load_instance_id(path)

    assert uuid.UUID(instance_id).version == 4


def test_instance_write_uses_replace_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []
    original = instance_module.replace_file

    def fake(source: Path, target: Path) -> None:
        calls.append((Path(source), Path(target)))
        original(source, target)

    monkeypatch.setattr(instance_module, "replace_file", fake)
    path = _path(tmp_path)

    load_instance_id(path)

    assert len(calls) == 1
    assert calls[0][1] == path
    assert calls[0][0].name.startswith(".instance-")
    assert list(path.parent.glob(".instance-*")) == []
