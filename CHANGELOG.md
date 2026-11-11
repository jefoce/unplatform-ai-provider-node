# Changelog

## 0.1.1 - 2026-11-11

### Added

- New models and modes: LTX 2.5 Extend, LTX 2.5 Upscale, MiniMax H3 Fast, MiniMax H3 Extend, MiniMax H3 Image, MiniMax H3 Image Fast, MOSS Pose and Qwen 2.1 Outpaint.
- Publish check for workflows that cannot be saved as a model.

### Changed

- Unified model descriptions across the app and the docs.
- Compatibility fixes.
- ComfyUI Manager install docs, including the separate Manager install on new ComfyUI versions.

### Fixed

- Registry publish.

## 0.1.0 - 2026-11-10

First release.

### Added

- Turn any ComfyUI workflow into a model for Unplatform AI with the UPAI nodes. Save the workflow and it is published.
- Nodes: UPAI Model, Prompt, Settings, Limits, Output, Image, Video and Audio references, Start and End frames.
- Several models in one workflow.
- Image and video generation over the `upai/1` HTTP protocol: text-to-image, image edit with references, text-to-video, image-to-video, first and last frame, reference-to-video, audio references.
- Queue with a running limit, queue position and progress, cancel and delete.
- Model status in the app: ready, stale (workflow changed since publish) or invalid with a reason.
- Access token, allowed origins and an optional LAN access setting.
- Disk guard: minimum free space and a results quota. Results are deleted after the app downloads them.
- Nine ready workflows with guides and prompt skills: FLUX.2 Klein, Ideogram 4, Krea 2, LTX 2.5, MiniMax H3, MOSS Image, Qwen 2.1, Wan 2.2, Z-Image.
- User guides: getting started, building a workflow, network, memory (VRAM and RAM), troubleshooting, FAQ, and one page per node.
- Mock server for testing the app without ComfyUI or models.
