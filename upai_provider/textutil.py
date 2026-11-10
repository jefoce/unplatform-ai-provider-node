"""Text helpers shared by job and tracker code."""

from .constants import ERROR_TEXT_MAX_CHARS


def one_line(text: str) -> str:
    """Return the first line, cut to the stored error length."""
    first = text.splitlines()[0] if text.splitlines() else ""
    return first[:ERROR_TEXT_MAX_CHARS]
