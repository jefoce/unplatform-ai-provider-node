"""Structural checks for the CPU workflow fixtures, no ComfyUI needed."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest

from upai_provider.constants import (
    NODE_UPAI_AUDIO_REF,
    NODE_UPAI_END_FRAME,
    NODE_UPAI_IMAGE_REF,
    NODE_UPAI_LIMITS,
    NODE_UPAI_MODEL,
    NODE_UPAI_OUTPUT,
    NODE_UPAI_PROMPT,
    NODE_UPAI_SETTINGS,
    NODE_UPAI_START_FRAME,
    NODE_UPAI_VIDEO_REF,
)

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "tests" / "workflows" / "api"
UI_DIR = ROOT / "tests" / "workflows" / "ui"

CASES = tuple(sorted(path.stem for path in API_DIR.glob("*.json")))
UPAI_TYPES = {
    NODE_UPAI_MODEL,
    NODE_UPAI_LIMITS,
    NODE_UPAI_PROMPT,
    NODE_UPAI_IMAGE_REF,
    NODE_UPAI_VIDEO_REF,
    NODE_UPAI_AUDIO_REF,
    NODE_UPAI_START_FRAME,
    NODE_UPAI_END_FRAME,
    NODE_UPAI_SETTINGS,
    NODE_UPAI_OUTPUT,
}
CORE_TYPES = {"EmptyImage", "ImageInvert", "ImageBatch", "StringLength", "CreateVideo", "sg-invert"}
ALLOWED_TYPES = UPAI_TYPES | CORE_TYPES
MODEL_LOADERS = {
    "CheckpointLoaderSimple",
    "UNETLoader",
    "VAELoader",
    "CLIPLoader",
    "LoraLoader",
    "DualCLIPLoader",
}


@cache
def _load(path: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(Path(path).read_text(encoding="utf-8")))


def _api(case: str) -> dict[str, Any]:
    return _load(str(API_DIR / f"{case}.json"))


def _ui(case: str) -> dict[str, Any]:
    return _load(str(UI_DIR / f"{case}.json"))


def _is_link(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
    )


def _link_source(node: dict[str, Any], name: str) -> str | None:
    value = node["inputs"].get(name)
    return value[0] if _is_link(value) else None


def _nodes(prompt: dict[str, Any], class_type: str) -> list[str]:
    return [node_id for node_id, node in prompt.items() if node["class_type"] == class_type]


def _outputs(prompt: dict[str, Any]) -> list[str]:
    return _nodes(prompt, NODE_UPAI_OUTPUT)


def _models(prompt: dict[str, Any]) -> list[str]:
    return _nodes(prompt, NODE_UPAI_MODEL)


def _model_kind(prompt: dict[str, Any], output_id: str) -> str:
    model_id = _link_source(prompt[output_id], "model")
    assert model_id is not None, f"output {output_id} has no model"
    model = prompt[model_id]
    assert model["class_type"] == NODE_UPAI_MODEL
    return str(model["inputs"]["kind"])


def _ancestors(prompt: dict[str, Any], start: str) -> set[str]:
    seen: set[str] = set()
    pending = [start]
    while pending:
        node_id = pending.pop()
        if node_id in seen or node_id not in prompt:
            continue
        seen.add(node_id)
        for value in prompt[node_id]["inputs"].values():
            if _is_link(value):
                pending.append(value[0])
    return seen


def _limits_id(prompt: dict[str, Any], model_id: str) -> str:
    limits_id = _link_source(prompt[model_id], "limits")
    assert limits_id is not None, f"model {model_id} has no limits"
    assert prompt[limits_id]["class_type"] == NODE_UPAI_LIMITS
    return limits_id


def _classes(prompt: dict[str, Any]) -> set[str]:
    return {str(node["class_type"]) for node in prompt.values()}


def test_every_api_workflow_has_a_ui_pair() -> None:
    api = {path.stem for path in API_DIR.glob("*.json")}
    ui = {path.stem for path in UI_DIR.glob("*.json")}
    assert api == ui
    assert {"image-single", "video-single", "two-models", "shared-prompt"} <= api


@pytest.mark.parametrize("case", CASES)
def test_api_prompt_shape(case: str) -> None:
    prompt = _api(case)
    raw = json.dumps(prompt)
    assert prompt
    for ext in (".safetensors", ".ckpt", ".pt"):
        assert ext not in raw, f"{case} references a model file"

    for node_id, node in prompt.items():
        assert isinstance(node, dict), node_id
        assert node["class_type"] in ALLOWED_TYPES, f"{case}: {node['class_type']}"
        assert node["class_type"] not in MODEL_LOADERS
        assert isinstance(node["inputs"], dict)
        for value in node["inputs"].values():
            if not _is_link(value):
                continue
            assert value[0] in prompt, f"{case}: {node_id} links to missing {value[0]}"
            assert value[1] >= 0

    outputs = _outputs(prompt)
    models = _models(prompt)
    assert outputs and models
    assert len({prompt[model]["inputs"]["id"] for model in models}) == len(models)
    referenced = {_link_source(prompt[output], "model") for output in outputs}
    assert referenced == set(models)
    for output_id in outputs:
        assert _model_kind(prompt, output_id) in {"image", "video"}
        assert _link_source(prompt[output_id], "images") or _link_source(prompt[output_id], "video")


@pytest.mark.parametrize("case", CASES)
def test_ui_workflow_matches_api_root(case: str) -> None:
    prompt = _api(case)
    ui = _ui(case)
    nodes = cast(list[dict[str, Any]], ui["nodes"])
    ids = {int(node["id"]) for node in nodes}
    assert len(ids) == len(nodes)
    for node in nodes:
        assert node["mode"] in {0, 2, 4}

    for link in cast(list[list[Any]], ui["links"]):
        assert len(link) == 6
        assert int(link[1]) in ids and int(link[3]) in ids

    definitions = cast(dict[str, Any], ui.get("definitions", {})).get("subgraphs", [])
    subgraph_ids = {str(item["id"]) for item in definitions}
    active = {int(node["id"]) for node in nodes if node["mode"] == 0}
    for node_id in prompt:
        if ":" in node_id:
            continue
        assert int(node_id) in active, f"{case}: API node {node_id} is inactive in UI"
    for node in nodes:
        if node["mode"] != 0 or node["type"] in subgraph_ids:
            continue
        assert str(node["id"]) in prompt, f"{case}: active UI node {node['id']} missing in API"


def test_two_models_have_one_output_each() -> None:
    prompt = _api("two-models")
    assert len(_models(prompt)) == 2
    assert len(_outputs(prompt)) == 2
    assert {_model_kind(prompt, output) for output in _outputs(prompt)} == {"image", "video"}


def test_shared_prompt_reaches_both_models() -> None:
    prompt = _api("shared-prompt")
    prompts = _nodes(prompt, NODE_UPAI_PROMPT)
    outputs = _outputs(prompt)
    assert len(prompts) == 1 and len(outputs) == 2
    for output_id in outputs:
        assert prompts[0] in _ancestors(prompt, output_id)


def test_limits_lowered_refs_count_and_frames() -> None:
    prompt = _api("limits-lowered")
    models = _models(prompt)
    assert len(models) == 1
    limits = prompt[_limits_id(prompt, models[0])]["inputs"]
    output = _outputs(prompt)[0]
    ancestors = _ancestors(prompt, output)

    refs = [node for node in ancestors if prompt[node]["class_type"] == NODE_UPAI_IMAGE_REF]
    assert len(refs) == 2
    assert limits["image_max"] == 1
    assert limits["count_max"] == 2
    assert limits["start_frame"] == "off"
    assert limits["end_frame"] == "optional"
    settings = [node for node in ancestors if prompt[node]["class_type"] == NODE_UPAI_SETTINGS]
    assert len(settings) == 1
    assert prompt[settings[0]]["inputs"]["count_max"] > limits["count_max"]
    assert any(prompt[node]["class_type"] == NODE_UPAI_START_FRAME for node in ancestors)
    assert any(prompt[node]["class_type"] == NODE_UPAI_END_FRAME for node in ancestors)


def test_limits_frames_required_and_off() -> None:
    prompt = _api("limits-frames-required")
    models = _models(prompt)
    assert len(models) == 1
    limits = prompt[_limits_id(prompt, models[0])]["inputs"]
    ancestors = _ancestors(prompt, _outputs(prompt)[0])
    assert limits["start_frame"] == "required"
    assert limits["end_frame"] == "off"
    assert any(prompt[node]["class_type"] == NODE_UPAI_START_FRAME for node in ancestors)
    assert any(prompt[node]["class_type"] == NODE_UPAI_END_FRAME for node in ancestors)


def test_bypassed_and_muted_nodes_are_absent_from_api() -> None:
    prompt = _api("bypassed-muted")
    ui = _ui("bypassed-muted")
    modes = {int(node["mode"]) for node in cast(list[dict[str, Any]], ui["nodes"])}
    assert {2, 4} <= modes
    assert len(_models(prompt)) == 1
    assert len(_outputs(prompt)) == 1
    active_models = [
        node
        for node in cast(list[dict[str, Any]], ui["nodes"])
        if node["type"] == NODE_UPAI_MODEL and node["mode"] == 0
    ]
    assert len(active_models) == 1


def test_subgraph_fixture_is_flattened() -> None:
    prompt = _api("subgraph")
    ui = _ui("subgraph")
    definitions = cast(dict[str, Any], ui["definitions"])["subgraphs"]
    assert definitions
    nested = [node_id for node_id in prompt if ":" in node_id]
    assert nested
    output = _outputs(prompt)[0]
    images = cast(list[Any], prompt[output]["inputs"]["images"])
    assert ":" in str(images[0])
    assert str(images[0]) in prompt


def test_single_kind_workflows_use_core_nodes_only() -> None:
    image = _api("image-single")
    video = _api("video-single")
    assert _model_kind(image, _outputs(image)[0]) == "image"
    assert _model_kind(video, _outputs(video)[0]) == "video"
    assert {"EmptyImage", "ImageInvert"} <= _classes(image)
    assert "CreateVideo" in _classes(video)
