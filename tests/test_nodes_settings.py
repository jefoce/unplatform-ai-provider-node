"""Tests for the UPAI Settings node."""

from typing import Any

import test_nodes_support as support

from upai_provider.constants import NODE_UPAI_SETTINGS
from upai_provider.nodes.settings import UPaiSettings

support.install()


def _params(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "resolutions": "512,1K",
        "aspect_ratios": "16:9,1:1",
        "default_resolution": "1K",
        "default_aspect_ratio": "16:9",
        "align": 16,
        "size_overrides": "",
        "duration_min": 1.0,
        "duration_max": 10.0,
        "duration_default": 5.0,
        "duration_step": 0.5,
        "fps": 16.0,
        "frame_mod": 4,
        "frame_add": 1,
        "count_max": 4,
        "count_mode": "batch",
        "test_resolution": "1K",
        "test_aspect_ratio": "1:1",
        "test_duration": 5.0,
        "test_count": 2,
        "test_seed": 42,
    }
    values.update(changes)
    return values


def test_settings_schema_uses_contract_id() -> None:
    schema = UPaiSettings.define_schema()

    assert schema.node_id == NODE_UPAI_SETTINGS
    assert [output.id for output in schema.outputs] == [
        "width",
        "height",
        "frames",
        "fps",
        "duration",
        "count",
        "seed",
    ]


def test_settings_resolution_inputs_are_text() -> None:
    specs = {spec.id: spec for spec in UPaiSettings.define_schema().inputs}

    for name in (
        "default_resolution",
        "default_aspect_ratio",
        "test_resolution",
        "test_aspect_ratio",
    ):
        assert specs[name].io_type == "STRING"


def test_settings_validate_accepts_image_labels() -> None:
    assert UPaiSettings.validate_inputs(**_params()) is True


def test_settings_validate_accepts_video_labels() -> None:
    params = _params(
        resolutions="480p,720p,768p",
        default_resolution="720p",
        test_resolution="480p",
    )

    assert UPaiSettings.validate_inputs(**params) is True


def test_settings_validate_rejects_value_outside_list() -> None:
    message = UPaiSettings.validate_inputs(**_params(default_resolution="0.9"))

    assert isinstance(message, str)
    assert "default_resolution" in message
    assert "0.9" in message


def test_settings_validate_checks_test_value() -> None:
    message = UPaiSettings.validate_inputs(**_params(test_resolution="0.9"))

    assert isinstance(message, str)
    assert "test_resolution" in message


def test_settings_validate_rejects_empty_list() -> None:
    message = UPaiSettings.validate_inputs(**_params(resolutions=""))

    assert message == "resolutions is empty"


def test_settings_compute_size_frames_and_count() -> None:
    output = UPaiSettings.execute(**_params())

    assert output.args == (1024, 1024, 81, 16.0, 5.0, 2, 42)


def test_settings_clamps_duration_and_count() -> None:
    output = UPaiSettings.execute(**_params(test_duration=20.0, count_max=2, test_count=9))

    assert output.args[3:] == (16.0, 10.0, 2, 42)


def test_settings_size_override_wins() -> None:
    output = UPaiSettings.execute(**_params(size_overrides="1K 1:1 = 832x480"))

    assert output.args[:2] == (832, 480)


def test_settings_falls_back_on_bad_size() -> None:
    output = UPaiSettings.execute(**_params(test_resolution="nope"))

    assert output.args[:2] == (1024, 1024)
