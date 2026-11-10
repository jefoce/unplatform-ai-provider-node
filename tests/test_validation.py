"""Capability validation tests for image and video requests."""

import base64
import io
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from upai_provider.media_sniff import detect_image_format, normalize_image_format
from upai_provider.mock import image_models, video_models
from upai_provider.protocol import (
    FrameImage,
    ImageJobRequest,
    InputReference,
    Model,
    ProtocolError,
    ReferenceCapability,
    ReferenceLimit,
    ReferencesCapability,
    Upload,
    VideoJobRequest,
)
from upai_provider.uploads import UploadStore
from upai_provider.validation import check_image_reference_limits, check_references
from upai_provider.validation_image import validate_image
from upai_provider.validation_video import validate_video

_UPLOAD = f"upai-upload:{'a' * 64}"
_DATA = "data:image/png;base64,AAAA"
_FRAMES = (
    FrameImage("first_frame", _DATA, 1),
    FrameImage("last_frame", _DATA, 1),
)


def _video_model() -> Model:
    model = video_models()[0]
    capabilities = model.capabilities
    frames = capabilities.frames
    assert frames is not None

    references = ReferencesCapability(
        image=capabilities.references.image,
        video=ReferenceCapability(1, 1),
        audio=ReferenceCapability(1, 0),
    )
    return replace(
        model,
        capabilities=replace(
            capabilities,
            references=references,
            frames=replace(frames, end=True, end_required=True),
        ),
    )


def _image_model(*, image_required: int = 0) -> Model:
    model = image_models()[0]
    capabilities = model.capabilities
    references = replace(
        capabilities.references,
        image=ReferenceCapability(capabilities.references.image.max, image_required),
    )
    return replace(model, capabilities=replace(capabilities, references=references))


def _video_request(
    *,
    frame_images: tuple[FrameImage, ...] = (),
    input_references: tuple[InputReference, ...] = (),
) -> VideoJobRequest:
    return VideoJobRequest(
        model="wan22-i2v",
        prompt="x",
        frame_images=frame_images,
        input_references=input_references,
    )


def test_check_references_checks_every_kind() -> None:
    capabilities = _image_model().capabilities
    check_references((), capabilities)

    with pytest.raises(ProtocolError) as caught:
        check_references((InputReference("video", _UPLOAD, 1),), capabilities)

    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "input_references"


def test_video_allows_configured_reference_kinds() -> None:
    request = _video_request(
        frame_images=_FRAMES,
        input_references=(
            InputReference("video", _UPLOAD, 1),
            InputReference("audio", _UPLOAD, 1),
        ),
    )

    validate_video(request, _video_model())


def test_video_requires_configured_reference_kind() -> None:
    request = _video_request(frame_images=_FRAMES)

    with pytest.raises(ProtocolError) as caught:
        validate_video(request, _video_model())

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "input_references"


def test_video_end_required_needs_last_frame() -> None:
    request = _video_request(
        frame_images=(_FRAMES[0],),
        input_references=(InputReference("video", _UPLOAD, 1),),
    )

    with pytest.raises(ProtocolError) as caught:
        validate_video(request, _video_model())

    assert caught.value.status == 400
    assert caught.value.details["field"] == "frame_images"


def test_image_requires_configured_image_reference() -> None:
    request = ImageJobRequest(model="sdxl-image", prompt="x")

    with pytest.raises(ProtocolError) as caught:
        validate_image(request, _image_model(image_required=1))

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "input_references"


def test_image_rejects_video_reference() -> None:
    request = ImageJobRequest(
        model="sdxl-image",
        prompt="x",
        input_references=(InputReference("video", _UPLOAD, 1),),
    )

    with pytest.raises(ProtocolError) as caught:
        validate_image(request, _image_model())

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "input_references"


def test_image_rejects_unsupported_resolution() -> None:
    request = ImageJobRequest(model="sdxl-image", prompt="x", resolution="1080p")

    with pytest.raises(ProtocolError) as caught:
        validate_image(request, _image_model())

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "resolution"


def test_image_rejects_unsupported_aspect_ratio() -> None:
    request = ImageJobRequest(model="sdxl-image", prompt="x", aspect_ratio="7:3")

    with pytest.raises(ProtocolError) as caught:
        validate_image(request, _image_model())

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "aspect_ratio"


def test_image_accepts_configured_resolution_and_aspect() -> None:
    request = ImageJobRequest(
        model="sdxl-image",
        prompt="x",
        resolution="1K",
        aspect_ratio="16:9",
    )

    assert validate_image(request, _image_model()) == 1


def test_image_rejects_seed_when_model_disables_seed() -> None:
    model = _image_model()
    model = replace(model, capabilities=replace(model.capabilities, seed=False))
    request = ImageJobRequest(model="sdxl-image", prompt="x", seed=7)

    with pytest.raises(ProtocolError) as caught:
        validate_image(request, model)

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "seed"


def test_image_accepts_omitted_seed_when_model_disables_seed() -> None:
    model = _image_model()
    model = replace(model, capabilities=replace(model.capabilities, seed=False))

    assert validate_image(ImageJobRequest(model="sdxl-image", prompt="x"), model) == 1


def test_image_rejects_negative_prompt_when_unsupported() -> None:
    request = ImageJobRequest(model="sdxl-image", prompt="x", negative_prompt="blurry")

    with pytest.raises(ProtocolError) as caught:
        validate_image(request, _image_model())

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "negative_prompt"


