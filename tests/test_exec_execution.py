"""Prompt patching, loopback submit and dispatch tests. All HTTP is fake."""

import base64
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

import aiohttp
import numpy as np
import pytest
import test_nodes_support as nodes_support
from test_exec_support import (
    JOB_ID,
    FakeResponse,
    FakeSession,
    FakeStore,
    FakeTracker,
    make_job,
    make_model,
    make_prompt,
    make_request,
)

import upai_provider.nodes.output as output_module
from upai_provider.execution import execute_job
from upai_provider.execution_errors import (
    ComfyUnavailableError,
    PromptRejectedError,
    WorkflowInvalidError,
)
from upai_provider.execution_patch import PromptRun, build_prompt
from upai_provider.execution_runs import build_prompts, count_mode_from_prompt
from upai_provider.execution_submit import submit_prompt
from upai_provider.jobs import JobStore
from upai_provider.materialize import MaterializedInput, MaterializedMedia
from upai_provider.nodes.output import UPaiOutput
from upai_provider.protocol import (
    FrameImage,
    InputReference,
    Job,
    JobStatus,
    RefBinding,
    format_run_id,
)
from upai_provider.scheduler import Scheduler
from upai_provider.tracker import Tracker
from upai_provider.uploads import UploadStore


def _inputs(document: dict[str, object], node_id: str) -> dict[str, object]:
    node = document[node_id]
    assert isinstance(node, dict)
    inputs = node["inputs"]
    assert isinstance(inputs, dict)
    return cast(dict[str, object], inputs)


class CancelTracker(FakeTracker):
    """Fake tracker that records cancel state for a partial submit failure."""

    def __init__(self) -> None:
        super().__init__()
        self.cancelling: list[str] = []
        self.running: set[str] = set()

    def mark_cancelling(self, prompt_id: str) -> None:
        self.cancelling.append(prompt_id)

    def is_running(self, prompt_id: str) -> bool:
        return prompt_id in self.running


class FinalAfterStore(FakeStore):
    """Fake store that reports a final job after a number of reads."""

    def __init__(self, job: Job, *, final_after: int) -> None:
        super().__init__((job,))
        self._reads = 0
        self._final_after = final_after
        self._final = replace(job, status="failed")

    async def get(self, job_id: str) -> Job | None:
        self._reads += 1
        return self._final if self._reads > self._final_after else self.jobs.get(job_id)


class RaisingFinalizeStore(FakeStore):
    """Fake store whose finalize raises, to prove pins still release."""

    async def finalize(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        urls: tuple[str, ...] | None = None,
    ) -> Job | None:
        raise RuntimeError("finalize down")


class CompletingStore(FakeStore):
    """Fake store that completes child 0 on the second read."""

    def __init__(self, job: Job, *, tracker_box: list[Tracker | None]) -> None:
        super().__init__((job,))
        self.tracker_box = tracker_box
        self.reads = 0
        self.fired = False

    async def get(self, job_id: str) -> Job | None:
        self.reads += 1
        if not self.fired and self.reads == 2:
            self.fired = True
            tracker = self.tracker_box[0]
            if tracker is not None:
                await tracker.handle_message(
                    {"type": "execution_success", "data": {"prompt_id": JOB_ID}}
                )

        return await super().get(job_id)


async def _no_active_jobs() -> set[str]:
    return set()


async def _no_dispatch(job_id: str) -> None:
    return None


