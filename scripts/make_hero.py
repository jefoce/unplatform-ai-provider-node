"""Build the dark-only animated hero, stills, loops and social preview.

Dev-only, needs Playwright, ffmpeg and fontTools. Deterministic: fixed strings and
geometry, software rasterization, so reruns give identical SVG, PNG and MP4 bytes.
"""

from __future__ import annotations

import argparse
import base64
import functools
import importlib
import logging
import math
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

LOGGER = logging.getLogger("make_hero")

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"

WIDTH, HEIGHT = 1200, 920
PANEL_Y, PANEL_HEIGHT = 20, 600
STILL_SCALE = 2
VIDEO_WIDTH, VIDEO_HEIGHT = 1920, 1080
SOCIAL_WIDTH, SOCIAL_HEIGHT = 1280, 640
FPS = 60
CUT_SEC = 6.0
ICON_PX = 256

HEADER_TEXT = "Unplatform AI Provider"
HEADER_SIZE = 32
HEADER_WEIGHT = 600
HEADER_X = 56
HEADER_CENTER_Y = 28
HEADER_HEIGHT = 56
HEADER_LIGHT = "#1f2328"
HEADER_DARK = "#f0f6fc"

PANEL = "#0f1113"
ACCENT = "#a8ff3e"
COMFY = "#f2ff59"
CONNECTOR = "#30363d"
SHADOW = "rgba(0, 0, 0, 0.60)"
GHOST_FILL = "#14171a"
GHOST_STROKE = "#262b31"

FG = "#ffffff"
FG2 = "#898a8b"
FG3 = "#626262"
CARD_BG = "#1c1e20"
PICKER_BG = "#23262a"
SEARCH_BG = "#131517"
WHITE_5 = "#ffffff0d"
WHITE_6 = "#ffffff0f"
LINE_STRONG = "#ffffff1a"
LINE_SOFT = "#ffffff0d"

ROW_X = 8
ROW_W = 344
ROW_PAD = 8
BADGE_W, BADGE_H = 40, 24
GROUP_H = 22
ROW_H_VIDEO = 60
ROW_H_IMAGE = 64
ROW_H_PLUS = 44
LIST_Y = 52
LIST_H = 360
SEARCH_X, SEARCH_Y, SEARCH_W, SEARCH_H = 8, 8, 344, 36
CHECK_X = ROW_W - ROW_PAD - 14
SCROLL_EASE = "cubic-bezier(0.25, 0.1, 0.25, 1)"
MAX_HOLD = 2.5 / 1.5

BOOM_EASE = "cubic-bezier(0.2, 0.9, 0.3, 1)"
RETURN_EASE = "cubic-bezier(0.45, 0, 0.25, 1)"
BASE_FILTER = f"drop-shadow(0 8px 14px {SHADOW})"

# Fixed cycle order, then one "+" cycle. No shuffle.
CYCLE_SLUGS = (
    "flux-2-klein",
    "ideogram-4",
    "krea-2",
    "qwen-2-1",
    "moss-image",
    "z-image",
    "ltx-2-5",
    "minimax-h3",
    "wan-2-2",
    None,
)

# Video models run on the diagonal, image models fill the rest in reading order.
# Values are (column, row).
GRID_POS = {
    "ltx-2-5": (0, 0),
    "flux-2-klein": (1, 0),
    "ideogram-4": (2, 0),
    "krea-2": (0, 1),
    "minimax-h3": (1, 1),
    "qwen-2-1": (2, 1),
    "moss-image": (0, 2),
    "z-image": (1, 2),
    "wan-2-2": (2, 2),
}

# Model cells are 512 px tiles with a 30 px transparent margin and 100 px radius.
MODEL_CELL = 96
MARGIN = MODEL_CELL * 30 / 512
TILE = MODEL_CELL - 2 * MARGIN
RADIUS = MODEL_CELL * 100 / 512
GRID_X = (680, 808, 936)
GRID_Y = (112, 272, 432)
APP_X, APP_Y = 80, 260
COMFY_X, COMFY_Y = 440, 260
ICON = 120
ICON_MARGIN = ICON * 30 / 512
ICON_RADIUS = ICON * 100 / 512

CHIP_X, CHIP_Y, CHIP_SIZE = 292, 292, 56
CHIP_CENTER = (320.0, 320.0)
LETTER_SIZE = 26.0

GRID_GAP = GRID_X[1] - GRID_X[0] - MODEL_CELL
PLUS_SIZE = MODEL_CELL * 0.8
PLUS_X = GRID_X[2] + MODEL_CELL + GRID_GAP
PLUS_Y = GRID_Y[1] + (MODEL_CELL - PLUS_SIZE) / 2
ENDPOINT_X, ENDPOINT_Y, ENDPOINT_W, ENDPOINT_H = 120, 85, 400, 110
PICKER_X, PICKER_Y, PICKER_W, PICKER_H = 140, 445, 360, 420

T_U_FIRE = 0.25
T_U_GRAD = 0.40
T_COMFY = 0.65
T_BOOM = 1.0
JOLT_SEC = 0.1
RETURN_SEC = 0.6
T_RIPPLE = 0.3
SCROLL_SEC = 0.55
FADE_SEC = 0.3
FADE_OUT_SEC = 0.12
SELECT_GAP_SEC = 0.15
FADE_IN_SEC = 0.12
CROSSFADE_SEC = 0.4

BASE_CONNECTORS = (
    "M 200 320 L 292 320",
    "M 348 320 L 440 320",
    "M 560 320 C 620 320, 620 160, 680 160",
    "M 776 160 L 808 160",
    "M 904 160 L 936 160",
    "M 560 320 L 680 320",
    "M 776 320 L 808 320",
    "M 904 320 L 936 320",
    "M 1032 320 L 1064 320",
    "M 560 320 C 620 320, 620 480, 680 480",
    "M 776 480 L 808 480",
    "M 904 480 L 936 480",
)


@dataclass(frozen=True)
class Cycle:
    index: int
    start: float
    slug: str | None
    x: float
    y: float
    hold: float
    rows: tuple[str, ...]
    picker: str

    @property
    def boom(self) -> float:
        return self.start + T_BOOM

    @property
    def hold_end(self) -> float:
        return self.boom + self.hold

    @property
    def jolt_peak(self) -> float:
        return self.hold_end + JOLT_SEC / 2

    @property
    def jolt(self) -> float:
        return self.hold_end + JOLT_SEC

    @property
    def end(self) -> float:
        return self.jolt + RETURN_SEC

    @property
    def is_plus(self) -> bool:
        return self.slug is None


@dataclass(frozen=True)
class PickerItem:
    title: str
    description: str = ""
    badges: tuple[tuple[str, str], ...] = ()
    plus: bool = False

    @property
    def height(self) -> int:
        if self.plus:
            return ROW_H_PLUS
        if self.description:
            return ROW_H_IMAGE
        return ROW_H_VIDEO

    @property
    def hold(self) -> float:
        return min(MAX_HOLD, 0.8 + 0.025 * (len(self.title) + len(self.description)))


@dataclass(frozen=True)
class State:
    time: float
    decls: str
    timing: str


@dataclass(frozen=True)
class Selection:
    picker: str
    row: int
    start: float
    end: float
    top: float
    height: int
    plus: bool


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise SystemExit("ffmpeg is required for icon and video output")
    return path


