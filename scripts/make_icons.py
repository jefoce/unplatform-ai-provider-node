#!/usr/bin/env python3
"""Build the 512x512 dark tiles for models, app and ComfyUI. Dev-only, needs Pillow.

Raw logos live in docs/images/src. Rerun after replacing a source.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "images" / "src"
OUT = ROOT / "docs" / "images"

SIZE = 512
SS = 2  # build at 2x, then downsample
INSET = 30 * SS
TILE = SIZE * SS - 2 * INSET
RADIUS = 100 * SS
REGISTRY_SIZE = 400

# Mark fits an 80% box inside the tile, leaving 10% padding per side.
MARK_FRACTION = 0.80

SHADOW_OFFSET = (0, 8 * SS)
SHADOW_BLUR = 14 * SS
SHADOW_ALPHA = 80

DARK = (21, 22, 26)
WHITE = (255, 255, 255)

# Source, background, and mark extraction mode. Mode is auto (alpha when
# present), distance (color vs background), luma (bright glyphs on dark),
# chroma (saturated mark on a drawn checkerboard) or dark (dark glyphs on light).
MARKS: dict[str, tuple[str, tuple[int, int, int] | None, str]] = {
    "flux-2-klein": ("flux-2-klein-raster.png", WHITE, "distance"),
    "ideogram-4": ("ideogram-4-raster.png", (35, 36, 37), "distance"),
    "krea-2": ("krea-2-raster.png", None, "auto"),
    "ltx-2-5": ("ltx-2-5-raster.png", None, "auto"),
    "minimax-h3": ("minimax-official.webp", (245, 245, 245), "distance"),
    "moss-image": ("moss-image-raster.png", WHITE, "distance"),
    "qwen-2-1": ("qwen-zonalogo.webp", None, "dark"),
    "wan-2-2": ("wan-2-2-raster.png", None, "auto"),
    "z-image": ("z-image.png", WHITE, "distance"),
}

# Crop to the region that best fits the tile.
CROPS: dict[str, tuple[int, int, int, int]] = {
    "ideogram-4": (2, 2, 653, 653),
    "minimax-h3": (490, 500, 860, 815),
    "qwen-2-1": (330, 318, 675, 438),
}

# Marks that must render fully opaque, no soft gradient alpha.
SOLID_MARKS = {"wan-2-2"}


def nonzero(value: int) -> int:
    return 255 if value > 0 else 0


def shadow_alpha(value: int) -> int:
    return value * SHADOW_ALPHA // 255


def solid_alpha(value: int) -> int:
    return 255 if value >= 200 else 0


def has_alpha(image: Image.Image) -> bool:
    return any(image.getchannel("A").histogram()[:250])


def rounded_mask(size: int, radius: int) -> Image.Image:
    """Anti-aliased rounded square mask."""
    scale = 4
    big = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(big)
    draw.rounded_rectangle((0, 0, size * scale - 1, size * scale - 1), radius * scale, fill=255)

    return big.resize((size, size), Image.Resampling.LANCZOS)


def extract_mask(
    image: Image.Image,
    bg: tuple[int, int, int] | None,
    mode: str,
) -> tuple[Image.Image, Image.Image]:
    """Return the trimmed silhouette mask and the matching RGB crop."""
    image = image.convert("RGBA")
    alpha = image.getchannel("A")
    transparent = alpha.point(nonzero)

    if mode == "auto" and has_alpha(image):
        mask = alpha
    elif mode == "luma":
        mask = ImageChops.multiply(image.convert("L"), transparent)
        mask = ramp(mask)
    elif mode == "chroma":
        red, green, blue = image.convert("RGB").split()
        high = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        low = ImageChops.darker(ImageChops.darker(red, green), blue)
        mask = ramp(ImageChops.multiply(ImageChops.difference(high, low), transparent))
    elif mode == "dark":
        mask = ImageChops.multiply(image.convert("L").point([255] * 128 + [0] * 128), transparent)
    else:
        if bg is None:
            raise SystemExit("mark has no alpha and no background color")
        diff = ImageChops.difference(image.convert("RGB"), Image.new("RGB", image.size, bg))
        red, green, blue = diff.split()
        distance = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        mask = ramp(ImageChops.multiply(distance, transparent))

    box = mask.getbbox()
    if box is None:
        raise SystemExit("empty mark")

    return mask.crop(box), image.convert("RGB").crop(box)


def ramp(mask: Image.Image) -> Image.Image:
    """Steepen a soft mask so any real color becomes a solid silhouette."""
    lut = [0 if v <= 10 else 255 if v >= 40 else round((v - 10) * 255 / 30) for v in range(256)]

    return mask.point(lut)


def fit(size: tuple[int, int], target: int) -> tuple[int, int]:
    scale = target / max(size)

    return max(1, round(size[0] * scale)), max(1, round(size[1] * scale))


def fill_mark(
    canvas: Image.Image, mask: Image.Image, color: tuple[int, int, int], target: int
) -> None:
    """Resize the silhouette and composite it flat and centered."""
    width, height = fit(mask.size, target)
    resized = mask.resize((width, height), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", (width, height), (*color, 255))
    layer.putalpha(resized)
    canvas.alpha_composite(layer, ((canvas.width - width) // 2, (canvas.height - height) // 2))


def paint_icon(canvas: Image.Image, art: Image.Image, mask: Image.Image, target: int) -> None:
    """Scale the icon into the target box, aspect kept and centered."""
    width, height = fit(mask.size, target)
    resized_mask = mask.resize((width, height), Image.Resampling.LANCZOS)
    layer = art.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
    layer.putalpha(resized_mask)
    canvas.alpha_composite(layer, ((canvas.width - width) // 2, (canvas.height - height) // 2))


def make_tile(
    face: Image.Image,
    *,
    gloss: int,
    overlay: Image.Image | None = None,
) -> Image.Image:
    """Compose shadow, rounded face, an optional clipped overlay and top gloss."""
    canvas = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
    mask = rounded_mask(TILE, RADIUS)

    shadow_mask = mask.point(shadow_alpha)
    shadow = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 255))
    shadow.putalpha(shadow_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    canvas.alpha_composite(shadow, (INSET + SHADOW_OFFSET[0], INSET + SHADOW_OFFSET[1]))

    face = face.convert("RGBA").resize((TILE, TILE), Image.Resampling.LANCZOS)
    face.putalpha(ImageChops.multiply(face.getchannel("A"), mask))
    if overlay is not None:
        face.alpha_composite(overlay)
    canvas.alpha_composite(face, (INSET, INSET))

    if gloss:
        gradient = Image.linear_gradient("L").resize((TILE, TILE), Image.Resampling.LANCZOS)
        lut = [max(0, round(gloss * (1 - (v / 255) / 0.55))) for v in range(256)]
        gloss_mask = ImageChops.multiply(gradient.point(lut), mask)
        gloss_layer = Image.new("RGBA", (TILE, TILE), (*WHITE, 255))
        gloss_layer.putalpha(gloss_mask)
        canvas.alpha_composite(gloss_layer, (INSET, INSET))

    return canvas


def build_model(slug: str, source: tuple[str, tuple[int, int, int] | None, str]) -> None:
    name, bg, mode = source
    image = Image.open(SRC / name)
    if slug in CROPS:
        image = image.crop(CROPS[slug])
    mask, _ = extract_mask(image, bg, mode)
    target = round(TILE * MARK_FRACTION)
    if slug in SOLID_MARKS:
        mask = mask.point(solid_alpha)

    face = Image.new("RGBA", (TILE, TILE), (*DARK, 255))
    canvas = make_tile(face, gloss=30)
    fill_mark(canvas, mask, WHITE, target)
    save(canvas, f"{slug}.png")


def make_icon_tile(
    icon: Image.Image,
    mask: Image.Image | None = None,
    *,
    fraction: float = 1.0,
) -> Image.Image:
    """Draw the tile box, then place the icon in a box of the given fraction, aspect kept."""
    icon = icon.convert("RGBA")
    if mask is None:
        mask = icon.getchannel("A")
        box = mask.getbbox()
        if box is None:
            raise SystemExit("empty icon")
        icon = icon.crop(box)
        mask = mask.crop(box)
    face = Image.new("RGBA", (TILE, TILE), (*DARK, 255))
    canvas = make_tile(face, gloss=30)
    paint_icon(canvas, icon, mask, round(TILE * fraction))

    return canvas


def build_app() -> None:
    image = Image.open(SRC / "app-icon.png").convert("RGBA")
    save(make_icon_tile(image, fraction=0.80), "app.png")


def build_comfyui() -> None:
    image = Image.open(SRC / "comfyui-raster.png")
    mask, rgb = extract_mask(image, WHITE, "distance")
    save(make_icon_tile(rgb, mask, fraction=0.60), "comfyui.png")


def build_registry() -> None:
    image = Image.open(OUT / "app.png")
    image.resize((REGISTRY_SIZE, REGISTRY_SIZE), Image.Resampling.LANCZOS).save(
        OUT / "registry-icon.png", format="PNG", compress_level=9
    )


def save(canvas: Image.Image, name: str) -> None:
    canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS).save(
        OUT / name, format="PNG", compress_level=9
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, source in MARKS.items():
        build_model(slug, source)
    build_app()
    build_comfyui()
    build_registry()


if __name__ == "__main__":
    main()