def _data_url(data: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def _media(tmp_path: Path, *, image: bool = True, frame: bool = False) -> MaterializedMedia:
    job_dir = tmp_path / "input" / JOB_ID
    job_dir.mkdir(parents=True)
    inputs: list[MaterializedInput] = []
    if image:
        path = job_dir / "image_1.png"
        path.write_bytes(b"image")
        inputs.append(MaterializedInput("image", 1, path))
    if frame:
        path = job_dir / "first_frame_1.png"
        path.write_bytes(b"frame")
        inputs.append(MaterializedInput("first_frame", 1, path))

    return MaterializedMedia(job_dir=job_dir, inputs=tuple(inputs))


def _uploads(tmp_path: Path) -> UploadStore:
    return UploadStore(tmp_path / "uploads", max_bytes=1024 * 1024, clock=lambda: 0.0)


def test_build_prompt_patches_and_keeps_export_untouched(tmp_path: Path) -> None:
    prompt = make_prompt(with_start=True)
    model = make_model(
        kind="video",
        start="4",
        refs={"image": (RefBinding("3", 1, False),)},
    )
    request = make_request(
        kind="video",
        prompt="job prompt",
        seed=11,
        frames=(FrameImage("first_frame", "unused", 1),),
        resolution="720p",
        aspect_ratio="9:16",
        duration=3,
    )

    built = build_prompt(
        prompt,
        model,
        request,
        _media(tmp_path, frame=True),
        job_id=JOB_ID,
        seed=11,
        count=1,
    )

    assert _inputs(prompt, "1")["text"] == "editor prompt"
    assert _inputs(built, "1")["text"] == "job prompt"
    assert _inputs(built, "2")["test_resolution"] == "720p"
    assert _inputs(built, "2")["test_aspect_ratio"] == "9:16"
    assert _inputs(built, "2")["test_duration"] == 3
    assert _inputs(built, "2")["test_seed"] == 11
    assert str(_inputs(built, "3")["image"]).endswith("image_1.png")
    assert str(_inputs(built, "4")["image"]).endswith("first_frame_1.png")
    assert _inputs(built, "5")["upai_job"] == JOB_ID


@pytest.mark.parametrize("kind", ["image", "video"])
def test_build_prompt_patches_negative_prompt(kind: str, tmp_path: Path) -> None:
    prompt = make_prompt()
    _inputs(prompt, "1")["negative"] = "editor negative"
    request = replace(
        make_request(kind=cast(Literal["image", "video"], kind)), negative_prompt="blurry"
    )

    built = build_prompt(
        prompt,
        make_model(kind=cast(Literal["image", "video"], kind)),
        request,
        _media(tmp_path),
        job_id=JOB_ID,
        seed=7,
        count=1,
    )

    assert _inputs(built, "1")["negative"] == "blurry"


@pytest.mark.parametrize("kind", ["image", "video"])
def test_build_prompt_keeps_editor_negative_when_request_omits_it(
    kind: str, tmp_path: Path
) -> None:
    prompt = make_prompt()
    _inputs(prompt, "1")["negative"] = "editor negative"

    built = build_prompt(
        prompt,
        make_model(kind=cast(Literal["image", "video"], kind)),
        make_request(kind=cast(Literal["image", "video"], kind)),
        _media(tmp_path),
        job_id=JOB_ID,
        seed=7,
        count=1,
    )

    assert _inputs(built, "1")["negative"] == "editor negative"


def test_missing_optional_reference_is_cleared(tmp_path: Path) -> None:
    model = make_model(refs={"image": (RefBinding("3", 1, False),)})
    built = build_prompt(
        make_prompt(),
        model,
        make_request(),
        _media(tmp_path, image=False),
        job_id=JOB_ID,
        seed=7,
        count=1,
    )

    assert _inputs(built, "3")["image"] == ""


def test_image_settings_use_request_values(tmp_path: Path) -> None:
    model = make_model()
    built = build_prompt(
        make_prompt(),
        model,
        make_request(resolution="512", aspect_ratio="16:9", n=2),
        _media(tmp_path),
        job_id=JOB_ID,
        seed=42,
        count=2,
    )

    assert _inputs(built, "2")["test_resolution"] == "512"
    assert _inputs(built, "2")["test_aspect_ratio"] == "16:9"
    assert _inputs(built, "2")["test_count"] == 2
    assert _inputs(built, "2")["test_seed"] == 42


def test_missing_bound_node_is_workflow_invalid(tmp_path: Path) -> None:
    model = make_model(prompt="99")

    with pytest.raises(WorkflowInvalidError):
        build_prompt(
            make_prompt(),
            model,
            make_request(),
            _media(tmp_path),
            job_id=JOB_ID,
            seed=7,
            count=1,
        )


def test_runs_mode_builds_one_prompt_per_run(tmp_path: Path) -> None:
    model = make_model()

    runs = build_prompts(
        make_prompt(),
        model,
        make_request(n=3),
        _media(tmp_path),
        job_id=JOB_ID,
        seed=7,
        count=3,
        count_mode="runs",
    )

    assert [run.seed for run in runs] == [7, 8, 9]
    assert [run.count for run in runs] == [1, 1, 1]
    assert runs[0].prompt_id == JOB_ID
    assert len({run.prompt_id for run in runs}) == 3
    assert [_inputs(cast(dict[str, object], run.prompt), "5")["upai_job"] for run in runs] == [
        format_run_id(JOB_ID, index) for index in range(3)
    ]
    for run in runs:
        assert _inputs(cast(dict[str, object], run.prompt), "2")["test_count"] == 1


def test_count_mode_comes_from_settings_node_only() -> None:
    model = make_model()
    prompt = make_prompt()
    assert count_mode_from_prompt(prompt, model) == "batch"

    _inputs(prompt, "2")["count_mode"] = "runs"
    assert count_mode_from_prompt(prompt, model) == "runs"


async def test_submit_prompt_posts_partial_targets() -> None:
    session = FakeSession()
    session.post_responses.append(FakeResponse(status=200, body={}))
    run = PromptRun(prompt_id=JOB_ID, prompt={"1": {}}, seed=7, count=1)

    await submit_prompt(
        session,
        server_url="http://127.0.0.1:8188",
        run=run,
        client_id="upai-instance",
        output_node="5",
    )

    assert session.post_calls == [
        (
            "http://127.0.0.1:8188/prompt",
            {
                "prompt": {"1": {}},
                "prompt_id": JOB_ID,
                "client_id": "upai-instance",
                "partial_execution_targets": ["5"],
            },
        )
    ]


async def test_submit_prompt_maps_400_to_rejected() -> None:
    session = FakeSession()
    session.post_responses.append(
        FakeResponse(status=400, body={"node_errors": {"5": {"message": "bad node"}}})
    )

    with pytest.raises(PromptRejectedError) as raised:
        await submit_prompt(
            session,
            server_url="http://127.0.0.1:8188",
            run=PromptRun(prompt_id=JOB_ID, prompt={}, seed=7, count=1),
            client_id="upai-instance",
            output_node="5",
        )

    assert raised.value.node_errors["5"] == {"message": "bad node"}


async def test_submit_prompt_rejects_200_with_node_errors() -> None:
    session = FakeSession()
    session.post_responses.append(
        FakeResponse(status=200, body={"node_errors": {"5": {"message": "bad node"}}})
    )

    with pytest.raises(PromptRejectedError):
        await submit_prompt(
            session,
            server_url="http://127.0.0.1:8188",
            run=PromptRun(prompt_id=JOB_ID, prompt={}, seed=7, count=1),
            client_id="upai-instance",
            output_node="5",
        )


async def test_submit_prompt_maps_server_error_to_unavailable() -> None:
    session = FakeSession()
    session.post_responses.append(FakeResponse(status=503, body={}))

    with pytest.raises(ComfyUnavailableError):
        await submit_prompt(
            session,
            server_url="http://127.0.0.1:8188",
            run=PromptRun(prompt_id=JOB_ID, prompt={}, seed=7, count=1),
            client_id="upai-instance",
            output_node="5",
        )


async def test_submit_prompt_maps_connection_error() -> None:
    session = FakeSession()
    session.post_error = aiohttp.ClientConnectionError("down")

    with pytest.raises(ComfyUnavailableError):
        await submit_prompt(
            session,
            server_url="http://127.0.0.1:8188",
            run=PromptRun(prompt_id=JOB_ID, prompt={}, seed=7, count=1),
            client_id="upai-instance",
            output_node="5",
        )


async def test_execute_job_materializes_patches_and_submits(
    tmp_path: Path, png_bytes: bytes
) -> None:
    store = FakeStore((make_job(seed=7),))
    tracker = FakeTracker()
    session = FakeSession()
    session.post_responses.append(FakeResponse(status=200, body={}))
    request = make_request(
        prompt="job prompt",
        seed=7,
        refs=(InputReference("image", _data_url(png_bytes), 1),),
        n=2,
    )

    outcome = await execute_job(
        job=make_job(seed=7),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=make_prompt(),
        request=request,
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=2,
    )

    assert outcome.is_submitted
    assert len(tracker.tracked) == 1
    assert tracker.tracked[0][0] == JOB_ID
    assert tracker.tracked[0][3] == "5"
    assert len(session.post_calls) == 1
    body = cast(dict[str, object], session.post_calls[0][1])
    assert body["partial_execution_targets"] == ["5"]
    assert body["client_id"] == "upai-instance"
    sent = cast(dict[str, object], body["prompt"])
    assert _inputs(sent, "1")["text"] == "job prompt"
    assert _inputs(sent, "2")["test_count"] == 2
    assert Path(cast(str, _inputs(sent, "3")["image"])).exists()
    assert _inputs(sent, "5")["upai_job"] == JOB_ID
    assert (await store.get(JOB_ID)) is not None


async def test_execute_job_runs_mode_submits_each_run(tmp_path: Path, png_bytes: bytes) -> None:
    prompt = make_prompt()
    _inputs(prompt, "2")["count_mode"] = "runs"
    store = FakeStore((make_job(seed=7),))
    tracker = FakeTracker()
    session = FakeSession()
    session.post_responses.extend(FakeResponse(status=200, body={}) for _ in range(3))

    outcome = await execute_job(
        job=make_job(seed=7),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=prompt,
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
            n=3,
        ),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=3,
    )

    assert outcome.is_submitted
    assert len(outcome.prompt_ids) == 3
    assert len(tracker.tracked) == 3
    assert len(session.post_calls) == 3
    seeds = []
    run_ids = []
    for _, raw in session.post_calls:
        body = cast(dict[str, object], raw)
        sent = cast(dict[str, object], body["prompt"])
        seeds.append(_inputs(sent, "2")["test_seed"])
        run_ids.append(_inputs(sent, "5")["upai_job"])
        assert _inputs(sent, "2")["test_count"] == 1
    assert seeds == [7, 8, 9]
    assert run_ids == [format_run_id(JOB_ID, index) for index in range(3)]


