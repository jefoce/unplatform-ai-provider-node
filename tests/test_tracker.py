"""Tracker event, finalize and poll tests. No real websocket or ComfyUI."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from test_exec_support import (
    JOB_ID,
    SECOND_JOB_ID,
    FakeResponse,
    FakeSession,
    FakeStore,
    make_job,
    make_prompt,
    make_sampler_prompt,
)

from upai_provider.constants import ERROR_TEXT_MAX_CHARS
from upai_provider.tracker import Tracker, websocket_url

WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"


def _workflow_samplers(name: str) -> tuple[str, tuple[int, ...]]:
    """Read the sampler class and the first two step counts from a workflow."""
    data = json.loads((WORKFLOWS / name).read_text(encoding="utf-8"))
    nodes = data["nodes"]
    class_type = next(node["type"] for node in nodes if node["type"] == "SamplerCustomAdvanced")
    if name.startswith("minimax"):
        steps = tuple(
            int(node["widgets_values"][1]) for node in nodes if node["type"] == "BasicScheduler"
        )
    else:
        manual = [node for node in nodes if node["type"] == "ManualSigmas"]
        steps = tuple(len(str(node["widgets_values"][0]).split(",")) - 1 for node in manual[:2])

    return class_type, steps[:2]


def _wan_advanced_samplers() -> list[tuple[int, int, int]]:
    """Read (steps, start_at_step, end_at_step) for each KSamplerAdvanced in the Wan workflow."""
    data = json.loads((WORKFLOWS / "wan-2-2-upai.json").read_text(encoding="utf-8"))
    return [
        (
            int(node["widgets_values"][3]),
            int(node["widgets_values"][7]),
            int(node["widgets_values"][8]),
        )
        for node in data["nodes"]
        if node["type"] == "KSamplerAdvanced"
    ]


def _tracker(
    store: FakeStore,
    *,
    session: object | None = None,
    cancel_prompt: Callable[[str, bool], Awaitable[None]] | None = None,
) -> Tracker:
    return Tracker(
        store=store,
        instance_id="instance",
        server_url="http://127.0.0.1:8188",
        session=session,
        clock=lambda: 0.0,
        cancel_prompt=cancel_prompt,
    )


async def test_execution_success_completes_job_and_excludes_cached_nodes() -> None:
    store = FakeStore((make_job(files=("a.png", "b.png")),))
    tracker = _tracker(store)
    tracker.track(
        JOB_ID,
        job_id=JOB_ID,
        prompt=make_prompt(),
        output_node="5",
        count=2,
    )

    await tracker.handle_message({"type": "execution_start", "data": {"prompt_id": JOB_ID}})
    start = await store.get(JOB_ID)
    assert start is not None
    assert start.status == "in_progress"
    assert start.started_at is not None

    await tracker.handle_message(
        {"type": "execution_cached", "data": {"prompt_id": JOB_ID, "nodes": ["3"]}}
    )
    await tracker.handle_message({"type": "executing", "data": {"prompt_id": JOB_ID, "node": "6"}})
    await tracker.handle_message(
        {
            "type": "progress_state",
            "data": {
                "prompt_id": JOB_ID,
                "nodes": {
                    "6": {"value": 5, "max": 10, "state": "running"},
                },
            },
        }
    )

    mid = await store.get(JOB_ID)
    assert mid is not None
    assert mid.progress is not None
    assert mid.progress.percent == 45
    assert mid.progress.node == "ImageInvert"
    assert (mid.progress.value, mid.progress.max) == (5, 10)

    await tracker.handle_message({"type": "executing", "data": {"prompt_id": JOB_ID, "node": "5"}})
    await tracker.handle_message({"type": "execution_success", "data": {"prompt_id": JOB_ID}})

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "completed"
    assert done.urls == (
        f"http://client.local:8188/upai/api/v1/images/jobs/{JOB_ID}/content?index=0",
        f"http://client.local:8188/upai/api/v1/images/jobs/{JOB_ID}/content?index=1",
    )


async def test_execution_error_fails_job_with_one_line() -> None:
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.handle_message(
        {
            "type": "execution_error",
            "data": {
                "prompt_id": JOB_ID,
                "node_type": "KSampler",
                "exception_message": "CUDA out of memory\nmore detail",
            },
        }
    )

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "failed"
    assert done.error == "KSampler: CUDA out of memory"


async def test_execution_error_is_truncated() -> None:
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.handle_message(
        {
            "type": "execution_error",
            "data": {
                "prompt_id": JOB_ID,
                "node_type": "KSampler",
                "exception_message": "x" * (ERROR_TEXT_MAX_CHARS + 50),
            },
        }
    )

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.error is not None
    assert len(done.error) == ERROR_TEXT_MAX_CHARS


async def test_execution_interrupted_cancels_job() -> None:
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.handle_message({"type": "execution_interrupted", "data": {"prompt_id": JOB_ID}})

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "cancelled"


async def test_child_prompt_ids_returns_every_child() -> None:
    tracker = _tracker(FakeStore())
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    tracker.track(SECOND_JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    assert tracker.child_prompt_ids(JOB_ID) == (JOB_ID, SECOND_JOB_ID)
    assert tracker.child_prompt_ids(SECOND_JOB_ID) == ()


async def test_is_running_follows_execution_start() -> None:
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    assert not tracker.is_running(JOB_ID)

    await tracker.handle_message({"type": "execution_start", "data": {"prompt_id": JOB_ID}})

    assert tracker.is_running(JOB_ID)
    assert not tracker.is_running(SECOND_JOB_ID)


async def test_poll_404_releases_cancelled_prompt() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.get_responses.append(FakeResponse(status=404))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    tracker.mark_cancelling(JOB_ID)

    await tracker.poll_once()

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "cancelled"
    assert tracker.child_prompt_ids(JOB_ID) == ()


async def test_poll_404_after_prompt_completed_keeps_the_result() -> None:
    store = FakeStore((make_job(status="in_progress", files=("a.png",)),))
    session = FakeSession()
    session.get_responses.extend(FakeResponse(status=404) for _ in range(3))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    tracker.mark_submitted(JOB_ID)

    for _ in range(3):
        await tracker.poll_once()

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "completed"
    assert done.files == ("a.png",)
    assert done.urls is not None
    assert tracker.child_prompt_ids(JOB_ID) == ()


async def test_poll_404_waits_for_every_run_before_completing() -> None:
    store = FakeStore((make_job(status="in_progress", files=("a.png",)),))
    session = FakeSession()
    session.get_responses.extend(FakeResponse(status=404) for _ in range(3))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5", count=1)
    tracker.track(SECOND_JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5", count=1)

    await tracker.handle_message({"type": "execution_success", "data": {"prompt_id": JOB_ID}})
    tracker.mark_submitted(SECOND_JOB_ID)

    for _ in range(3):
        await tracker.poll_once()

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status != "completed"
    assert done.urls is None
    assert done.status == "failed"


async def test_poll_404_without_cancel_keeps_job() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.get_responses.append(FakeResponse(status=404))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.poll_once()

    job = await store.get(JOB_ID)
    assert job is not None
    assert job.status == "pending"
    assert tracker.child_prompt_ids(JOB_ID) == (JOB_ID,)


async def test_poll_404_waits_until_the_prompt_is_submitted() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.get_responses.extend(FakeResponse(status=404) for _ in range(6))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    for _ in range(3):
        await tracker.poll_once()

    waiting = await store.get(JOB_ID)
    assert waiting is not None
    assert waiting.status == "pending"
    assert tracker.child_prompt_ids(JOB_ID) == (JOB_ID,)
    assert tracker._tracked[JOB_ID].missing_polls == 0

    tracker.mark_submitted(JOB_ID)
    for _ in range(3):
        await tracker.poll_once()

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "failed"
    assert done.error == "prompt lost by ComfyUI"


async def test_status_message_polls_cancelled_prompt_away() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.get_responses.append(FakeResponse(status=404))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    tracker.mark_cancelling(JOB_ID)

    await tracker.handle_message(
        {"type": "status", "data": {"status": {"exec_info": {"queue_remaining": 0}}}}
    )

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "cancelled"


async def test_status_message_skips_prompts_without_cancel() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.handle_message(
        {"type": "status", "data": {"status": {"exec_info": {"queue_remaining": 0}}}}
    )

    assert session.get_calls == []


async def test_progress_message_updates_running_node() -> None:
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.handle_message(
        {
            "type": "progress",
            "data": {"prompt_id": JOB_ID, "node": "6", "value": 2, "max": 4},
        }
    )

    job = await store.get(JOB_ID)
    assert job is not None
    assert job.progress is not None
    assert job.progress.node == "ImageInvert"
    assert (job.progress.value, job.progress.max) == (2, 4)


async def test_two_children_interleaving_keeps_job_percent() -> None:
    store = FakeStore((make_job(files=("a.png", "b.png")),))
    tracker = _tracker(store)
    prompt = make_sampler_prompt(steps=(100,))
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=prompt, output_node="99", count=1)
    tracker.track(SECOND_JOB_ID, job_id=JOB_ID, prompt=prompt, output_node="99", count=1)

    await tracker.handle_message({"type": "execution_success", "data": {"prompt_id": JOB_ID}})

    percents: list[int] = []
    for value in (95, 99, 97):
        await tracker.handle_message(
            {
                "type": "progress",
                "data": {"prompt_id": SECOND_JOB_ID, "node": "10", "value": value, "max": 100},
            }
        )
        job = await store.get(JOB_ID)
        assert job is not None
        assert job.progress is not None
        percents.append(job.progress.percent)

    assert percents == [95, 97, 97]


async def test_progress_weight_change_does_not_lower_percent() -> None:
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.handle_message({"type": "execution_start", "data": {"prompt_id": JOB_ID}})
    await tracker.handle_message(
        {"type": "execution_cached", "data": {"prompt_id": JOB_ID, "nodes": ["3"]}}
    )
    await tracker.handle_message({"type": "executing", "data": {"prompt_id": JOB_ID, "node": "5"}})
    await tracker.handle_message({"type": "executing", "data": {"prompt_id": JOB_ID, "node": "6"}})

    before = await store.get(JOB_ID)
    assert before is not None
    assert before.progress is not None

    await tracker.handle_message(
        {
            "type": "progress",
            "data": {"prompt_id": JOB_ID, "node": "6", "value": 0, "max": 10},
        }
    )

    after = await store.get(JOB_ID)
    assert after is not None
    assert after.progress is not None
    assert after.progress.percent == before.progress.percent


async def test_nodes_outside_output_path_do_not_raise_percent() -> None:
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    prompt = make_prompt()
    prompt["9"] = {"class_type": "ImageInvert", "inputs": {"image": ["3", 0]}}
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=prompt, output_node="5")

    await tracker.handle_message({"type": "executing", "data": {"prompt_id": JOB_ID, "node": "6"}})
    await tracker.handle_message(
        {
            "type": "progress_state",
            "data": {
                "prompt_id": JOB_ID,
                "nodes": {"6": {"value": 5, "max": 10, "state": "running"}},
            },
        }
    )
    before = await store.get(JOB_ID)
    assert before is not None
    assert before.progress is not None

    await tracker.handle_message(
        {
            "type": "progress_state",
            "data": {
                "prompt_id": JOB_ID,
                "nodes": {
                    "6": {"value": 5, "max": 10, "state": "running"},
                    "9": {"value": 10, "max": 10, "state": "finished"},
                },
            },
        }
    )

    after = await store.get(JOB_ID)
    assert after is not None
    assert after.progress is not None
    assert after.progress.percent == before.progress.percent


async def test_progress_state_keeps_running_node_and_picks_lowest() -> None:
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.handle_message({"type": "executing", "data": {"prompt_id": JOB_ID, "node": "6"}})
    await tracker.handle_message(
        {
            "type": "progress_state",
            "data": {
                "prompt_id": JOB_ID,
                "nodes": {
                    "5": {"value": 0, "max": 10, "state": "running"},
                    "6": {"value": 0, "max": 10, "state": "running"},
                },
            },
        }
    )
    assert tracker._tracked[JOB_ID].running == "6"

    await tracker.handle_message(
        {
            "type": "progress_state",
            "data": {
                "prompt_id": JOB_ID,
                "nodes": {
                    "3": {"value": 0, "max": 10, "state": "running"},
                    "5": {"value": 0, "max": 10, "state": "running"},
                },
            },
        }
    )
    assert tracker._tracked[JOB_ID].running == "3"

    await tracker.handle_message(
        {
            "type": "progress_state",
            "data": {
                "prompt_id": JOB_ID,
                "nodes": {
                    "6": {"value": 0, "max": 10, "state": "finished"},
                    "5": {"value": 0, "max": 10, "state": "running"},
                },
            },
        }
    )
    tracked = tracker._tracked[JOB_ID]
    assert tracked.running == "5"
    assert "6" in tracked.completed


@pytest.mark.parametrize("name", ["minimax-h3-upai.json", "ltx-2-5-upai.json"])
async def test_workflow_sampler_percent_is_step_based_and_monotonic(name: str) -> None:
    class_type, steps = _workflow_samplers(name)
    prompt = make_sampler_prompt(steps=steps, class_type=class_type)
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=prompt, output_node="99")

    await tracker.handle_message({"type": "execution_start", "data": {"prompt_id": JOB_ID}})
    await tracker.handle_message({"type": "executing", "data": {"prompt_id": JOB_ID, "node": "10"}})
    await tracker.handle_message(
        {
            "type": "progress",
            "data": {"prompt_id": JOB_ID, "node": "10", "value": 7, "max": steps[0]},
        }
    )

    job = await store.get(JOB_ID)
    assert job is not None
    assert job.progress is not None
    total_steps = sum(steps)
    assert job.progress.percent == 5 + int(90 * 7 / total_steps)

    percents = [job.progress.percent]
    for value in range(8, steps[0] + 1):
        await tracker.handle_message(
            {
                "type": "progress",
                "data": {"prompt_id": JOB_ID, "node": "10", "value": value, "max": steps[0]},
            }
        )
        job = await store.get(JOB_ID)
        assert job is not None and job.progress is not None
        percents.append(job.progress.percent)

    await tracker.handle_message({"type": "executing", "data": {"prompt_id": JOB_ID, "node": "11"}})
    for value in range(0, steps[1] + 1):
        await tracker.handle_message(
            {
                "type": "progress",
                "data": {"prompt_id": JOB_ID, "node": "11", "value": value, "max": steps[1]},
            }
        )
        job = await store.get(JOB_ID)
        assert job is not None and job.progress is not None
        percents.append(job.progress.percent)

    assert percents == sorted(percents)
    assert all(percent < 100 for percent in percents)


async def test_wan_advanced_samplers_count_usable_step_range() -> None:
    samplers = _wan_advanced_samplers()
    assert len(samplers) == 2

    prompt: dict[str, object] = {"1": {"class_type": "UPAIImageRef", "inputs": {}}}
    previous = "1"
    for index, (steps, start, end) in enumerate(samplers):
        node_id = str(10 + index)
        prompt[node_id] = {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "steps": steps,
                "start_at_step": start,
                "end_at_step": end,
                "latent": [previous, 0],
            },
        }
        previous = node_id
    prompt["99"] = {"class_type": "UPAIOutput", "inputs": {"images": [previous, 0]}}

    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=prompt, output_node="99")

    usable = [sampler.steps for sampler in tracker._tracked[JOB_ID].samplers]
    assert usable == [2, 2]
    assert sum(usable) == 4

    await tracker.handle_message({"type": "execution_start", "data": {"prompt_id": JOB_ID}})

    percents: list[int] = []
    for index in range(len(samplers)):
        node_id = str(10 + index)
        await tracker.handle_message(
            {"type": "executing", "data": {"prompt_id": JOB_ID, "node": node_id}}
        )
        for value in range(usable[index] + 1):
            await tracker.handle_message(
                {
                    "type": "progress",
                    "data": {
                        "prompt_id": JOB_ID,
                        "node": node_id,
                        "value": value,
                        "max": samplers[index][0],
                    },
                }
            )
            job = await store.get(JOB_ID)
            assert job is not None and job.progress is not None
            percents.append(job.progress.percent)
            if index == 0 and value == usable[index]:
                assert job.progress.percent == 50

    assert percents == sorted(percents)
    assert all(percent < 100 for percent in percents)
    store = FakeStore((make_job(files=("a.png", "b.png")),))
    tracker = _tracker(store)
    tracker.track(
        JOB_ID,
        job_id=JOB_ID,
        prompt=make_prompt(),
        output_node="5",
        count=1,
    )
    tracker.track(
        SECOND_JOB_ID,
        job_id=JOB_ID,
        prompt=make_prompt(),
        output_node="5",
        count=1,
    )

    await tracker.handle_message({"type": "execution_success", "data": {"prompt_id": JOB_ID}})
    first = await store.get(JOB_ID)
    assert first is not None
    assert first.status == "in_progress"
    assert tracker.child_prompt_ids(JOB_ID) == (SECOND_JOB_ID,)

    await tracker.handle_message(
        {"type": "execution_success", "data": {"prompt_id": SECOND_JOB_ID}}
    )
    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "completed"
    assert done.urls is not None
    assert len(done.urls) == 2
    assert tracker.child_prompt_ids(JOB_ID) == ()


async def test_runs_url_count_survives_child_finalization() -> None:
    store = FakeStore((make_job(),))
    tracker = _tracker(store)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5", count=1)
    tracker.track(SECOND_JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5", count=1)

    await tracker.handle_message({"type": "execution_success", "data": {"prompt_id": JOB_ID}})
    first = await store.get(JOB_ID)
    assert first is not None
    assert first.status == "in_progress"
    assert tracker.child_prompt_ids(JOB_ID) == (SECOND_JOB_ID,)

    await tracker.handle_message(
        {"type": "execution_success", "data": {"prompt_id": SECOND_JOB_ID}}
    )

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "completed"
    assert done.urls is not None
    assert [url.rsplit("=", 1)[1] for url in done.urls] == ["0", "1"]


async def test_untrack_releases_run_count_after_last_child() -> None:
    tracker = _tracker(FakeStore())
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    tracker.track(SECOND_JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    assert tracker._job_counts[JOB_ID] == 2

    tracker.untrack(JOB_ID)
    assert tracker._job_counts[JOB_ID] == 2

    tracker.untrack(SECOND_JOB_ID)
    assert JOB_ID not in tracker._job_counts


async def test_second_child_error_fails_job_and_cancels_siblings() -> None:
    store = FakeStore((make_job(),))
    calls: list[tuple[str, bool]] = []

    async def cancel(prompt_id: str, is_running: bool) -> None:
        calls.append((prompt_id, is_running))

    tracker = _tracker(store, cancel_prompt=cancel)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    tracker.track(SECOND_JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    await tracker.handle_message({"type": "execution_start", "data": {"prompt_id": SECOND_JOB_ID}})

    await tracker.handle_message(
        {
            "type": "execution_error",
            "data": {
                "prompt_id": SECOND_JOB_ID,
                "node_type": "KSampler",
                "exception_message": "boom",
            },
        }
    )

    failed = await store.get(JOB_ID)
    assert failed is not None
    assert failed.status == "failed"
    assert tracker.child_prompt_ids(JOB_ID) == (JOB_ID,)
    assert tracker._tracked[JOB_ID].is_cancelling
    assert calls == [(JOB_ID, False)]

    await tracker.handle_message({"type": "execution_interrupted", "data": {"prompt_id": JOB_ID}})

    assert tracker.child_prompt_ids(JOB_ID) == ()
    still_failed = await store.get(JOB_ID)
    assert still_failed is not None
    assert still_failed.status == "failed"


async def test_last_child_gone_releases_all_tracking() -> None:
    store = FakeStore((make_job(),))
    calls: list[tuple[str, bool]] = []

    async def cancel(prompt_id: str, is_running: bool) -> None:
        calls.append((prompt_id, is_running))

    tracker = _tracker(store, cancel_prompt=cancel)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    tracker.track(SECOND_JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.handle_message({"type": "execution_interrupted", "data": {"prompt_id": JOB_ID}})
    assert tracker.child_prompt_ids(JOB_ID) == (SECOND_JOB_ID,)
    assert calls == [(SECOND_JOB_ID, False)]

    await tracker.handle_message(
        {"type": "execution_interrupted", "data": {"prompt_id": SECOND_JOB_ID}}
    )

    assert tracker.child_prompt_ids(JOB_ID) == ()
    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "cancelled"


async def test_poll_fails_prompt_lost_by_comfyui_after_three_404s() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.get_responses.extend(FakeResponse(status=404) for _ in range(3))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    tracker.mark_submitted(JOB_ID)

    await tracker.poll_once()
    await tracker.poll_once()
    waiting = await store.get(JOB_ID)
    assert waiting is not None
    assert waiting.status == "pending"
    assert tracker.child_prompt_ids(JOB_ID) == (JOB_ID,)

    await tracker.poll_once()
    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "failed"
    assert done.error == "prompt lost by ComfyUI"
    assert tracker.child_prompt_ids(JOB_ID) == ()


async def test_poll_missing_count_resets_on_a_successful_response() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.get_responses.extend(
        [
            FakeResponse(status=404),
            FakeResponse(status=404),
            FakeResponse(status=200, body={"status": "in_progress"}),
            FakeResponse(status=404),
            FakeResponse(status=404),
        ]
    )
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")
    tracker.mark_submitted(JOB_ID)

    for _ in range(5):
        await tracker.poll_once()

    waiting = await store.get(JOB_ID)
    assert waiting is not None
    assert waiting.status == "in_progress"
    assert tracker.child_prompt_ids(JOB_ID) == (JOB_ID,)

    session.get_responses.append(FakeResponse(status=404))
    await tracker.poll_once()

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "failed"
    assert done.error == "prompt lost by ComfyUI"


async def test_poll_completes_job_when_websocket_is_down() -> None:
    store = FakeStore((make_job(files=("a.png",)),))
    session = FakeSession()
    session.get_responses.append(FakeResponse(body={"status": "completed"}))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.poll_once()

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "completed"
    assert session.get_calls == [(f"http://127.0.0.1:8188/api/jobs/{JOB_ID}", True)]


async def test_poll_fails_job() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.get_responses.append(FakeResponse(body={"status": "failed", "execution_error": "boom"}))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.poll_once()

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "failed"
    assert done.error == "boom"


async def test_poll_fails_job_from_a_dict_execution_error() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.get_responses.append(
        FakeResponse(
            body={
                "status": "failed",
                "execution_error": {
                    "node_type": "KSampler",
                    "exception_message": "CUDA out of memory\nmore detail",
                },
            }
        )
    )
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.poll_once()

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "failed"
    assert done.error == "CUDA out of memory"


async def test_websocket_loop_consumes_messages_and_stops() -> None:
    store = FakeStore((make_job(),))
    session = FakeSession()
    session.ws_messages.append(
        json.dumps({"type": "execution_start", "data": {"prompt_id": JOB_ID}})
    )
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.start()
    tracker.set_server_url("http://127.0.0.1:8188")
    for _ in range(100):
        job = await store.get(JOB_ID)
        if job is not None and job.status == "in_progress":
            break
        await asyncio.sleep(0.01)
    await tracker.stop()

    job = await store.get(JOB_ID)
    assert job is not None
    assert job.status == "in_progress"
    assert session.ws_calls == [("ws://127.0.0.1:8188/ws?clientId=upai-instance", 30.0)]


async def test_start_without_server_url_opens_no_socket() -> None:
    session = FakeSession()
    tracker = _tracker(FakeStore(), session=session)

    await tracker.start()
    await asyncio.sleep(0.01)

    assert session.ws_calls == []

    tracker.set_server_url("http://127.0.0.1:8188")
    for _ in range(100):
        if session.ws_calls:
            break
        await asyncio.sleep(0.01)
    await tracker.stop()

    assert session.ws_calls == [("ws://127.0.0.1:8188/ws?clientId=upai-instance", 30.0)]


async def test_set_server_url_reconnects_to_the_new_port() -> None:
    session = FakeSession()
    tracker = _tracker(FakeStore(), session=session)

    await tracker.start()
    tracker.set_server_url("http://127.0.0.1:8189/")
    for _ in range(100):
        if any(url.startswith("ws://127.0.0.1:8189/") for url, _ in session.ws_calls):
            break
        await asyncio.sleep(0.01)
    await tracker.stop()

    assert ("ws://127.0.0.1:8189/ws?clientId=upai-instance", 30.0) in session.ws_calls


def test_websocket_url_uses_instance_client_id() -> None:
    assert (
        websocket_url("http://127.0.0.1:8188", "abc") == "ws://127.0.0.1:8188/ws?clientId=upai-abc"
    )
    assert (
        websocket_url("https://127.0.0.1:8188", "abc")
        == "wss://127.0.0.1:8188/ws?clientId=upai-abc"
    )


async def test_websocket_connect_reconciles_completed_prompt() -> None:
    store = FakeStore((make_job(files=("a.png",)),))
    session = FakeSession()
    session.get_responses.append(FakeResponse(body={"status": "completed"}))
    tracker = _tracker(store, session=session)
    tracker.track(JOB_ID, job_id=JOB_ID, prompt=make_prompt(), output_node="5")

    await tracker.start()
    tracker.set_server_url("http://127.0.0.1:8188")
    for _ in range(100):
        job = await store.get(JOB_ID)
        if job is not None and job.status == "completed":
            break
        await asyncio.sleep(0.01)
    await tracker.stop()

    done = await store.get(JOB_ID)
    assert done is not None
    assert done.status == "completed"
