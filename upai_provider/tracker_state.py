"""Tracker state shared by message, event and poll mixins."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from .protocol import Job, JobStatus

_PROGRESS_WEIGHT = 10
_DEFAULT_WEIGHT = 1


class _Store(Protocol):
    async def get(self, job_id: str) -> Job | None: ...

    async def update(self, job_id: str, **changes: object) -> Job | None: ...

    async def finalize(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        urls: tuple[str, ...] | None = None,
    ) -> Job | None: ...


@dataclass(frozen=True)
class _Sampler:
    node_id: str
    steps: int


@dataclass
class _Tracked:
    prompt_id: str
    job_id: str
    output_node: str
    count: int
    node_names: Mapping[str, str]
    nodes: frozenset[str]
    samplers: tuple[_Sampler, ...] = ()
    before_nodes: frozenset[str] = frozenset()
    after_nodes: frozenset[str] = frozenset()
    cached: set[str] = field(default_factory=set)
    completed: set[str] = field(default_factory=set)
    running: str | None = None
    progress: dict[str, tuple[float, float]] = field(default_factory=dict)
    started: bool = False
    is_cancelling: bool = False
    is_done: bool = False
    is_submitted: bool = False
    missing_polls: int = 0


def _link(value: object, prompt: Mapping[str, object]) -> str | None:
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
        and value[0] in prompt
    ):
        return value[0]

    return None


def _links(value: object, prompt: Mapping[str, object]) -> list[str]:
    direct = _link(value, prompt)
    if direct is not None:
        return [direct]

    found: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_links(item, prompt))
    elif isinstance(value, Mapping):
        for item in value.values():
            found.extend(_links(item, prompt))

    return found


def _parents(prompt: Mapping[str, object], node_id: str) -> set[str]:
    node = prompt.get(node_id)
    if not isinstance(node, Mapping):
        return set()

    inputs = node.get("inputs")
    if not isinstance(inputs, Mapping):
        return set()

    found: set[str] = set()
    for value in inputs.values():
        found.update(_links(value, prompt))

    return found


def _ancestors(prompt: Mapping[str, object], output_node: str) -> frozenset[str]:
    """Return output_node and every node linked into it through any input."""
    found: set[str] = set()
    pending = [output_node]
    while pending:
        node_id = pending.pop()
        if node_id in found:
            continue
        node = prompt.get(node_id)
        if not isinstance(node, Mapping):
            continue

        found.add(node_id)
        inputs = node.get("inputs")
        if not isinstance(inputs, Mapping):
            continue

        for value in inputs.values():
            pending.extend(_links(value, prompt))

    if found:
        return frozenset(found)

    return frozenset(str(node_id) for node_id in prompt)


def _node_names(prompt: Mapping[str, object]) -> dict[str, str]:
    names: dict[str, str] = {}
    for node_id, node in prompt.items():
        if not isinstance(node, Mapping):
            continue
        class_type = node.get("class_type")
        names[str(node_id)] = class_type if isinstance(class_type, str) else str(node_id)

    return names


def _id_key(node_id: str) -> tuple[int, int, str]:
    """Sort numeric ids numerically, then the rest as text."""
    if node_id.isdigit():
        return (0, int(node_id), node_id)

    return (1, 0, node_id)


def _topo_order(prompt: Mapping[str, object], nodes: frozenset[str]) -> tuple[str, ...]:
    """Order reachable nodes from inputs to the output."""
    parents = {
        node: {parent for parent in _parents(prompt, node) if parent in nodes} for node in nodes
    }
    children: dict[str, set[str]] = {node: set() for node in nodes}
    for node, node_parents in parents.items():
        for parent in node_parents:
            children[parent].add(node)

    ready = sorted(
        (node for node, node_parents in parents.items() if not node_parents), key=_id_key
    )
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for child in sorted(children[node], key=_id_key):
            parents[child].discard(node)
            if not parents[child]:
                ready.append(child)
        ready.sort(key=_id_key)

    seen = set(order)
    order.extend(sorted((node for node in nodes if node not in seen), key=_id_key))
    return tuple(order)


def _class_type(prompt: Mapping[str, object], node_id: str) -> str | None:
    node = prompt.get(node_id)
    if not isinstance(node, Mapping):
        return None

    class_type = node.get("class_type")
    return class_type if isinstance(class_type, str) else None


def _is_sampler(prompt: Mapping[str, object], node_id: str) -> bool:
    class_type = _class_type(prompt, node_id)
    return class_type is not None and "Sampler" in class_type


def _numeric(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)

    return None


def _input_int(prompt: Mapping[str, object], node_id: str, name: str) -> int | None:
    """Read one numeric input, following a link to the primitive value."""
    node = prompt.get(node_id)
    if not isinstance(node, Mapping):
        return None

    inputs = node.get("inputs")
    if not isinstance(inputs, Mapping):
        return None

    direct = _numeric(inputs.get(name))
    if direct is not None:
        return direct

    linked = _link(inputs.get(name), prompt)
    if linked is None:
        return None

    source = prompt.get(linked)
    if not isinstance(source, Mapping):
        return None

    source_inputs = source.get("inputs")
    if not isinstance(source_inputs, Mapping):
        return None

    value = _numeric(source_inputs.get("value"))
    if value is not None:
        return value

    for item in source_inputs.values():
        value = _numeric(item)
        if value is not None:
            return value

    return None


def _sampler_steps(prompt: Mapping[str, object], node_id: str) -> int:
    """Return the sampler steps that actually run, honoring KSamplerAdvanced range."""
    steps = _input_int(prompt, node_id, "steps")
    if steps is None:
        return 0

    steps = max(0, steps)
    if _class_type(prompt, node_id) != "KSamplerAdvanced":
        return steps

    end_at_step = _input_int(prompt, node_id, "end_at_step")
    start_at_step = _input_int(prompt, node_id, "start_at_step")
    end = steps if end_at_step is None or end_at_step == 10000 else min(end_at_step, steps)
    start = min(max(0, start_at_step or 0), steps)

    return max(0, end - start)


def _sampler_layout(
    prompt: Mapping[str, object],
    nodes: frozenset[str],
) -> tuple[tuple[_Sampler, ...], frozenset[str], frozenset[str]]:
    order = _topo_order(prompt, nodes)
    sampler_ids = [node for node in order if _is_sampler(prompt, node)]
    if not sampler_ids:
        return (), frozenset(), frozenset()

    positions = {node: index for index, node in enumerate(order)}
    first = positions[sampler_ids[0]]
    last = positions[sampler_ids[-1]]
    samplers = tuple(_Sampler(node, _sampler_steps(prompt, node)) for node in sampler_ids)
    before = frozenset(node for node in order[:first] if node not in sampler_ids)
    after = frozenset(node for node in order[last + 1 :] if node not in sampler_ids)

    return samplers, before, after


class _TrackerBase:
    """Shared state and helpers every tracker mixin uses."""

    _store: _Store
    _server_url: str
    _clock: Callable[[], float]
    _tracked: dict[str, _Tracked]
    _job_counts: dict[str, int]
    _job_prompts: dict[str, int]
    _job_done: dict[str, int]
    _session: object | None
    _poll_interval: float

    async def _update_progress(self, tracked: _Tracked, *, status: str = "in_progress") -> None: ...

    async def _finish_prompt(self, tracked: _Tracked) -> None: ...

    async def _fail_prompt(self, tracked: _Tracked, message: str) -> None: ...

    async def _cancel_prompt(self, tracked: _Tracked) -> None: ...

    async def cancel_prompt(self, prompt_id: str, is_running: bool) -> None: ...

    async def poll_once(self, *, only_cancelling: bool = False) -> None: ...

    def _job_entries(self, job_id: str) -> list[_Tracked]: ...

    def untrack(self, prompt_id: str) -> None: ...

    def _weight(self, tracked: _Tracked, node_id: str) -> int: ...

    def _percent(self, tracked: _Tracked) -> int: ...

    def _job_percent(self, job_id: str) -> int: ...

    def _current_progress(self, tracked: _Tracked) -> tuple[str | None, int | None, int | None]: ...

    def _job_current_progress(self, job_id: str) -> tuple[str | None, int | None, int | None]: ...


class TrackerState(_TrackerBase):
    """Track prompts and expose their state to the other mixins."""

    def track(
        self,
        prompt_id: str,
        *,
        job_id: str,
        prompt: Mapping[str, object],
        output_node: str,
        count: int = 1,
    ) -> None:
        """Start tracking one prompt id. Child ids map to the parent job id."""
        nodes = _ancestors(prompt, output_node)
        samplers, before_nodes, after_nodes = _sampler_layout(prompt, nodes)
        self._tracked[prompt_id] = _Tracked(
            prompt_id=prompt_id,
            job_id=job_id,
            output_node=output_node,
            count=count,
            node_names=_node_names(prompt),
            nodes=nodes,
            samplers=samplers,
            before_nodes=before_nodes,
            after_nodes=after_nodes,
        )
        self._job_counts[job_id] = self._job_counts.get(job_id, 0) + count
        self._job_prompts[job_id] = self._job_prompts.get(job_id, 0) + 1

    def untrack(self, prompt_id: str) -> None:
        """Stop tracking one prompt id and release its job state when last."""
        tracked = self._tracked.pop(prompt_id, None)
        if tracked is None or self._job_entries(tracked.job_id):
            return

        self._job_counts.pop(tracked.job_id, None)
        self._job_prompts.pop(tracked.job_id, None)
        self._job_done.pop(tracked.job_id, None)

    def child_prompt_ids(self, job_id: str) -> tuple[str, ...]:
        """Return every tracked prompt id for one job, in submit order."""
        return tuple(item.prompt_id for item in self._job_entries(job_id))

    def is_running(self, prompt_id: str) -> bool:
        """Return True once ComfyUI has started executing this prompt."""
        tracked = self._tracked.get(prompt_id)
        return tracked is not None and tracked.started

    def mark_cancelling(self, prompt_id: str) -> None:
        """Remember that a cancel was requested for this prompt."""
        tracked = self._tracked.get(prompt_id)
        if tracked is not None:
            tracked.is_cancelling = True

    def mark_submitted(self, prompt_id: str) -> None:
        """Remember that ComfyUI accepted this prompt."""
        tracked = self._tracked.get(prompt_id)
        if tracked is not None:
            tracked.is_submitted = True

    def _job_entries(self, job_id: str) -> list[_Tracked]:
        return [item for item in self._tracked.values() if item.job_id == job_id]

    def _weight(self, tracked: _Tracked, node_id: str) -> int:
        value, maximum = tracked.progress.get(node_id, (0.0, 0.0))
        return _PROGRESS_WEIGHT if maximum > 0 else _DEFAULT_WEIGHT

    def _fixed_percent(self, tracked: _Tracked) -> int:
        total = sum(
            self._weight(tracked, node_id)
            for node_id in tracked.nodes
            if node_id not in tracked.cached
        )
        if total <= 0:
            return 100

        done = sum(
            self._weight(tracked, node_id)
            for node_id in tracked.completed
            if node_id in tracked.nodes and node_id not in tracked.cached
        )
        running = 0.0
        if (
            tracked.running is not None
            and tracked.running in tracked.nodes
            and tracked.running not in tracked.completed
            and tracked.running not in tracked.cached
        ):
            value, maximum = tracked.progress.get(tracked.running, (0.0, 0.0))
            fraction = 0.0 if maximum <= 0 else min(1.0, max(0.0, value / maximum))
            running = self._weight(tracked, tracked.running) * fraction

        return min(100, max(0, int((done + running) / total * 100)))

    def _done_weight_percent(
        self,
        tracked: _Tracked,
        nodes: frozenset[str],
        span: int,
    ) -> int:
        total = sum(
            self._weight(tracked, node_id) for node_id in nodes if node_id not in tracked.cached
        )
        if total <= 0:
            return 0

        done = sum(
            self._weight(tracked, node_id)
            for node_id in nodes
            if node_id in tracked.completed and node_id not in tracked.cached
        )
        return int(span * done / total)

    def _percent(self, tracked: _Tracked) -> int:
        active = [sampler for sampler in tracked.samplers if sampler.node_id not in tracked.cached]
        total_steps = sum(sampler.steps for sampler in active)
        if not active or total_steps <= 0:
            return self._fixed_percent(tracked)

        done_steps = 0
        is_started = False
        for sampler in active:
            node_id = sampler.node_id
            if node_id in tracked.completed:
                done_steps += sampler.steps
                is_started = True
                continue

            if node_id == tracked.running or node_id in tracked.progress:
                value = tracked.progress.get(node_id, (0.0, 0.0))[0]
                done_steps += min(sampler.steps, max(0, int(value)))
                is_started = True

        if not is_started:
            return self._done_weight_percent(tracked, tracked.before_nodes, 5)

        if done_steps >= total_steps:
            return 95 + self._done_weight_percent(tracked, tracked.after_nodes, 4)

        return 5 + int(90 * done_steps / total_steps)

    def _job_percent(self, job_id: str) -> int:
        prompts = self._job_prompts.get(job_id, 0)
        if prompts <= 0:
            return 0

        total = self._job_done.get(job_id, 0) * 100
        for item in self._job_entries(job_id):
            if item.is_done or not item.started:
                continue

            total += self._percent(item)

        return min(100, max(0, int(total / prompts)))

    def _current_progress(self, tracked: _Tracked) -> tuple[str | None, int | None, int | None]:
        node_id = tracked.running
        if node_id is None:
            return None, None, None

        value, maximum = tracked.progress.get(node_id, (0.0, 0.0))
        return (
            tracked.node_names.get(node_id, node_id),
            int(round(value)),
            int(round(maximum)),
        )

    def _job_current_progress(
        self,
        job_id: str,
    ) -> tuple[str | None, int | None, int | None]:
        for item in self._job_entries(job_id):
            if item.running is None or item.is_done:
                continue

            node, value, maximum = self._current_progress(item)
            if node is not None:
                return node, value, maximum

        return None, None, None
