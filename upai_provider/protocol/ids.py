"""Identifier patterns shared by the protocol and the pack. Stdlib only."""

import re

RUN_ID_SEPARATOR = "_r"

JOB_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
MODEL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,128}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def format_run_id(job_id: str, run_index: int) -> str:
    """Return the internal run id for one job run."""
    if not JOB_ID_PATTERN.match(job_id):
        raise ValueError("job id must be a lowercase UUID4")
    if run_index < 0:
        raise ValueError("run index must be non-negative")

    return f"{job_id}{RUN_ID_SEPARATOR}{run_index}"


def parse_run_id(value: str) -> tuple[str, int] | None:
    """Split an internal run id into its job id and run index. None when invalid."""
    job_id, separator, index_text = value.rpartition(RUN_ID_SEPARATOR)
    if not separator or not JOB_ID_PATTERN.match(job_id):
        return None
    if not index_text.isascii() or not index_text.isdigit():
        return None

    return job_id, int(index_text)