async def test_runs_mode_count_three_writes_distinct_files_and_urls(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    nodes_support.set_directories(input=tmp_path, temp=tmp_path)
    prompt = make_prompt()
    _inputs(prompt, "2")["count_mode"] = "runs"
    session = FakeSession()
    session.post_responses.extend(FakeResponse(status=200, body={}) for _ in range(3))

    outcome = await execute_job(
        job=make_job(seed=7),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=prompt,
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
            n=3,
        ),
        store=FakeStore((make_job(seed=7),)),
        uploads=_uploads(tmp_path),
        session=session,
        tracker=None,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=3,
    )
    assert outcome.is_submitted

    posted = [
        cast(dict[str, object], cast(dict[str, object], raw)["prompt"])
        for _, raw in session.post_calls
    ]
    run_ids = [cast(str, _inputs(document, "5")["upai_job"]) for document in posted]
    seeds = [_inputs(document, "2")["test_seed"] for document in posted]
    assert run_ids == [format_run_id(JOB_ID, index) for index in range(3)]
    assert len(set(seeds)) == 3

    captured: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        output_module,
        "register_output",
        lambda job_id, files: captured.append((job_id, list(files))),
    )
    for run_id in run_ids:
        UPaiOutput.execute(
            model={"kind": "image"},
            upai_job=run_id,
            format="png",
            crf=18,
            preview=False,
            images=np.zeros((1, 4, 8, 3), dtype=np.float32),
        )

    assert [item[0] for item in captured] == run_ids
    files = [path for _, paths in captured for path in paths]
    assert len(files) == len(set(files)) == 3
    assert [Path(path).name for path in files] == ["0-0.png", "1-0.png", "2-0.png"]

    store = FakeStore((make_job(files=tuple(files)),))
    tracker = Tracker(
        store=store,
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        clock=lambda: 0.0,
    )
    for prompt_id, document in zip(outcome.prompt_ids, posted, strict=True):
        tracker.track(prompt_id, job_id=JOB_ID, prompt=document, output_node="5", count=1)
        await tracker.handle_message(
            {"type": "execution_success", "data": {"prompt_id": prompt_id}}
        )

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.urls is not None
    assert len(done.urls) == len(set(done.urls)) == 3
    assert [url.rsplit("=", 1)[1] for url in done.urls] == ["0", "1", "2"]