def _downscale(path: Path) -> bytes:
    """Downscale one PNG to ICON_PX with ffmpeg, deterministically."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "icon.png"
        subprocess.run(  # noqa: S603
            [
                _ffmpeg(),
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-vf",
                f"scale={ICON_PX}:{ICON_PX}:flags=lanczos",
                "-pix_fmt",
                "rgba",
                "-map_metadata",
                "-1",
                "-fflags",
                "+bitexact",
                "-flags:v",
                "+bitexact",
                str(out),
            ],
            check=True,
        )
        return out.read_bytes()


@functools.cache
def _data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(_downscale(path)).decode("ascii")


def _cycles() -> list[Cycle]:
    cycles: list[Cycle] = []
    start = 0.0
    for index, slug in enumerate(CYCLE_SLUGS):
        if slug is None:
            picker, rows, x, y = "video", ("Your workflow",), PLUS_X, PLUS_Y
        else:
            picker = "image" if slug in IMAGE_SLUGS else "video"
            rows = WORKFLOW_ROWS[slug]
            col, row = GRID_POS[slug]
            x, y = GRID_X[col], GRID_Y[row]
        hold = sum(PICKER_ITEMS[(picker, title)].hold for title in rows)
        cycle = Cycle(index, start, slug, x, y, hold, rows, picker)
        cycles.append(cycle)
        start = cycle.end
    return cycles


def _cubic_length(
    start: tuple[float, float],
    control_a: tuple[float, float],
    control_b: tuple[float, float],
    end: tuple[float, float],
    steps: int = 48,
) -> float:
    total = 0.0
    prev = start
    for step in range(1, steps + 1):
        t = step / steps
        u = 1 - t
        x = u**3 * start[0] + 3 * u * u * t * control_a[0] + 3 * u * t * t * control_b[0]
        x += t**3 * end[0]
        y = u**3 * start[1] + 3 * u * u * t * control_a[1] + 3 * u * t * t * control_b[1]
        y += t**3 * end[1]
        total += ((x - prev[0]) ** 2 + (y - prev[1]) ** 2) ** 0.5
        prev = (x, y)
    return total


def _forward_geometry(x: float, y: float, *, plus: bool) -> tuple[str, float]:
    if plus:
        return f"M 560 320 L {PLUS_X} 320", PLUS_X - 560
    row = y + MODEL_CELL / 2
    path = f"M 560 320 C 620 320, 620 {row}, 680 {row}"
    length = _cubic_length((560, 320), (620, 320), (620, row), (680, row))
    col = GRID_X.index(int(x))
    if col >= 1:
        path += f" L 776 {row} L 808 {row}"
        length += 128
    if col >= 2:
        path += f" L 904 {row} L 936 {row}"
        length += 128
    return path, length


def _return_geometry(x: float, y: float, *, plus: bool) -> tuple[str, float, float]:
    """Return path, total length and the forward part length."""
    if plus:
        forward, forward_length = _forward_geometry(x, y, plus=True)
        del forward
        reverse = f"M {PLUS_X} 320 L 560 320"
    else:
        row = y + MODEL_CELL / 2
        col = GRID_X.index(int(x))
        line_xs = [680]
        if col >= 1:
            line_xs += [776, 808]
        if col >= 2:
            line_xs += [904, 936]
        forward, forward_length = _forward_geometry(x, y, plus=False)
        del forward
        reverse = f"M {line_xs[-1]} {row}"
        for prev in reversed(line_xs[:-1]):
            reverse += f" L {prev} {row}"
        reverse += f" C 620 {row}, 620 320, 560 320"
    reverse += " L 440 320 L 348 320 L 292 320 L 200 320"
    return reverse, forward_length + 360, forward_length


@functools.lru_cache(maxsize=4)
def _inter(weight: int) -> TTFont:
    font = TTFont(str(IMAGES / "fonts" / "InterVariable.ttf"))
    instantiateVariableFont(font, {"wght": weight}, inplace=True)
    return font


@functools.lru_cache(maxsize=4096)
def _glyph(letter: str, weight: int) -> tuple[str, int, int]:
    """Path data, advance width and units per em for one glyph."""
    font = _inter(weight)
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap() or {}
    name = cmap.get(ord(letter))
    if name is None:
        return "", 0, int(font["head"].unitsPerEm)  # type: ignore[attr-defined]
    glyph = glyph_set[name]
    pen = SVGPathPen(glyph_set)
    glyph.draw(pen)
    return pen.getCommands(), int(font["hmtx"][name][0]), int(font["head"].unitsPerEm)  # type: ignore[attr-defined]


def text_to_path(letter: str, size: float, cx: float, cy: float) -> tuple[str, str]:
    """Convert one glyph to a path and a transform that centers it on cx, cy."""
    font = _inter(700)
    glyph_set = font.getGlyphSet()
    glyph = glyph_set[letter]
    pen = SVGPathPen(glyph_set)
    glyph.draw(pen)
    bounds = BoundsPen(glyph_set)
    glyph.draw(bounds)
    if bounds.bounds is None:
        raise SystemExit(f"empty glyph {letter!r}")
    x_min, y_min, x_max, y_max = bounds.bounds
    units = int(font["head"].unitsPerEm)  # type: ignore[attr-defined]
    scale = size / units
    tx = cx - (x_min + x_max) / 2 * scale
    ty = cy + (y_min + y_max) / 2 * scale
    transform = f"translate({tx:.3f} {ty:.3f}) scale({scale:.6f} -{scale:.6f})"
    return pen.getCommands(), transform


def _text_width(text: str, size: float, weight: int, letter_spacing: float = 0.0) -> float:
    total = 0.0
    for index, letter in enumerate(text):
        _, advance, units = _glyph(letter, weight)
        total += advance * size / units
        if index and letter_spacing:
            total += letter_spacing
    return total


def text_run(
    text: str,
    size: float,
    x: float,
    baseline: float,
    *,
    weight: int = 400,
    color: str = FG2,
    letter_spacing: float = 0.0,
    anchor: str = "start",
    opacity: float | None = None,
) -> tuple[str, float]:
    """Lay out text as SVG paths, returning the fragment and its width."""
    width = _text_width(text, size, weight, letter_spacing)
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    parts: list[str] = []
    cursor = x
    for index, letter in enumerate(text):
        commands, advance, units = _glyph(letter, weight)
        scale = size / units
        if commands:
            parts.append(
                f'<path d="{commands}" transform="translate({cursor:.3f} {baseline:.3f}) '
                f'scale({scale:.6f} -{scale:.6f})"/>'
            )
        cursor += advance * scale
        if index < len(text) - 1:
            cursor += letter_spacing
    attrs = f' fill="{color}"'
    if opacity is not None:
        attrs += f' opacity="{opacity:g}"'
    return f"<g{attrs}>{''.join(parts)}</g>", width


def _header_text_metrics(text: str) -> tuple[float, float]:
    """Baseline that centers the glyph bounds on HEADER_CENTER_Y, plus the rightmost path x."""
    font = _inter(HEADER_WEIGHT)
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap() or {}
    units = int(font["head"].unitsPerEm)  # type: ignore[attr-defined]
    scale = HEADER_SIZE / units
    cursor = float(HEADER_X)
    x_max = float(HEADER_X)
    y_min = float("inf")
    y_max = float("-inf")
    for letter in text:
        name = cmap.get(ord(letter))
        if name is None:
            continue
        glyph = glyph_set[name]
        pen = BoundsPen(glyph_set)
        glyph.draw(pen)
        if pen.bounds is not None:
            _, glyph_min, x1, glyph_max = pen.bounds
            x_max = max(x_max, cursor + x1 * scale)
            y_min = min(y_min, glyph_min)
            y_max = max(y_max, glyph_max)
        cursor += int(font["hmtx"][name][0]) * scale
    baseline = HEADER_CENTER_Y + (y_min + y_max) / 2 * scale
    return baseline, x_max


def _header_icon() -> str:
    """Reuse the icon data URI already embedded in a header SVG."""
    for name in ("header-light.svg", "header-dark.svg"):
        path = IMAGES / name
        if not path.exists():
            continue
        match = re.search(r'href="(data:image/png;base64,[^"]+)"', path.read_text(encoding="utf-8"))
        if match is not None:
            return match.group(1)
    raise SystemExit("header icon not found")


def build_headers() -> tuple[Path, Path]:
    """Write both header SVGs with the wordmark as paths, width from the real path bounds."""
    icon = _header_icon()
    baseline, path_max_x = _header_text_metrics(HEADER_TEXT)
    width = math.ceil(max(48, path_max_x) + 8)
    written: list[Path] = []
    for name, color in (("header-light.svg", HEADER_LIGHT), ("header-dark.svg", HEADER_DARK)):
        text, _ = text_run(
            HEADER_TEXT,
            HEADER_SIZE,
            HEADER_X,
            baseline,
            weight=HEADER_WEIGHT,
            color=color,
        )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{HEADER_HEIGHT}" '
            f'viewBox="0 0 {width} {HEADER_HEIGHT}" role="img" aria-label="{HEADER_TEXT}">\n'
            f'  <image x="0" y="4" width="48" height="48" href="{icon}"/>\n'
            f"  {text}\n"
            "</svg>\n"
        )
        path = IMAGES / name
        path.write_text(svg, encoding="utf-8")
        LOGGER.info("wrote %s %d bytes", name, path.stat().st_size)
        written.append(path)
    return written[0], written[1]


LUCIDE: dict[str, tuple[str, ...]] = {
    "monitor": (
        "M4 3h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z",
        "M8 21h8",
        "M12 17v4",
    ),
    "clock": ("M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20", "M12 6v6l4 2"),
    "speaker": (
        "M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 "
        "0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 "
        "0 0 11 19.298z",
        "M16 9a5 5 0 0 1 0 6",
        "M19.364 18.364a9 9 0 0 0 0-12.728",
    ),
    "check": ("M20 6 9 17l-5-5",),
    "refresh": (
        "M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8",
        "M21 3v5h-5",
        "M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16",
        "M8 16H3v5",
    ),
    "ellipsis": (
        "M12 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0",
        "M19 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0",
        "M5 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0",
    ),
    "plus": ("M5 12h14", "M12 5v14"),
}


ICON_DEFS = "".join(
    f'<g id="ico-{name}">' + "".join(f'<path d="{d}"/>' for d in paths) + "</g>"
    for name, paths in LUCIDE.items()
)


def _icon(name: str, x: float, y: float, size: float, color: str, width: float = 2) -> str:
    scale = size / 24
    return (
        f'<use href="#ico-{name}" transform="translate({x:g} {y:g}) scale({scale:.6f})" '
        f'fill="none" stroke="{color}" stroke-width="{width:g}" stroke-linecap="round" '
        'stroke-linejoin="round"/>'
    )


def _wrap(text: str, width: float, size: float, weight: int) -> list[str]:
    """Greedy wrap, clamped to two lines with a trailing ellipsis."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if not current or _text_width(candidate, size, weight) <= width:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    if len(lines) <= 2:
        return lines
    first = lines[0]
    remainder = text[len(first) :].strip()
    second = ""
    for word in remainder.split():
        candidate = word if not second else f"{second} {word}"
        if _text_width(f"{candidate} …", size, weight) <= width:
            second = candidate
        else:
            break
    return [first, f"{second} …" if second else "…"]


IMAGE_ITEMS: tuple[PickerItem, ...] = (
    PickerItem(
        "FLUX.2 Klein",
        description="Text-to-image and multi-image editing with FLUX.2 Klein 9B distilled.",
    ),
    PickerItem("Ideogram 4", description="Text-to-image with local Ideogram 4 weights."),
    PickerItem("Krea 2", description="Text-to-image and style reference with Krea 2 Turbo."),
    PickerItem("Qwen 2.1", description="Text-to-image and reference LoRA editing."),
    PickerItem("Qwen 2.1 Head Swap", description="Image 1 base, image 2 head."),
    PickerItem("Qwen 2.1 Body Swap", description="Image 1 base, image 2 body."),
    PickerItem("MOSS Image", description="Text-to-image and img2img with MOSS Image."),
    PickerItem("Z-Image", description="Text-to-image and img2img with Z-Image base."),
    PickerItem("Your workflow", plus=True),
)

