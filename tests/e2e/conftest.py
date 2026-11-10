"""ComfyUI subprocess fixture and HTTP helpers for the comfy marker."""

from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image

from upai_provider.constants import (
    NODE_UPAI_AUDIO_REF,
    NODE_UPAI_END_FRAME,
    NODE_UPAI_IMAGE_REF,
    NODE_UPAI_LIMITS,
    NODE_UPAI_MODEL,
    NODE_UPAI_OUTPUT,
    NODE_UPAI_PROMPT,
    NODE_UPAI_SETTINGS,
    NODE_UPAI_START_FRAME,
    NODE_UPAI_VIDEO_REF,
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / "tests" / "workflows" / "api"
PORT = int(os.environ.get("UPAI_COMFY_PORT", "8189"))
STARTUP_TIMEOUT_SEC = 120.0
JOB_TIMEOUT_SEC = 180.0
SHUTDOWN_TIMEOUT_SEC = 15.0
FRAME_NAME = "upai-frame.png"

UPAI_NODE_CLASSES = (
    NODE_UPAI_MODEL,
    NODE_UPAI_LIMITS,
    NODE_UPAI_PROMPT,
    NODE_UPAI_IMAGE_REF,
    NODE_UPAI_VIDEO_REF,
    NODE_UPAI_AUDIO_REF,
    NODE_UPAI_START_FRAME,
    NODE_UPAI_END_FRAME,
    NODE_UPAI_SETTINGS,
    NODE_UPAI_OUTPUT,
)


def _python(comfy_dir: Path) -> Path | None:
    override = os.environ.get("UPAI_COMFY_PYTHON")
    if override:
        return Path(override)
    for candidate in (comfy_dir / ".venv" / "bin" / "python", Path(sys.executable)):
        if candidate.is_file():
            return candidate
    return None


def _port_busy() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def _has_upai_nodes() -> bool:
    package = ROOT / "upai_provider" / "nodes"
    return package.is_dir() and any(package.glob("*.py"))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _environment_reason() -> str | None:
    if not os.environ.get("UPAI_COMFY_DIR"):
        return "UPAI_COMFY_DIR is not set"
    comfy_dir = Path(os.environ["UPAI_COMFY_DIR"])
    if not (comfy_dir / "main.py").is_file():
        return f"UPAI_COMFY_DIR does not look like a ComfyUI checkout: {comfy_dir}"
    if _python(comfy_dir) is None:
        return "no Python interpreter for ComfyUI (set UPAI_COMFY_PYTHON)"
    if not _has_upai_nodes():
        return "UPAI nodes are absent on this branch (w-nodes has not landed)"
    return None


def _skip_reason() -> str | None:
    reason = _environment_reason()
    if reason is not None:
        return reason
    if _port_busy():
        return f"port {PORT} is already in use"
    return None


def _make_cert(directory: Path) -> tuple[Path, Path] | None:
    """Generate a throwaway self-signed cert with openssl, None when unavailable."""
    openssl = shutil.which("openssl")
    if openssl is None:
        return None

    key = directory / "key.pem"
    cert = directory / "cert.pem"
    command = [
        openssl,
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(key),
        "-out",
        str(cert),
        "-days",
        "1",
        "-subj",
        "/CN=localhost",
    ]
    result = subprocess.run(command, capture_output=True, check=False)  # noqa: S603
    if result.returncode != 0 or not key.is_file() or not cert.is_file():
        return None

    return key, cert


def _http(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
    ssl_context: ssl.SSLContext | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    merged = dict(headers or {})
    if data is not None:
        merged.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=merged, method=method)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as response:  # noqa: S310
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers.items())


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
    ssl_context: ssl.SSLContext | None = None,
) -> tuple[int, Any]:
    status, body, _ = _http(
        url,
        method=method,
        payload=payload,
        headers=headers,
        timeout=timeout,
        ssl_context=ssl_context,
    )
    return status, json.loads(body) if body else None


