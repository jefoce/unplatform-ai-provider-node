"""Export file roundtrip and registry status tests."""

import base64
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import make_client, make_runtime
from helpers import assert_error, json_body
from test_export_support import (
    copy_prompt,
    node,
    two_model_prompt,
    video_prompt,
    workflow_fixture,
)

import upai_provider.export_file as export_file_module
import upai_provider.export_registry as export_registry_module
from upai_provider.export_file import load_export, write_export
from upai_provider.export_graph import derive_export
from upai_provider.export_registry import ExportRegistry, _source_path
from upai_provider.export_serialize import export_to_data


def derive(
    prompt: dict[str, Any],
    *,
    source: str = "workflows/demo.json",
    source_mtime: float = 100.0,
):
    return derive_export(
        source=source,
        prompt=prompt,
        source_mtime=source_mtime,
        exported_at="2026-11-06T00:00:00Z",
        comfy_version="0.43.0",
    )


def known_classes() -> set[str]:
    return {
        "UPAIModel",
        "UPAILimits",
        "UPAIPrompt",
        "UPAIStartFrame",
        "UPAIImageRef",
        "UPAISettings",
        "UPAIOutput",
        "CLIPTextEncode",
        "KSampler",
        "CreateVideo",
    }


def write_build(path: Path, build: Any) -> None:
    write_export(path, build.export, build.invalid_reasons, build.warnings)


def test_export_file_roundtrip(tmp_path: Path) -> None:
    build = derive(video_prompt())
    path = tmp_path / "exports" / "demo.json"
    write_build(path, build)

    loaded = load_export(path)
    assert loaded is not None
    assert loaded.export.workflow_id == "demo"
    assert loaded.export.models[0].capabilities == build.export.models[0].capabilities
    assert loaded.export.models[0].bindings == build.export.models[0].bindings
    assert loaded.warnings == build.warnings


def test_export_file_roundtrip_keeps_price(tmp_path: Path) -> None:
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["price_per_run_usd"] = 2.5
    path = tmp_path / "exports" / "demo.json"
    write_build(path, derive(prompt))

    loaded = load_export(path)
    assert loaded is not None
    assert loaded.export.models[0].price_per_run_usd == 2.5


def test_stored_model_without_price_defaults_to_zero(tmp_path: Path) -> None:
    build = derive(video_prompt())
    data = json.loads(json.dumps(export_to_data(build.export, {}, ())))
    del data["models"][0]["price_per_run_usd"]
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_export(path)
    assert loaded is not None
    assert loaded.export.models[0].price_per_run_usd == 0.0


def test_one_broken_model_does_not_hide_the_others(tmp_path: Path) -> None:
    build = derive(video_prompt())
    data = {
        "workflow_id": build.export.workflow_id,
        "workflow_name": build.export.workflow_name,
        "source": build.export.source,
        "source_mtime": build.export.source_mtime,
        "exported_at": build.export.exported_at,
        "comfy_version": build.export.comfy_version,
        "models": [
            json.loads(json.dumps(_model_data(build))),
            {"model_id": "broken", "kind": "bogus"},
        ],
        "prompt": dict(build.export.prompt),
    }
    path = tmp_path / "demo.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_export(path)
    assert loaded is not None
    assert [model.model_id for model in loaded.export.models] == ["wan"]


def _model_data(build: Any) -> dict[str, Any]:
    models = cast(list[dict[str, Any]], export_to_data(build.export, {}, ())["models"])
    return models[0]


def test_write_export_uses_replace_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, Path]] = []
    original = export_file_module.replace_file

    def fake(source: Path, target: Path) -> None:
        calls.append((Path(source), Path(target)))
        original(source, target)

    monkeypatch.setattr(export_file_module, "replace_file", fake)
    build = derive(video_prompt())
    path = tmp_path / "exports" / "demo.json"

    write_build(path, build)

    assert len(calls) == 1
    assert calls[0][1] == path
    assert list(path.parent.glob(".export-*")) == []


def _registry(
    tmp_path: Path, *, known: bool = True, prompt: dict[str, Any] | None = None
) -> tuple[ExportRegistry, Path]:
    source = tmp_path / "workflows" / "demo.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    build = derive(
        video_prompt() if prompt is None else prompt,
        source_mtime=source.stat().st_mtime + 10,
    )
    exports = tmp_path / "upai" / "exports"
    write_build(exports / "demo.json", build)
    registry = ExportRegistry(
        exports,
        source_root=tmp_path,
        known_classes=known_classes if known else None,
    )
    return registry, source


def _limits_registry(tmp_path: Path) -> ExportRegistry:
    source = tmp_path / "workflows" / "limits-lowered.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    build = derive(
        workflow_fixture("limits-lowered"),
        source="workflows/limits-lowered.json",
        source_mtime=source.stat().st_mtime + 10,
    )
    exports = tmp_path / "upai" / "exports"
    write_build(exports / "limits-lowered.json", build)
    return ExportRegistry(exports, source_root=tmp_path)


