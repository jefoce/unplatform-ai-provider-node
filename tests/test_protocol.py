"""Protocol parser and serializer tests."""

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import FakeClock, load_fixture

from upai_provider.export_capabilities_io import capabilities_from_data, capabilities_to_data
from upai_provider.jobs import JobStore
from upai_provider.mock import video_models
from upai_provider.protocol import (
    ERROR_CODES,
    Capabilities,
    CountCapability,
    Export,
    ExportModel,
    Job,
    Model,
    ModelBinding,
    ProtocolError,
    RefBinding,
    WorkflowRef,
    format_run_id,
    job_to_wire,
    models_to_wire,
    parse_config_file,
    parse_image_job_request,
    parse_job,
    parse_run_id,
    parse_video_job_request,
)
from upai_provider.protocol.parse_files import parse_jobs_records
from upai_provider.protocol.shapes import Health
from upai_provider.protocol.wire import capabilities_to_wire, health_to_wire

_REQUIRED_JOB_KEYS = {
    "id",
    "kind",
    "model",
    "status",
    "progress",
    "seed",
    "urls",
    "error",
    "usage",
    "created_at",
    "started_at",
    "finished_at",
    "expires_at",
}

_UPLOAD = f"upai-upload:{'a' * 64}"


@pytest.mark.parametrize("code", ERROR_CODES)
def test_protocol_error_accepts_known_codes(code: str) -> None:
    error = ProtocolError(code, "boom")
    assert error.code == code


def test_protocol_error_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="unknown error code: bogus"):
        ProtocolError("bogus", "boom")


_FULL_VIDEO: dict[str, Any] = {
    "model": "wan22-i2v",
    "prompt": "walk",
    "negative_prompt": "blurry",
    "duration": 4,
    "resolution": "720p",
    "aspect_ratio": "9:16",
    "seed": 7,
    "frame_images": [
        {
            "type": "image_url",
            "frame_type": "first_frame",
            "image_url": {"url": _UPLOAD},
            "future": True,
        },
        {"type": "image_url", "frame_type": "last_frame", "image_url": {"url": _UPLOAD}},
        {"type": "image_url", "frame_type": "first_frame", "image_url": {"url": _UPLOAD}},
    ],
    "input_references": [
        {"type": "image_url", "image_url": {"url": _UPLOAD}},
        {"type": "audio_url", "audio_url": {"url": _UPLOAD}},
        {"type": "image_url", "image_url": {"url": _UPLOAD}},
    ],
    "future": {"nested": 1},
}


def _expect(payload: object, parser: Callable[[object], object], field: str) -> None:
    with pytest.raises(ProtocolError) as caught:
        parser(payload)

    error = caught.value
    assert error.code == "invalid_request"
    assert error.details["field"] == field


def test_parse_full_video_body() -> None:
    video = parse_video_job_request(_FULL_VIDEO)

    assert video.model == "wan22-i2v"
    assert video.negative_prompt == "blurry"
    assert video.duration == 4
    assert video.resolution == "720p"
    assert video.aspect_ratio == "9:16"
    assert video.seed == 7

    assert [frame.frame_type for frame in video.frame_images] == [
        "first_frame",
        "last_frame",
        "first_frame",
    ]
    assert [frame.slot for frame in video.frame_images] == [1, 1, 2]

    assert [reference.kind for reference in video.input_references] == [
        "image",
        "audio",
        "image",
    ]
    assert [reference.slot for reference in video.input_references] == [1, 1, 2]


def test_parse_image_body() -> None:
    omitted = parse_image_job_request({"model": "sdxl-image", "prompt": "x"})
    assert omitted.n is None
    assert omitted.negative_prompt is None

    explicit = parse_image_job_request(
        {"model": "sdxl-image", "prompt": "x", "n": 3, "negative_prompt": "dark"}
    )
    assert explicit.n == 3
    assert explicit.negative_prompt == "dark"


def test_parse_negative_prompt_is_optional() -> None:
    video = parse_video_job_request({"model": "wan22-t2v", "prompt": "x"})
    assert video.negative_prompt is None


@pytest.mark.parametrize(
    ("parser", "payload", "field"),
    [
        (parse_video_job_request, {"model": 1, "prompt": "x"}, "model"),
        (parse_video_job_request, {"model": "m", "prompt": 2}, "prompt"),
        (parse_video_job_request, {"model": "m", "prompt": "x", "seed": True}, "seed"),
        (parse_video_job_request, {"model": "m", "prompt": "x", "duration": "long"}, "duration"),
        (
            parse_video_job_request,
            {"model": "m", "prompt": "x", "negative_prompt": 1},
            "negative_prompt",
        ),
        (parse_image_job_request, {"model": "m", "prompt": "x", "n": "3"}, "n"),
        (parse_image_job_request, {"prompt": "x"}, "model"),
    ],
)
def test_bad_types_raise(
    parser: Callable[[object], object], payload: dict[str, Any], field: str
) -> None:
    _expect(payload, parser, field)