@dataclass
class ComfyServer:
    base_dir: Path
    process: subprocess.Popen[bytes]
    log_path: Path
    url: str = f"http://127.0.0.1:{PORT}"
    ssl_context: ssl.SSLContext | None = None

    @property
    def user_root(self) -> Path:
        return self.base_dir / "user" / "default"

    @property
    def netloc(self) -> str:
        return urllib.parse.urlsplit(self.url).netloc

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> tuple[int, bytes, dict[str, str]]:
        return _http(
            f"{self.url}{path}",
            method=method,
            payload=payload,
            headers=headers,
            timeout=timeout,
            ssl_context=self.ssl_context,
        )

    def json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> tuple[int, Any]:
        status, body, _ = self.request(
            method, path, payload=payload, headers=headers, timeout=timeout
        )
        return status, json.loads(body) if body else None

    def export_workflow(
        self,
        source: str,
        prompt: dict[str, Any],
        *,
        saved_at: float = 0.0,
    ) -> dict[str, Any]:
        """Write the source under the user root, then export it through /upai."""
        path = self.user_root / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prompt), encoding="utf-8")
        status, body = self.json(
            "POST",
            "/upai/internal/export",
            payload={"source": source, "prompt": prompt, "saved_at": saved_at},
            headers={"Origin": self.url, "Host": self.netloc},
        )
        if status != 200:
            raise AssertionError(f"export rejected with {status}: {body}")
        return cast(dict[str, Any], body)

    def wait_job(self, polling_url: str, *, timeout: float = JOB_TIMEOUT_SEC) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            status, body = self.json("GET", polling_url)
            if (
                status == 200
                and isinstance(body, dict)
                and body.get("status") in ("completed", "failed", "cancelled")
            ):
                return cast(dict[str, Any], body)
            if time.monotonic() >= deadline:
                raise AssertionError(f"job {polling_url} did not finish: {status} {body}")
            time.sleep(0.1)

    def content(self, path: str) -> bytes:
        status, body, _ = self.request("GET", path)
        if status != 200:
            raise AssertionError(f"content {path} returned {status}")
        return body

    def active_jobs(self) -> list[dict[str, Any]]:
        status, body = _request_json(
            f"{self.url}/api/jobs?status=pending,in_progress",
            ssl_context=self.ssl_context,
        )
        if status != 200 or not isinstance(body, dict):
            return []
        jobs = body.get("jobs")
        return [cast(dict[str, Any], item) for item in jobs] if isinstance(jobs, list) else []

    def history_records(self) -> dict[str, Any]:
        status, body = _request_json(f"{self.url}/history", ssl_context=self.ssl_context)
        if status != 200 or not isinstance(body, dict):
            return {}
        return cast(dict[str, Any], body)

    def object_info(self) -> dict[str, Any]:
        status, body = _request_json(
            f"{self.url}/object_info", timeout=30.0, ssl_context=self.ssl_context
        )
        if status != 200:
            raise AssertionError(f"object_info returned {status}: {body}")
        return cast(dict[str, Any], body)

    def submit(self, prompt: dict[str, Any], targets: list[str]) -> str:
        prompt_id = str(uuid.uuid4())
        payload = {
            "prompt": prompt,
            "client_id": "upai-e2e",
            "prompt_id": prompt_id,
            "partial_execution_targets": targets,
        }
        status, body = _request_json(
            f"{self.url}/prompt", method="POST", payload=payload, ssl_context=self.ssl_context
        )
        if status != 200:
            raise AssertionError(f"prompt rejected with {status}: {body}")
        return prompt_id

    def history(self, prompt_id: str) -> dict[str, Any] | None:
        status, body = _request_json(
            f"{self.url}/history/{prompt_id}", ssl_context=self.ssl_context
        )
        if status != 200 or not isinstance(body, dict):
            return None
        record = body.get(prompt_id)
        return cast(dict[str, Any], record) if isinstance(record, dict) else None

    def wait_history(self, prompt_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + JOB_TIMEOUT_SEC
        while True:
            record = self.history(prompt_id)
            if record is not None:
                return record
            if time.monotonic() >= deadline:
                raise AssertionError(f"prompt {prompt_id} did not finish")
            time.sleep(0.1)

    def view(self, saved: dict[str, Any]) -> bytes:
        query = urllib.parse.urlencode(
            {
                "filename": saved["filename"],
                "subfolder": saved.get("subfolder", ""),
                "type": saved.get("type", "temp"),
            }
        )
        with urllib.request.urlopen(f"{self.url}/view?{query}", timeout=30.0) as response:  # noqa: S310
            return response.read()

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=SHUTDOWN_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=SHUTDOWN_TIMEOUT_SEC)

    def log_tail(self, lines: int = 40) -> str:
        if not self.log_path.is_file():
            return ""
        return "\n".join(
            self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        )


