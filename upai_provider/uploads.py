"""Content-addressed upload storage."""

import asyncio
import contextlib
import hashlib
import os
import tempfile
import threading
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from .constants import CONTENT_TYPES, UPLOAD_QUOTA_BYTES
from .fileutil import replace_file
from .protocol import SHA256_PATTERN, ProtocolError, Upload

_TEMP_PREFIX = ".upload-"
_TEMP_SUFFIX = ".tmp"


def _preferred_extensions() -> dict[str, str]:
    """Map each content type to its first declared suffix."""
    extensions: dict[str, str] = {}
    for suffix, content_type in CONTENT_TYPES.items():
        extensions.setdefault(content_type, suffix)

    return extensions


_EXT_FOR_CONTENT_TYPE = _preferred_extensions()


def content_type_for(path: Path) -> str:
    """Return the content type for a known file suffix."""
    return CONTENT_TYPES.get(path.suffix.lower().lstrip("."), "application/octet-stream")


def _extension_for(filename: str, content_type: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in CONTENT_TYPES:
        return suffix

    return _EXT_FOR_CONTENT_TYPE.get(content_type, "bin")


def _is_temp_name(name: str) -> bool:
    return name.startswith(_TEMP_PREFIX) and name.endswith(_TEMP_SUFFIX)


class UploadStore:
    """Content-addressed uploads under one pack-owned root."""

    def __init__(
        self,
        root: Path,
        *,
        max_bytes: int,
        clock: Callable[[], float],
        max_total_bytes: int = UPLOAD_QUOTA_BYTES,
    ) -> None:
        self._root = root
        self._max_bytes = max_bytes
        self._max_total_bytes = max_total_bytes
        self._clock = clock
        self._lock = asyncio.Lock()
        self._quota_lock = threading.Lock()
        self._pin_lock = threading.Lock()
        self._pins: dict[str, set[str]] = {}
        self._pin_counts: dict[str, int] = {}
        self._committed_bytes: int | None = None
        self._reserved_bytes = 0

    @property
    def root(self) -> Path:
        """Directory that holds every stored upload."""
        return self._root

    @property
    def max_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self._max_bytes

    @property
    def max_total_bytes(self) -> int:
        """Maximum total bytes stored under the upload root."""
        return self._max_total_bytes

    async def save(self, filename: str, content_type: str, data: bytes) -> Upload:
        """Store bytes by sha256 and return the upload record."""

        async def chunks() -> AsyncIterator[bytes]:
            yield data

        return await self.save_stream(filename, content_type, chunks())

    async def save_stream(
        self,
        filename: str,
        content_type: str,
        chunks: AsyncIterator[bytes],
        *,
        reserved_bytes: int = 0,
        max_bytes: int | None = None,
    ) -> Upload:
        """Stream chunks to a temp file, cap per chunk, then store by sha256.

        reserved_bytes is the request Content-Length, held against the quota
        before the first chunk is read. max_bytes lowers the per-request cap.
        """
        cap = self._max_bytes if max_bytes is None else min(self._max_bytes, max_bytes)
        self._root.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._ensure_committed)
        handle, temp_name = tempfile.mkstemp(
            dir=self._root, prefix=_TEMP_PREFIX, suffix=_TEMP_SUFFIX
        )
        temp_path = Path(temp_name)
        reserved = 0
        try:
            with os.fdopen(handle, "wb") as file:
                self._reserve(reserved_bytes)
                reserved = reserved_bytes

                digest = hashlib.sha256()
                size = 0
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > cap:
                        raise ProtocolError(
                            "too_large",
                            f"upload exceeds {cap} bytes",
                            details={"field": "file"},
                            status=413,
                        )
                    if size > reserved:
                        self._reserve(size - reserved)
                        reserved = size
                    digest.update(chunk)
                    await asyncio.to_thread(file.write, chunk)

                if size == 0:
                    raise ProtocolError(
                        "invalid_request",
                        "upload is empty",
                        details={"field": "file"},
                        status=400,
                    )

            sha256 = digest.hexdigest()
            async with self._lock:
                existing = self._find(sha256)
                if existing is not None:
                    os.utime(existing, None)
                    self._settle(reserved, 0)
                    reserved = 0
                    return self._record(existing, sha256, filename)

                target = self._root / f"{sha256}.{_extension_for(filename, content_type)}"
                await asyncio.to_thread(replace_file, temp_path, target)
                self._settle(reserved, size)
                reserved = 0
                return self._record(target, sha256, filename)
        except BaseException:
            self._release(reserved)
            raise
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp_path)

    def _record(self, path: Path, sha256: str, filename: str) -> Upload:
        return Upload(
            sha256=sha256,
            ref=f"upai-upload:{sha256}",
            size=path.stat().st_size,
            content_type=content_type_for(path),
            filename=filename,
        )

    def _find(self, sha256: str) -> Path | None:
        if not SHA256_PATTERN.match(sha256):
            return None

        try:
            for path in self._root.glob(f"{sha256}.*"):
                if path.is_file():
                    return path
        except OSError:
            return None

        return None

    def _ensure_committed(self) -> int:
        with self._quota_lock:
            return self._ensure_committed_locked()

    def _ensure_committed_locked(self) -> int:
        if self._committed_bytes is None:
            self._committed_bytes = self._total_bytes()

        return self._committed_bytes

    def _reserve(self, size: int) -> None:
        with self._quota_lock:
            committed = self._ensure_committed_locked()
            if committed + self._reserved_bytes + size > self._max_total_bytes:
                raise ProtocolError(
                    "too_large",
                    "upload quota exceeded",
                    details={"field": "file", "reason": "quota"},
                    status=413,
                )
            self._reserved_bytes += size

    def _release(self, size: int) -> None:
        with self._quota_lock:
            self._reserved_bytes = max(0, self._reserved_bytes - size)

    def _settle(self, reservation: int, added: int) -> None:
        with self._quota_lock:
            self._reserved_bytes = max(0, self._reserved_bytes - reservation)
            committed = self._committed_bytes
            if committed is not None:
                self._committed_bytes = committed + added

    def _forget(self, size: int) -> None:
        with self._quota_lock:
            committed = self._committed_bytes
            if committed is not None:
                self._committed_bytes = max(0, committed - size)

    def _total_bytes(self) -> int:
        if not self._root.is_dir():
            return 0

        total = 0
        for path in self._root.rglob("*"):
            if not path.is_file() or _is_temp_name(path.name):
                continue

            try:
                total += path.stat().st_size
            except OSError:
                continue

        return total

    def remaining_bytes(self) -> int:
        """Bytes still available under the total upload quota."""
        with self._quota_lock:
            committed = self._ensure_committed_locked()
            reserved = self._reserved_bytes
        return max(0, self._max_total_bytes - committed - reserved)

    def head(self, sha256: str) -> Upload | None:
        """Return an existing upload record by hash."""
        path = self._find(sha256)
        if path is None:
            return None

        try:
            os.utime(path, None)
            return self._record(path, sha256, path.name)
        except OSError:
            return None

    async def head_async(self, sha256: str) -> Upload | None:
        """Return an existing upload record without blocking the event loop."""
        return await asyncio.to_thread(self.head, sha256)

    def path(self, sha256: str) -> Path | None:
        """Return the stored file path by hash."""
        return self._find(sha256)

    def pin(self, job_id: str, sha256: str) -> None:
        """Keep one stored upload while a non-final job references it."""
        with self._pin_lock:
            refs = self._pins.setdefault(job_id, set())
            if sha256 in refs:
                return

            refs.add(sha256)
            self._pin_counts[sha256] = self._pin_counts.get(sha256, 0) + 1

    def release(self, job_id: str) -> None:
        """Drop every upload pin held by one job."""
        with self._pin_lock:
            refs = self._pins.pop(job_id, set())
            for sha256 in refs:
                count = self._pin_counts.get(sha256, 0) - 1
                if count <= 0:
                    self._pin_counts.pop(sha256, None)
                else:
                    self._pin_counts[sha256] = count

    def _is_pinned(self, name: str) -> bool:
        with self._pin_lock:
            return self._pin_counts.get(name.split(".", 1)[0], 0) > 0

    def sweep(self, max_age_sec: float, now: float) -> None:
        """Remove unpinned files under the root older than max_age_sec."""
        if not self._root.is_dir():
            return

        cutoff = now - max_age_sec
        for path in self._root.iterdir():
            if not path.is_file():
                continue
            try:
                stat_result = path.stat()
            except OSError:
                continue
            if stat_result.st_mtime >= cutoff:
                continue
            if not _is_temp_name(path.name) and self._is_pinned(path.name):
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                continue
            if not _is_temp_name(path.name):
                self._forget(stat_result.st_size)
