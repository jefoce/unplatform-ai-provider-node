"""Generated media assets for the mock driver."""

import asyncio
import contextlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import av
from av.error import FFmpegError
from PIL import Image

from .encoder import select_encoder
from .fileutil import replace_file

_ASSET_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class MockAssets:
    png: Path
    mp4: Path


def _mock_pixels() -> list[tuple[int, int, int]]:
    return [(x * 4 % 256, y * 4 % 256, (x + y) * 2 % 256) for y in range(64) for x in range(64)]


def _write_mp4(path: Path, pixels: list[tuple[int, int, int]]) -> None:
    image = Image.new("RGB", (64, 64))
    image.putdata(pixels)
    container = av.open(str(path), mode="w")
    try:
        stream = cast(Any, container.add_stream(select_encoder(), rate=16))
        stream.width = 64
        stream.height = 64
        stream.pix_fmt = "yuv420p"
        for index in range(16):
            frame = av.VideoFrame.from_image(image)
            frame.pts = index
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()


def _is_valid_png(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
    except (OSError, ValueError):
        return False

    return True


def _is_valid_mp4(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        with av.open(str(path)) as container:
            return bool(container.streams.video)
    except (OSError, ValueError, FFmpegError):
        return False


def _is_valid(assets_dir: Path) -> bool:
    return _is_valid_png(assets_dir / "mock.png") and _is_valid_mp4(assets_dir / "mock.mp4")


def _temp_path(assets_dir: Path, suffix: str) -> Path:
    handle, name = tempfile.mkstemp(dir=assets_dir, prefix=".mock-", suffix=suffix)
    os.close(handle)
    return Path(name)


def _generate_assets(assets_dir: Path, png: Path, mp4: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    pixels = _mock_pixels()
    image = Image.new("RGB", (64, 64))
    image.putdata(pixels)
    temp_png = _temp_path(assets_dir, ".png")
    temp_mp4 = _temp_path(assets_dir, ".mp4")
    try:
        image.save(temp_png, format="PNG")
        _write_mp4(temp_mp4, pixels)
        replace_file(temp_png, png)
        replace_file(temp_mp4, mp4)
    finally:
        for path in (temp_png, temp_mp4):
            with contextlib.suppress(FileNotFoundError):
                os.unlink(path)


async def ensure_mock_assets(root: Path) -> MockAssets:
    """Generate the mock PNG and MP4 once under root/assets."""
    assets_dir = root / "assets"
    png = assets_dir / "mock.png"
    mp4 = assets_dir / "mock.mp4"
    if await asyncio.to_thread(_is_valid, assets_dir):
        return MockAssets(png, mp4)

    async with _ASSET_LOCK:
        if await asyncio.to_thread(_is_valid, assets_dir):
            return MockAssets(png, mp4)

        await asyncio.to_thread(_generate_assets, assets_dir, png, mp4)

    return MockAssets(png, mp4)
