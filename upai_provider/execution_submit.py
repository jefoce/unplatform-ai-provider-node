"""POST a patched prompt to ComfyUI over loopback HTTP."""

import asyncio
from collections.abc import Mapping
from typing import cast

import aiohttp

from .execution_errors import ComfyUnavailableError, PromptRejectedError
from .execution_patch import PromptRun
from .materialize import HttpSession, PostResponse

_HTTP_OK = (200, 201)


async def _response_body(response: PostResponse) -> Mapping[str, object]:
    try:
        body = await response.json(content_type=None)
    except (ValueError, TypeError):
        return {}

    return cast(Mapping[str, object], body) if isinstance(body, dict) else {}


async def submit_prompt(
    session: HttpSession,
    *,
    server_url: str,
    run: PromptRun,
    client_id: str,
    output_node: str,
) -> None:
    """POST one prompt to ComfyUI. Raises on rejection or an unreachable server."""
    payload = {
        "prompt": run.prompt,
        "prompt_id": run.prompt_id,
        "client_id": client_id,
        "partial_execution_targets": [output_node],
    }
    url = f"{server_url.rstrip('/')}/prompt"
    try:
        async with session.post(url, json=payload) as response:
            body = await _response_body(response)
            if response.status == 400:
                node_errors = body.get("node_errors")
                raise PromptRejectedError(
                    node_errors if isinstance(node_errors, Mapping) else {},
                    is_queued=False,
                )

            if response.status not in _HTTP_OK:
                raise ComfyUnavailableError(
                    f"prompt route returned {response.status}",
                    is_queued=False,
                )

            node_errors = body.get("node_errors")
            if isinstance(node_errors, Mapping) and node_errors:
                raise PromptRejectedError(node_errors, is_queued=True)
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
        raise ComfyUnavailableError("prompt route is unreachable", is_queued=True) from exc


def _first_node_error(node_errors: Mapping[str, object]) -> str:
    for node_id, value in node_errors.items():
        if isinstance(value, Mapping):
            message = value.get("message") or value.get("exception_message")
            if isinstance(message, str) and message:
                return f"{node_id}: {message}"

            errors = value.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, Mapping):
                    message = first.get("message")
                    if isinstance(message, str) and message:
                        return f"{node_id}: {message}"

    return "workflow rejected by ComfyUI"