def _counting_load(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    calls: list[Path] = []
    original = export_registry_module.load_export

    def counting(path: Path) -> Any:
        calls.append(path)
        return original(path)

    monkeypatch.setattr(export_registry_module, "load_export", counting)
    return calls


def test_registry_caches_loaded_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry, _ = _registry(tmp_path)
    calls = _counting_load(monkeypatch)

    first = registry.loads()
    second = registry.loads()

    assert first == second
    assert len(calls) == 1


def test_registry_reloads_when_a_new_file_appears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _ = _registry(tmp_path)
    calls = _counting_load(monkeypatch)
    registry.loads()
    before = len(calls)

    build = derive(two_model_prompt(), source="workflows/second.json")
    write_build(registry.exports_dir / "second.json", build)
    directory = registry.exports_dir.stat().st_mtime
    os.utime(registry.exports_dir, (directory + 60, directory + 60))

    loaded = registry.loads()

    assert len(calls) == before + 2
    assert {item.export.workflow_id for item in loaded} == {"demo", "second"}


def test_registry_reloads_when_a_file_is_rewritten_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, _ = _registry(tmp_path)
    calls = _counting_load(monkeypatch)
    registry.loads()
    before = len(calls)

    build = derive(two_model_prompt(), source="workflows/demo.json")
    write_build(registry.exports_dir / "demo.json", build)

    loaded = registry.loads()

    assert len(calls) == before + 1
    assert [model.model_id for model in loaded[0].export.models] == ["wan", "wan-t2v"]


def test_registry_reloads_when_inode_changes_with_same_mtime_and_size(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    first = registry.catalog("video")[0]
    assert first.name == "Wan"
    path = registry.exports_dir / "demo.json"
    first_stat = path.stat()

    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["name"] = "Wax"
    build = derive(prompt, source_mtime=registry.loads()[0].export.source_mtime)
    write_build(path, build)
    second_stat = path.stat()

    assert second_stat.st_size == first_stat.st_size
    assert second_stat.st_ino != first_stat.st_ino
    os.utime(path, ns=(first_stat.st_atime_ns, first_stat.st_mtime_ns))

    assert path.stat().st_mtime_ns == first_stat.st_mtime_ns
    assert registry.catalog("video")[0].name == "Wax"


@pytest.mark.parametrize(
    "source",
    ["C:/workflows/demo.json", "C:\\workflows\\demo.json", "c:demo.json"],
)
def test_source_path_rejects_windows_drive(tmp_path: Path, source: str) -> None:
    assert _source_path(source, tmp_path) is None


def test_source_path_accepts_relative_json(tmp_path: Path) -> None:
    assert _source_path("workflows/demo.json", tmp_path) == tmp_path / "workflows" / "demo.json"


def test_registry_accepts_hidden_image_frames(tmp_path: Path) -> None:
    model = _limits_registry(tmp_path).catalog("image")[0]

    assert model.status == "ready"
    assert model.status_reason is None
    assert model.capabilities.frames is None
    assert model.capabilities.references.image.max == 1


async def test_image_job_with_two_refs_is_rejected(
    aiohttp_client: Any, tmp_path: Path, png_bytes: bytes
) -> None:
    runtime = make_runtime(tmp_path)
    runtime.is_mock = False
    runtime.exports = _limits_registry(tmp_path)
    client = await make_client(aiohttp_client, runtime)
    url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

    response = await client.post(
        "/upai/api/v1/images/jobs",
        json={
            "model": "limits-lowered.limits-image",
            "prompt": "",
            "input_references": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "image_url", "image_url": {"url": url}},
            ],
        },
    )

    assert response.status == 400
    body = await json_body(response)
    assert_error(body, "invalid_request")
    assert body["error"]["details"]["field"] == "input_references"


def test_registry_reads_known_classes_once_per_catalog(tmp_path: Path) -> None:
    source = tmp_path / "workflows" / "demo.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    second = tmp_path / "workflows" / "second.json"
    second.write_text("{}", encoding="utf-8")
    exports = tmp_path / "upai" / "exports"
    write_build(
        exports / "demo.json",
        derive(video_prompt(), source_mtime=source.stat().st_mtime + 10),
    )
    write_build(
        exports / "second.json",
        derive(
            video_prompt(),
            source="workflows/second.json",
            source_mtime=second.stat().st_mtime + 10,
        ),
    )
    calls = 0

    def counting() -> set[str]:
        nonlocal calls
        calls += 1
        return known_classes()

    registry = ExportRegistry(exports, source_root=tmp_path, known_classes=counting)
    models = registry.catalog("video")

    assert len(models) == 2
    assert calls == 1


