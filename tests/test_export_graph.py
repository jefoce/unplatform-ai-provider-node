"""Graph walk, model membership, rules and capability tests."""

from typing import Any

from test_export_support import (
    copy_prompt,
    image_prompt,
    node,
    two_model_prompt,
    video_prompt,
    workflow_fixture,
)

from upai_provider.export_graph import derive_export


def derive(prompt: dict[str, Any], *, source: str = "workflows/demo.json"):
    return derive_export(
        source=source,
        prompt=prompt,
        source_mtime=100.0,
        exported_at="2026-11-06T00:00:00Z",
        comfy_version="0.43.0",
    )


def test_video_capabilities_and_bindings() -> None:
    build = derive(video_prompt())
    model = build.export.models[0]
    caps = model.capabilities

    assert build.export.workflow_id == "demo"
    assert build.export.workflow_name == "demo"
    assert model.model_id == "wan"
    assert model.name == "Wan"
    assert model.kind == "video"
    assert model.output_node == "11"
    assert model.bindings.prompt == "3"
    assert model.bindings.settings == "7"
    assert model.bindings.start == "4"
    assert model.bindings.end is None
    assert [ref.index for ref in model.bindings.refs["image"]] == [1, 2]

    assert caps.prompt.required is True
    assert caps.prompt.max_chars == 1000
    assert caps.negative_prompt is False
    assert caps.references.image.max == 2
    assert caps.references.image.required == 1
    assert caps.frames is not None
    assert caps.frames.start is True
    assert caps.frames.start_required is False
    assert caps.frames.end is False
    assert caps.duration is not None
    assert (caps.duration.min, caps.duration.max, caps.duration.default) == (2.0, 4.0, 4.0)
    assert caps.fps == 16
    assert caps.frame_rule is not None
    assert (caps.frame_rule.mod, caps.frame_rule.add) == (4, 1)
    assert caps.audio_output is False
    assert caps.sizes["480p"]["16:9"] == "832x480"
    assert caps.sizes["480p"]["9:16"] == "480x848"
    assert not build.invalid_reasons


def test_duration_default_snaps_to_step_grid() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["duration_min"] = 1
    prompt["7"]["inputs"]["duration_max"] = 10
    prompt["7"]["inputs"]["duration_default"] = 6
    prompt["7"]["inputs"]["duration_step"] = 2
    prompt["2"]["inputs"]["duration_min"] = 3
    prompt["2"]["inputs"]["duration_max"] = 10

    duration = derive(prompt).export.models[0].capabilities.duration
    assert duration is not None
    assert duration.default == 7
    assert (duration.default - duration.min) % duration.step == 0


def test_duration_default_snaps_inside_an_off_grid_maximum() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["duration_min"] = 1
    prompt["7"]["inputs"]["duration_max"] = 4
    prompt["7"]["inputs"]["duration_default"] = 6
    prompt["7"]["inputs"]["duration_step"] = 2
    prompt["2"]["inputs"]["duration_min"] = 1
    prompt["2"]["inputs"]["duration_max"] = 4

    build = derive(prompt)
    duration = build.export.models[0].capabilities.duration
    assert duration is not None
    assert duration.default == 3
    assert (duration.default - duration.min) % duration.step == 0
    assert not build.invalid_reasons


def test_all_invalid_resolution_labels_make_model_invalid() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["resolutions"] = "0.2,0.3,0.9,1.0,2.0"

    build = derive(prompt)
    assert "model has no valid video resolution labels" in build.invalid_reasons["wan"]
    assert build.export.models[0].capabilities.resolutions == ()
    assert len([w for w in build.warnings if "not a video label" in w]) == 5


def test_empty_aspect_ratio_list_makes_model_invalid() -> None:
    prompt = copy_prompt(image_prompt())
    prompt["3"]["inputs"]["aspect_ratios"] = ""

    build = derive(prompt)
    assert "aspect ratio" in build.invalid_reasons["sdxl"]
    assert build.export.models[0].capabilities.aspect_ratios == ()