def _wait_ready(server: ComfyServer) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if server.process.poll() is not None:
            raise AssertionError(
                f"ComfyUI exited with {server.process.returncode}\n{server.log_tail()}"
            )
        try:
            status, _ = _request_json(
                f"{server.url}/object_info", timeout=2.0, ssl_context=server.ssl_context
            )
        except (OSError, ValueError):
            status = 0
        if status == 200:
            return
        time.sleep(0.25)
    raise AssertionError(f"ComfyUI did not start in {STARTUP_TIMEOUT_SEC}s\n{server.log_tail()}")


def _launch(
    *,
    python: Path,
    comfy_dir: Path,
    base_dir: Path,
    port: int,
    extra_args: tuple[str, ...] = (),
    ssl_context: ssl.SSLContext | None = None,
) -> ComfyServer:
    """Start one ComfyUI process with the pack linked into custom_nodes."""
    custom_nodes = base_dir / "custom_nodes"
    custom_nodes.mkdir()
    (custom_nodes / "unplatform-ai-provider-node").symlink_to(ROOT, target_is_directory=True)
    fail_node = ROOT / "tests" / "e2e" / "fail_node"
    if fail_node.is_dir():
        (custom_nodes / "upai-e2e-fail-node").symlink_to(fail_node, target_is_directory=True)
    input_dir = base_dir / "input"
    input_dir.mkdir()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(input_dir / FRAME_NAME)

    log_path = base_dir / "comfy.log"
    command = [
        str(python),
        "main.py",
        "--port",
        str(port),
        "--disable-auto-launch",
        "--cpu",
        "--base-directory",
        str(base_dir),
        *extra_args,
    ]
    with log_path.open("wb") as log:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=comfy_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    scheme = "https" if ssl_context is not None else "http"
    server = ComfyServer(
        base_dir=base_dir,
        process=process,
        log_path=log_path,
        url=f"{scheme}://127.0.0.1:{port}",
        ssl_context=ssl_context,
    )
    _wait_ready(server)
    return server


@pytest.fixture(scope="session")
def comfy_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ComfyServer]:
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason, allow_module_level=False)

    comfy_dir = Path(os.environ["UPAI_COMFY_DIR"])
    python = _python(comfy_dir)
    assert python is not None

    base_dir = tmp_path_factory.mktemp("comfy-base")
    server = _launch(python=python, comfy_dir=comfy_dir, base_dir=base_dir, port=PORT)
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(scope="session")
def tls_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ComfyServer]:
    reason = _environment_reason()
    if reason is not None:
        pytest.skip(reason, allow_module_level=False)

    comfy_dir = Path(os.environ["UPAI_COMFY_DIR"])
    python = _python(comfy_dir)
    assert python is not None

    cert_dir = tmp_path_factory.mktemp("comfy-tls-cert")
    pair = _make_cert(cert_dir)
    if pair is None:
        pytest.skip("openssl is not available for a self-signed cert", allow_module_level=False)
    assert pair is not None
    key, cert = pair

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    port = _free_port()
    base_dir = tmp_path_factory.mktemp("comfy-tls-base")
    server = _launch(
        python=python,
        comfy_dir=comfy_dir,
        base_dir=base_dir,
        port=port,
        extra_args=("--tls-keyfile", str(key), "--tls-certfile", str(cert)),
        ssl_context=context,
    )
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture(scope="session")
def api_workflows() -> dict[str, dict[str, Any]]:
    workflows: dict[str, dict[str, Any]] = {}
    for path in sorted(WORKFLOW_DIR.glob("*.json")):
        workflows[path.stem] = cast(
            dict[str, Any],
            json.loads(path.read_text(encoding="utf-8")),
        )
    return workflows
