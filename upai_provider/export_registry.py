"""Load export files into models with ready, stale or invalid status."""

import logging
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath

from .export_file import load_export
from .export_types import LoadedExport, ResolvedModel
from .protocol import ExportModel, Model, Pricing, WorkflowRef
from .protocol.shapes import ModelKind, ModelStatus

logger = logging.getLogger(__name__)

STALE_REASON = "source workflow is newer than this export"
DELETED_REASON = "source workflow was deleted"


def _source_path(source: str, root: Path | None) -> Path | None:
    if root is None:
        return None

    relative = PurePosixPath(source)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
        or ":" in relative.parts[0]
    ):
        return None

    return root.joinpath(*relative.parts)


def _refs_reason(model: ExportModel) -> str | None:
    bindings = model.bindings
    capabilities = model.capabilities
    for name in ("image", "video", "audio"):
        refs = bindings.refs.get(name, ())
        indexes = sorted(binding.index for binding in refs)
        if indexes != list(range(1, len(indexes) + 1)):
            return f"{name} reference indexes must be unique and contiguous from 1"

        capability = getattr(capabilities.references, name)
        if capability.required > capability.max:
            return f"{name}_required cannot be above {name}_max"

    frames = capabilities.frames
    if frames is not None:
        if frames.start_required and bindings.start is None:
            return "start_frame is required but no node is connected"
        if frames.end_required and bindings.end is None:
            return "end_frame is required but no node is connected"

    if model.kind == "image" and (bindings.refs.get("video") or bindings.refs.get("audio")):
        return "image models cannot have video or audio references"

    return None


def _class_reason(prompt: Mapping[str, object], known: set[str]) -> str | None:
    for node_id in sorted(prompt):
        node = prompt.get(node_id)
        if not isinstance(node, dict):
            continue

        class_type = node.get("class_type")
        if isinstance(class_type, str) and class_type not in known:
            return f"node class {class_type} is not installed"

    return None


class ExportRegistry:
    """Read one export directory. Parsed files are cached by file signature."""

    def __init__(
        self,
        exports_dir: Path,
        *,
        source_root: Path | None = None,
        known_classes: Callable[[], set[str]] | None = None,
    ) -> None:
        self.exports_dir = exports_dir
        self.source_root = source_root
        self.known_classes = known_classes
        self._cache: tuple[LoadedExport, ...] | None = None
        self._cache_signature: tuple[tuple[str, int, int, int], ...] | None = None

    def _signature(self) -> tuple[tuple[str, int, int, int], ...] | None:
        try:
            paths = sorted(self.exports_dir.glob("*.json"))
        except OSError:
            return None

        entries: list[tuple[str, int, int, int]] = []
        for path in paths:
            try:
                info = path.stat()
            except OSError:
                continue
            entries.append((path.name, info.st_ino, info.st_mtime_ns, info.st_size))

        return tuple(entries)

    def loads(self) -> tuple[LoadedExport, ...]:
        """Load every readable export file, reusing the cache until a file changes."""
        signature = self._signature()
        if signature is None:
            self._cache = ()
            self._cache_signature = None
            return ()

        if self._cache is not None and self._cache_signature == signature:
            return self._cache

        loaded: list[LoadedExport] = []
        for path in sorted(self.exports_dir.glob("*.json")):
            export = load_export(path)
            if export is not None:
                loaded.append(export)

        self._cache = tuple(loaded)
        self._cache_signature = signature
        return self._cache

    def _status(
        self,
        loaded: LoadedExport,
        model_id: str,
        source_mtime: float | None,
        class_reason: str | None,
        source_missing: bool,
    ) -> tuple[ModelStatus, str | None]:
        if source_missing:
            return "invalid", DELETED_REASON

        reason = loaded.invalid_reasons.get(model_id)
        if reason:
            return "invalid", reason

        if class_reason:
            return "invalid", class_reason

        for model in loaded.export.models:
            if model.model_id != model_id:
                continue

            reason = _refs_reason(model)
            if reason:
                return "invalid", reason
            break

        if source_mtime is not None and source_mtime > loaded.export.source_mtime:
            return "stale", STALE_REASON

        return "ready", None

    def resolved(self) -> tuple[ResolvedModel, ...]:
        """Return every enabled model with its current status."""
        resolved: list[ResolvedModel] = []
        known = self.known_classes() if self.known_classes is not None else None
        for loaded in self.loads():
            source = _source_path(loaded.export.source, self.source_root)
            source_mtime: float | None = None
            source_missing = False
            if source is not None:
                try:
                    source_mtime = source.stat().st_mtime
                except OSError:
                    source_missing = True
            class_reason: str | None = None
            if known is not None:
                class_reason = _class_reason(loaded.export.prompt, known)
            for model in loaded.export.models:
                if not model.enabled:
                    continue

                status, reason = self._status(
                    loaded, model.model_id, source_mtime, class_reason, source_missing
                )
                resolved.append(ResolvedModel(loaded.export, model, status, reason))

        return tuple(resolved)

    def catalog(self, kind: ModelKind) -> tuple[Model, ...]:
        """Return the protocol model list for one kind."""
        models: list[Model] = []
        seen: set[str] = set()
        for item in self.resolved():
            if item.model.kind != kind:
                continue

            full_id = f"{item.export.workflow_id}.{item.model.model_id}"
            if full_id in seen:
                logger.warning("skipping duplicate exported model %s", full_id)
                continue

            seen.add(full_id)
            models.append(
                Model(
                    id=full_id,
                    name=item.model.name,
                    description=item.model.description,
                    kind=item.model.kind,
                    status=item.status,
                    status_reason=item.status_reason,
                    updated_at=item.export.exported_at,
                    pricing=Pricing(item.model.price_per_run_usd),
                    capabilities=item.model.capabilities,
                    workflow=WorkflowRef(item.export.workflow_id, item.export.workflow_name),
                )
            )

        return tuple(models)

    def find(self, full_id: str) -> ResolvedModel | None:
        """Return one model by its wire id."""
        return next(
            (
                item
                for item in self.resolved()
                if f"{item.export.workflow_id}.{item.model.model_id}" == full_id
            ),
            None,
        )