VIDEO_ITEMS: tuple[PickerItem, ...] = (
    PickerItem(
        "LTX 2.5",
        badges=(("monitor", "720–1080p"), ("clock", "1-5 s"), ("speaker", "")),
    ),
    PickerItem(
        "MiniMax H3",
        badges=(("monitor", "352–1088p"), ("clock", "4-15 s"), ("speaker", "")),
    ),
    PickerItem(
        "MiniMax H3 Fast",
        badges=(("monitor", "352–1088p"), ("clock", "4-15 s"), ("speaker", "")),
    ),
    PickerItem("Wan 2.2", badges=(("monitor", "480–720p"), ("clock", "1-5 s"))),
    PickerItem("Your workflow", plus=True),
)

WORKFLOW_ROWS: dict[str, tuple[str, ...]] = {
    "flux-2-klein": ("FLUX.2 Klein",),
    "ideogram-4": ("Ideogram 4",),
    "krea-2": ("Krea 2",),
    "moss-image": ("MOSS Image",),
    "qwen-2-1": ("Qwen 2.1", "Qwen 2.1 Head Swap", "Qwen 2.1 Body Swap"),
    "z-image": ("Z-Image",),
    "ltx-2-5": ("LTX 2.5",),
    "minimax-h3": ("MiniMax H3", "MiniMax H3 Fast"),
    "wan-2-2": ("Wan 2.2",),
}

IMAGE_SLUGS = frozenset(
    {"flux-2-klein", "ideogram-4", "krea-2", "moss-image", "qwen-2-1", "z-image"}
)

PICKER_ITEMS = {
    (kind, item.title): item
    for kind, items in (("image", IMAGE_ITEMS), ("video", VIDEO_ITEMS))
    for item in items
}
ROW_INDEX = {
    (kind, item.title): index
    for kind, items in (("image", IMAGE_ITEMS), ("video", VIDEO_ITEMS))
    for index, item in enumerate(items)
}

CYCLES = _cycles()
LOOP_SEC = CYCLES[-1].end


def _badge_chip(x: float, y: float, label: str = "NVDA") -> str:
    text, _ = text_run(
        label,
        10,
        x + BADGE_W / 2,
        y + 16,
        weight=500,
        color=FG2,
        letter_spacing=0.6,
        anchor="middle",
    )
    return (
        f'<rect x="{x:g}" y="{y:g}" width="{BADGE_W}" height="{BADGE_H}" rx="6" fill="{WHITE_5}"/>'
        f"{text}"
    )


def _capability_badges(badges: tuple[tuple[str, str], ...], x: float, y: float) -> str:
    parts: list[str] = []
    cursor = x
    for icon_name, label in badges:
        icon_w = 12
        gap = 5 if label else 0
        text_w = _text_width(label, 12, 400) if label else 0
        width = 5 + icon_w + gap + text_w + 5
        parts.append(
            f'<rect x="{cursor:.2f}" y="{y:g}" width="{width:.2f}" height="24" rx="6" '
            f'fill="{WHITE_5}"/>'
        )
        parts.append(_icon(icon_name, cursor + 5, y + 6, 12, FG2))
        if label:
            text, _ = text_run(label, 12, cursor + 5 + icon_w + gap, y + 16, color=FG2)
            parts.append(text)
        cursor += width + 4
    return "".join(parts)


def _row_svg(item: PickerItem, *, top: float) -> str:
    parts = [f'<g transform="translate({ROW_X} {top:.2f})">']
    if item.plus:
        parts.append(
            f'<rect class="plus-row" x="0.5" y="0.5" width="{ROW_W - 1}" '
            f'height="{ROW_H_PLUS - 1}" rx="8" fill="none" stroke="{ACCENT}" '
            'stroke-width="1" stroke-dasharray="4 4" opacity="0.55"/>'
        )
        parts.append(_icon("plus", 16, 14, 16, ACCENT, 1.5))
        title, _ = text_run(item.title, 14, 40, 27, weight=500, color=FG)
        parts.append(title)
    else:
        badge_y = (item.height - BADGE_H) / 2
        parts.append(_badge_chip(ROW_PAD, badge_y))
        content_x = ROW_PAD + BADGE_W + 8
        title, _ = text_run(item.title, 14, content_x, 21, weight=500, color=FG)
        parts.append(title)
        if item.description:
            max_width = CHECK_X - 8 - content_x
            for line_index, line in enumerate(_wrap(item.description, max_width, 12, 400)):
                desc, _ = text_run(line, 12, content_x, 38 + line_index * 16, color=FG2)
                parts.append(desc)
        if item.badges:
            parts.append(_capability_badges(item.badges, content_x, 28))
    parts.append("</g>")
    return "".join(parts)


def _picker_list(rows: tuple[PickerItem, ...]) -> tuple[str, list[float], list[int], float]:
    """Render one picker list and return its SVG, row tops, heights and total height."""
    parts: list[str] = []
    header, _ = text_run("ComfyUI", 10, 16, 13, weight=500, color=FG2, opacity=0.55)
    parts.append(header)
    tops: list[float] = []
    heights: list[int] = []
    top = float(GROUP_H)
    for item in rows:
        parts.append(_row_svg(item, top=top))
        tops.append(top)
        heights.append(item.height)
        top += item.height
    return "".join(parts), tops, heights, top


def _dash(offset: float, opacity: float) -> str:
    return f"stroke-dashoffset:{offset:.2f};opacity:{opacity:g}"


def _keyframes(name: str, states: list[State], *, base: str, duration: float = LOOP_SEC) -> str:
    frames = [
        (min(max(state.time / duration * 100, 0.0), 100.0), state.decls, state.timing)
        for state in sorted(states, key=lambda item: item.time)
    ]
    merged: list[tuple[float, str, str]] = []
    for frame in frames:
        if merged and abs(merged[-1][0] - frame[0]) < 0.0004:
            merged[-1] = frame
        else:
            merged.append(frame)
    if merged[0][0] > 0.0004:
        merged.insert(0, (0.0, base, "linear"))
    if merged[-1][0] < 99.9996:
        merged.append((100.0, base, "linear"))
    body = "".join(
        f"{pct:.3f}%{{{decls};animation-timing-function:{timing}}}" for pct, decls, timing in merged
    )
    return f"@keyframes {name}{{{body}}}"


def _travel_states(
    start: float,
    end: float,
    length: float,
    *,
    dash: float = 40,
    base: float = 0.0,
    opacity: float = 1.0,
    ease: str = "ease-in",
) -> list[State]:
    stop = -(length - dash) + base
    ramp = 0.05
    states: list[State] = []
    if start <= 0:
        states.append(State(0.0, _dash(base, 0.0), "linear"))
        states.append(State(ramp, _dash(base, opacity), ease))
    else:
        states.append(State(start, _dash(base, 0.0), "linear"))
        states.append(State(start + ramp, _dash(base, opacity), ease))
    states.append(State(end, _dash(stop, opacity), "linear"))
    states.append(State(end + ramp, _dash(stop, 0.0), "linear"))
    return states


def _pop_states(cycles: list[Cycle]) -> list[State]:
    states: list[State] = []
    for cycle in cycles:
        states += [
            State(cycle.start, "transform:scale(1)", "linear"),
            State(cycle.boom, "transform:scale(1)", BOOM_EASE),
            State(cycle.boom + 0.06, "transform:scale(1.3)", "ease-in-out"),
            State(cycle.boom + 0.14, "transform:scale(1.2)", "linear"),
            State(cycle.jolt_peak, "transform:scale(1.26)", "ease-in-out"),
            State(cycle.jolt, "transform:scale(1.2)", RETURN_EASE),
            State(cycle.end, "transform:scale(1)", "linear"),
        ]
    return states


def _glow_states(cycles: list[Cycle]) -> list[State]:
    states: list[State] = []
    for cycle in cycles:
        states += [
            State(cycle.boom - 0.0005, "opacity:0;stroke:var(--accent)", "linear"),
            State(cycle.boom, "opacity:0.9;stroke:var(--accent)", "linear"),
            State(cycle.boom + 0.1, "opacity:0.75;stroke:var(--accent)", "linear"),
            State(cycle.boom + 0.15, "opacity:0.7;stroke:var(--comfy)", "linear"),
            State(cycle.jolt, "opacity:0.9;stroke:var(--comfy)", "linear"),
            State(cycle.jolt + FADE_SEC, "opacity:0;stroke:var(--comfy)", "linear"),
        ]
    return states


def _ripple_states(cycles: list[Cycle]) -> list[State]:
    states: list[State] = []
    for cycle in cycles:
        states += [
            State(cycle.boom - 0.0005, "transform:scale(1);opacity:0", "linear"),
            State(cycle.boom, "transform:scale(1);opacity:0.8", "ease-out"),
            State(cycle.boom + T_RIPPLE, "transform:scale(1.6);opacity:0", "linear"),
        ]
    return states


