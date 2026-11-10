"""Apply UPAI Limits values and read node inputs."""

import math
from collections.abc import Mapping

from .export_types import ModelGraph
from .protocol import (
    CountCapability,
    DurationCapability,
    FramesCapability,
    ReferenceCapability,
)


def _inputs(node: Mapping[str, object] | None) -> Mapping[str, object]:
    if node is None:
        return {}

    value = node.get("inputs")
    return value if isinstance(value, dict) else {}


def _int(inputs: Mapping[str, object], name: str, default: int | None = None) -> int | None:
    value = inputs.get(name)
    if isinstance(value, bool) or value is None:
        return default

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    return default


def _number(inputs: Mapping[str, object], name: str, default: float | None = None) -> float | None:
    value = inputs.get(name)
    if isinstance(value, bool) or value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    return default


def _bool(inputs: Mapping[str, object], name: str, default: bool = False) -> bool:
    value = inputs.get(name)
    return value if isinstance(value, bool) else default


def _text(inputs: Mapping[str, object], name: str, default: str = "") -> str:
    value = inputs.get(name)
    return value if isinstance(value, str) else default


def _required(graph: ModelGraph, node_id: str | None) -> bool:
    if node_id is None:
        return False

    return _bool(_inputs(graph.nodes.get(node_id)), "required")


def _frames(
    graph: ModelGraph, limits: Mapping[str, object], invalid: list[str]
) -> FramesCapability:
    start = graph.start_node is not None
    end = graph.end_node is not None
    start_required = _required(graph, graph.start_node)
    end_required = _required(graph, graph.end_node)

    for name, node in (("start_frame", start), ("end_frame", end)):
        mode = limits.get(name)
        if not isinstance(mode, str):
            continue

        mode = mode.strip().lower()
        if mode == "off":
            if name == "start_frame":
                start, start_required = False, False
            else:
                end, end_required = False, False
        elif mode == "optional":
            if name == "start_frame":
                start_required = False
            else:
                end_required = False
        elif mode == "required":
            if not node:
                invalid.append(f"{name} is required but no node is connected")
            elif name == "start_frame":
                start_required = True
            else:
                end_required = True

    return FramesCapability(start, end, start_required, end_required)


def _reference(
    kind: str,
    base: ReferenceCapability,
    limits: Mapping[str, object],
    invalid: list[str],
    warnings: list[str],
) -> ReferenceCapability:
    maximum = base.max
    required = base.required

    raw_max = _int(limits, f"{kind}_max")
    if raw_max is not None and raw_max >= 0:
        if raw_max > base.max:
            warnings.append(f"{kind}_max is above the {base.max} reference nodes, using {base.max}")
        else:
            maximum = raw_max

    raw_required = _int(limits, f"{kind}_required")
    if raw_required is not None and raw_required >= 0:
        required = raw_required

    if required > maximum:
        invalid.append(f"{kind}_required cannot be above {kind}_max")
        required = maximum

    return ReferenceCapability(maximum, required)


def _duration(
    base: DurationCapability,
    limits: Mapping[str, object],
    invalid: list[str],
    warnings: list[str],
) -> DurationCapability:
    minimum = base.min
    maximum = base.max

    raw_min = _number(limits, "duration_min")
    if raw_min is not None and raw_min > 0:
        if raw_min > base.min:
            minimum = raw_min
        elif raw_min < base.min:
            warnings.append("duration_min cannot be widened")

    raw_max = _number(limits, "duration_max")
    if raw_max is not None and raw_max > 0:
        if raw_max < base.max:
            maximum = raw_max
        elif raw_max > base.max:
            warnings.append("duration_max cannot be widened")

    if minimum > maximum:
        invalid.append("duration_min cannot be above duration_max")
        minimum = maximum

    if base.step > 0:
        steps = round((base.default - minimum) / base.step)
        default = minimum + max(0, steps) * base.step
    else:
        default = base.default

    default = min(max(default, minimum), maximum)
    if base.step > 0:
        steps = math.floor((default - minimum) / base.step + 1e-9)
        default = minimum + steps * base.step

    return DurationCapability(minimum, maximum, default, base.step)


def _count(
    base: CountCapability,
    limits: Mapping[str, object],
    warnings: list[str],
) -> CountCapability:
    raw_max = _int(limits, "count_max")
    if raw_max is None or raw_max <= 0:
        return base

    if raw_max < base.max:
        return CountCapability(raw_max)

    if raw_max > base.max:
        warnings.append("count_max cannot be widened")

    return base
