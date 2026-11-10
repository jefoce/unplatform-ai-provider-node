"""Tests for the UPAI Model, Limits and Prompt nodes."""

import test_nodes_support as support

from upai_provider.constants import (
    NODE_UPAI_LIMITS,
    NODE_UPAI_MODEL,
    NODE_UPAI_PROMPT,
    WS_TYPE_UPAI_LIMITS,
    WS_TYPE_UPAI_MODEL,
)
from upai_provider.nodes.limits import UPaiLimits
from upai_provider.nodes.model import UPaiModel
from upai_provider.nodes.prompt import UPaiPrompt

support.install()


def test_model_schema_uses_contract_id_and_types() -> None:
    schema = UPaiModel.define_schema()

    assert schema.node_id == NODE_UPAI_MODEL
    assert schema.category == "Unplatform AI"
    assert [output.io_type for output in schema.outputs] == [WS_TYPE_UPAI_MODEL]
    assert [item.id for item in schema.inputs][-1] == "limits"
    assert schema.inputs[-1].optional is True

    ids = [item.id for item in schema.inputs]
    assert ids.index("prompt_reference_label") == ids.index("price_per_run_usd") + 1


def test_model_execute_returns_the_spec() -> None:
    output = UPaiModel.execute(
        id=" wan-22 ",
        name=" Wan ",
        description="local",
        kind="video",
        enabled=True,
        price_per_run_usd=0.25,
        prompt_reference_label=" <{kind}_{n}> ",
        limits={"image_max": 2},
    )

    assert output.args == (
        {
            "id": "wan-22",
            "name": "Wan",
            "description": "local",
            "kind": "video",
            "enabled": True,
            "price_per_run_usd": 0.25,
            "prompt_reference_label": "<{kind}_{n}>",
            "prompt_reference_label_image": "",
            "prompt_reference_label_video": "",
            "prompt_reference_label_audio": "",
            "limits": {"image_max": 2},
        },
    )


def test_model_reference_label_is_optional() -> None:
    inputs = {item.id: item for item in UPaiModel.define_schema().inputs}

    assert "prompt_reference_label" in inputs
    assert inputs["prompt_reference_label"].optional is True
    assert UPaiModel.validate_inputs() is True
    assert UPaiModel.validate_inputs(prompt_reference_label="") is True


def test_model_reference_label_validation() -> None:
    assert UPaiModel.validate_inputs(prompt_reference_label="<{kind}_{n}>") is True
    assert UPaiModel.validate_inputs(prompt_reference_label="") is True
    assert UPaiModel.validate_inputs(prompt_reference_label="{foo}_{n}") == (
        "reference_label has an unknown placeholder {foo}"
    )
    assert UPaiModel.validate_inputs(prompt_reference_label="{kind}") == (
        "reference_label must contain {n} or {i}"
    )


def test_model_per_kind_reference_labels_are_optional() -> None:
    schema = UPaiModel.define_schema()
    inputs = {item.id: item for item in schema.inputs}
    ids = [item.id for item in schema.inputs]
    kinds = [
        "prompt_reference_label_image",
        "prompt_reference_label_video",
        "prompt_reference_label_audio",
    ]

    start = ids.index("prompt_reference_label") + 1
    assert ids[start : start + 3] == kinds
    for name in kinds:
        assert inputs[name].optional is True
        assert inputs[name].kwargs["default"] == ""


def test_model_execute_adds_per_kind_labels() -> None:
    output = UPaiModel.execute(
        id="wan",
        name="Wan",
        description="",
        kind="video",
        enabled=True,
        price_per_run_usd=0,
        prompt_reference_label="<{kind}_{n}>",
        prompt_reference_label_image=" <Picture {n}> ",
        prompt_reference_label_video="<Video {n}>",
        prompt_reference_label_audio="",
    )

    spec = output.args[0]
    assert spec["prompt_reference_label_image"] == "<Picture {n}>"
    assert spec["prompt_reference_label_video"] == "<Video {n}>"
    assert spec["prompt_reference_label_audio"] == ""


def test_model_per_kind_label_validation_names_the_kind() -> None:
    assert UPaiModel.validate_inputs(prompt_reference_label_image="<{n}>") is True
    assert UPaiModel.validate_inputs(prompt_reference_label_image="{kind}") == (
        "image: reference_label must contain {n} or {i}"
    )
    assert UPaiModel.validate_inputs(prompt_reference_label_audio="{foo}_{n}") == (
        "audio: reference_label has an unknown placeholder {foo}"
    )


def test_limits_schema_and_execute() -> None:
    schema = UPaiLimits.define_schema()

    assert schema.node_id == NODE_UPAI_LIMITS
    assert [output.io_type for output in schema.outputs] == [WS_TYPE_UPAI_LIMITS]
    inputs = {item.id: item for item in schema.inputs}
    assert inputs["image_max"].kwargs["default"] == -1
    assert inputs["image_required"].io_type == "INT"
    assert inputs["image_required"].kwargs["max"] == 16
    assert inputs["video_required"].kwargs["max"] == 16
    assert inputs["audio_required"].kwargs["max"] == 16
    assert inputs["count_max"].kwargs["default"] == 0

    output = UPaiLimits.execute(
        image_max=2,
        image_required=2,
        video_max=1,
        video_required=0,
        audio_max=0,
        audio_required=0,
        start_frame="required",
        end_frame="off",
        duration_min=2.0,
        duration_max=8.0,
        count_max=3,
    )
    assert output.args == (
        {
            "image_max": 2,
            "image_required": 2,
            "video_max": 1,
            "video_required": 0,
            "audio_max": 0,
            "audio_required": 0,
            "start_frame": "required",
            "end_frame": "off",
            "duration_min": 2.0,
            "duration_max": 8.0,
            "count_max": 3,
        },
    )


def test_prompt_schema_and_execute() -> None:
    schema = UPaiPrompt.define_schema()

    assert schema.node_id == NODE_UPAI_PROMPT
    assert [item.id for item in schema.outputs] == ["prompt", "negative"]
    assert UPaiPrompt.execute("hello", "blur", True, 20).args == ("hello", "blur")