def _endpoint_card(cycles: list[Cycle]) -> tuple[str, str, str]:
    prefix = "http://192.168.1.20:8188 · upai/1 · "
    prefix_svg, prefix_width = text_run(prefix, 11, 12, 82, color=FG2)
    base_svg, _ = text_run("4 video, 8 image models", 11, 12 + prefix_width, 82, color=FG2)
    plus_svg, _ = text_run("4 video, 9 image models", 11, 12 + prefix_width, 82, color=FG2)
    name_svg, _ = text_run("NVIDIA", 14, 60, 30, weight=600, color=FG)
    connected_svg, _ = text_run("Connected", 12, 25, 56, color=FG2)

    keys: list[str] = []
    rules: list[str] = []
    dot_states: list[State] = []
    base_states: list[State] = [State(0.0, "opacity:1", "linear")]
    plus_states: list[State] = [State(0.0, "opacity:0", "linear")]
    for cycle in cycles:
        dot_states += [
            State(cycle.start, "opacity:1", "linear"),
            State(cycle.start + 0.05, "opacity:0.25", "ease-in-out"),
            State(cycle.start + 0.15, "opacity:1", "linear"),
            State(cycle.end - 0.2, "opacity:1", "ease-in-out"),
            State(cycle.end - 0.08, "opacity:0.55", "ease-in-out"),
            State(cycle.end, "opacity:1", "linear"),
        ]
        if cycle.is_plus:
            base_states += [
                State(cycle.boom - 0.0005, "opacity:1", "linear"),
                State(cycle.boom + FADE_SEC, "opacity:0", "ease-in-out"),
                State(cycle.boom + 1.2, "opacity:0", "ease-in-out"),
                State(cycle.boom + 1.2 + FADE_SEC, "opacity:1", "linear"),
            ]
            plus_states += [
                State(cycle.boom - 0.0005, "opacity:0", "linear"),
                State(cycle.boom + FADE_SEC, "opacity:1", "ease-in-out"),
                State(cycle.boom + 1.2, "opacity:1", "ease-in-out"),
                State(cycle.boom + 1.2 + FADE_SEC, "opacity:0", "linear"),
            ]
    keys += [
        _keyframes("endpoint_dot", dot_states, base="opacity:1"),
        _keyframes("count_base", base_states, base="opacity:1"),
        _keyframes("count_plus", plus_states, base="opacity:0"),
    ]
    rules += [
        f".endpoint-dot{{animation:endpoint_dot {LOOP_SEC:g}s linear infinite}}",
        f".count-base{{animation:count_base {LOOP_SEC:g}s linear infinite}}",
        f".count-plus{{animation:count_plus {LOOP_SEC:g}s linear infinite}}",
    ]
    svg = (
        f'<g class="endpoint-card" transform="translate({ENDPOINT_X} {ENDPOINT_Y})">'
        f'<rect class="endpoint-bg" x="0" y="0" width="{ENDPOINT_W}" '
        f'height="{ENDPOINT_H}" rx="16"/>'
        f'<rect class="endpoint-border" x="0.5" y="0.5" width="{ENDPOINT_W - 1}" '
        f'height="{ENDPOINT_H - 1}" rx="15.5"/>'
        f"{_badge_chip(12, 14)}"
        f"{name_svg}"
        f"{_icon('ellipsis', 372, 14, 16, FG2)}"
        f'<circle class="endpoint-dot" cx="16" cy="52" r="3" fill="{ACCENT}"/>'
        f"{connected_svg}"
        f"{prefix_svg}"
        f'<g class="count-base">{base_svg}</g>'
        f'<g class="count-plus">{plus_svg}</g>'
        "</g>"
    )
    return svg, "".join(keys), "".join(rules)


def _blink_time(cycle: Cycle) -> float:
    _, total, forward = _return_geometry(cycle.x, cycle.y, plus=cycle.is_plus)
    return cycle.jolt + (forward + 204) / total * RETURN_SEC


def _picker_layouts() -> dict[str, tuple[str, list[float], list[int], float]]:
    return {
        kind: _picker_list(rows) for kind, rows in (("image", IMAGE_ITEMS), ("video", VIDEO_ITEMS))
    }


def _selections(
    cycles: list[Cycle], layouts: dict[str, tuple[str, list[float], list[int], float]]
) -> list[Selection]:
    selections: list[Selection] = []
    for cycle in cycles:
        _, tops, heights, _ = layouts[cycle.picker]
        moment = cycle.boom
        for title in cycle.rows:
            key = (cycle.picker, title)
            item = PICKER_ITEMS[key]
            index = ROW_INDEX[key]
            selections.append(
                Selection(
                    cycle.picker,
                    index,
                    moment,
                    moment + item.hold,
                    tops[index],
                    heights[index],
                    item.plus,
                )
            )
            moment += item.hold
    return selections


def _hl_decl(top: float, opacity: float) -> str:
    return f"transform:translateY({top:.2f}px);opacity:{opacity:g}"


def _ck_decl(center: float, opacity: float) -> str:
    return f"transform:translateY({center:.2f}px);opacity:{opacity:g}"


def _finish(states: list[State]) -> list[State]:
    if states and states[-1].time < LOOP_SEC - 0.0005:
        states.append(State(LOOP_SEC, states[-1].decls, states[-1].timing))
    return states


def _teleport_states(
    items: list[Selection],
    *,
    position: Callable[[Selection], float],
    decl: Callable[[float, float], str],
    delay: float = 0.0,
) -> list[State]:
    """Deselect fade, empty gap, jump while invisible, select fade. No sliding."""
    if not items:
        return []
    first_position = position(items[0])
    states = [State(0.0, decl(first_position, 0.0), "linear")]
    previous: Selection | None = None
    for item in items:
        item_position = position(item)
        if previous is None:
            select = item.start + delay
            states += [
                State(item.start, decl(item_position, 0.0), "linear"),
                State(select, decl(item_position, 0.0), "linear"),
                State(select + FADE_IN_SEC, decl(item_position, 1.0), "ease-in-out"),
            ]
        else:
            previous_position = position(previous)
            select = item.start + FADE_OUT_SEC + SELECT_GAP_SEC
            states += [
                State(item.start, decl(previous_position, 1.0), "linear"),
                State(item.start + FADE_OUT_SEC, decl(previous_position, 0.0), "ease-in-out"),
                State(select, decl(item_position, 0.0), "linear"),
                State(select + FADE_IN_SEC, decl(item_position, 1.0), "ease-in-out"),
            ]
        previous = item
    return states


def _check_center(item: Selection) -> float:
    return item.top + (item.height - 14) / 2


def _selection_hide_time() -> float:
    """Moment the list is hidden, used to reset the last selection unseen."""
    return LOOP_SEC - CROSSFADE_SEC - (FADE_OUT_SEC + SELECT_GAP_SEC + FADE_IN_SEC)


def _highlight_states(selections: list[Selection], picker: str, *, plus: bool) -> list[State]:
    own = [item for item in selections if item.picker == picker]
    targets = [item for item in own if item.plus == plus]
    if not targets:
        return []
    delay = FADE_OUT_SEC + SELECT_GAP_SEC if plus and not own[0].plus else 0.0
    states = _teleport_states(targets, position=lambda item: item.top, decl=_hl_decl, delay=delay)
    if not plus:
        plus_item = next((item for item in own if item.plus), None)
        if plus_item is not None and plus_item.start >= targets[-1].end - 0.001:
            states += [
                State(plus_item.start, _hl_decl(targets[-1].top, 1.0), "linear"),
                State(
                    plus_item.start + FADE_OUT_SEC, _hl_decl(targets[-1].top, 0.0), "ease-in-out"
                ),
            ]
        if picker == "image":
            last = targets[-1]
            hide = _selection_hide_time()
            states += [
                State(hide, _hl_decl(last.top, 1.0), "linear"),
                State(hide + FADE_OUT_SEC, _hl_decl(last.top, 0.0), "ease-in-out"),
            ]
    return _finish(states)


def _check_states(selections: list[Selection], picker: str) -> list[State]:
    own = [item for item in selections if item.picker == picker]
    if not own:
        return []
    states = _teleport_states(own, position=_check_center, decl=_ck_decl)
    if picker == "image":
        last = own[-1]
        hide = _selection_hide_time()
        states += [
            State(hide, _ck_decl(_check_center(last), 1.0), "linear"),
            State(hide + FADE_OUT_SEC, _ck_decl(_check_center(last), 0.0), "ease-in-out"),
        ]
    return _finish(states)


def _scroll_target(item: Selection, total: float) -> float:
    max_scroll = max(0.0, total - LIST_H)
    return max(0.0, min(max_scroll, item.top - (LIST_H - item.height) / 2))


def _scroll_states(
    selections: list[Selection],
    picker: str,
    total: float,
) -> list[State]:
    own = [item for item in selections if item.picker == picker]
    if not own:
        return []
    first_target = _scroll_target(own[0], total)
    states = [State(0.0, f"transform:translateY(-{first_target:.2f}px)", "linear")]
    previous = first_target
    for item in own[1:]:
        target = _scroll_target(item, total)
        if abs(target - previous) < 0.01:
            continue
        start = item.start + FADE_OUT_SEC
        states += [
            State(start, f"transform:translateY(-{previous:.2f}px)", SCROLL_EASE),
            State(start + SCROLL_SEC, f"transform:translateY(-{target:.2f}px)", "linear"),
        ]
        previous = target
    if picker == "image" and abs(previous - first_target) > 0.01:
        start = LOOP_SEC - CROSSFADE_SEC - SCROLL_SEC
        states += [
            State(start, f"transform:translateY(-{previous:.2f}px)", SCROLL_EASE),
            State(start + SCROLL_SEC, f"transform:translateY(-{first_target:.2f}px)", "linear"),
        ]
    return _finish(states)


