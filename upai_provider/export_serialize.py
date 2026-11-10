"""Encode and decode the stored export JSON shape."""

import logging
from collections.abc import Mapping
from typing import cast

from .export_capabilities_io import (
    _REF_KINDS,
    capabilities_from_data,
    capabilities_to_data,
)
from .export_fields import (
    _bool,
    _float,
    _int,
    _mapping,
    _obj,
    _optional_str,
    _optional_strings,
    _str,
)
from .export_types import LoadedExport
from .protocol import Export, ExportModel, ModelBinding, RefBinding
from .protocol.shapes import ModelKind

logger = logging.getLogger(__name__)


def _refs_to_data(refs: Mapping[str, tuple[RefBinding, ...]]) -> dict[str, object]:
    return {
        name: [
            {"node": binding.node, "index": binding.index, "required": binding.required}
            for binding in refs.get(name, ())
        ]
        for name in _REF_KINDS
    }


def _refs_from_data(value: object) -> Mapping[str, tuple[RefBinding, ...]]:
    obj = _mapping(value, "bindings.refs")
    refs: dict[str, tuple[RefBinding, ...]] = {}
    for name in _REF_KINDS:
        raw = obj.get(name, [])
        if not isinstance(raw, list):
            raise ValueError(f"bindings.refs.{name} must be a list")

        bindings: list[RefBinding] = []
        for item in raw:
            entry = _obj(item, f"bindings.refs.{name}")
            bindings.append(
                RefBinding(
                    _str(entry, "node"),
                    _int(entry, "index"),
                    _bool(entry, "required"),
                )
            )

        refs[name] = tuple(bindings)

    return refs


def _binding_to_data(binding: ModelBinding) -> dict[str, object]:
    return {
        "workflow": binding.workflow,
        "prompt": binding.prompt,
        "settings": binding.settings,
        "output": binding.output,
        "start": binding.start,
        "end": binding.end,
        "refs": _refs_to_data(binding.refs),
    }


def _binding_from_data(value: object) -> ModelBinding:
    obj = _obj(value, "bindings")
    return ModelBinding(
        workflow=_str(obj, "workflow"),
        prompt=_optional_str(obj, "prompt"),
        settings=_optional_str(obj, "settings"),
        output=_str(obj, "output"),
        start=_optional_str(obj, "start"),
        end=_optional_str(obj, "end"),
        refs=_refs_from_data(obj.get("refs")),
    )


def export_to_data(
    export: Export,
    invalid_reasons: Mapping[str, str],
    warnings: tuple[str, ...],
) -> dict[str, object]:
    """Serialize one export to the stored JSON shape."""
    models: list[dict[str, object]] = []
    for model in export.models:
        models.append(
            {
                "model_id": model.model_id,
                "name": model.name,
                "description": model.description,
                "kind": model.kind,
                "enabled": model.enabled,
                "price_per_run_usd": model.price_per_run_usd,
                "output_node": model.output_node,
                "bindings": _binding_to_data(model.bindings),
                "capabilities": capabilities_to_data(model.capabilities),
                "invalid_reason": invalid_reasons.get(model.model_id),
            }
        )

    return {
        "workflow_id": export.workflow_id,
        "workflow_name": export.workflow_name,
        "source": export.source,
        "source_mtime": export.source_mtime,
        "exported_at": export.exported_at,
        "comfy_version": export.comfy_version,
        "warnings": list(warnings),
        "models": models,
        "prompt": dict(export.prompt),
    }


def _model_from_data(value: object) -> tuple[ExportModel, str | None]:
    obj = _obj(value, "model")
    kind = _str(obj, "kind")
    if kind not in ("video", "image"):
        raise ValueError("model.kind must be video or image")

    model = ExportModel(
        model_id=_str(obj, "model_id"),
        name=_str(obj, "name"),
        description=_str(obj, "description"),
        kind=cast(ModelKind, kind),
        enabled=_bool(obj, "enabled", True),
        price_per_run_usd=(
            _float(obj, "price_per_run_usd") if obj.get("price_per_run_usd") is not None else 0.0
        ),
        output_node=_str(obj, "output_node"),
        bindings=_binding_from_data(obj.get("bindings")),
        capabilities=capabilities_from_data(obj.get("capabilities")),
    )
    return model, _optional_str(obj, "invalid_reason")


def export_from_data(raw: object) -> LoadedExport:
    """Decode one stored export object, skipping unusable models."""
    obj = _obj(raw, "export")
    models_raw = obj.get("models")
    if not isinstance(models_raw, list):
        raise ValueError("models must be a list")

    models: list[ExportModel] = []
    invalid: dict[str, str] = {}
    seen: set[str] = set()
    for item in models_raw:
        try:
            model, reason = _model_from_data(item)
        except (ValueError, TypeError) as exc:
            logger.warning("skipping invalid exported model: %s", exc)
            continue

        if model.model_id in seen:
            logger.warning("skipping duplicate exported model %s", model.model_id)
            continue

        seen.add(model.model_id)
        models.append(model)
        if reason:
            invalid[model.model_id] = reason

    export = Export(
        workflow_id=_str(obj, "workflow_id"),
        workflow_name=_str(obj, "workflow_name"),
        source=_str(obj, "source"),
        source_mtime=_float(obj, "source_mtime"),
        exported_at=_str(obj, "exported_at"),
        comfy_version=_str(obj, "comfy_version"),
        models=tuple(models),
        prompt=_mapping(obj.get("prompt"), "prompt"),
    )
    warnings = _optional_strings(obj, "warnings")
    return LoadedExport(export, invalid, warnings)
