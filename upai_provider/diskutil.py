"""Free disk space for a pack-owned path. Stdlib only."""

import shutil
from pathlib import Path


def free_bytes(path: Path) -> int:
    """Return free bytes on the volume that holds path, or 0 on error."""
    target = path
    while True:
        try:
            return shutil.disk_usage(target).free
        except FileNotFoundError:
            if target.parent == target:
                return 0
            target = target.parent
        except OSError:
            return 0