def _picker_inner(
    rows: tuple[PickerItem, ...],
    kind: str,
    layout: tuple[str, list[float], list[int], float],
    selections: list[Selection],
    *,
    animated: bool,
) -> tuple[str, str, str]:
    list_svg, _, _, total = layout
    keys: list[str] = []
    rules: list[str] = []
    highlight = ""
    check = ""
    if animated:
        model_height = ROW_H_IMAGE if kind == "image" else ROW_H_VIDEO
        model_states = _highlight_states(selections, kind, plus=False)
        plus_states = _highlight_states(selections, kind, plus=True)
        check_states = _check_states(selections, kind)
        scroll_states = _scroll_states(selections, kind, total)
        keys += [
            _keyframes(f"hl_{kind}", model_states, base=_hl_decl(0, 0)),
            _keyframes(f"ck_{kind}", check_states, base=_ck_decl(0, 0)),
            _keyframes(f"scroll_{kind}", scroll_states, base="transform:translateY(0px)"),
        ]
        rules += [
            f".row-hl-{kind}{{animation:hl_{kind} {LOOP_SEC:g}s linear infinite}}",
            f".ck-{kind}{{animation:ck_{kind} {LOOP_SEC:g}s linear infinite}}",
            f".scroll-{kind}{{animation:scroll_{kind} {LOOP_SEC:g}s linear infinite}}",
        ]
        if plus_states:
            keys.append(_keyframes(f"hl_plus_{kind}", plus_states, base=_hl_decl(0, 0)))
            rules.append(
                f".row-hl-plus-{kind}{{animation:hl_plus_{kind} {LOOP_SEC:g}s linear infinite}}"
            )
        highlight = (
            f'<rect class="row-hl row-hl-{kind}" x="{ROW_X}" y="0" width="{ROW_W}" '
            f'height="{model_height}" rx="8" fill="{WHITE_6}" opacity="0"/>'
        )
        if plus_states:
            highlight += (
                f'<rect class="row-hl row-hl-plus-{kind}" x="{ROW_X}" y="0" width="{ROW_W}" '
                f'height="{ROW_H_PLUS}" rx="8" fill="{WHITE_6}" opacity="0"/>'
            )
        check = f'<g class="ck ck-{kind}" opacity="0">{_icon("check", CHECK_X, 0, 14, ACCENT)}</g>'
    picker_class = f"picker picker-{kind}" if animated else "picker picker-static"
    scroll_class = f"scroll scroll-{kind}" if animated else "scroll"
    body = (
        f'<g class="{picker_class}">'
        f'<g class="{scroll_class}" transform="translate(0 0)">'
        f'<g transform="translate(0 {LIST_Y})">{highlight}{list_svg}{check}</g>'
        "</g></g>"
    )
    return body, "".join(keys), "".join(rules)


def _picker_shell(inner: str, x: float, y: float) -> str:
    placeholder, _ = text_run("Search...", 12, 20, 30, color=FG3)
    return (
        f'<g class="picker-card" transform="translate({x} {y})">'
        f'<rect class="picker-bg" x="0" y="0" width="{PICKER_W}" height="{PICKER_H}" rx="12"/>'
        f'<rect class="picker-border" x="0.5" y="0.5" width="{PICKER_W - 1}" '
        f'height="{PICKER_H - 1}" rx="11.5"/>'
        f'<g clip-path="url(#pickerClip)">{inner}</g>'
        f'<rect class="search-bg" x="{SEARCH_X}" y="{SEARCH_Y}" width="{SEARCH_W}" '
        f'height="{SEARCH_H}" rx="8"/>'
        f"{placeholder}"
        f"{_icon('refresh', 328, 17, 14, FG2)}"
        "</g>"
    )


def _picker_cards(cycles: list[Cycle], *, animated: bool, menus: str) -> tuple[str, str, str]:
    keys: list[str] = []
    rules: list[str] = []
    layouts = _picker_layouts()
    selections = _selections(cycles, layouts)
    image_inner, image_keys, image_rules = _picker_inner(
        IMAGE_ITEMS, "image", layouts["image"], selections, animated=animated
    )
    video_inner, video_keys, video_rules = _picker_inner(
        VIDEO_ITEMS, "video", layouts["video"], selections, animated=animated
    )
    keys += [image_keys, video_keys]
    rules += [image_rules, video_rules]
    if menus == "two":
        return (
            _picker_shell(image_inner, ENDPOINT_X, ENDPOINT_Y)
            + _picker_shell(video_inner, PICKER_X, PICKER_Y),
            "".join(keys),
            "".join(rules),
        )
    if animated:
        keys.append(_crossfade_keys(cycles))
        rules += [
            f".picker-image{{animation:picker_image {LOOP_SEC:g}s linear infinite}}",
            f".picker-video{{animation:picker_video {LOOP_SEC:g}s linear infinite}}",
        ]
    return (
        _picker_shell(image_inner + video_inner, PICKER_X, PICKER_Y),
        "".join(keys),
        "".join(rules),
    )


def _crossfade_keys(cycles: list[Cycle]) -> str:
    video_start = next(cycle.start for cycle in cycles if cycle.picker == "video")
    image_states = [
        State(0.0, "opacity:1", "linear"),
        State(video_start, "opacity:1", "ease-in-out"),
        State(video_start + 0.2, "opacity:0", "linear"),
        State(LOOP_SEC - 0.3, "opacity:0", "ease-in-out"),
        State(LOOP_SEC, "opacity:1", "linear"),
    ]
    video_states = [
        State(0.0, "opacity:0", "linear"),
        State(video_start + 0.1, "opacity:0", "ease-in-out"),
        State(video_start + CROSSFADE_SEC, "opacity:1", "linear"),
        State(LOOP_SEC - CROSSFADE_SEC, "opacity:1", "ease-in-out"),
        State(LOOP_SEC - 0.2, "opacity:0", "linear"),
    ]
    return _keyframes("picker_image", image_states, base="opacity:1") + _keyframes(
        "picker_video", video_states, base="opacity:0"
    )


def _targets(cycles: list[Cycle]) -> tuple[str, str, str, str]:
    parts: list[str] = []
    ripples: list[str] = []
    keys: list[str] = []
    rules: list[str] = []
    for cycle in cycles:
        if cycle.slug is None:
            continue
        slug = cycle.slug
        key = slug.replace("-", "_")
        x, y = cycle.x, cycle.y
        tile = _data_uri(IMAGES / f"{slug}.png")
        keys += [
            _keyframes(f"pop_{key}", _pop_states([cycle]), base="transform:scale(1)"),
            _keyframes(f"glow_{key}", _glow_states([cycle]), base="opacity:0;stroke:var(--accent)"),
            _keyframes(
                f"ripple_{key}", _ripple_states([cycle]), base="transform:scale(1);opacity:0"
            ),
        ]
        ripples.append(
            f'<g transform="translate({x} {y})">'
            f'<rect class="ripple ripple_{key}" x="{MARGIN:.3f}" y="{MARGIN:.3f}" '
            f'width="{TILE:.3f}" height="{TILE:.3f}" rx="{RADIUS:.3f}"/>'
            "</g>"
        )
        parts.append(
            f'<g class="cell cell_{key}" data-slug="{slug}" data-cycle="{cycle.index}">'
            f'<g transform="translate({x} {y})">'
            f'<image x="0" y="0" width="{MODEL_CELL}" height="{MODEL_CELL}" href="{tile}"/>'
            f'<rect class="halo halo_{key}" x="{MARGIN:.3f}" y="{MARGIN:.3f}" '
            f'width="{TILE:.3f}" height="{TILE:.3f}" rx="{RADIUS:.3f}" '
            'filter="url(#glowModel)"/>'
            f'<rect class="ring ring_{key}" x="{MARGIN:.3f}" y="{MARGIN:.3f}" '
            f'width="{TILE:.3f}" height="{TILE:.3f}" rx="{RADIUS:.3f}"/>'
            "</g></g>"
        )
        rules.append(
            f".cell_{key}{{transform-origin:{x + MODEL_CELL / 2:.2f}px "
            f"{y + MODEL_CELL / 2:.2f}px;animation:pop_{key} {LOOP_SEC:g}s linear infinite}}"
            f".halo_{key},.ring_{key}{{animation:glow_{key} {LOOP_SEC:g}s linear infinite}}"
            f".ripple_{key}{{animation:ripple_{key} {LOOP_SEC:g}s linear infinite}}"
        )

    plus_cycles = [cycle for cycle in cycles if cycle.slug is None]
    keys += [
        _keyframes("pop_plus", _pop_states(plus_cycles), base="transform:scale(1)"),
        _keyframes("glow_plus", _glow_states(plus_cycles), base="opacity:0;stroke:var(--accent)"),
        _keyframes("ripple_plus", _ripple_states(plus_cycles), base="transform:scale(1);opacity:0"),
    ]
    plus_radius = PLUS_SIZE * 20 / 96
    plus_mark = "M 19.2 38.4 H 57.6 M 38.4 19.2 V 57.6"
    ripples.append(
        f'<g transform="translate({PLUS_X} {PLUS_Y})">'
        f'<rect class="ripple ripple_plus" x="0" y="0" width="{PLUS_SIZE}" '
        f'height="{PLUS_SIZE}" rx="{plus_radius:g}"/>'
        "</g>"
    )
    parts.append(
        f'<g class="cell cell_plus" data-cycle="{",".join(str(c.index) for c in plus_cycles)}">'
        f'<g transform="translate({PLUS_X} {PLUS_Y})">'
        f'<rect class="plus-face" x="0" y="0" width="{PLUS_SIZE}" height="{PLUS_SIZE}" '
        f'rx="{plus_radius:g}"/>'
        f'<rect class="plus-border" x="0" y="0" width="{PLUS_SIZE}" height="{PLUS_SIZE}" '
        f'rx="{plus_radius:g}"/>'
        f'<path class="plus-mark" d="{plus_mark}"/>'
        f'<rect class="halo halo_plus" x="0" y="0" width="{PLUS_SIZE}" height="{PLUS_SIZE}" '
        f'rx="{plus_radius:g}" filter="url(#glowModel)"/>'
        f'<rect class="ring ring_plus" x="0" y="0" width="{PLUS_SIZE}" height="{PLUS_SIZE}" '
        f'rx="{plus_radius:g}"/>'
        "</g></g>"
    )
    rules.append(
        f".cell_plus{{transform-origin:{PLUS_X + PLUS_SIZE / 2:.2f}px "
        f"{PLUS_Y + PLUS_SIZE / 2:.2f}px;animation:pop_plus {LOOP_SEC:g}s linear infinite}}"
        f".halo_plus,.ring_plus{{animation:glow_plus {LOOP_SEC:g}s linear infinite}}"
        f".ripple_plus{{animation:ripple_plus {LOOP_SEC:g}s linear infinite}}"
    )
    return "".join(parts), "".join(ripples), "".join(keys), "".join(rules)


