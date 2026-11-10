"""End-to-end workflow runs against a real ComfyUI on port 8189."""

from __future__ import annotations

import copy
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

pytestmark = pytest.mark.comfy

API_DIR = Path(__file__).resolve().parents[1] / "workflows" / "api"
CASE_NAMES = tuple(sorted(path.stem for path in API_DIR.glob("*.json")))
NODE_CLASSES = (
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
)


def _model_targets(prompt: dict[str, Any]) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for node_id, node in prompt.items():
        if node["class_type"] != NODE_UPAI_OUTPUT:
            continue
        link = node["inputs"].get("model")
        assert isinstance(link, list) and len(link) == 2, f"{node_id} has no model link"
        model = prompt[link[0]]
        assert model["class_type"] == NODE_UPAI_MODEL
        targets.append((node_id, str(model["inputs"]["kind"])))
    return targets


def _saved_files(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if isinstance(value.get("filename"), str) and isinstance(value.get("type"), str):
            return [value]
        return [item for child in value.values() for item in _saved_files(child)]
    if isinstance(value, list):
        return [item for child in value for item in _saved_files(child)]
    return []


def _content_matches(data: bytes, kind: str) -> bool:
    if kind == "image":
        return data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8") or data[:4] == b"RIFF"
    if kind == "video":
        return b"ftyp" in data[:64] or data[:4] == b"RIFF" or data.startswith(b"\x1aE\xdf\xa3")
    return True


def _bust_cache(prompt: dict[str, Any], case: str) -> None:
    color = int.from_bytes(case.encode("utf-8")[:3], "big")
    for node in prompt.values():
        if node["class_type"] == "EmptyImage":
            node["inputs"]["color"] = color


def test_upai_nodes_registered(comfy_server: Any) -> None:
    info = comfy_server.object_info()
    missing = [name for name in NODE_CLASSES if name not in info]
    assert not missing, f"UPai nodes missing from object_info: {missing}"


@pytest.mark.parametrize("case", CASE_NAMES)
def test_api_workflow_runs(
    comfy_server: Any, api_workflows: dict[str, dict[str, Any]], case: str
) -> None:
    prompt = copy.deepcopy(api_workflows[case])
    _bust_cache(prompt, case)
    targets = _model_targets(prompt)
    assert targets, f"{case} has no model output"

    for output_id, kind in targets:
        prompt_id = comfy_server.submit(prompt, [output_id])
        record = comfy_server.wait_history(prompt_id)
        status = cast(dict[str, Any], record.get("status", {}))
        assert status.get("status_str") == "success", record
        outputs = cast(dict[str, Any], record.get("outputs", {}))
        assert output_id in outputs, f"{case} produced no output for node {output_id}"
        assert all(other not in outputs for other, _ in targets if other != output_id)

        files = _saved_files(outputs[output_id])
        assert files, f"{case} node {output_id} returned no files: {outputs[output_id]}"
        for saved in files:
            data = comfy_server.view(saved)
            assert data, f"{case} returned an empty file: {saved}"
            assert _content_matches(data, kind), f"{case} {kind} content mismatch: {saved}"
