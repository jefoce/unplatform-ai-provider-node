"""Fakes shared by the execution, tracker and content tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Literal

import aiohttp

from upai_provider.materialize import HttpResponseContent
from upai_provider.mock import image_models, video_models
from upai_provider.protocol import (
    ExportModel,
    FrameImage,
    ImageJobRequest,
    InputReference,
    Job,
    JobProgress,
    JobStatus,
    ModelBinding,
    RefBinding,
    VideoJobRequest,
)
from upai_provider.timeutil import iso_now

JOB_ID = "11111111-1111-4111-8111-111111111111"
SECOND_JOB_ID = "22222222-2222-4222-8222-222222222222"


def make_job(
    *,
    job_id: str = JOB_ID,
    kind: Literal["video", "image"] = "image",
    status: JobStatus = "pending",
    files: Sequence[str] = (),
    base_url: str = "http://client.local:8188",
    seed: int = 7,
) -> Job:
    return Job(
        id=job_id,
        kind=kind,
        model="workflow.model",
        status=status,
        progress=JobProgress(0, None, 0, 0, 0),
        seed=seed,
        urls=None,
        error=None,
        usage_cost=0.0,
        created_at="2026-01-01T00:00:00Z",
        started_at=None,
        finished_at=None,
        expires_at=None,
        files=tuple(files),
        base_url=base_url,
    )


class FakeStore:
    """In-memory subset of JobStore used by execution and tracker."""

    def __init__(self, jobs: Iterable[Job] = ()) -> None:
        self.jobs = {job.id: job for job in jobs}

    async def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    async def update(self, job_id: str, **changes: object) -> Job | None:
        job = self.jobs.get(job_id)
        if job is None or job.status in ("completed", "failed", "cancelled", "expired"):
            return job

        updated = replace(job, **changes)
        self.jobs[job_id] = updated
        return updated

    async def finalize(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        urls: tuple[str, ...] | None = None,
    ) -> Job | None:
        job = self.jobs.get(job_id)
        if job is None or job.status in ("completed", "failed", "cancelled", "expired"):
            return job

        progress = job.progress
        if progress is not None:
            percent = 100 if status == "completed" else progress.percent
            progress = replace(
                progress,
                percent=percent,
                queue_position=None,
                waiting_on=None,
            )
        elif status == "completed":
            progress = JobProgress(100, None, None, None, None)

        updated = replace(
            job,
            status=status,
            progress=progress,
            error=error,
            urls=urls,
            finished_at=iso_now(lambda: 0),
            expires_at=3600,
        )
        self.jobs[job_id] = updated
        return updated


class FakeContent:
    def __init__(self, chunks: Sequence[bytes]) -> None:
        self.chunks = chunks

    async def iter_chunked(self, size: int) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        body: object = None,
        headers: Mapping[str, str] | None = None,
        chunks: Sequence[bytes] = (),
    ) -> None:
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.content: HttpResponseContent = FakeContent(chunks)

    async def json(self, *, content_type: str | None = None) -> object:
        return self.body

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    """Fake HTTP and websocket surface. Records requests for assertions."""

    def __init__(self) -> None:
        self.get_responses: list[FakeResponse] = []
        self.post_responses: list[FakeResponse] = []
        self.get_calls: list[tuple[str, bool]] = []
        self.post_calls: list[tuple[str, object]] = []
        self.get_error: Exception | None = None
        self.post_error: Exception | None = None
        self.ws_messages: list[str] = []
        self.ws_calls: list[tuple[str, float]] = []

    def get(self, url: str, *, allow_redirects: bool = True) -> FakeResponse:
        self.get_calls.append((url, allow_redirects))
        if self.get_error is not None:
            raise self.get_error
        return self.get_responses.pop(0) if self.get_responses else FakeResponse(status=404)

    def post(self, url: str, *, json: object) -> FakeResponse:
        self.post_calls.append((url, json))
        if self.post_error is not None:
            raise self.post_error
        return self.post_responses.pop(0) if self.post_responses else FakeResponse(body={})

    def ws_connect(self, url: str, *, heartbeat: float) -> FakeSocket:
        self.ws_calls.append((url, heartbeat))
        messages = [FakeWsMessage(item) for item in self.ws_messages]
        self.ws_messages = []
        return FakeSocket(messages)


class FakeWsMessage:
    type = aiohttp.WSMsgType.TEXT

    def __init__(self, data: str) -> None:
        self.data = data


class FakeSocket:
    def __init__(self, messages: Sequence[FakeWsMessage]) -> None:
        self.messages = list(messages)

    async def __aenter__(self) -> FakeSocket:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def _iter(self) -> AsyncIterator[FakeWsMessage]:
        for message in self.messages:
            await asyncio.sleep(0)
            yield message

    def __aiter__(self) -> AsyncIterator[FakeWsMessage]:
        return self._iter()


class FakeTracker:
    def __init__(self) -> None:
        self.tracked: list[tuple[str, str, Mapping[str, object], str, int]] = []
        self.untracked: list[str] = []
        self.submitted: list[str] = []

    def track(
        self,
        prompt_id: str,
        *,
        job_id: str,
        prompt: Mapping[str, object],
        output_node: str,
        count: int = 1,
    ) -> None:
        self.tracked.append((prompt_id, job_id, prompt, output_node, count))

    def mark_submitted(self, prompt_id: str) -> None:
        self.submitted.append(prompt_id)

    def untrack(self, prompt_id: str) -> None:
        self.untracked.append(prompt_id)


def make_model(
    *,
    kind: Literal["video", "image"] = "image",
    prompt: str | None = "1",
    settings: str | None = "2",
    output: str = "5",
    start: str | None = None,
    end: str | None = None,
    refs: Mapping[str, Sequence[RefBinding]] | None = None,
) -> ExportModel:
    capabilities = (
        image_models()[0].capabilities if kind == "image" else video_models()[0].capabilities
    )
    ref_map: dict[str, tuple[RefBinding, ...]] = {
        "image": (),
        "video": (),
        "audio": (),
    }
    for key, values in (refs or {}).items():
        ref_map[key] = tuple(values)

    return ExportModel(
        model_id="workflow.model",
        name="Model",
        description="",
        kind=kind,
        enabled=True,
        output_node=output,
        bindings=ModelBinding(
            workflow="1",
            prompt=prompt,
            settings=settings,
            output=output,
            start=start,
            end=end,
            refs=ref_map,
        ),
        capabilities=capabilities,
    )


def make_prompt(*, with_start: bool = False) -> dict[str, object]:
    prompt: dict[str, object] = {
        "1": {"class_type": "UPAIPrompt", "inputs": {"text": "editor prompt"}},
        "2": {
            "class_type": "UPAISettings",
            "inputs": {
                "test_resolution": "480p",
                "test_aspect_ratio": "16:9",
                "test_duration": 5,
                "test_count": 1,
                "test_seed": 0,
            },
        },
        "3": {"class_type": "UPAIImageRef", "inputs": {"image": "editor.png", "index": 1}},
        "6": {"class_type": "ImageInvert", "inputs": {"image": ["3", 0]}},
        "5": {"class_type": "UPAIOutput", "inputs": {"images": ["6", 0], "upai_job": ""}},
    }
    if with_start:
        prompt["4"] = {"class_type": "UPAIStartFrame", "inputs": {"image": "start.png"}}

    return prompt


def make_sampler_prompt(
    *,
    steps: Sequence[int],
    class_type: str = "KSampler",
) -> dict[str, object]:
    """Build a source, one sampler per step count, and an output node."""
    prompt: dict[str, object] = {"1": {"class_type": "UPAIImageRef", "inputs": {}}}
    previous = "1"
    for index, count in enumerate(steps):
        node_id = str(10 + index)
        prompt[node_id] = {
            "class_type": class_type,
            "inputs": {"steps": count, "latent": [previous, 0]},
        }
        previous = node_id

    prompt["99"] = {"class_type": "UPAIOutput", "inputs": {"images": [previous, 0]}}
    return prompt


def make_request(
    *,
    kind: Literal["video", "image"] = "image",
    prompt: str = "job prompt",
    seed: int = 7,
    refs: Sequence[InputReference] = (),
    frames: Sequence[FrameImage] = (),
    resolution: str | None = None,
    aspect_ratio: str | None = None,
    duration: float | None = None,
    n: int | None = None,
) -> ImageJobRequest | VideoJobRequest:
    if kind == "image":
        return ImageJobRequest(
            model="workflow.model",
            prompt=prompt,
            n=n,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            seed=seed,
            input_references=tuple(refs),
        )

    return VideoJobRequest(
        model="workflow.model",
        prompt=prompt,
        duration=duration,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        seed=seed,
        frame_images=tuple(frames),
        input_references=tuple(refs),
    )