def test_bad_frame_type() -> None:
    payload = {
        "model": "wan22-i2v",
        "prompt": "x",
        "frame_images": [
            {"type": "video_url", "frame_type": "first_frame", "image_url": {"url": "u"}}
        ],
    }
    _expect(payload, parse_video_job_request, "frame_images[0].type")


def test_video_reference_needs_video_url_object() -> None:
    payload = {
        "model": "wan22-t2v",
        "prompt": "x",
        "input_references": [{"type": "video_url", "image_url": {"url": "u"}}],
    }
    _expect(payload, parse_video_job_request, "input_references[0].video_url")


def test_media_url_rejects_unknown_scheme() -> None:
    frame = {
        "model": "wan22-i2v",
        "prompt": "x",
        "frame_images": [
            {
                "type": "image_url",
                "frame_type": "first_frame",
                "image_url": {"url": "not-a-url-at-all"},
            }
        ],
    }
    _expect(frame, parse_video_job_request, "frame_images[0].image_url.url")

    reference = {
        "model": "wan22-t2v",
        "prompt": "x",
        "input_references": [{"type": "image_url", "image_url": {"url": "not-a-url-at-all"}}],
    }
    _expect(reference, parse_video_job_request, "input_references[0].image_url.url")


@pytest.mark.parametrize("url", ["data:image/png;base64,AAAA", _UPLOAD, "http://example.com/x"])
def test_media_url_accepts_supported_schemes(url: str) -> None:
    video = parse_video_job_request(
        {
            "model": "wan22-i2v",
            "prompt": "x",
            "frame_images": [
                {"type": "image_url", "frame_type": "first_frame", "image_url": {"url": url}}
            ],
            "input_references": [{"type": "image_url", "image_url": {"url": url}}],
        }
    )

    assert video.frame_images[0].url == url
    assert video.input_references[0].url == url


def test_parse_job_fixture() -> None:
    fixture = load_fixture("job-completed.json")
    job = parse_job(fixture)

    assert isinstance(job, Job)
    assert job.status == "completed"
    assert job.urls is not None
    assert len(job.urls) == 1
    assert not hasattr(job, "request")


async def test_job_request_is_not_persisted(tmp_path: Path, clock: FakeClock) -> None:
    fixture = load_fixture("job-pending.json")
    fixture["request"] = {"model": "wan22-t2v", "prompt": "roundtrip"}
    job = parse_job(fixture)

    assert not hasattr(job, "request")
    assert "request" not in job_to_wire(job)

    store = JobStore(tmp_path / "jobs.json", clock=clock, ttl_seconds=3600)
    await store.create(job)
    reloaded = JobStore(tmp_path / "jobs.json", clock=clock, ttl_seconds=3600)
    await reloaded.load()

    stored = await reloaded.get(job.id)
    assert stored is not None
    assert not hasattr(stored, "request")
    records = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))
    assert "request" not in records["jobs"][0]


def test_format_and_parse_run_id() -> None:
    job_id = "11111111-1111-4111-8111-111111111111"
    run_id = format_run_id(job_id, 3)

    assert run_id == f"{job_id}_r3"
    assert parse_run_id(run_id) == (job_id, 3)
    assert parse_run_id(format_run_id(job_id, 0)) == (job_id, 0)
    assert not set(run_id) & set('<>:"|?*')


def test_format_run_id_rejects_bad_values() -> None:
    with pytest.raises(ValueError, match="job id"):
        format_run_id("not-a-uuid", 0)

    with pytest.raises(ValueError, match="run index"):
        format_run_id("11111111-1111-4111-8111-111111111111", -1)


def test_parse_run_id_rejects_bad_values() -> None:
    job_id = "11111111-1111-4111-8111-111111111111"

    assert parse_run_id(job_id) is None
    assert parse_run_id(f"{job_id}:0") is None
    assert parse_run_id("not-a-uuid_r0") is None
    assert parse_run_id(f"{job_id}_rx") is None
    assert parse_run_id(f"{job_id}_r-1") is None


def test_parse_job_rejects_bad_status() -> None:
    fixture = load_fixture("job-completed.json")
    fixture["status"] = "bogus"
    _expect(fixture, parse_job, "status")


def test_parse_job_base_url_is_optional() -> None:
    fixture = load_fixture("job-completed.json")
    assert parse_job(fixture).base_url == ""

    fixture["base_url"] = "http://alpha.test:9999"
    assert parse_job(fixture).base_url == "http://alpha.test:9999"


