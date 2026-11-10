"""Contract tests for the release version script against a throwaway git repo."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "release-version.sh"


def _bash() -> str:
    """Resolve a real bash, using Git Bash on Windows instead of the WSL launcher."""
    if os.name == "nt":
        git = shutil.which("git")
        if git is not None:
            candidate = Path(git).resolve().parents[1] / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
        pytest.skip("Git Bash is required")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is required")
    return bash


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "--quiet", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path, version: str, changelog: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "upai_provider").mkdir()
    (repo / "pyproject.toml").write_text(f'version = "{version}"\n', encoding="utf-8")
    (repo / "upai_provider" / "version.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    (repo / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    _commit(repo, "initial")
    return repo


def _run(repo: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    output = repo / "github-output.txt"
    output.write_text("", encoding="utf-8")
    env = {**os.environ, "GITHUB_OUTPUT": str(output)}
    result = subprocess.run(  # noqa: S603
        [_bash(), str(SCRIPT)],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    outputs: dict[str, str] = {}
    for line in output.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        outputs[key] = value
    return result, outputs


def test_unreleased_version_skips(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "0.1.0", "## 0.1.0 - unreleased\n\nNotes.\n")
    result, outputs = _run(repo)
    assert result.returncode == 0, result.stderr
    assert outputs["release"] == "false"
    assert not (repo / "release-notes.md").exists()


def test_new_tag_releases(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "0.1.0", "## 0.1.0 - 2026-01-01\n\nNotes.\n")
    result, outputs = _run(repo)
    assert result.returncode == 0, result.stderr
    assert outputs["release"] == "true"
    assert outputs["tag"] == "v0.1.0"
    notes = (repo / "release-notes.md").read_text(encoding="utf-8")
    assert notes.strip() == "Notes."


def test_same_commit_rerun_releases(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "0.1.0", "## 0.1.0 - 2026-01-01\n\nNotes.\n")
    _git(repo, "tag", "v0.1.0", "HEAD")
    result, outputs = _run(repo)
    assert result.returncode == 0, result.stderr
    assert outputs["release"] == "true"
    assert outputs["tag"] == "v0.1.0"


def test_tag_at_another_commit_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "0.1.0", "## 0.1.0 - 2026-01-01\n\nNotes.\n")
    _git(repo, "tag", "v0.1.0", "HEAD")
    (repo / "README.md").write_text("extra\n", encoding="utf-8")
    head = _commit(repo, "second")
    result, _ = _run(repo)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "v0.1.0" in output
    assert head in output
    assert "HEAD" in output


def test_older_version_than_newest_tag_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "0.2.0", "## 0.2.0 - 2026-01-01\n\nNotes.\n")
    _git(repo, "tag", "v0.3.0", "HEAD")
    result, _ = _run(repo)
    assert result.returncode != 0
    assert "must be greater" in (result.stdout + result.stderr)
