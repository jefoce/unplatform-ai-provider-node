# Logo sources

Raw downloads and raster previews live in `src/`. Each model table row is the
official mark used for the tile. Vendor logos are trademarks of their owners and
are used here only to identify the model.

## Models

| Slug | Source | License or terms |
|---|---|---|
| `flux-2-klein` | https://bfl.ai/icon0.svg (Black Forest Labs site icon, `src/flux-2-klein-raster.png`) | None stated. Black Forest Labs trademark. |
| `ideogram-4` | https://ideogram.ai/favicon.svg (Ideogram site icon, `src/ideogram-4-raster.png`) | None stated. Ideogram trademark. |
| `krea-2` | https://www.krea.ai/press/krea/krea-icon-black.svg (official press kit mark, `src/krea-2-raster.png`) | None stated. Krea trademark. |
| `ltx-2-5` | https://cdn.prod.website-files.com/68872d15af29880764eac4aa/6991ae8e8bccea76df4efe04_ltx-logo-black.svg (official mark, `src/ltx-2-5-raster.png`) | None stated. Lightricks/LTX trademark. |
| `minimax-h3` | https://file.cdn.minimax.io/public/brand-vi/20260914/logo-1.webp (official brand page asset, `src/minimax-official.webp`; the official GitHub org avatar https://github.com/MiniMax-AI.png?size=512 bakes a gradient background and wordmark, so it was not usable as a clean mark) | None stated. MiniMax trademark. |
| `moss-image` | https://raw.githubusercontent.com/OpenMOSS/MOSS-Image/HEAD/assets/logo.svg (`src/moss-image-raster.png`) | Repository Apache-2.0. |
| `qwen-2-1` | https://zonalogo.com/assets/qwen-ai-logo.webp (`src/qwen-zonalogo.webp`, user choice, wordmark) | None stated. Qwen trademark. |
| `wan-2-2` | `src/wan.svg` (user-provided official mark, URL not recorded). Verified against https://raw.githubusercontent.com/Wan-Video/Wan2.2/main/assets/logo.png: same mark, kept. `src/wan-2-2-raster.png` is derived from it. | None stated. Wan trademark. |
| `z-image` | https://tongyi-mai.github.io/Z-Image-blog/ (official wordmark heading, `src/z-image.png`; no graphic mark published) | None stated. Tongyi-MAI/Alibaba trademark. |

## App and ComfyUI

| File | Source | License or terms |
|---|---|---|
| `app.png`, `registry-icon.png` | `src/app-icon.png` (project app icon, 512 and 400 px) | Project asset. |
| `comfyui.png` | https://comfy.org/icons/logomark.svg (official ComfyUI logomark, `src/comfyui-raster.png`) | None stated. ComfyUI trademark. |

## Fonts

| File | Source | License or terms |
|---|---|---|
| `fonts/InterVariable.ttf` | https://rsms.me/inter/font-files/InterVariable.ttf (official Inter project, https://github.com/rsms/inter, release v4.1) | SIL Open Font License 1.1, full text in `fonts/Inter-OFL.txt`. |

`scripts/make_hero.py` converts the "U" chip letter to a path with fontTools. The
font is not served at runtime and the pack does not depend on it.

## Icons

| File | Source | License or terms |
|---|---|---|
| `hero-dark.svg` | https://lucide.dev (monitor, clock, speaker, check, refresh, ellipsis, plus path data) | ISC License, https://lucide.dev/license. |

The card text and icons are converted to static SVG paths at build time. Lucide
is not served at runtime and the pack does not depend on it.

## Preprocessing

- The committed `*-raster.png` files are the script inputs. Older SVG sources
  were rasterized once at 4096 px with macOS `qlmanage`, then cropped to the
  mark. `krea-2-raster.png` and `ltx-2-5-raster.png` were rasterized at 2048 px
  on a transparent background with Chromium (Playwright).
- `minimax-official.webp` is cropped to the waveform mark, box
  (490, 500, 860, 815) of the 2000x1314 asset, and keyed against `#f5f5f5`.
- `qwen-zonalogo.webp` is cropped to the wordmark, box (330, 318, 675, 438), and
  keyed against its light checkerboard background.
- `wan-2-2-raster.png` is derived from `src/wan.svg`. Verified against
  https://raw.githubusercontent.com/Wan-Video/Wan2.2/main/assets/logo.png: same
  mark, kept.
- `z-image.png` is the official wordmark from the blog heading set in the site's
  font stack. Z-Image publishes no graphic mark.