async def test_execute_job_400_fails_job_and_untracks_run(tmp_path: Path, png_bytes: bytes) -> None:
    store = FakeStore((make_job(),))
    tracker = CancelTracker()
    session = FakeSession()
    uploads = _uploads(tmp_path)
    session.post_responses.append(
        FakeResponse(status=400, body={"node_errors": {"5": {"message": "bad node"}}})
    )
    cancelled: list[tuple[str, bool]] = []

    async def cancel(prompt_id: str, is_running: bool) -> None:
        cancelled.append((prompt_id, is_running))

    outcome = await execute_job(
        job=make_job(),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=make_prompt(),
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
        ),
        store=store,
        uploads=uploads,
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=1,
        cancel_prompt=cancel,
    )

    assert not outcome.is_submitted
    assert outcome.node_errors == {"5": {"message": "bad node"}}
    stored = await store.get(JOB_ID)
    assert stored is not None
    assert stored.status == "failed"
    assert "5: bad node" in (stored.error or "")
    assert tracker.untracked == [JOB_ID]
    assert tracker.cancelling == []
    assert cancelled == []
    sha256 = hashlib.sha256(png_bytes).hexdigest()
    assert uploads._pin_counts.get(sha256, 0) == 0


async def test_execute_job_200_node_errors_keeps_run_tracked(
    tmp_path: Path, png_bytes: bytes
) -> None:
    store = FakeStore((make_job(),))
    tracker = CancelTracker()
    session = FakeSession()
    session.post_responses.append(
        FakeResponse(status=200, body={"node_errors": {"5": {"message": "bad node"}}})
    )
    cancelled: list[tuple[str, bool]] = []

    async def cancel(prompt_id: str, is_running: bool) -> None:
        cancelled.append((prompt_id, is_running))

    outcome = await execute_job(
        job=make_job(),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=make_prompt(),
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
        ),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=1,
        cancel_prompt=cancel,
    )

    assert not outcome.is_submitted
    assert outcome.node_errors == {"5": {"message": "bad node"}}
    assert tracker.cancelling == [JOB_ID]
    assert cancelled == [(JOB_ID, False)]
    assert tracker.untracked == []


