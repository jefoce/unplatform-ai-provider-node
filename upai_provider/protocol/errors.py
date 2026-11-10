"""Protocol error with an HTTP status and optional field details."""

from collections.abc import Mapping
from typing import Literal, TypeGuard

ERROR_CODES = (
    "invalid_request",
    "unauthorized",
    "forbidden",
    "model_not_found",
    "job_not_found",
    "upload_not_found",
    "not_found",
    "method_not_allowed",
    "too_large",
    "insufficient_storage",
    "workflow_invalid",
    "queue_full",
    "comfy_unavailable",
    "config_invalid",
    "internal",
    "timeout",
    "job_failed",
)
ErrorCode = Literal[
    "invalid_request",
    "unauthorized",
    "forbidden",
    "model_not_found",
    "job_not_found",
    "upload_not_found",
    "not_found",
    "method_not_allowed",
    "too_large",
    "insufficient_storage",
    "workflow_invalid",
    "queue_full",
    "comfy_unavailable",
    "config_invalid",
    "internal",
    "timeout",
    "job_failed",
]


def is_error_code(value: object) -> TypeGuard[ErrorCode]:
    """Return true when value is a known error code."""
    return isinstance(value, str) and value in ERROR_CODES


class ProtocolError(Exception):
    """Bad input or unavailable resource, mapped to a JSON error response."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
        status: int = 400,
    ) -> None:
        if not is_error_code(code):
            raise ValueError(f"unknown error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.status = status
