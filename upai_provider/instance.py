"""Stable instance identity stored in instance.json. Stdlib only."""

import contextlib
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

from .fileutil import replace_file

logger = logging.getLogger(__name__)


def _read_instance_id(path: Path) -> str | None:
    """Return the stored UUID4 string, or None when the file is missing or invalid."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None

    if not isinstance(raw, dict):
        return None

    value = raw.get("instance_id")
    if not isinstance(value, str):
        return None

    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None

    if parsed.version != 4:
        return None

    return str(parsed)


def _write_instance_id(path: Path, instance_id: str) -> None:
    """Write the id atomically in the target directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".instance-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(
                {"instance_id": instance_id},
                file,
                separators=(",", ":"),
                sort_keys=True,
            )
        replace_file(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise


def load_instance_id(path: Path) -> str:
    """Load or create the instance id stored at path."""
    existing = _read_instance_id(path)
    if existing is not None:
        return existing

    if path.is_file():
        logger.warning("instance file %s is invalid; creating a new id", path)

    instance_id = str(uuid.uuid4())
    _write_instance_id(path, instance_id)
    return instance_id