async def test_execute_job_transport_error_keeps_run_tracked(
    tmp_path: Path, png_bytes: bytes
) -> None:
    store = FakeStore((make_job(),))
    tracker = CancelTracker()
    session = FakeSession()
    session.post_error = aiohttp.ClientConnectionError("down")
    cancelled: list[tuple[str, bool]] = []

    async def cancel(prompt_id: str, is_running: bool) -> None:
        cancelled.append((prompt_id, is_running))

    outcome = await execute_job(
        job=make_job(),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=make_prompt(),
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
        ),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=1,
        cancel_prompt=cancel,
    )

    assert not outcome.is_submitted
    assert outcome.error == "prompt route is unreachable"
    assert tracker.cancelling == [JOB_ID]
    assert cancelled == [(JOB_ID, False)]
    assert tracker.untracked == []


async def test_transport_error_with_healthy_websocket_releases_the_slot(
    tmp_path: Path, png_bytes: bytes
) -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.post_error = aiohttp.ClientConnectionError("down")
    tracker = Tracker(
        store=store,
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        session=session,
        clock=lambda: 0.0,
    )
    scheduler = Scheduler(
        cast(JobStore, store),
        max_running=1,
        fetch_active_jobs=_no_active_jobs,
        dispatch=_no_dispatch,
        tracker=tracker,
    )
    cancelled: list[tuple[str, bool]] = []

    async def cancel(prompt_id: str, is_running: bool) -> None:
        cancelled.append((prompt_id, is_running))

    outcome = await execute_job(
        job=make_job(),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=make_prompt(),
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
        ),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=1,
        cancel_prompt=cancel,
    )

    assert not outcome.is_submitted
    assert outcome.error == "prompt route is unreachable"
    stored = await store.get(JOB_ID)
    assert stored is not None
    assert stored.status == "failed"
    assert tracker.child_prompt_ids(JOB_ID) == ()
    assert scheduler._is_released(JOB_ID, stored)


