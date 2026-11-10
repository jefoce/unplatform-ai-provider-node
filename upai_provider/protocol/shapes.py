"""Frozen dataclasses for protocol requests, responses and stored data."""

from dataclasses import dataclass
from typing import Literal

from .capabilities import Capabilities
from .constants import MAX_RUNNING_DEFAULT, MIN_FREE_DISK_BYTES, RESULTS_QUOTA_BYTES
from .status import JobStatus

MAX_PENDING_DEFAULT = 8
RESULT_TTL_HOURS_DEFAULT = 24.0
SYNC_TIMEOUT_SEC_DEFAULT = 600.0

ModelKind = Literal["video", "image"]
ModelStatus = Literal["ready", "stale", "invalid"]
ReferenceKind = Literal["image", "video", "audio"]
FrameType = Literal["first_frame", "last_frame"]


@dataclass(frozen=True)
class Pricing:
    per_run_usd: float


@dataclass(frozen=True)
class WorkflowRef:
    id: str
    name: str


@dataclass(frozen=True)
class Model:
    id: str
    name: str
    description: str
    kind: ModelKind
    status: ModelStatus
    status_reason: str | None
    updated_at: str
    pricing: Pricing
    capabilities: Capabilities
    workflow: WorkflowRef | None = None


@dataclass(frozen=True)
class JobProgress:
    percent: int
    node: str | None
    value: int | None
    max: int | None
    queue_position: int | None
    waiting_on: str | None = None


@dataclass(frozen=True)
class Job:
    id: str
    kind: ModelKind
    model: str
    status: JobStatus
    progress: JobProgress | None
    seed: int | None
    urls: tuple[str, ...] | None
    error: str | None
    usage_cost: float
    created_at: str
    started_at: str | None
    finished_at: str | None
    expires_at: int | None
    files: tuple[str, ...] = ()
    base_url: str = ""
    sequence: int = 0


@dataclass(frozen=True)
class Health:
    protocol: int
    server: str
    server_version: str
    implementation: str
    implementation_version: str
    auth_required: bool
    lan_allowed: bool
    max_upload_bytes: int
    upload_quota_bytes: int
    instance_id: str = ""
    max_running: int = 0
    max_pending: int = 0
    max_inline_bytes: int = 0
    disk_free_bytes: int = 0
    result_delete: bool = False


@dataclass(frozen=True)
class InputReference:
    kind: ReferenceKind
    url: str
    slot: int


@dataclass(frozen=True)
class FrameImage:
    frame_type: FrameType
    url: str
    slot: int


@dataclass(frozen=True)
class VideoJobRequest:
    model: str
    prompt: str
    negative_prompt: str | None = None
    duration: float | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    seed: int | None = None
    frame_images: tuple[FrameImage, ...] = ()
    input_references: tuple[InputReference, ...] = ()


@dataclass(frozen=True)
class ImageJobRequest:
    model: str
    prompt: str
    negative_prompt: str | None = None
    n: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    seed: int | None = None
    input_references: tuple[InputReference, ...] = ()


@dataclass(frozen=True)
class Upload:
    sha256: str
    ref: str
    size: int
    content_type: str
    filename: str


@dataclass(frozen=True)
class CreateJobResponse:
    id: str
    status: JobStatus
    polling_url: str


@dataclass(frozen=True)
class SyncImageItem:
    b64_json: str
    media_type: str


@dataclass(frozen=True)
class SyncImageResponse:
    data: tuple[SyncImageItem, ...]
    usage_cost: float


@dataclass(frozen=True)
class ModelList:
    data: tuple[Model, ...]


@dataclass(frozen=True)
class RawConfig:
    token: str = ""
    allow_remote: bool = False
    allow_lan: bool = False
    allowed_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    allow_url_fetch: bool = False
    result_ttl_hours: float = RESULT_TTL_HOURS_DEFAULT
    max_pending: int = MAX_PENDING_DEFAULT
    sync_timeout_sec: float = SYNC_TIMEOUT_SEC_DEFAULT
    max_running: int = MAX_RUNNING_DEFAULT
    min_free_disk_bytes: int = MIN_FREE_DISK_BYTES
    results_quota_bytes: int = RESULTS_QUOTA_BYTES
