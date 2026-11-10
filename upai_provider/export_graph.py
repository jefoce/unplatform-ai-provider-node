"""Walk an API prompt into models, bindings and capabilities."""

import re
from collections.abc import Iterator, Mapping
from pathlib import PurePosixPath
from typing import cast

from .constants import NODE_UPAI_MODEL, NODE_UPAI_OUTPUT
from .export_capabilities import derive_capabilities
from .export_types import ExportBuild, NodeMap
from .protocol import Export, ExportModel, ModelBinding
from .protocol.ids import MODEL_ID_PATTERN
from .protocol.shapes import ModelKind


def slugify(text: str) -> str:
    """Return a protocol-safe id derived from text."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:64] or "workflow"


def _node(node_map: NodeMap, node_id: str | None) -> Mapping[str, object] | None:
    if node_id is None:
        return None

    return node_map.get(node_id)


def _inputs(node: object) -> Mapping[str, object]:
    if not isinstance(node, dict):
        return {}

    value = node.get("inputs")
    return value if isinstance(value, dict) else {}


def _node_class(node: object) -> str | None:
    if not isinstance(node, dict):
        return None

    value = node.get("class_type")
    return value if isinstance(value, str) else None


def _text(inputs: Mapping[str, object], name: str) -> str:
    value = inputs.get(name)
    return value if isinstance(value, str) else ""


def _int(inputs: Mapping[str, object], name: str) -> int | None:
    value = inputs.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        return None

    return value


def _float(inputs: Mapping[str, object], name: str) -> float:
    value = inputs.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0

    return float(value)


def _bool(inputs: Mapping[str, object], name: str) -> bool:
    value = inputs.get(name)
    return value if isinstance(value, bool) else False


def _pairs(value: object, node_ids: set[str]) -> Iterator[tuple[str, int]]:
    if not isinstance(value, (list, tuple)):
        return

    if (
        len(value) == 2
        and isinstance(value[0], str)
        and value[0] in node_ids
        and isinstance(value[1], int)
        and not isinstance(value[1], bool)
    ):
        yield value[0], value[1]
        return

    for item in value:
        yield from _pairs(item, node_ids)


def link_nodes(value: object, node_ids: set[str]) -> tuple[str, ...]:
    """Return node ids referenced by an input value."""
    return tuple(node for node, _ in _pairs(value, node_ids))


def _linked_output_used(node_map: NodeMap, node_ids: set[str], source: str, slot: int) -> bool:
    for node_id in node_ids:
        for value in _inputs(node_map.get(node_id)).values():
            if (source, slot) in _pairs(value, set(node_map)):
                return True

    return False


def ancestor_ids(node_map: Mapping[str, object], start: str | None) -> set[str]:
    """Return the node ids reachable from start through input links."""
    if start is None or start not in node_map:
        return set()

    seen: set[str] = set()
    pending = [start]
    node_ids = set(node_map)
    while pending:
        current = pending.pop()
        if current in seen:
            continue

        seen.add(current)
        for value in _inputs(node_map.get(current)).values():
            pending.extend(source for source in link_nodes(value, node_ids) if source not in seen)

    return seen


def _enabled(inputs: Mapping[str, object]) -> bool:
    value = inputs.get("enabled")
    return value if isinstance(value, bool) else True


def _workflow_meta(source: str) -> tuple[str, str]:
    stem = PurePosixPath(source).stem
    return slugify(stem), stem


def _kind(value: str) -> ModelKind | None:
    return cast(ModelKind, value) if value in ("video", "image") else None


def derive_export(
    *,
    source: str,
    prompt: Mapping[str, object],
    source_mtime: float,
    exported_at: str,
    comfy_version: str,
) -> ExportBuild:
    """Derive one export from the API prompt produced by graphToPrompt."""
    from .export_rules import model_graph

    node_map: dict[str, Mapping[str, object]] = {
        str(node_id): cast(Mapping[str, object], node)
        for node_id, node in prompt.items()
        if isinstance(node, dict)
    }
    workflow_id, workflow_name = _workflow_meta(source)
    node_ids = set(node_map)
    model_nodes = sorted(
        node_id for node_id in node_ids if _node_class(node_map.get(node_id)) == NODE_UPAI_MODEL
    )
    output_nodes = sorted(
        node_id for node_id in node_ids if _node_class(node_map.get(node_id)) == NODE_UPAI_OUTPUT
    )

    workflow_errors: list[str] = []
    if not model_nodes:
        workflow_errors.append("no UPAI Model node found")

    outputs_by_model: dict[str, list[str]] = {}
    for output_node in output_nodes:
        sources = link_nodes(_inputs(node_map.get(output_node)).get("model"), node_ids)
        if len(sources) != 1 or _node_class(node_map.get(sources[0])) != NODE_UPAI_MODEL:
            workflow_errors.append(f"output {output_node} is not connected to a UPAI Model node")
            continue

        outputs_by_model.setdefault(sources[0], []).append(output_node)

    models: list[ExportModel] = []
    invalid_reasons: dict[str, str] = {}
    seen_models: set[str] = set()
    warnings: list[str] = []

    for model_node in model_nodes:
        inputs = _inputs(node_map.get(model_node))
        raw_id = _text(inputs, "id")
        name = _text(inputs, "name")
        description = _text(inputs, "description")
        raw_kind = _text(inputs, "kind")
        kind = _kind(raw_kind) or "video"
        price = _float(inputs, "price_per_run_usd")

        if raw_id:
            candidate = raw_id
        elif name.strip():
            candidate = slugify(name)
        else:
            candidate = workflow_id
        model_id = candidate if MODEL_ID_PATTERN.match(candidate) else slugify(candidate)
        issues: list[str] = []
        if model_id != candidate:
            issues.append(f"model id {candidate!r} is not a valid slug")

        if _kind(raw_kind) is None:
            issues.append(f"model {model_id} has an unknown kind")

        outputs = sorted(outputs_by_model.get(model_node, ()))
        if not outputs:
            issues.append("model has no UPAI Output node")
        elif len(outputs) > 1:
            issues.append("model connects to more than one UPAI Output node")

        output_node = outputs[0] if outputs else ""
        graph, graph_issues = model_graph(
            node_map,
            model_node=model_node,
            kind=kind,
            output_node=output_node,
        )
        issues.extend(graph_issues)
        result = derive_capabilities(graph)
        if result.invalid_reason:
            issues.append(result.invalid_reason)
        warnings.extend(result.warnings)

        bindings = ModelBinding(
            workflow=model_node,
            prompt=graph.prompt_node,
            settings=graph.settings_node,
            output=output_node,
            start=graph.start_node,
            end=graph.end_node,
            refs=graph.refs,
        )
        model = ExportModel(
            model_id=model_id,
            name=name or model_id,
            description=description,
            kind=kind,
            enabled=_enabled(inputs),
            output_node=output_node,
            bindings=bindings,
            capabilities=result.capabilities,
            price_per_run_usd=price,
        )

        if model_id in seen_models:
            invalid_reasons[model_id] = _join(
                invalid_reasons.get(model_id, ""), "model id is not unique"
            )
            continue

        seen_models.add(model_id)
        if issues:
            invalid_reasons[model_id] = "; ".join(issues)
        models.append(model)

    export = Export(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        source=source,
        source_mtime=source_mtime,
        exported_at=exported_at,
        comfy_version=comfy_version,
        models=tuple(models),
        prompt=prompt,
    )
    return ExportBuild(export, invalid_reasons, tuple(warnings), tuple(workflow_errors))


def _join(first: str, second: str) -> str:
    return f"{first}; {second}" if first else second
