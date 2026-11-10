"""Timestamp formatting shared by jobs and runtime state."""

from collections.abc import Callable
from datetime import datetime, timezone


def iso_now(clock: Callable[[], float]) -> str:
    """Format the clock as a UTC timestamp."""
    return datetime.fromtimestamp(clock(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