async def test_execute_job_partial_submit_failure_keeps_submitted_children(
    tmp_path: Path, png_bytes: bytes
) -> None:
    prompt = make_prompt()
    _inputs(prompt, "2")["count_mode"] = "runs"
    store = FakeStore((make_job(seed=7),))
    tracker = CancelTracker()
    session = FakeSession()
    session.post_responses.extend(
        [
            FakeResponse(status=200, body={}),
            FakeResponse(status=400, body={"node_errors": {"5": {"message": "bad node"}}}),
        ]
    )
    cancelled: list[tuple[str, bool]] = []

    async def cancel(prompt_id: str, is_running: bool) -> None:
        cancelled.append((prompt_id, is_running))

    outcome = await execute_job(
        job=make_job(seed=7),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=prompt,
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
            n=3,
        ),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=3,
        cancel_prompt=cancel,
    )

    assert not outcome.is_submitted
    assert len(tracker.tracked) == 3
    failed_id = tracker.tracked[1][0]
    tail_id = tracker.tracked[2][0]
    assert tracker.cancelling == [JOB_ID]
    assert cancelled == [(JOB_ID, False)]
    assert tracker.untracked == [failed_id, tail_id]
    stored = await store.get(JOB_ID)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.error == "5: bad node"


async def test_execute_job_marks_every_run_submitted(tmp_path: Path, png_bytes: bytes) -> None:
    prompt = make_prompt()
    _inputs(prompt, "2")["count_mode"] = "runs"
    store = FakeStore((make_job(seed=7),))
    tracker = FakeTracker()
    session = FakeSession()
    session.post_responses.extend(FakeResponse(status=200, body={}) for _ in range(3))

    outcome = await execute_job(
        job=make_job(seed=7),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=prompt,
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
            n=3,
        ),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=3,
    )

    assert outcome.is_submitted
    assert tracker.submitted == [tracked[0] for tracked in tracker.tracked]
    assert len(tracker.submitted) == 3


async def test_execute_job_bad_binding_fails_job(tmp_path: Path, png_bytes: bytes) -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    uploads = _uploads(tmp_path)

    outcome = await execute_job(
        job=make_job(),
        model=make_model(prompt="99", refs={"image": (RefBinding("3", 1, False),)}),
        prompt=make_prompt(),
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
        ),
        store=store,
        uploads=uploads,
        session=session,
        tracker=None,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=1,
    )

    assert not outcome.is_submitted
    assert outcome.node_errors is not None
    stored = await store.get(JOB_ID)
    assert stored is not None
    assert stored.status == "failed"
    assert session.post_calls == []
    sha256 = hashlib.sha256(png_bytes).hexdigest()
    assert uploads._pin_counts.get(sha256, 0) == 0


