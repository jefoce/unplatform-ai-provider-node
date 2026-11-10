"""Build the client-facing content URLs for a finished job."""


def content_urls(base_url: str, *, job_id: str, kind: str, count: int) -> tuple[str, ...]:
    """Return content URLs for one job, video first frame or image batch."""
    base = base_url.rstrip("/")
    if kind == "video":
        return (f"{base}/upai/api/v1/videos/{job_id}/content?index=0",)

    return tuple(
        f"{base}/upai/api/v1/images/jobs/{job_id}/content?index={index}"
        for index in range(max(1, count))
    )
