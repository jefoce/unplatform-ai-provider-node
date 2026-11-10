"""Crop, round, shadow and pad the workflow screenshots under docs/images.

Dev-only: needs Pillow. Sources live in docs/images/src/shots, the processed
PNGs land in docs/images. Deterministic, so reruns stay byte identical.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import cast

from PIL import Image, ImageChops, ImageDraw, ImageFilter

LOGGER = logging.getLogger("make_shots")

IMAGES_DIR = Path(__file__).resolve().parent.parent / "docs" / "images"
SOURCE_DIR = IMAGES_DIR / "src" / "shots"
SLUGS = (
    "flux-2-klein",
    "ideogram-4",
    "krea-2",
    "ltx-2-5",
    "minimax-h3",
    "moss-image",
    "qwen-2-1",
    "wan-2-2",
    "z-image",
)
CONTENT_WIDTH = 1600
CROP_MARGIN = 48
BG_DIFF_THRESHOLD = 64  # clears the 1 px frame and canvas grid, keeps node text
RADIUS = 16
PAD = 40
SHADOW_OFFSET = (0, 8)
SHADOW_BLUR = 24
SHADOW_ALPHA = 70


def _node_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of pixels that differ from the most common color."""
    colors = image.getcolors(maxcolors=image.width * image.height)
    if colors is None:
        raise SystemExit("too many colors to find the background")

    background = cast(
        tuple[int, int, int],
        max(colors, key=lambda item: (item[0], item[1]))[1],
    )
    diff = ImageChops.difference(image, Image.new("RGB", image.size, background))
    red, green, blue = diff.split()
    max_diff = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    mask = max_diff.point([255 if value > BG_DIFF_THRESHOLD else 0 for value in range(256)])
    bbox = mask.getbbox()
    if bbox is None:
        raise SystemExit("no node pixels found")
    return bbox


def _crop(image: Image.Image) -> Image.Image:
    left, top, right, bottom = _node_bbox(image)
    box = (
        max(left - CROP_MARGIN, 0),
        max(top - CROP_MARGIN, 0),
        min(right + CROP_MARGIN, image.width),
        min(bottom + CROP_MARGIN, image.height),
    )
    return image.crop(box)


def _rounded_mask(size: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), RADIUS, fill=255)
    return mask


def _shadow_mask(size: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", size, 0)
    x = PAD + SHADOW_OFFSET[0]
    y = PAD + SHADOW_OFFSET[1]
    ImageDraw.Draw(mask).rounded_rectangle(
        (x, y, x + size[0] - 2 * PAD - 1, y + size[1] - 2 * PAD - 1),
        RADIUS,
        fill=SHADOW_ALPHA,
    )
    return mask.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))


def render(source: Path, destination: Path) -> tuple[tuple[int, int], tuple[int, int]]:
    """Process one screenshot, return its crop and output size."""
    cropped = _crop(Image.open(source).convert("RGB"))
    height = round(cropped.height * CONTENT_WIDTH / cropped.width)
    content = cropped.resize((CONTENT_WIDTH, height), Image.Resampling.LANCZOS)
    content_size = content.size

    canvas = Image.new("RGBA", (content_size[0] + 2 * PAD, content_size[1] + 2 * PAD), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.putalpha(_shadow_mask(canvas.size))
    canvas = Image.alpha_composite(canvas, shadow)

    content.putalpha(_rounded_mask(content_size))
    canvas.paste(content, (PAD, PAD), content)

    canvas.save(destination, format="PNG", optimize=True)
    return cropped.size, canvas.size


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", action="append", choices=SLUGS, help="limit to one slug")
    args = parser.parse_args()

    for slug in args.slug or SLUGS:
        source = SOURCE_DIR / f"{slug}-workflow.png"
        destination = IMAGES_DIR / f"{slug}-workflow.png"
        crop_size, output_size = render(source, destination)
        LOGGER.info(
            "%s crop %dx%d output %dx%d",
            destination.name,
            crop_size[0],
            crop_size[1],
            output_size[0],
            output_size[1],
        )


if __name__ == "__main__":
    main()