def test_resolution_filter_keeps_valid_labels_and_warns() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["resolutions"] = "0.9,480p,720p,1K"
    prompt["7"]["inputs"]["default_resolution"] = "0.9"

    build = derive(prompt)
    caps = build.export.models[0].capabilities
    assert caps.resolutions == ("480p", "720p")
    assert caps.default_resolution == "480p"
    assert any("0.9" in w and "video label" in w for w in build.warnings)
    assert any("1K" in w and "video label" in w for w in build.warnings)
    assert "wan" not in build.invalid_reasons


def test_override_backed_video_label_is_accepted() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["resolutions"] = "0.9,720p"
    prompt["7"]["inputs"]["size_overrides"] = "0.9 16:9 = 1280x736"

    build = derive(prompt)
    caps = build.export.models[0].capabilities
    assert caps.resolutions == ("0.9", "720p")
    assert caps.sizes["0.9"]["16:9"] == "1280x736"
    assert "wan" not in build.invalid_reasons


def test_video_labels_backed_by_overrides_are_valid() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["resolutions"] = "0.2..2.0,480p"
    prompt["7"]["inputs"]["size_overrides"] = (
        "0.2..2.0 16:9 = 1280x736\n0.2..2.0 9:16 = 736x1280\n480p 16:9 = 832x480"
    )

    build = derive(prompt)
    caps = build.export.models[0].capabilities
    assert caps.resolutions == ("0.2..2.0", "480p")
    assert caps.sizes["0.2..2.0"]["16:9"] == "1280x736"
    assert "wan" not in build.invalid_reasons


def test_video_model_rejects_image_label() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["resolutions"] = "1K"

    build = derive(prompt)
    assert "model has no valid video resolution labels" in build.invalid_reasons["wan"]
    assert any("1K" in w and "video label" in w for w in build.warnings)


def test_image_model_rejects_video_label() -> None:
    prompt = copy_prompt(image_prompt())
    prompt["3"]["inputs"]["resolutions"] = "480p"

    build = derive(prompt)
    assert "model has no valid image resolution labels" in build.invalid_reasons["sdxl"]
    assert any("480p" in w and "image label" in w for w in build.warnings)


def test_sizes_for_video_labels_align_16() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["resolutions"] = "480p,720p,768p,1080p"
    prompt["7"]["inputs"]["align"] = 16

    sizes = derive(prompt).export.models[0].capabilities.sizes
    assert sizes["480p"]["16:9"] == "832x480"
    assert sizes["720p"]["16:9"] == "1280x720"
    assert sizes["768p"]["16:9"] == "1360x768"
    assert sizes["1080p"]["16:9"] == "1920x1088"


def test_sizes_for_video_labels_align_32() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["resolutions"] = "480p,720p,768p,1080p"
    prompt["7"]["inputs"]["align"] = 32

    sizes = derive(prompt).export.models[0].capabilities.sizes
    assert sizes["480p"]["9:16"] == "480x864"
    assert sizes["720p"]["16:9"] == "1280x736"
    assert sizes["768p"]["16:9"] == "1376x768"
    assert sizes["1080p"]["16:9"] == "1920x1088"


def test_size_override_wins_for_video_label() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["resolutions"] = "480p,720p"
    prompt["7"]["inputs"]["size_overrides"] = "720p 16:9 = 1232x688"

    sizes = derive(prompt).export.models[0].capabilities.sizes
    assert sizes["720p"]["16:9"] == "1232x688"


def test_size_override_accepts_uppercase_x_and_spaces() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["7"]["inputs"]["resolutions"] = "480p,720p"
    prompt["7"]["inputs"]["size_overrides"] = "720p 16:9 = 1280X736\n480p 16:9 = 832 x 480"

    sizes = derive(prompt).export.models[0].capabilities.sizes
    assert sizes["720p"]["16:9"] == "1280x736"
    assert sizes["480p"]["16:9"] == "832x480"


