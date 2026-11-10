"""Image request validation. No ComfyUI imports."""

from .protocol import ImageJobRequest, Model, ProtocolError
from .validation import (
    check_references,
    validate_negative_prompt,
    validate_prompt,
    validate_resolution_and_aspect,
    validate_seed,
)


def validate_image(request: ImageJobRequest, model: Model) -> int:
    """Validate an image request and return the requested count."""
    capabilities = model.capabilities
    validate_prompt(request.prompt, capabilities)
    validate_negative_prompt(request.negative_prompt, capabilities)
    validate_seed(request.seed, capabilities)
    validate_resolution_and_aspect(
        capabilities,
        resolution=request.resolution,
        aspect_ratio=request.aspect_ratio,
    )

    count = 1 if request.n is None else request.n
    max_count = capabilities.count.max if capabilities.count is not None else 1
    if count < 1 or count > max_count:
        raise ProtocolError(
            "invalid_request",
            f"n must be between 1 and {max_count}",
            details={"field": "n"},
        )

    check_references(request.input_references, capabilities)

    return count