def test_registry_catalog_uses_full_model_id(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    models = registry.catalog("video")

    assert [model.id for model in models] == ["demo.wan"]
    assert models[0].status == "ready"
    assert models[0].workflow is not None
    assert models[0].workflow.id == "demo"
    assert models[0].workflow.name == "demo"


def test_registry_catalog_uses_price(tmp_path: Path) -> None:
    source = tmp_path / "workflows" / "demo.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["price_per_run_usd"] = 0.75
    build = derive(prompt, source_mtime=source.stat().st_mtime + 10)
    exports = tmp_path / "upai" / "exports"
    write_build(exports / "demo.json", build)

    model = ExportRegistry(exports, source_root=tmp_path).catalog("video")[0]
    assert model.pricing.per_run_usd == 0.75


def test_registry_marks_stale_when_source_is_newer(tmp_path: Path) -> None:
    registry, source = _registry(tmp_path)
    current = source.stat().st_mtime
    os.utime(source, (current + 60, current + 60))

    model = registry.catalog("video")[0]
    assert model.status == "stale"
    assert model.status_reason is not None


def test_registry_marks_missing_node_class_invalid(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    registry.known_classes = lambda: {"UPAIModel", "UPAIOutput"}

    model = registry.catalog("video")[0]
    assert model.status == "invalid"
    assert model.status_reason is not None
    assert "not installed" in model.status_reason


def test_registry_rejects_unrelated_missing_class(tmp_path: Path) -> None:
    prompt = copy_prompt(video_prompt())
    prompt["99"] = node("NotInstalled")
    registry, _ = _registry(tmp_path, prompt=prompt)

    model = registry.catalog("video")[0]
    assert model.status == "invalid"
    assert model.status_reason == "node class NotInstalled is not installed"


def test_registry_rejects_missing_class_for_every_model(tmp_path: Path) -> None:
    prompt = copy_prompt(two_model_prompt())
    prompt["99"] = node("NotInstalled")
    registry, _ = _registry(tmp_path, prompt=prompt)

    models = registry.catalog("video")
    assert [model.id for model in models] == ["demo.wan", "demo.wan-t2v"]
    for model in models:
        assert model.status == "invalid"
        assert model.status_reason == "node class NotInstalled is not installed"


def test_registry_ready_when_all_classes_are_installed(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path, prompt=copy_prompt(two_model_prompt()))

    models = registry.catalog("video")
    assert [model.status for model in models] == ["ready", "ready"]


def test_registry_marks_deleted_source_invalid(tmp_path: Path) -> None:
    registry, source = _registry(tmp_path, prompt=copy_prompt(two_model_prompt()))
    assert [model.status for model in registry.catalog("video")] == ["ready", "ready"]

    source.unlink()

    models = registry.catalog("video")
    assert [model.status for model in models] == ["invalid", "invalid"]
    for model in models:
        assert model.status_reason == "source workflow was deleted"


def test_registry_marks_source_stale_when_it_reappears_newer(tmp_path: Path) -> None:
    registry, source = _registry(tmp_path)
    stored = registry.loads()[0].export.source_mtime
    source.unlink()
    missing = registry.catalog("video")[0]
    assert missing.status == "invalid"
    assert missing.status_reason == "source workflow was deleted"

    source.write_text("{}", encoding="utf-8")
    os.utime(source, (stored + 60, stored + 60))

    model = registry.catalog("video")[0]
    assert model.status == "stale"
    assert model.status_reason is not None


def test_registry_lists_invalid_stored_models(tmp_path: Path) -> None:
    source = tmp_path / "workflows" / "demo.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    prompt = copy_prompt(video_prompt())
    prompt["6"]["inputs"]["index"] = 3
    build = derive(prompt, source_mtime=source.stat().st_mtime + 10)
    exports = tmp_path / "upai" / "exports"
    write_build(exports / "demo.json", build)

    model = ExportRegistry(exports, source_root=tmp_path).catalog("video")[0]
    assert model.status == "invalid"
    assert model.status_reason is not None
    assert "contiguous" in model.status_reason


def test_registry_skips_disabled_models(tmp_path: Path) -> None:
    source = tmp_path / "workflows" / "demo.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["enabled"] = False
    build = derive(prompt, source_mtime=source.stat().st_mtime + 10)
    exports = tmp_path / "upai" / "exports"
    write_build(exports / "demo.json", build)

    assert ExportRegistry(exports, source_root=tmp_path).catalog("video") == ()


def test_registry_skips_broken_export_file(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    (registry.exports_dir / "bad.json").write_text("{not json", encoding="utf-8")

    assert [model.id for model in registry.catalog("video")] == ["demo.wan"]


def test_registry_skips_dangling_export_file(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path)
    (registry.exports_dir / "dangling.json").symlink_to(registry.exports_dir / "missing.json")

    assert [model.id for model in registry.catalog("video")] == ["demo.wan"]