async def test_execute_job_unavailable_server_fails_job(tmp_path: Path, png_bytes: bytes) -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    uploads = _uploads(tmp_path)
    session.post_responses.append(FakeResponse(status=503, body={}))

    outcome = await execute_job(
        job=make_job(),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=make_prompt(),
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
        ),
        store=store,
        uploads=uploads,
        session=session,
        tracker=None,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=1,
    )

    assert not outcome.is_submitted
    assert outcome.error == "prompt route returned 503"
    stored = await store.get(JOB_ID)
    assert stored is not None
    assert stored.status == "failed"
    sha256 = hashlib.sha256(png_bytes).hexdigest()
    assert uploads._pin_counts.get(sha256, 0) == 0


async def test_execute_job_stops_when_job_final_before_submit(tmp_path: Path) -> None:
    prompt = make_prompt()
    _inputs(prompt, "2")["count_mode"] = "runs"
    store = FinalAfterStore(make_job(seed=7), final_after=0)
    tracker = FakeTracker()
    session = FakeSession()

    outcome = await execute_job(
        job=make_job(seed=7),
        model=make_model(),
        prompt=prompt,
        request=make_request(n=2),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=2,
    )

    assert not outcome.is_submitted
    assert outcome.error == "job is no longer active"
    assert session.post_calls == []
    assert len(tracker.tracked) == 2
    assert len(tracker.untracked) == 2
    assert JOB_ID in tracker.untracked


async def test_execute_job_releases_upload_pins_when_job_is_already_final(
    tmp_path: Path, png_bytes: bytes
) -> None:
    job = make_job(status="failed")
    store = FakeStore((job,))
    uploads = _uploads(tmp_path)
    request = make_request(refs=(InputReference("image", _data_url(png_bytes), 1),))

    outcome = await execute_job(
        job=job,
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=make_prompt(),
        request=request,
        store=store,
        uploads=uploads,
        session=FakeSession(),
        tracker=FakeTracker(),
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=1,
    )

    assert not outcome.is_submitted
    assert outcome.error == "job is no longer active"
    sha256 = hashlib.sha256(png_bytes).hexdigest()
    assert uploads._pin_counts.get(sha256, 0) == 0


async def test_execute_job_releases_pins_when_materialize_fails(
    tmp_path: Path, png_bytes: bytes
) -> None:
    job = make_job(status="failed")
    store = FakeStore((job,))
    uploads = _uploads(tmp_path)
    request = make_request(
        refs=(
            InputReference("image", _data_url(png_bytes), 1),
            InputReference("image", "ftp://example.test/b.png", 2),
        )
    )

    outcome = await execute_job(
        job=job,
        model=make_model(),
        prompt=make_prompt(),
        request=request,
        store=store,
        uploads=uploads,
        session=FakeSession(),
        tracker=FakeTracker(),
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=1,
    )

    assert not outcome.is_submitted
    sha256 = hashlib.sha256(png_bytes).hexdigest()
    assert uploads._pin_counts.get(sha256, 0) == 0


async def test_execute_job_releases_pins_when_finalize_raises(
    tmp_path: Path, png_bytes: bytes
) -> None:
    store = RaisingFinalizeStore((make_job(),))
    uploads = _uploads(tmp_path)
    request = make_request(refs=(InputReference("image", _data_url(png_bytes), 1),))

    with pytest.raises(RuntimeError, match="finalize down"):
        await execute_job(
            job=make_job(),
            model=make_model(prompt="99", refs={"image": (RefBinding("3", 1, False),)}),
            prompt=make_prompt(),
            request=request,
            store=store,
            uploads=uploads,
            session=FakeSession(),
            tracker=None,
            input_root=tmp_path / "input",
            instance_id="instance",
            server_url="http://127.0.0.1:8188",
            count=1,
        )

    sha256 = hashlib.sha256(png_bytes).hexdigest()
    assert uploads._pin_counts.get(sha256, 0) == 0