def test_parse_job_ignores_unknown_fields() -> None:
    fixture = load_fixture("job-completed.json")
    fixture["future"] = {"x": 1}
    fixture["progress"]["future"] = True

    job = parse_job(fixture)
    assert job.id == fixture["id"]


def test_parse_job_progress_waiting_on() -> None:
    fixture = load_fixture("job-pending.json")
    fixture["progress"]["waiting_on"] = "comfyui_busy"

    job = parse_job(fixture)
    assert job.progress is not None
    assert job.progress.waiting_on == "comfyui_busy"

    progress = cast(dict[str, object], job_to_wire(job)["progress"])
    assert progress["waiting_on"] == "comfyui_busy"


def test_parse_jobs_records() -> None:
    fixture = load_fixture("job-completed.json")
    jobs, skipped = parse_jobs_records({"jobs": [fixture]})
    assert len(jobs) == 1
    assert skipped == 0

    invalid, count = parse_jobs_records({"jobs": [5]})
    assert invalid == ()
    assert count == 1


def test_parse_config_file() -> None:
    config = parse_config_file(
        {
            "token": "secret",
            "allow_remote": True,
            "allow_lan": True,
            "allowed_origins": ["http://localhost:3000"],
            "allow_url_fetch": True,
            "result_ttl_hours": 1.5,
            "max_pending": 2,
            "sync_timeout_sec": 30,
            "max_running": 3,
            "future": "ignored",
        }
    )

    assert config.token == "secret"  # noqa: S105
    assert config.allow_remote is True
    assert config.allow_lan is True
    assert config.allowed_origins == ("http://localhost:3000",)
    assert config.allow_url_fetch is True
    assert config.result_ttl_hours == 1.5
    assert config.max_pending == 2
    assert config.sync_timeout_sec == 30
    assert config.max_running == 3


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"max_pending": "x"}, "max_pending"),
        ({"allow_remote": "yes"}, "allow_remote"),
        ({"allow_lan": "yes"}, "allow_lan"),
        ({"allowed_origins": "nope"}, "allowed_origins"),
        ({"token": 3}, "token"),
        ({"result_ttl_hours": "x"}, "result_ttl_hours"),
        ({"max_running": "x"}, "max_running"),
        ({"max_running": 9}, "max_running"),
    ],
)
def test_parse_config_file_rejects_bad_types(payload: dict[str, Any], field: str) -> None:
    _expect(payload, parse_config_file, field)


def test_parse_config_file_defaults_allow_lan() -> None:
    assert parse_config_file({}).allow_lan is False


def test_job_wire_has_required_fields() -> None:
    job = parse_job(load_fixture("job-completed.json"))
    wire = job_to_wire(job)

    assert set(wire) >= _REQUIRED_JOB_KEYS
    assert "base_url" not in wire
    assert wire["usage"] == {"cost": 0}
    assert isinstance(wire["urls"], list)
    assert isinstance(wire["expires_at"], int)


def test_pending_job_wire_nullables() -> None:
    job = parse_job(load_fixture("job-pending.json"))
    wire = job_to_wire(job)

    assert wire["urls"] is None
    assert wire["expires_at"] is None


def test_models_wire() -> None:
    wire = models_to_wire(video_models())
    data = wire["data"]

    assert isinstance(data, list)
    assert [model["id"] for model in data] == ["wan22-i2v", "wan22-t2v"]


def test_model_wire_workflow() -> None:
    model = replace(video_models()[0], workflow=WorkflowRef("wan22", "Wan 2.2"))
    data = cast(list[dict[str, object]], models_to_wire((model,))["data"])

    assert data[0]["workflow"] == {"id": "wan22", "name": "Wan 2.2"}

    plain = cast(list[dict[str, object]], models_to_wire((video_models()[0],))["data"])
    assert "workflow" not in plain[0]


def _model_with_reference_label(label: str) -> Model:
    base = video_models()[0]
    prompt = replace(base.capabilities.prompt, reference_label=label)
    return replace(base, capabilities=replace(base.capabilities, prompt=prompt))


def _model_with_reference_labels(labels: dict[str, str], label: str | None = None) -> Model:
    base = video_models()[0]
    prompt = replace(base.capabilities.prompt, reference_label=label, reference_labels=labels)
    return replace(base, capabilities=replace(base.capabilities, prompt=prompt))


def _model_wire_prompt(model: Model) -> dict[str, object]:
    data = cast(list[dict[str, object]], models_to_wire((model,))["data"])
    capabilities = cast(dict[str, object], data[0]["capabilities"])
    return cast(dict[str, object], capabilities["prompt"])


def test_model_wire_includes_reference_label() -> None:
    prompt = _model_wire_prompt(_model_with_reference_label("<{kind}_{n}>"))

    assert prompt["reference_label"] == "<{kind}_{n}>"