def test_negative_prompt_is_capable_only_when_wired() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["20"] = node("CLIPTextEncode", text=["3", 1])
    prompt["9"]["inputs"]["negative"] = ["20", 0]

    build = derive(prompt)
    assert build.export.models[0].capabilities.negative_prompt is True

    unwired = derive(video_prompt())
    assert unwired.export.models[0].capabilities.negative_prompt is False


def test_empty_id_and_name_fall_back_to_workflow_id() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["id"] = ""
    prompt["1"]["inputs"]["name"] = ""

    model = derive(prompt).export.models[0]
    assert model.model_id == "demo"
    assert model.name == "demo"


def test_price_per_run_usd_is_persisted() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["price_per_run_usd"] = 1.25

    build = derive(prompt)
    assert build.export.models[0].price_per_run_usd == 1.25


def test_reference_label_absent_is_none() -> None:
    build = derive(video_prompt())
    assert build.export.models[0].capabilities.prompt.reference_label is None


def test_reference_label_is_kept() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["prompt_reference_label"] = "<{kind}_{n}>"

    build = derive(prompt)
    assert build.export.models[0].capabilities.prompt.reference_label == "<{kind}_{n}>"
    assert "wan" not in build.invalid_reasons


def test_reference_label_unknown_placeholder_is_invalid() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["prompt_reference_label"] = "{foo}_{n}"

    build = derive(prompt)
    assert "unknown placeholder {foo}" in build.invalid_reasons["wan"]
    assert build.export.models[0].capabilities.prompt.reference_label is None


def test_reference_label_over_max_is_invalid() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["prompt_reference_label"] = "{n}" + "x" * 64

    build = derive(prompt)
    assert "at most 64 characters" in build.invalid_reasons["wan"]
    assert build.export.models[0].capabilities.prompt.reference_label is None


def test_per_kind_labels_become_capability_map() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["prompt_reference_label_image"] = "<Picture {n}>"
    prompt["1"]["inputs"]["prompt_reference_label_video"] = "<Video {n}>"
    prompt["1"]["inputs"]["prompt_reference_label_audio"] = "<Audio {n}>"

    build = derive(prompt)
    assert build.export.models[0].capabilities.prompt.reference_labels == {
        "image": "<Picture {n}>",
        "video": "<Video {n}>",
        "audio": "<Audio {n}>",
    }
    assert "wan" not in build.invalid_reasons


def test_unknown_per_kind_label_is_dropped_with_warning() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["prompt_reference_label_image"] = "<Picture {n}>"
    prompt["1"]["inputs"]["prompt_reference_label_video"] = "<Video {n}>"
    prompt["1"]["inputs"]["prompt_reference_label_audio"] = "<Audio {n}>"
    prompt["1"]["inputs"]["prompt_reference_label_sound"] = "<{n}>"

    build = derive(prompt)
    assert any("sound" in warning for warning in build.warnings)
    assert build.export.models[0].capabilities.prompt.reference_labels == {
        "image": "<Picture {n}>",
        "video": "<Video {n}>",
        "audio": "<Audio {n}>",
    }
    assert "wan" not in build.invalid_reasons


def test_invalid_per_kind_label_marks_model_invalid() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["1"]["inputs"]["prompt_reference_label_image"] = "{foo}_{n}"

    build = derive(prompt)
    assert "image" in build.invalid_reasons["wan"]
    assert "unknown placeholder {foo}" in build.invalid_reasons["wan"]
    assert build.export.models[0].capabilities.prompt.reference_labels is None


def test_per_kind_labels_absent_is_none() -> None:
    build = derive(video_prompt())
    assert build.export.models[0].capabilities.prompt.reference_labels is None


def test_shared_nodes_belong_to_both_models() -> None:
    build = derive(two_model_prompt())
    first, second = build.export.models

    assert [model.model_id for model in build.export.models] == ["wan", "wan-t2v"]
    assert first.bindings.prompt == second.bindings.prompt == "3"
    assert first.bindings.settings == second.bindings.settings == "7"
    assert len(first.bindings.refs["image"]) == 2
    assert second.bindings.refs["image"] == ()
    assert second.capabilities.references.image.max == 0
    assert not build.invalid_reasons