async def test_execute_job_stops_after_job_turns_final(tmp_path: Path) -> None:
    prompt = make_prompt()
    _inputs(prompt, "2")["count_mode"] = "runs"
    store = FinalAfterStore(make_job(seed=7), final_after=1)
    tracker = FakeTracker()
    session = FakeSession()
    session.post_responses.append(FakeResponse(status=200, body={}))

    outcome = await execute_job(
        job=make_job(seed=7),
        model=make_model(),
        prompt=prompt,
        request=make_request(n=2),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=2,
    )

    assert not outcome.is_submitted
    assert outcome.error == "job is no longer active"
    assert len(session.post_calls) == 1
    assert len(tracker.tracked) == 2
    assert len(tracker.untracked) == 1
    assert JOB_ID not in tracker.untracked


async def test_child_zero_completion_does_not_finalize_before_next_submit(
    tmp_path: Path, png_bytes: bytes
) -> None:
    prompt = make_prompt()
    _inputs(prompt, "2")["count_mode"] = "runs"
    tracker_box: list[Tracker | None] = [None]
    store = CompletingStore(make_job(seed=7), tracker_box=tracker_box)
    tracker = Tracker(
        store=store,
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        clock=lambda: 0.0,
    )
    tracker_box[0] = tracker
    session = FakeSession()
    session.post_responses.extend(FakeResponse(status=200, body={}) for _ in range(2))

    outcome = await execute_job(
        job=make_job(seed=7),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=prompt,
        request=make_request(
            refs=(InputReference("image", _data_url(png_bytes), 1),),
            n=2,
        ),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=2,
    )

    assert outcome.is_submitted
    assert len(session.post_calls) == 2
    stored = await store.get(JOB_ID)
    assert stored is not None
    assert stored.status not in ("completed", "failed", "cancelled", "expired")


async def test_execute_job_materialize_error_fails_job(tmp_path: Path) -> None:
    store = FakeStore((make_job(),))
    request = make_request(refs=(InputReference("image", "https://example.test/a.png", 1),))

    outcome = await execute_job(
        job=make_job(),
        model=make_model(refs={"image": (RefBinding("3", 1, False),)}),
        prompt=make_prompt(),
        request=request,
        store=store,
        uploads=_uploads(tmp_path),
        session=FakeSession(),
        tracker=None,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=1,
    )

    assert not outcome.is_submitted
    assert outcome.error == "URL fetch is disabled"
    stored = await store.get(JOB_ID)
    assert stored is not None
    assert stored.status == "failed"


async def test_execute_job_cancels_child_when_job_turns_final_after_submit(
    tmp_path: Path,
) -> None:
    prompt = make_prompt()
    _inputs(prompt, "2")["count_mode"] = "runs"
    store = FinalAfterStore(make_job(seed=7), final_after=1)
    tracker = CancelTracker()
    session = FakeSession()
    session.post_responses.append(FakeResponse(status=200, body={}))
    cancelled: list[tuple[str, bool]] = []

    async def cancel(prompt_id: str, is_running: bool) -> None:
        cancelled.append((prompt_id, is_running))

    outcome = await execute_job(
        job=make_job(seed=7),
        model=make_model(),
        prompt=prompt,
        request=make_request(n=2),
        store=store,
        uploads=_uploads(tmp_path),
        session=session,
        tracker=tracker,
        input_root=tmp_path / "input",
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        count=2,
        cancel_prompt=cancel,
    )

    assert not outcome.is_submitted
    assert outcome.error == "job is no longer active"
    assert len(session.post_calls) == 1
    assert len(tracker.tracked) == 2
    assert len(tracker.untracked) == 1
    assert JOB_ID not in tracker.untracked
    assert tracker.cancelling == [JOB_ID]
    assert cancelled == [(JOB_ID, False)]
