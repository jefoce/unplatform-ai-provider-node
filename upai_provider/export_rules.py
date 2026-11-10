"""Validate one model graph and collect its UPAI nodes."""

from .constants import (
    NODE_UPAI_AUDIO_REF,
    NODE_UPAI_END_FRAME,
    NODE_UPAI_IMAGE_REF,
    NODE_UPAI_LIMITS,
    NODE_UPAI_PROMPT,
    NODE_UPAI_SETTINGS,
    NODE_UPAI_START_FRAME,
    NODE_UPAI_VIDEO_REF,
)
from .export_graph import (
    _bool,
    _inputs,
    _int,
    _linked_output_used,
    _node,
    _node_class,
    ancestor_ids,
    link_nodes,
)
from .export_types import ModelGraph, NodeMap
from .protocol import RefBinding
from .protocol.shapes import ModelKind

_REF_CLASSES = {
    NODE_UPAI_IMAGE_REF: "image",
    NODE_UPAI_VIDEO_REF: "video",
    NODE_UPAI_AUDIO_REF: "audio",
}


def model_graph(
    node_map: NodeMap,
    *,
    model_node: str,
    kind: ModelKind,
    output_node: str,
) -> tuple[ModelGraph, list[str]]:
    """Build the graph for one model and list its issues."""
    invalid: list[str] = []
    output = _node(node_map, output_node)
    model = _node(node_map, model_node)
    members = ancestor_ids(node_map, output_node if output is not None else model_node)

    prompts = sorted(
        node_id for node_id in members if _node_class(node_map.get(node_id)) == NODE_UPAI_PROMPT
    )
    settings = sorted(
        node_id for node_id in members if _node_class(node_map.get(node_id)) == NODE_UPAI_SETTINGS
    )
    starts = sorted(
        node_id
        for node_id in members
        if _node_class(node_map.get(node_id)) == NODE_UPAI_START_FRAME
    )
    ends = sorted(
        node_id for node_id in members if _node_class(node_map.get(node_id)) == NODE_UPAI_END_FRAME
    )

    for label, found in (
        ("UPAI Prompt", prompts),
        ("UPAI Settings", settings),
        ("UPAI Start Frame", starts),
        ("UPAI End Frame", ends),
    ):
        if len(found) > 1:
            invalid.append(f"model has more than one {label} node")

    refs: dict[str, list[RefBinding]] = {"image": [], "video": [], "audio": []}
    for node_id in sorted(members):
        kind_name = _REF_CLASSES.get(_node_class(node_map.get(node_id)) or "")
        if kind_name is None:
            continue

        inputs = _inputs(node_map.get(node_id))
        index = _int(inputs, "index")
        if index is None or not 1 <= index <= 16:
            invalid.append(f"{kind_name} reference {node_id} needs an index from 1 to 16")
            index = 0

        refs[kind_name].append(RefBinding(node_id, index, _bool(inputs, "required")))

    for kind_name, bindings in refs.items():
        indexes = sorted(binding.index for binding in bindings)
        expected = list(range(1, len(indexes) + 1))
        if indexes != expected:
            invalid.append(f"{kind_name} reference indexes must be unique and contiguous from 1")

    limits_sources = link_nodes(_inputs(model).get("limits"), set(node_map))
    limits_node: str | None = None
    if len(limits_sources) > 1:
        invalid.append("model has more than one UPAI Limits node")
    elif limits_sources:
        limits_node = limits_sources[0]
        if _node_class(node_map.get(limits_node)) != NODE_UPAI_LIMITS:
            invalid.append("model limits input is not a UPAI Limits node")
            limits_node = None

    prompt_node = prompts[0] if prompts else None
    negative_used = False
    if prompt_node is not None:
        negative_used = _linked_output_used(node_map, members, prompt_node, 1)

    start_node = starts[0] if starts else None
    end_node = ends[0] if ends else None
    refs_tuple = {name: tuple(items) for name, items in refs.items()}

    graph = ModelGraph(
        model_node=model_node,
        kind=kind,
        output_node=output_node,
        prompt_node=prompt_node,
        settings_node=settings[0] if settings else None,
        start_node=start_node,
        end_node=end_node,
        limits_node=limits_node,
        refs=refs_tuple,
        prompt_negative_used=negative_used,
        nodes=node_map,
    )

    output_inputs = _inputs(output)
    if kind == "image":
        if refs["video"] or refs["audio"]:
            invalid.append("image models cannot have video or audio references")
        if not link_nodes(output_inputs.get("images"), set(node_map)):
            invalid.append("image model output needs an image input")
    elif not (
        link_nodes(output_inputs.get("video"), set(node_map))
        or link_nodes(output_inputs.get("images"), set(node_map))
    ):
        invalid.append("video model output needs a video or image input")

    return graph, invalid
