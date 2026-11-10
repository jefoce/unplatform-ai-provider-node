"""Loopback websocket tracker for pack prompts."""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Protocol, cast
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp

from .tracker_events import TrackerEvents
from .tracker_messages import TrackerMessages
from .tracker_poll import TrackerPoll
from .tracker_state import TrackerState, _Store

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 2.0
BACKOFF_START_SEC = 1.0
BACKOFF_MAX_SEC = 30.0
_WS_HEARTBEAT_SEC = 30.0


class _WsMessage(Protocol):
    type: int
    data: str | bytes


class _WsSocket(Protocol):
    def __aiter__(self) -> AsyncIterator[_WsMessage]: ...

    async def __aenter__(self) -> "_WsSocket": ...

    async def __aexit__(self, *args: object) -> None: ...


class _WsConnect(Protocol):
    def __call__(self, url: str, *, heartbeat: float) -> _WsSocket: ...


def websocket_url(server_url: str, instance_id: str) -> str:
    """Return the loopback websocket URL for one pack instance."""
    parts = urlsplit(server_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    query = urlencode({"clientId": f"upai-{instance_id}"})
    return urlunsplit((scheme, parts.netloc, "/ws", query, ""))


class Tracker(TrackerState, TrackerMessages, TrackerEvents, TrackerPoll):
    """One loopback websocket, reconnects, polls while the socket is down."""

    def __init__(
        self,
        *,
        store: _Store,
        instance_id: str,
        server_url: str,
        session: object | None = None,
        poll_interval: float = POLL_INTERVAL_SEC,
        backoff_start: float = BACKOFF_START_SEC,
        backoff_max: float = BACKOFF_MAX_SEC,
        clock: Callable[[], float] = time.time,
        cancel_prompt: Callable[[str, bool], Awaitable[None]] | None = None,
    ) -> None:
        self._store = store
        self._instance_id = instance_id
        self._server_url = server_url.rstrip("/")
        self._session = session
        self._poll_interval = poll_interval
        self._backoff_start = backoff_start
        self._backoff = backoff_start
        self._backoff_max = backoff_max
        self._clock = clock
        self._cancel_prompt_cb = cancel_prompt
        self._tracked = {}
        self._job_counts = {}
        self._job_prompts = {}
        self._job_done = {}
        self._task: asyncio.Task[None] | None = None
        self._is_enabled = False
        self._is_url_confirmed = False

    def set_server_url(self, server_url: str) -> None:
        """Point the reconnect loop at a new ComfyUI address."""
        normalized = server_url.rstrip("/")
        changed = normalized != self._server_url
        self._server_url = normalized
        self._is_url_confirmed = True
        if not self._is_enabled:
            return

        self._backoff = self._backoff_start
        if self._task is not None and not changed:
            return

        if self._task is not None:
            self._task.cancel()

        self._task = asyncio.create_task(self._run())

    async def start(self) -> None:
        """Start the reconnect loop once a server URL is confirmed."""
        if self._session is None:
            raise RuntimeError("tracker needs an HTTP session")
        self._is_enabled = True
        if not self._is_url_confirmed or self._task is not None:
            return

        self._task = asyncio.create_task(self._run())

    async def cancel_prompt(self, prompt_id: str, is_running: bool) -> None:
        """Cancel one prompt through the wired callback."""
        if self._cancel_prompt_cb is None:
            return

        try:
            await self._cancel_prompt_cb(prompt_id, is_running)
        except Exception as exc:
            logger.warning("cancel prompt %s failed: %s", prompt_id, type(exc).__name__)

    async def stop(self) -> None:
        """Cancel the reconnect loop."""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _consume(self) -> None:
        connect = getattr(self._session, "ws_connect", None)
        if not callable(connect):
            raise RuntimeError("tracker session has no websocket support")

        connect = cast(_WsConnect, connect)
        url = websocket_url(self._server_url, self._instance_id)
        async with connect(url, heartbeat=_WS_HEARTBEAT_SEC) as socket:
            self._backoff = self._backoff_start
            await self.poll_once()
            async for message in socket:
                message_type = getattr(message, "type", None)
                if message_type == aiohttp.WSMsgType.TEXT:
                    try:
                        decoded = json.loads(message.data)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(decoded, Mapping):
                        await self.handle_message(decoded)
                elif message_type in (
                    aiohttp.WSMsgType.ERROR,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                ):
                    break

    async def _run(self) -> None:
        while True:
            try:
                await self._consume()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("tracker websocket error: %s", type(exc).__name__)

            await self._sleep_with_poll(self._backoff)
            self._backoff = min(self._backoff_max, self._backoff * 2)


__all__ = ["Tracker", "websocket_url"]
