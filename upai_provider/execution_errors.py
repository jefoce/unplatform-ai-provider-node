"""Errors raised while materializing, patching and submitting a job."""

from collections.abc import Mapping


class WorkflowInvalidError(Exception):
    """The exported prompt no longer matches its bindings."""

    def __init__(self, message: str, node_errors: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.node_errors = dict(node_errors or {})


class PromptRejectedError(Exception):
    """ComfyUI rejected the prompt or reported node errors."""

    def __init__(
        self,
        node_errors: Mapping[str, object] | None = None,
        *,
        is_queued: bool = False,
    ) -> None:
        super().__init__("workflow rejected by ComfyUI")
        self.node_errors = dict(node_errors or {})
        self.is_queued = is_queued


class ComfyUnavailableError(Exception):
    """The loopback prompt route could not be reached."""

    def __init__(self, message: str, *, is_queued: bool = False) -> None:
        super().__init__(message)
        self.is_queued = is_queued