def test_image_accepts_empty_negative_prompt_when_unsupported() -> None:
    request = ImageJobRequest(model="sdxl-image", prompt="x", negative_prompt="")

    assert validate_image(request, _image_model()) == 1


def test_image_accepts_negative_prompt_when_supported() -> None:
    model = _image_model()
    model = replace(model, capabilities=replace(model.capabilities, negative_prompt=True))
    request = ImageJobRequest(model="sdxl-image", prompt="x", negative_prompt="blurry")

    assert validate_image(request, model) == 1


def test_video_rejects_negative_prompt_when_unsupported() -> None:
    request = VideoJobRequest(model="wan22-t2v", prompt="x", negative_prompt="blurry")

    with pytest.raises(ProtocolError) as caught:
        validate_video(request, video_models()[1])

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "negative_prompt"


def test_video_rejects_seed_when_model_disables_seed() -> None:
    model = video_models()[1]
    model = replace(model, capabilities=replace(model.capabilities, seed=False))
    request = VideoJobRequest(model="wan22-t2v", prompt="x", seed=7)

    with pytest.raises(ProtocolError) as caught:
        validate_video(request, model)

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "seed"


def _image_bytes(image_format: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (0, 128, 0)).save(buffer, format=image_format)
    return buffer.getvalue()


def _data_url(data: bytes, media_type: str = "image/png") -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


class _EmptyUploads:
    def head(self, sha256: str) -> Upload | None:
        return None

    async def head_async(self, sha256: str) -> Upload | None:
        return None

    def path(self, sha256: str) -> Path | None:
        return None


class _RecordingUploads(_EmptyUploads):
    def __init__(self) -> None:
        self.head_awaited = False

    async def head_async(self, sha256: str) -> Upload | None:
        self.head_awaited = True
        return None


_LIMIT = ReferenceLimit(max_bytes=1024, formats=("png", "jpg", "webp"))


@pytest.mark.parametrize(
    ("image_format", "expected"),
    [("PNG", "png"), ("JPEG", "jpeg"), ("WEBP", "webp")],
)
def test_detect_image_format_by_magic_bytes(image_format: str, expected: str) -> None:
    assert detect_image_format(_image_bytes(image_format)) == expected


def test_detect_image_format_rejects_unknown_bytes() -> None:
    assert detect_image_format(b"GIF89a") is None


def test_jpg_and_jpeg_normalize_to_jpeg() -> None:
    assert normalize_image_format("jpg") == "jpeg"
    assert normalize_image_format("jpeg") == "jpeg"


async def test_data_reference_uses_decoded_bytes_not_declared_mime() -> None:
    reference = InputReference("image", _data_url(_image_bytes("PNG"), "image/gif"), 1)

    await check_image_reference_limits(
        references=(reference,),
        frames=(),
        limit=_LIMIT,
        uploads=_EmptyUploads(),
    )


async def test_data_reference_rejects_wrong_magic_bytes() -> None:
    reference = InputReference("image", _data_url(_image_bytes("GIF"), "image/png"), 1)

    with pytest.raises(ProtocolError) as caught:
        await check_image_reference_limits(
            references=(reference,),
            frames=(),
            limit=_LIMIT,
            uploads=_EmptyUploads(),
        )

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "input_references"


async def test_data_reference_over_max_bytes_rejected() -> None:
    reference = InputReference("image", _data_url(_image_bytes("PNG")), 1)
    limit = ReferenceLimit(max_bytes=8, formats=("png",))

    with pytest.raises(ProtocolError) as caught:
        await check_image_reference_limits(
            references=(reference,),
            frames=(),
            limit=limit,
            uploads=_EmptyUploads(),
        )

    assert caught.value.status == 413
    assert caught.value.code == "too_large"
    assert caught.value.details["field"] == "input_references"


async def test_upload_reference_checks_stored_bytes(tmp_path: Path) -> None:
    store = UploadStore(tmp_path / "uploads", max_bytes=1024 * 1024, clock=lambda: 0.0)
    stored = await store.save("frame.png", "image/png", _image_bytes("GIF"))
    reference = InputReference("image", stored.ref, 1)

    with pytest.raises(ProtocolError) as caught:
        await check_image_reference_limits(
            references=(reference,),
            frames=(),
            limit=_LIMIT,
            uploads=store,
        )

    assert caught.value.status == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "input_references"


async def test_upload_reference_uses_async_head() -> None:
    uploads = _RecordingUploads()
    reference = InputReference("image", _UPLOAD, 1)

    with pytest.raises(ProtocolError) as caught:
        await check_image_reference_limits(
            references=(reference,),
            frames=(),
            limit=_LIMIT,
            uploads=uploads,
        )

    assert caught.value.code == "upload_not_found"
    assert uploads.head_awaited is True


async def test_frame_image_reference_is_checked() -> None:
    frame = FrameImage("first_frame", _data_url(_image_bytes("GIF"), "image/png"), 1)

    with pytest.raises(ProtocolError) as caught:
        await check_image_reference_limits(
            references=(),
            frames=(frame,),
            limit=_LIMIT,
            uploads=_EmptyUploads(),
        )

    assert caught.value.code == "invalid_request"
    assert caught.value.details["field"] == "frame_images"
