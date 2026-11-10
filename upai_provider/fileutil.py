"""Atomic file replace with retry for transient Windows locks."""

from __future__ import annotations

import os
import time
from pathlib import Path

REPLACE_RETRIES = 5
REPLACE_BACKOFF_SEC = 0.05


def replace_file(source: str | Path, target: str | Path) -> None:
    """Replace target with source, retrying transient PermissionError."""
    for attempt in range(REPLACE_RETRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == REPLACE_RETRIES - 1:
                raise

            time.sleep(min(REPLACE_BACKOFF_SEC * 2**attempt, 0.5))
