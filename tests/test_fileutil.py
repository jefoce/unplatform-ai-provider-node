"""replace_file retry behavior."""

import errno
from collections.abc import Callable
from pathlib import Path

import pytest

from upai_provider import fileutil
from upai_provider.fileutil import REPLACE_BACKOFF_SEC, REPLACE_RETRIES


def _fake_replace(
    calls: list[tuple[str | Path, str | Path]], failures: int
) -> Callable[[str | Path, str | Path], None]:
    def replace(source: str | Path, target: str | Path) -> None:
        calls.append((source, target))
        if len(calls) <= failures:
            raise PermissionError(errno.EACCES, "locked")

    return replace


def test_replace_succeeds_first_try(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | Path, str | Path]] = []
    monkeypatch.setattr(fileutil.os, "replace", _fake_replace(calls, 0))

    fileutil.replace_file("src", "dst")

    assert calls == [("src", "dst")]


def test_two_permission_errors_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | Path, str | Path]] = []
    sleeps: list[float] = []
    monkeypatch.setattr(fileutil.os, "replace", _fake_replace(calls, 2))
    monkeypatch.setattr(fileutil.time, "sleep", sleeps.append)

    fileutil.replace_file("src", "dst")

    assert len(calls) == 3
    assert sleeps == [REPLACE_BACKOFF_SEC, REPLACE_BACKOFF_SEC * 2]


def test_exhausted_retries_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | Path, str | Path]] = []
    sleeps: list[float] = []
    monkeypatch.setattr(fileutil.os, "replace", _fake_replace(calls, REPLACE_RETRIES))
    monkeypatch.setattr(fileutil.time, "sleep", sleeps.append)

    with pytest.raises(PermissionError):
        fileutil.replace_file("src", "dst")

    assert len(calls) == REPLACE_RETRIES
    assert len(sleeps) == REPLACE_RETRIES - 1


def test_other_oserror_propagates_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | Path, str | Path]] = []

    def replace(source: str | Path, target: str | Path) -> None:
        calls.append((source, target))
        raise OSError(errno.ENOENT, "missing")

    monkeypatch.setattr(fileutil.os, "replace", replace)

    with pytest.raises(OSError):
        fileutil.replace_file("src", "dst")

    assert len(calls) == 1
