# MiniMax H3 UPAI flow

![MiniMax H3 workflow in ComfyUI](../docs/images/minimax-h3-workflow.png)

## What it does

One UPAI video workflow for MiniMax H3 with presets `minimax-h3` (MiniMax H3, 20 steps) and `minimax-h3-fast` (MiniMax H3 Fast, 8 steps). Input is a prompt, optional start and end frames, and up to 9 image refs, 3 video refs and 3 audio refs. Output is 24 fps MP4.

## Modes

| Mode | Input | Output |
|---|---|---|
| Text-to-video | prompt | 24 fps MP4 |
| Image-to-video | prompt and start frame | 24 fps MP4 |
| First-last-frame video | prompt, start frame and end frame | 24 fps MP4 |
| Reference-to-video | prompt and up to 9 image, 3 video and 3 audio refs | 24 fps MP4 |

## Quick start

1. Install ComfyUI 0.43.0 or newer and the `unplatform-ai-provider-node` pack.
2. Open `minimax-h3-upai.json` in ComfyUI.
3. ComfyUI reads the download and install links from the workflow. Open the right-side Error tab and click Install for missing packs and Download for missing models. No copy-paste from this readme.
4. This flow uses no GGUF. All model files are auto-downloaded from the workflow.
5. Restart ComfyUI after installing a pack. Save the workflow once so UPAI exports it.
6. Check `GET /upai/api/v1/health`.

## Memory

Full speed means the largest phase fits in VRAM. Smaller cards run with offload to system RAM, slower. System RAM must hold the model files.

| Phase | Weights | Headroom | Total |
|---|---:|---:|---:|
| Text encode | 25.28 GiB | 0.50 GiB | 25.78 GiB |
| Sampling, 1280x736, 124 frames | 19.53 GiB | 4.00 GiB | 23.53 GiB |
| Decode, VAEDecode | 5.13 GiB | 3.00 GiB | 8.13 GiB |

Full-speed VRAM: 32 GB card. System RAM: 64 GB.

| File | Size | Note |
|---|---:|---|
| `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | 25.28 GiB | measured |
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 19.53 GiB | measured |
| `minimax_h3_video_vae_fp16.safetensors` | 4.85 GiB | measured |
| `minimax_h3_audio_vae_fp32.safetensors` | 0.56 GiB | measured, loads at 0.28 GiB |
| `minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors` | 0.58 GiB | estimate, not resident |

The audio VAE loads at 0.50x its fp32 file size. LoRAs patch the model and do not stay resident. The measured text encode phase is 25.78 GiB, under 29.6 GiB usable.

Low VRAM:

- Use the `minimax-h3-fast` preset.
- In UPAI Settings, set `default_resolution` to `0.4` or lower (node id 10), set `duration_min` and `duration_max` to 2 to 3 s, and set `count_max` to 1. The 17k+5 frame rule gives 56 frames at 2 s and 73 frames at 3 s.
- Start ComfyUI with `--fast-disk`.
- If decode runs out of memory, start ComfyUI with `--cpu-vae`. MiniMax uses `VAEDecode` nodes 61 and 67.

## Models

| File | Folder | Note |
|---|---|---|
| `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | `models/text_encoders` | auto |
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `models/diffusion_models` | auto |
| `minimax_h3_video_vae_fp16.safetensors` | `models/vae` | auto |
| `minimax_h3_audio_vae_fp32.safetensors` | `models/vae` | auto |
| `minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors` | `models/loras` | auto, optional |

No GGUF file is used. Only these five files are needed.

Licenses:

- `qwen3vl_32b_minimax_h3_int8_convrot.safetensors`: License: Apache-2.0. Source: https://huggingface.co/Qwen/Qwen3-VL-32B-Instruct
- `minimax_h3_ref2va_pruned_int8_convrot.safetensors`, `minimax_h3_video_vae_fp16.safetensors`, `minimax_h3_audio_vae_fp32.safetensors`: License: MiniMax H3 Community License Agreement. Source: https://huggingface.co/MiniMaxAI/MiniMax-H3
- `minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors`: License: Apache-2.0. Source: https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI

The audio ref is a text field. Put the audio file under `ComfyUI/input/` and type its name. The node patches the path at dispatch.

## Settings

| Preset | Steps | Sampler | Scheduler | Turbo LoRA |
|---|---|---|---|---|
| `minimax-h3` | 20 | `res_multistep` | `simple` | no |
| `minimax-h3-fast` | 8 | `euler` | `simple` | yes |

Frames follow 17k+5: 5, 22, 39, ..., 362. Duration runs 4 to 15 s. 5 s gives 124 frames, 10.125 s gives 243 and 15.08 s gives 362. fps is 24.

Sizes snap to a 32-pixel grid. Tiers run from 0.2 to 2.0 area and 6 aspect ratios (16:9, 21:9, 4:3, 1:1, 3:4, 9:16), with 84 exact size overrides. The default is 0.9 at 16:9, 1280x736. H3-Base official area cap is 0.98 MP, 1344x768 at 16:9. Labels 1.0 and above exceed the cap.

References allow 9 image refs, 3 video refs and 3 audio refs, max 12 files total. Video refs run 2 to 15 s at 24 fps. Audio refs run 2 to 15 s. Prompt max is 7000 characters. Start and end frames are optional.

## Troubleshooting

- UPAI nodes missing: install `unplatform-ai-provider-node` and restart ComfyUI.
- Loader red: the H3 model file is missing from the listed folder.
- Audio ref ignored: put the file in `ComfyUI/input/` and type the file name.
- Frames plus refs work together: up to 9 image, 3 video and 3 audio refs.
- Out of memory: use a lower area label such as 0.4 or 0.2, use the fast preset, and close other GPU apps. The fast preset lowers steps, not model size.
- Health check: `curl http://127.0.0.1:8188/upai/api/v1/health`.
