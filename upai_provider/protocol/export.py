"""Frozen shapes for one exported workflow and its models."""

from collections.abc import Mapping
from dataclasses import dataclass

from .capabilities import Capabilities
from .shapes import ModelKind


@dataclass(frozen=True)
class RefBinding:
    node: str
    index: int
    required: bool


@dataclass(frozen=True)
class ModelBinding:
    workflow: str
    prompt: str | None
    settings: str | None
    output: str
    start: str | None
    end: str | None
    refs: Mapping[str, tuple[RefBinding, ...]]


@dataclass(frozen=True)
class ExportModel:
    model_id: str
    name: str
    description: str
    kind: ModelKind
    enabled: bool
    output_node: str
    bindings: ModelBinding
    capabilities: Capabilities
    price_per_run_usd: float = 0.0


@dataclass(frozen=True)
class Export:
    workflow_id: str
    workflow_name: str
    source: str
    source_mtime: float
    exported_at: str
    comfy_version: str
    models: tuple[ExportModel, ...]
    prompt: Mapping[str, object]
