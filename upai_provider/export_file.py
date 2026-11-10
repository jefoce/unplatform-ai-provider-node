"""Read and write export files atomically."""

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from .export_serialize import export_from_data, export_to_data
from .export_types import LoadedExport
from .fileutil import replace_file
from .protocol import Export

logger = logging.getLogger(__name__)


def load_export(path: Path) -> LoadedExport | None:
    """Load one export file. A broken file is skipped, never raised."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("ignoring unreadable export file %s: %s", path, exc)
        return None

    try:
        return export_from_data(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("ignoring invalid export file %s: %s", path, exc)
        return None


def write_export(
    path: Path,
    export: Export,
    invalid_reasons: Mapping[str, str],
    warnings: tuple[str, ...],
) -> None:
    """Write one export atomically under its parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = export_to_data(export, invalid_reasons, warnings)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".export-", suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
            file.write("\n")
        replace_file(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
