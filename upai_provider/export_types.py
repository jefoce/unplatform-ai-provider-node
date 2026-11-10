"""Internal shapes shared by export derivation, files and registry."""

from collections.abc import Mapping
from dataclasses import dataclass

from .constants import ALLOWED_IMAGE_FORMATS, REFERENCE_MAX_BYTES
from .protocol import (
    Capabilities,
    PromptCapability,
    ReferenceCapability,
    ReferenceLimit,
    ReferenceLimits,
    ReferencesCapability,
)
from .protocol.export import Export, ExportModel, RefBinding
from .protocol.shapes import ModelKind, ModelStatus

NodeMap = Mapping[str, Mapping[str, object]]


@dataclass(frozen=True)
class ModelGraph:
    """One model and the UPAI nodes reachable from its output."""

    model_node: str
    kind: ModelKind
    output_node: str
    prompt_node: str | None
    settings_node: str | None
    start_node: str | None
    end_node: str | None
    limits_node: str | None
    refs: Mapping[str, tuple[RefBinding, ...]]
    prompt_negative_used: bool
    nodes: NodeMap


@dataclass(frozen=True)
class ExportBuild:
    """A derived export plus the issues found while deriving it."""

    export: Export
    invalid_reasons: Mapping[str, str]
    warnings: tuple[str, ...] = ()
    workflow_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadedExport:
    """One export file with the issues stored next to its models."""

    export: Export
    invalid_reasons: Mapping[str, str]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedModel:
    """One exported model with its current status."""

    export: Export
    model: ExportModel
    status: ModelStatus
    status_reason: str | None


def empty_capabilities() -> Capabilities:
    """Return the smallest valid capability object for an invalid model."""
    return Capabilities(
        prompt=PromptCapability(False, 0),
        negative_prompt=False,
        references=ReferencesCapability(
            image=ReferenceCapability(0, 0),
            video=ReferenceCapability(0, 0),
            audio=ReferenceCapability(0, 0),
        ),
        resolutions=(),
        default_resolution="",
        aspect_ratios=(),
        default_aspect_ratio="",
        sizes={},
        seed=False,
        reference_limits=ReferenceLimits(
            ReferenceLimit(REFERENCE_MAX_BYTES, ALLOWED_IMAGE_FORMATS)
        ),
    )