def _pulses(cycles: list[Cycle]) -> tuple[str, str, str]:
    parts: list[str] = []
    keys: list[str] = []
    rules: list[str] = []

    app_path = "M 200 320 L 292 320"
    app_states: list[State] = []
    for cycle in cycles:
        app_states += _travel_states(cycle.start, cycle.start + T_U_FIRE, 92)
    keys.append(_keyframes("pulse_app", app_states, base=_dash(-52, 0.0)))
    parts += [
        f'<path class="pulse-core pulse_app" d="{app_path}" stroke="{ACCENT}"/>',
        f'<path class="pulse-halo pulse_app" d="{app_path}" stroke="{ACCENT}" '
        'filter="url(#glowLine)"/>',
    ]
    rules.append(f".pulse_app{{animation:pulse_app {LOOP_SEC:g}s linear infinite}}")

    u_path = "M 348 320 L 440 320"
    u_states: list[State] = []
    for cycle in cycles:
        u_states += _travel_states(cycle.start + T_U_GRAD, cycle.start + T_COMFY, 92)
    keys.append(_keyframes("pulse_u", u_states, base=_dash(-52, 0.0)))
    parts += [
        f'<path class="pulse-core pulse_u" d="{u_path}" stroke="{ACCENT}"/>',
        f'<path class="pulse-halo pulse_u" d="{u_path}" stroke="{COMFY}" filter="url(#glowLine)"/>',
    ]
    rules.append(f".pulse_u{{animation:pulse_u {LOOP_SEC:g}s linear infinite}}")

    for cycle in cycles:
        forward, forward_length = _forward_geometry(cycle.x, cycle.y, plus=cycle.is_plus)
        name = f"fwd_{cycle.index}"
        states = _travel_states(cycle.start + T_COMFY, cycle.boom, forward_length)
        keys.append(_keyframes(name, states, base=_dash(-(forward_length - 40), 0.0)))
        parts += [
            f'<path class="pulse-core {name}" d="{forward}" stroke="{ACCENT}"/>',
            f'<path class="pulse-halo {name}" d="{forward}" stroke="{COMFY}" '
            'filter="url(#glowLine)"/>',
        ]
        rules.append(f".{name}{{animation:{name} {LOOP_SEC:g}s linear infinite}}")

        reverse, total, _ = _return_geometry(cycle.x, cycle.y, plus=cycle.is_plus)
        lead = f"ret_lead_{cycle.index}"
        trail = f"ret_trail_{cycle.index}"
        keys.append(
            _keyframes(
                lead,
                _travel_states(
                    cycle.jolt,
                    cycle.end,
                    total,
                    dash=36,
                    opacity=1.0,
                    ease="ease-out",
                ),
                base=_dash(-(total - 36), 0.0),
            )
        )
        keys.append(
            _keyframes(
                trail,
                _travel_states(
                    cycle.jolt,
                    cycle.end,
                    total,
                    dash=36,
                    base=36,
                    opacity=1.0,
                    ease="ease-out",
                ),
                base=_dash(-(total - 36) + 36, 0.0),
            )
        )
        parts += [
            f'<path class="pulse-core {lead}" d="{reverse}" stroke="{COMFY}"/>',
            f'<path class="pulse-halo {lead}" d="{reverse}" stroke="{COMFY}" '
            'filter="url(#glowLine)"/>',
            f'<path class="pulse-core {trail}" d="{reverse}" stroke="{ACCENT}"/>',
            f'<path class="pulse-halo {trail}" d="{reverse}" stroke="{ACCENT}" '
            'filter="url(#glowLine)"/>',
        ]
        rules.append(
            f".{lead}{{animation:{lead} {LOOP_SEC:g}s linear infinite}}"
            f".{trail}{{animation:{trail} {LOOP_SEC:g}s linear infinite}}"
        )

    app_ring: list[State] = []
    comfy_ring: list[State] = []
    for cycle in cycles:
        app_ring += [
            State(cycle.end - 0.2, "opacity:0", "ease-in-out"),
            State(cycle.end - 0.08, "opacity:0.55", "ease-in-out"),
            State(cycle.end + 0.15, "opacity:0", "linear"),
        ]
        comfy_ring += [
            State(cycle.start + T_COMFY - 0.0005, "opacity:0", "linear"),
            State(cycle.start + T_COMFY + 0.05, "opacity:0.9", "ease-out"),
            State(cycle.start + T_COMFY + 0.25, "opacity:0", "linear"),
        ]
    keys += [
        _keyframes("app_ring", app_ring, base="opacity:0"),
        _keyframes("comfy_ring", comfy_ring, base="opacity:0"),
    ]
    rules += [
        f".app-ring{{animation:app_ring {LOOP_SEC:g}s linear infinite}}",
        f".comfy-ring{{animation:comfy_ring {LOOP_SEC:g}s linear infinite}}",
    ]
    return "".join(parts), "".join(keys), "".join(rules)


def _chip_border_states(cycles: list[Cycle]) -> tuple[list[State], list[State]]:
    """Forward and return border opacity ramps."""
    forward: list[State] = []
    reverse: list[State] = []
    for cycle in cycles:
        forward += [
            State(cycle.start + T_U_FIRE - 0.0005, "opacity:0", "linear"),
            State(cycle.start + T_U_FIRE, "opacity:0", "ease-in-out"),
            State(cycle.start + T_U_GRAD, "opacity:1", "linear"),
            State(cycle.start + T_COMFY, "opacity:1", "ease-in-out"),
            State(cycle.start + T_COMFY + RETURN_SEC, "opacity:0", "linear"),
        ]
        start = _blink_time(cycle)
        fade_end = min(start + RETURN_SEC, LOOP_SEC)
        reverse += [
            State(start - 0.0005, "opacity:0", "linear"),
            State(start, "opacity:0", "ease-in-out"),
            State(start + 0.05, "opacity:1", "linear"),
            State(min(start + 0.1, fade_end - 0.01), "opacity:1", "ease-in-out"),
            State(fade_end, "opacity:0", "linear"),
        ]
    return forward, reverse


def _chip_clip_states(cycles: list[Cycle], *, reverse: bool) -> list[State]:
    zero, one = "transform:scaleX(0)", "transform:scaleX(1)"
    states: list[State] = []
    for cycle in cycles:
        if reverse:
            start = _blink_time(cycle)
            fade_end = min(start + RETURN_SEC, LOOP_SEC)
            hold = start + 0.05 + max(0.02, (fade_end - start - 0.05) * 0.4)
            states += [
                State(start - 0.0005, zero, "linear"),
                State(start, zero, "ease-in-out"),
                State(start + 0.05, one, "linear"),
                State(hold, one, "ease-in-out"),
                State(fade_end, zero, "linear"),
            ]
        else:
            start = cycle.start + T_U_FIRE
            states += [
                State(start - 0.0005, zero, "linear"),
                State(start, zero, "ease-in-out"),
                State(start + 0.15, one, "linear"),
                State(start + RETURN_SEC + 0.3, one, "ease-in-out"),
                State(start + 2 * RETURN_SEC + 0.3, zero, "linear"),
            ]
    return states


def _ghosts() -> str:
    parts: list[str] = []
    steps = ((0, 64.0, 0.5), (68, 51.2, 0.25), (120, 40.96, 0.125))
    for step, (dx, size, opacity) in enumerate(steps):
        for row_index, row in enumerate((112, 432)):
            x = 1036 + dx
            y = row + (MODEL_CELL - size) / 2
            radius = size * 100 / 512
            parts.append(
                f'<g opacity="{opacity:g}">'
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{size:.2f}" height="{size:.2f}" '
                f'rx="{radius:.2f}" fill="{GHOST_FILL}" stroke="{GHOST_STROKE}" '
                'stroke-width="1"/>'
            )
            if (step + row_index) % 2 == 0:
                parts.append(
                    f'<ellipse cx="{x + size / 2:.2f}" cy="{y + size * 0.55:.2f}" '
                    f'rx="{size * 0.26:.2f}" ry="{size * 0.18:.2f}" fill="#1e2428" '
                    'filter="url(#ghostBlur)" opacity="0.8"/>'
                )
            parts.append("</g>")
    return "".join(parts)


def _cards(
    cycles: list[Cycle], *, endpoint: bool, menus: str, animated: bool
) -> tuple[str, str, str]:
    parts: list[str] = []
    keys: list[str] = []
    rules: list[str] = []
    if endpoint and menus != "two":
        card_svg, card_keys, card_rules = _endpoint_card(cycles)
        parts.append(card_svg)
        keys.append(card_keys)
        rules.append(card_rules)
    picker_svg, picker_keys, picker_rules = _picker_cards(cycles, animated=animated, menus=menus)
    parts.append(picker_svg)
    keys.append(picker_keys)
    rules.append(picker_rules)
    return "".join(parts), "".join(keys), "".join(rules)


