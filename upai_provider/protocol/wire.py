"""Explicit wire serializers. Only response shapes leave the pack."""

from collections.abc import Mapping

from .capabilities import Capabilities
from .shapes import (
    CreateJobResponse,
    Health,
    Job,
    JobProgress,
    Model,
    SyncImageResponse,
    Upload,
)


def capabilities_to_wire(capabilities: Capabilities) -> dict[str, object]:
    prompt: dict[str, object] = {
        "required": capabilities.prompt.required,
        "max_chars": capabilities.prompt.max_chars,
    }
    if capabilities.prompt.reference_label is not None:
        prompt["reference_label"] = capabilities.prompt.reference_label
    if capabilities.prompt.reference_labels:
        prompt["reference_labels"] = dict(capabilities.prompt.reference_labels)

    data: dict[str, object] = {
        "prompt": prompt,
        "negative_prompt": capabilities.negative_prompt,
        "references": {
            "image": {
                "max": capabilities.references.image.max,
                "required": capabilities.references.image.required,
            },
            "video": {
                "max": capabilities.references.video.max,
                "required": capabilities.references.video.required,
            },
            "audio": {
                "max": capabilities.references.audio.max,
                "required": capabilities.references.audio.required,
            },
        },
        "resolutions": list(capabilities.resolutions),
        "default_resolution": capabilities.default_resolution,
        "aspect_ratios": list(capabilities.aspect_ratios),
        "default_aspect_ratio": capabilities.default_aspect_ratio,
        "sizes": {key: dict(value) for key, value in capabilities.sizes.items()},
        "seed": capabilities.seed,
        "reference_limits": {
            "image": {
                "max_bytes": capabilities.reference_limits.image.max_bytes,
                "formats": list(capabilities.reference_limits.image.formats),
            }
        },
    }

    if capabilities.frames is not None:
        data["frames"] = {
            "start": capabilities.frames.start,
            "end": capabilities.frames.end,
            "start_required": capabilities.frames.start_required,
            "end_required": capabilities.frames.end_required,
        }

    if capabilities.duration is not None:
        data["duration"] = {
            "min": capabilities.duration.min,
            "max": capabilities.duration.max,
            "default": capabilities.duration.default,
            "step": capabilities.duration.step,
        }

    if capabilities.fps is not None:
        data["fps"] = capabilities.fps

    if capabilities.frame_rule is not None:
        data["frame_rule"] = {
            "mod": capabilities.frame_rule.mod,
            "add": capabilities.frame_rule.add,
        }

    if capabilities.audio_output is not None:
        data["audio_output"] = capabilities.audio_output

    if capabilities.count is not None:
        data["count"] = {"max": capabilities.count.max}

    return data


def _model_to_wire(model: Model) -> dict[str, object]:
    data: dict[str, object] = {
        "id": model.id,
        "name": model.name,
        "description": model.description,
        "kind": model.kind,
        "status": model.status,
        "status_reason": model.status_reason,
        "updated_at": model.updated_at,
        "pricing": {"per_run_usd": model.pricing.per_run_usd},
        "capabilities": capabilities_to_wire(model.capabilities),
    }
    if model.workflow is not None:
        data["workflow"] = {"id": model.workflow.id, "name": model.workflow.name}

    return data


def _progress_to_wire(progress: JobProgress | None) -> dict[str, object] | None:
    if progress is None:
        return None

    return {
        "percent": progress.percent,
        "node": progress.node,
        "value": progress.value,
        "max": progress.max,
        "queue_position": progress.queue_position,
        "waiting_on": progress.waiting_on,
    }


def health_to_wire(health: Health) -> dict[str, object]:
    """Serialize GET /health."""
    return {
        "protocol": health.protocol,
        "server": health.server,
        "server_version": health.server_version,
        "implementation": health.implementation,
        "implementation_version": health.implementation_version,
        "auth_required": health.auth_required,
        "lan_allowed": health.lan_allowed,
        "max_upload_bytes": health.max_upload_bytes,
        "upload_quota_bytes": health.upload_quota_bytes,
        "instance_id": health.instance_id,
        "max_running": health.max_running,
        "max_pending": health.max_pending,
        "max_inline_bytes": health.max_inline_bytes,
        "disk_free_bytes": health.disk_free_bytes,
        "result_delete": health.result_delete,
    }


def models_to_wire(models: tuple[Model, ...]) -> dict[str, object]:
    """Serialize a model list envelope."""
    return {"data": [_model_to_wire(model) for model in models]}


def job_to_wire(job: Job) -> dict[str, object]:
    """Serialize a job. Internal file paths stay out of the wire."""
    return {
        "id": job.id,
        "kind": job.kind,
        "model": job.model,
        "status": job.status,
        "progress": _progress_to_wire(job.progress),
        "seed": job.seed,
        "urls": list(job.urls) if job.urls is not None else None,
        "error": job.error,
        "usage": {"cost": job.usage_cost},
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "expires_at": job.expires_at,
    }


def create_job_to_wire(response: CreateJobResponse) -> dict[str, object]:
    """Serialize a create-job response."""
    return {
        "id": response.id,
        "status": response.status,
        "polling_url": response.polling_url,
    }


def upload_to_wire(upload: Upload) -> dict[str, object]:
    """Serialize an upload record."""
    return {
        "sha256": upload.sha256,
        "ref": upload.ref,
        "size": upload.size,
        "content_type": upload.content_type,
        "filename": upload.filename,
    }


def sync_images_to_wire(response: SyncImageResponse) -> dict[str, object]:
    """Serialize a synchronous image response."""
    data: list[dict[str, object]] = [
        {"b64_json": item.b64_json, "media_type": item.media_type} for item in response.data
    ]
    return {"data": data, "usage": {"cost": response.usage_cost}}


def error_to_wire(code: str, message: str, details: Mapping[str, object]) -> dict[str, object]:
    """Serialize the shared error envelope."""
    return {"error": {"code": code, "message": message, "details": dict(details)}}