def test_model_wire_omits_missing_reference_label() -> None:
    prompt = _model_wire_prompt(video_models()[1])

    assert "reference_label" not in prompt


def test_capabilities_reference_label_round_trips() -> None:
    capabilities = _model_with_reference_label("<{kind}_{n}>").capabilities
    data = capabilities_to_data(capabilities)

    prompt = cast(dict[str, object], data["prompt"])
    assert prompt["reference_label"] == "<{kind}_{n}>"
    assert capabilities_from_data(data).prompt.reference_label == "<{kind}_{n}>"


def test_capabilities_without_reference_label_decodes_none() -> None:
    data = capabilities_to_data(video_models()[1].capabilities)

    prompt = cast(dict[str, object], data["prompt"])
    assert "reference_label" not in prompt
    assert capabilities_from_data(data).prompt.reference_label is None


def test_model_wire_includes_reference_labels() -> None:
    prompt = _model_wire_prompt(_model_with_reference_labels({"image": "<Picture {n}>"}))

    assert prompt["reference_labels"] == {"image": "<Picture {n}>"}


def test_model_wire_omits_missing_reference_labels() -> None:
    prompt = _model_wire_prompt(video_models()[1])

    assert "reference_labels" not in prompt


def test_capabilities_reference_labels_round_trip() -> None:
    labels = {"image": "<Picture {n}>", "audio": "<Audio {i}>"}
    capabilities = _model_with_reference_labels(labels).capabilities
    data = capabilities_to_data(capabilities)

    prompt = cast(dict[str, object], data["prompt"])
    assert prompt["reference_labels"] == labels
    assert capabilities_from_data(data).prompt.reference_labels == labels


def test_capabilities_serialize_global_and_per_kind_labels() -> None:
    capabilities = _model_with_reference_labels(
        {"image": "<Picture {n}>"}, label="<{kind}_{n}>"
    ).capabilities
    data = capabilities_to_data(capabilities)

    prompt = cast(dict[str, object], data["prompt"])
    assert prompt["reference_label"] == "<{kind}_{n}>"
    assert prompt["reference_labels"] == {"image": "<Picture {n}>"}

    decoded = capabilities_from_data(data).prompt
    assert decoded.reference_label == "<{kind}_{n}>"
    assert decoded.reference_labels == {"image": "<Picture {n}>"}


def test_capabilities_without_reference_labels_decodes_none() -> None:
    data = capabilities_to_data(video_models()[1].capabilities)

    assert capabilities_from_data(data).prompt.reference_labels is None


def _full_capabilities() -> Capabilities:
    """Every optional capability block populated, without a reference label."""
    base = video_models()[1].capabilities
    return replace(base, count=CountCapability(4))


def test_capabilities_data_matches_wire() -> None:
    capabilities = _full_capabilities()

    assert capabilities_to_data(capabilities) == capabilities_to_wire(capabilities)


def test_capabilities_data_reference_label_only_when_set() -> None:
    base = _full_capabilities()
    for data in (capabilities_to_data(base), capabilities_to_wire(base)):
        assert "reference_label" not in cast(dict[str, object], data["prompt"])

    prompt = replace(base.prompt, reference_label="<{kind}_{n}>")
    labeled = replace(base, prompt=prompt)
    for data in (capabilities_to_data(labeled), capabilities_to_wire(labeled)):
        assert cast(dict[str, object], data["prompt"])["reference_label"] == "<{kind}_{n}>"


def test_health_wire_instance_fields() -> None:
    health = Health(
        protocol=1,
        server="s",
        server_version="v",
        implementation="i",
        implementation_version="iv",
        auth_required=False,
        lan_allowed=False,
        max_upload_bytes=10,
        upload_quota_bytes=20,
        instance_id="instance",
        max_running=3,
    )

    wire = health_to_wire(health)
    assert wire["instance_id"] == "instance"
    assert wire["max_running"] == 3


def test_export_dataclasses_construct() -> None:
    ref = RefBinding(node="7", index=1, required=False)
    bindings = ModelBinding(
        workflow="1",
        prompt="12",
        settings="9",
        output="20",
        start="5",
        end=None,
        refs={"image": (ref,)},
    )
    model = ExportModel(
        model_id="wan22-i2v",
        name="Wan 2.2 I2V",
        description="",
        kind="video",
        enabled=True,
        output_node="20",
        bindings=bindings,
        capabilities=video_models()[0].capabilities,
    )
    export = Export(
        workflow_id="wan22",
        workflow_name="Wan 2.2",
        source="workflows/wan22.json",
        source_mtime=1.5,
        exported_at="2026-11-06T00:00:00Z",
        comfy_version="0.43.0",
        models=(model,),
        prompt={"20": {"class_type": "UPAIOutput"}},
    )

    assert export.models[0].bindings.refs["image"] == (ref,)
