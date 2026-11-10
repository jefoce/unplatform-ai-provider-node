"""Job status values shared by the protocol and the pack. Stdlib only."""

from typing import Literal, TypeGuard

JOB_STATUSES = ("pending", "in_progress", "completed", "failed", "cancelled", "expired")
JobStatus = Literal["pending", "in_progress", "completed", "failed", "cancelled", "expired"]
FINAL_JOB_STATUSES = ("completed", "failed", "cancelled", "expired")


def is_job_status(value: object) -> TypeGuard[JobStatus]:
    """Return true when value is a known job status."""
    return isinstance(value, str) and value in JOB_STATUSES