def test_image_capabilities() -> None:
    build = derive(image_prompt())
    model = build.export.models[0]

    assert model.kind == "image"
    assert model.capabilities.count is not None
    assert model.capabilities.count.max == 4
    assert model.capabilities.frames is None
    assert model.capabilities.duration is None
    assert model.capabilities.references.image.max == 1
    assert not build.invalid_reasons


def test_image_model_allows_hidden_frame_nodes() -> None:
    build = derive(workflow_fixture("limits-lowered"))
    model = build.export.models[0]

    assert not build.invalid_reasons
    assert model.kind == "image"
    assert model.bindings.start == "7"
    assert model.bindings.end == "8"
    assert model.capabilities.frames is None
    assert model.capabilities.references.image.max == 1


def test_ref_indexes_must_be_contiguous() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["6"]["inputs"]["index"] = 3

    build = derive(prompt)
    assert "contiguous" in build.invalid_reasons["wan"]


def test_duplicate_model_id_is_invalid() -> None:
    prompt = two_model_prompt()
    prompt["12"]["inputs"]["id"] = "wan"

    build = derive(prompt)
    assert len(build.export.models) == 1
    assert "unique" in build.invalid_reasons["wan"]


def test_more_than_one_prompt_is_invalid() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["20"] = node("UPAIPrompt", text="x", negative="", required=True, max_chars=10)
    prompt["21"] = node("CLIPTextEncode", text=["20", 0])
    prompt["9"]["inputs"]["negative"] = ["21", 0]

    build = derive(prompt)
    assert "more than one UPAI Prompt" in build.invalid_reasons["wan"]


def test_image_model_rejects_video_refs() -> None:
    prompt = image_prompt()
    prompt["7"] = node("UPAIVideoRef", index=1, required=False, video="a.mp4")
    prompt["5"]["inputs"]["video"] = ["7", 0]

    build = derive(prompt)
    assert "video or audio" in build.invalid_reasons["sdxl"]


def test_missing_settings_is_invalid() -> None:
    prompt = copy_prompt(video_prompt())
    del prompt["7"]
    del prompt["11"]["inputs"]["fps"]

    build = derive(prompt)
    assert "no UPAI Settings" in build.invalid_reasons["wan"]


def test_limits_required_above_max_is_invalid() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["2"]["inputs"]["image_max"] = 0
    prompt["2"]["inputs"]["image_required"] = 1

    build = derive(prompt)
    assert "image_required cannot be above image_max" in build.invalid_reasons["wan"]


def test_limits_max_above_node_count_is_clamped() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["2"]["inputs"]["image_max"] = 5

    build = derive(prompt)
    assert build.export.models[0].capabilities.references.image.max == 2
    assert any("image_max" in warning for warning in build.warnings)


def test_limits_required_forces_a_frame() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["2"]["inputs"]["start_frame"] = "required"
    prompt["4"]["inputs"]["required"] = False

    build = derive(prompt)
    frames = build.export.models[0].capabilities.frames
    assert frames is not None
    assert frames.start is True
    assert frames.start_required is True


def test_required_frame_without_node_is_invalid() -> None:
    prompt = copy_prompt(video_prompt())
    del prompt["4"]
    prompt["9"]["inputs"]["latent"] = ["7", 2]
    prompt["2"]["inputs"]["start_frame"] = "required"

    build = derive(prompt)
    assert "start_frame is required" in build.invalid_reasons["wan"]


def test_output_without_model_is_a_workflow_error() -> None:
    prompt = copy_prompt(video_prompt())
    prompt["11"]["inputs"]["model"] = ["99", 0]

    build = derive(prompt)
    assert any("output 11" in error for error in build.workflow_errors)


def test_no_model_is_a_workflow_error() -> None:
    build = derive({"1": node("UPAIOutput")})
    assert build.export.models == ()
    assert "no UPAI Model node found" in build.workflow_errors