def build_svg(
    *,
    ghosts: bool = True,
    endpoint: bool = True,
    menus: str = "one",
    animated: bool = True,
) -> str:
    cycles = CYCLES
    model_cells, ripples, keys, rules = _targets(cycles)
    pulses, pulse_keys, pulse_rules = _pulses(cycles)
    keys += pulse_keys
    rules += pulse_rules
    chip_path, chip_transform = text_to_path("U", LETTER_SIZE, *CHIP_CENTER)
    app_icon = _data_uri(IMAGES / "app.png")
    comfy_icon = _data_uri(IMAGES / "comfyui.png")
    connectors = "".join(f'<path class="connector" d="{d}"/>' for d in BASE_CONNECTORS)
    shimmers = "".join(
        f'<path class="shimmer" style="animation-delay:-{index * 0.31:.2f}s" d="{d}"/>'
        for index, d in enumerate(BASE_CONNECTORS[:3])
    )
    ghost_svg = f'<g class="ghosts">{_ghosts()}</g>' if ghosts else ""
    card_svg, card_keys, card_rules = _cards(
        cycles, endpoint=endpoint, menus=menus, animated=animated
    )
    keys += card_keys
    rules += card_rules
    border_rect = (
        f'<rect class="chip-border" x="{CHIP_X + 0.75}" y="{CHIP_Y + 0.75}" '
        f'width="{CHIP_SIZE - 1.5}" height="{CHIP_SIZE - 1.5}" rx="15.25"/>'
    )
    chip = (
        '<g class="chip-group">'
        f'<rect class="chip chip-shadow" x="{CHIP_X}" y="{CHIP_Y}" width="{CHIP_SIZE}" '
        f'height="{CHIP_SIZE}" rx="16"/>'
        f'<path class="chip-glow" d="{chip_path}" transform="{chip_transform}"/>'
        f'<path class="chip-letter" d="{chip_path}" transform="{chip_transform}"/>'
        f'<g clip-path="url(#chipSweepFwd)">'
        f'<g class="chip-border-fwd">{border_rect}</g></g>'
        f'<g clip-path="url(#chipSweepRet)">'
        f'<g class="chip-border-ret">{border_rect}</g></g>'
        "</g>"
    )
    app = (
        '<g class="app">'
        f'<image class="icon" x="{APP_X}" y="{APP_Y}" width="{ICON}" height="{ICON}" '
        f'href="{app_icon}"/>'
        f'<rect class="app-ring" x="{APP_X + ICON_MARGIN:.3f}" y="{APP_Y + ICON_MARGIN:.3f}" '
        f'width="{ICON - 2 * ICON_MARGIN:.3f}" height="{ICON - 2 * ICON_MARGIN:.3f}" '
        f'rx="{ICON_RADIUS:.3f}"/>'
        "</g>"
    )
    comfy = (
        '<g class="comfy">'
        f'<image class="icon" x="{COMFY_X}" y="{COMFY_Y}" width="{ICON}" height="{ICON}" '
        f'href="{comfy_icon}"/>'
        f'<rect class="comfy-ring" x="{COMFY_X + ICON_MARGIN:.3f}" '
        f'y="{COMFY_Y + ICON_MARGIN:.3f}" width="{ICON - 2 * ICON_MARGIN:.3f}" '
        f'height="{ICON - 2 * ICON_MARGIN:.3f}" rx="{ICON_RADIUS:.3f}"/>'
        "</g>"
    )
    border_fwd, border_ret = _chip_border_states(cycles)
    keys += "".join(
        [
            _keyframes("chip_border_fwd", border_fwd, base="opacity:0"),
            _keyframes("chip_border_ret", border_ret, base="opacity:0"),
            _keyframes("chip_glow", border_fwd + border_ret, base="opacity:0"),
            _keyframes(
                "chip_clip_fwd",
                _chip_clip_states(cycles, reverse=False),
                base="transform:scaleX(0)",
            ),
            _keyframes(
                "chip_clip_ret",
                _chip_clip_states(cycles, reverse=True),
                base="transform:scaleX(0)",
            ),
        ]
    )
    rules += (
        f".chip-border-fwd{{animation:chip_border_fwd {LOOP_SEC:g}s linear infinite}}"
        f".chip-border-ret{{animation:chip_border_ret {LOOP_SEC:g}s linear infinite}}"
        f".chip-glow{{animation:chip_glow {LOOP_SEC:g}s linear infinite}}"
        f".chip-sweep-fwd{{animation:chip_clip_fwd {LOOP_SEC:g}s linear infinite}}"
        f".chip-sweep-ret{{animation:chip_clip_ret {LOOP_SEC:g}s linear infinite}}"
    )
    css = (
        ":root{"
        f"--accent:{ACCENT};--comfy:{COMFY};--connector:{CONNECTOR};--shadow:{SHADOW}"
        "}"
        ".icon{filter:" + BASE_FILTER + "}"
        ".chip{fill:#050607;stroke:none}"
        ".chip-shadow{filter:drop-shadow(0 8px 14px var(--shadow))}"
        ".chip-glow{fill:#fff;filter:url(#glowLetter);opacity:0}"
        ".chip-letter{fill:#fff}"
        ".chip-border{fill:none;stroke:url(#chipGradient);stroke-width:1.5;"
        "filter:drop-shadow(0 0 6px var(--accent))}"
        ".chip-border-fwd,.chip-border-ret{opacity:0}"
        ".chip-sweep-fwd{transform-box:view-box;"
        f"transform-origin:{CHIP_X:g}px {CHIP_CENTER[1]:g}px;transform:scaleX(0)}}"
        ".chip-sweep-ret{transform-box:view-box;"
        f"transform-origin:{CHIP_X + CHIP_SIZE:g}px {CHIP_CENTER[1]:g}px;"
        "transform:scaleX(0)}"
        ".connector{fill:none;stroke:var(--connector);stroke-width:1;stroke-linecap:round}"
        ".shimmer{fill:none;stroke:var(--accent);stroke-width:1;stroke-linecap:round;"
        "opacity:.06;animation:shimmer 3.4s ease-in-out infinite}"
        ".pulse-core{fill:none;stroke-width:1;stroke-linecap:round;"
        "stroke-dasharray:40 2000;opacity:0}"
        ".pulse-halo{fill:none;stroke-width:2.5;stroke-linecap:round;"
        "stroke-dasharray:40 2000;stroke-opacity:.6;opacity:0}"
        ".cell{transform-box:view-box;filter:" + BASE_FILTER + "}"
        ".app-ring{fill:none;stroke:var(--accent);stroke-width:1;opacity:0}"
        ".comfy-ring{fill:none;stroke:var(--comfy);stroke-width:1;opacity:0}"
        ".plus-face{fill:#0b0d0f}"
        ".plus-border{fill:none;stroke:var(--accent);stroke-width:1;stroke-dasharray:4 5}"
        ".plus-mark{fill:none;stroke:var(--accent);stroke-width:1.5;stroke-linecap:round}"
        ".ring{fill:none;stroke:var(--accent);stroke-width:1;opacity:0}"
        ".halo{fill:none;stroke:var(--accent);stroke-width:2.5;stroke-opacity:.6;opacity:0}"
        ".ripple{fill:none;stroke:var(--accent);stroke-width:3;opacity:0;"
        "transform-box:fill-box;transform-origin:center}"
        ".endpoint-bg{fill:" + CARD_BG + ";filter:url(#cardShadow)}"
        ".endpoint-border{fill:none;stroke:" + LINE_STRONG + ";stroke-width:1}"
        ".picker-bg{fill:" + PICKER_BG + ";filter:url(#pickerShadow)}"
        ".picker-border{fill:none;stroke:" + LINE_SOFT + ";stroke-width:1}"
        ".search-bg{fill:" + SEARCH_BG + "}"
        ".picker-static{opacity:1}"
        ".picker-image{opacity:1}"
        ".picker-video{opacity:0}"
        ".count-base{opacity:1}"
        ".count-plus{opacity:0}"
        ".placeholder{fill:none;stroke:var(--connector);stroke-width:1;stroke-dasharray:5 6}"
        "@keyframes shimmer{0%,100%{opacity:.03}50%{opacity:.09}}"
        "@media (prefers-reduced-motion:reduce){"
        ".cell,.pulse-core,.pulse-halo,.halo,.ring,.ripple,.shimmer,.chip-border-fwd,"
        ".chip-border-ret,.chip-glow,.chip-sweep-fwd,.chip-sweep-ret,.app-ring,.comfy-ring,"
        ".endpoint-dot,.count-base,.count-plus,.picker-image,.picker-video,.scroll,"
        ".row-hl,.ck{animation:none!important}"
        ".pulse-core,.pulse-halo,.halo,.ring,.ripple,.chip-border-fwd,.chip-border-ret,"
        ".chip-glow,.app-ring,.comfy-ring,.row-hl,.ck{opacity:0}"
        ".chip-sweep-fwd,.chip-sweep-ret{transform:scaleX(0)}}" + keys + rules
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        'aria-label="Unplatform AI connects to ComfyUI and runs local models">'
        "<title>Unplatform AI Provider</title>"
        f'<rect x="0" y="{PANEL_Y}" width="{WIDTH}" height="{PANEL_HEIGHT}" rx="12" '
        f'fill="{PANEL}"/>'
        "<defs>"
        f"{ICON_DEFS}"
        '<filter id="glowLine" filterUnits="userSpaceOnUse" x="180" y="140" '
        'width="900" height="380">'
        '<feGaussianBlur stdDeviation="0.8"/>'
        "</filter>"
        '<filter id="glowModel" filterUnits="userSpaceOnUse" x="-8" y="-8" '
        'width="112" height="112">'
        '<feGaussianBlur stdDeviation="1.6"/>'
        "</filter>"
        '<filter id="glowLetter" filterUnits="userSpaceOnUse" x="286" y="282" '
        'width="84" height="76">'
        '<feGaussianBlur stdDeviation="5" result="blur"/>'
        '<feComponentTransfer in="blur"><feFuncA type="linear" slope="1.4"/>'
        "</feComponentTransfer></filter>"
        '<filter id="ghostBlur" filterUnits="userSpaceOnUse" x="1000" y="50" '
        'width="240" height="450">'
        '<feGaussianBlur stdDeviation="5"/>'
        "</filter>"
        '<filter id="cardShadow" filterUnits="userSpaceOnUse" x="-40" y="-40" '
        'width="480" height="200">'
        '<feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#000000" '
        'flood-opacity="0.75"/>'
        "</filter>"
        '<filter id="pickerShadow" filterUnits="userSpaceOnUse" x="-50" y="-50" '
        'width="460" height="520">'
        '<feDropShadow dx="0" dy="18" stdDeviation="15" flood-color="#000000" '
        'flood-opacity="0.8"/>'
        "</filter>"
        '<clipPath id="pickerClip">'
        f'<rect x="0" y="{LIST_Y}" width="{PICKER_W}" height="{LIST_H}" rx="0"/>'
        "</clipPath>"
        '<linearGradient id="chipGradient" gradientUnits="userSpaceOnUse" '
        f'x1="{CHIP_X}" y1="{CHIP_CENTER[1]}" x2="{CHIP_X + CHIP_SIZE}" y2="{CHIP_CENTER[1]}">'
        f'<stop offset="0" stop-color="{ACCENT}"/>'
        f'<stop offset="1" stop-color="{COMFY}"/>'
        "</linearGradient>"
        '<clipPath id="chipSweepFwd">'
        f'<rect class="chip-sweep-fwd" x="{CHIP_X}" y="{CHIP_Y}" width="{CHIP_SIZE}" '
        f'height="{CHIP_SIZE}"/>'
        "</clipPath>"
        '<clipPath id="chipSweepRet">'
        f'<rect class="chip-sweep-ret" x="{CHIP_X}" y="{CHIP_Y}" width="{CHIP_SIZE}" '
        f'height="{CHIP_SIZE}"/>'
        "</clipPath>"
        "</defs>"
        f"<style>{css}</style>"
        f'<g class="ripples">{ripples}</g>'
        f"{ghost_svg}"
        f'<g class="connectors">{connectors}{shimmers}</g>'
        f'<g class="pulses">{pulses}</g>'
        f"{app}"
        f"{chip}"
        f"{comfy}"
        f'<g class="models">{model_cells}</g>'
        f'<g class="cards">{card_svg}</g>'
        "</svg>"
    )


def _playwright() -> Any:
    """Import Playwright lazily; it lives in a separate dev venv."""
    try:
        return importlib.import_module("playwright.sync_api").sync_playwright
    except ImportError:
        raise SystemExit("playwright is required: use /tmp/upai-playwright/bin/python") from None


def _paint_wait(page: Any) -> None:
    """Wait two frames so the compositor has the new animation time."""
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def _chromium(playwright: Any) -> Any:
    """Full Chromium build: the headless shell fails under sandboxed IPC."""
    return playwright.chromium.launch(channel="chromium", args=["--disable-gpu"])


def _page_html(svg_text: str, width: int, height: int) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        f"html,body{{margin:0;padding:0;width:{width}px;height:{height}px;overflow:hidden;"
        f"background:{PANEL};display:flex;align-items:center;justify-content:center}}"
        f"svg{{width:{width}px;height:{height}px;display:block}}"
        "</style></head><body>"
        f"{svg_text}</body></html>"
    )


def _render_still(
    svg_text: str,
    path: Path,
    *,
    width: int = WIDTH,
    height: int = HEIGHT,
    scale: int = 1,
) -> None:
    sync_playwright = _playwright()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = _chromium(playwright)
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=scale,
                reduced_motion="reduce",
            )
            page = context.new_page()
            page.set_content(_page_html(svg_text, width, height))
            page.wait_for_load_state("load")
            page.screenshot(path=str(path))
            context.close()
        finally:
            browser.close()
    LOGGER.info("wrote %s", path)


def render_stills(svg_text: str) -> Path:
    out = IMAGES / "hero-dark.png"
    _render_still(svg_text, out, scale=STILL_SCALE)
    return out


def _social_html(svg_text: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        f"html,body{{margin:0;padding:0;width:{SOCIAL_WIDTH}px;height:{SOCIAL_HEIGHT}px;"
        f"overflow:hidden;background:{PANEL}}}"
        "svg{position:absolute;inset:0;width:100%;height:100%;display:block}"
        ".title{position:absolute;right:48px;bottom:36px;text-align:right;color:#e6edf3;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,"
        "Arial,sans-serif;font-size:34px;font-weight:700;letter-spacing:-.5px}"
        "</style></head><body>"
        f"{svg_text}"
        '<div class="title">Unplatform AI Provider</div>'
        "</body></html>"
    )


def render_social(svg_text: str) -> Path:
    sync_playwright = _playwright()
    social = svg_text.replace(f'viewBox="0 0 {WIDTH} {HEIGHT}"', f'viewBox="0 0 {WIDTH} 600"', 1)
    out = IMAGES / "social-preview.png"
    with sync_playwright() as playwright:
        browser = _chromium(playwright)
        try:
            context = browser.new_context(
                viewport={"width": SOCIAL_WIDTH, "height": SOCIAL_HEIGHT},
                device_scale_factor=1,
                reduced_motion="reduce",
            )
            page = context.new_page()
            page.set_content(_social_html(social))
            page.wait_for_load_state("load")
            page.screenshot(path=str(out))
            context.close()
        finally:
            browser.close()
    LOGGER.info("wrote %s", out.name)
    return out


def _video_html(svg_text: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        f"html,body{{margin:0;padding:0;width:{VIDEO_WIDTH}px;height:{VIDEO_HEIGHT}px;"
        f"overflow:hidden;background:{PANEL};display:flex;align-items:center;"
        "justify-content:center}"
        "svg{height:1080px;width:1440px;display:block}"
        "</style></head><body>"
        f"{svg_text}</body></html>"
    )


def _encode(frames: Path, count: int, out: Path) -> None:
    subprocess.run(  # noqa: S603
        [
            _ffmpeg(),
            "-y",
            "-loglevel",
            "error",
            "-framerate",
            str(FPS),
            "-i",
            str(frames / "%04d.png"),
            "-frames:v",
            str(count),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-threads",
            "1",
            "-x264-params",
            "threads=1:sliced-threads=0",
            "-movflags",
            "+faststart",
            "-map_metadata",
            "-1",
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            str(out),
        ],
        check=True,
    )
    LOGGER.info("wrote %s %d bytes", out.name, out.stat().st_size)


def render_videos(svg_text: str) -> list[Path]:
    sync_playwright = _playwright()
    frames_total = round(FPS * LOOP_SEC)
    cut_frames = round(FPS * CUT_SEC)
    written: list[Path] = []
    with sync_playwright() as playwright:
        browser = _chromium(playwright)
        try:
            context = browser.new_context(
                viewport={"width": VIDEO_WIDTH, "height": VIDEO_HEIGHT},
                device_scale_factor=1,
            )
            page = context.new_page()
            page.set_content(_video_html(svg_text))
            page.wait_for_load_state("load")
            page.evaluate("() => document.getAnimations().forEach(a => a.pause())")
            # Warm the raster caches so the first captured frame matches later runs.
            page.evaluate("(t) => document.getAnimations().forEach(a => {a.currentTime = t})", 0)
            _paint_wait(page)
            page.wait_for_timeout(300)
            page.screenshot()
            # Move off frame 0 so the first captured frame repaints.
            page.evaluate("(t) => document.getAnimations().forEach(a => {a.currentTime = t})", 1)
            _paint_wait(page)
            page.wait_for_timeout(30)
            with tempfile.TemporaryDirectory() as tmp:
                frames = Path(tmp)
                for frame in range(frames_total):
                    moment = frame * 1000 / FPS
                    page.evaluate(
                        "(t) => document.getAnimations().forEach(a => {a.currentTime = t})",
                        moment,
                    )
                    _paint_wait(page)
                    page.wait_for_timeout(20)
                    page.screenshot(path=str(frames / f"{frame:04d}.png"))
                full = IMAGES / "hero-dark.mp4"
                _encode(frames, frames_total, full)
                written.append(full)
                cut = IMAGES / "hero-dark-6s.mp4"
                _encode(frames, cut_frames, cut)
                written.append(cut)
            context.close()
        finally:
            browser.close()
    return written


def _compare_dir() -> Path:
    target = Path("/tmp")  # noqa: S108 - comparison stills are requested there
    try:
        probe = target / ".upai-hero-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return target
    except OSError:
        fallback = Path(tempfile.mkdtemp(prefix="upai-hero-"))
        LOGGER.warning("cannot write /tmp, using %s", fallback)
        return fallback


def render_comparisons() -> list[Path]:
    out_dir = _compare_dir()
    variants = (
        ("hero-ghosts-on", {"ghosts": True, "endpoint": True, "menus": "one"}),
        ("hero-ghosts-off", {"ghosts": False, "endpoint": True, "menus": "one"}),
        ("hero-menus-one", {"ghosts": True, "endpoint": True, "menus": "one"}),
        ("hero-menus-two", {"ghosts": True, "endpoint": False, "menus": "two"}),
        ("hero-endpoint-on", {"ghosts": True, "endpoint": True, "menus": "one"}),
        ("hero-endpoint-off", {"ghosts": True, "endpoint": False, "menus": "one"}),
    )
    written: list[Path] = []
    for name, options in variants:
        # Animated markup plus reduced motion resolves the picker cross-fade to the
        # same static frame as hero-dark.png instead of stacking both lists.
        svg_text = build_svg(**options)
        out = out_dir / f"{name}.png"
        _render_still(svg_text, out, scale=1)
        written.append(out)
    return written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-video", action="store_true", help="skip the MP4 loops")
    parser.add_argument("--ghosts", choices=("on", "off"), default="on")
    parser.add_argument("--endpoint", choices=("on", "off"), default="on")
    parser.add_argument("--menus", choices=("one", "two"), default="one")
    parser.add_argument("--compare", action="store_true", help="write comparison stills")
    args = parser.parse_args()

    build_headers()
    svg_text = build_svg(
        ghosts=args.ghosts == "on",
        endpoint=args.endpoint == "on",
        menus=args.menus,
    )
    svg_path = IMAGES / "hero-dark.svg"
    svg_path.write_text(svg_text, encoding="utf-8")
    LOGGER.info("wrote %s %d bytes", svg_path.name, svg_path.stat().st_size)
    render_stills(svg_text)
    render_social(svg_text)
    if not args.skip_video:
        render_videos(svg_text)
    if args.compare:
        render_comparisons()


if __name__ == "__main__":
    main()
