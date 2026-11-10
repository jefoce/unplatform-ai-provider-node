# Run on less VRAM and RAM

Full speed means the largest phase fits in VRAM. Smaller cards run with offload to system RAM, slower. System RAM must hold the models.

ComfyUI 0.43 uses dynamic VRAM by default. `enables_dynamic_vram()` returns true unless you start ComfyUI with `--disable-dynamic-vram`, `--highvram`, `--gpu-only`, `--novram` or `--cpu`. Dynamic VRAM moves weights between VRAM and system RAM, and can stream from disk with `--fast-disk`. `--lowvram` does nothing while dynamic VRAM is on.

Caching matters too. `--cache-ram` is the default mode. `--cache-none` lowers RAM and VRAM use at the cost of running every node again on each run.

Qwen 2.1 and MiniMax H3 rows are measured. Other workflows are estimates.

## Headroom

| Phase | Headroom |
|---|---:|
| Text encode | 0.50 GiB |
| Image sampling, default resolution | 2.00 GiB |
| Video sampling, default resolution and frame count | 4.00 GiB |
| Video decode with VAEDecode | 3.00 GiB |
| Video decode with VAEDecodeTiled | 1.50 GiB |

Usable VRAM = card GiB - 2.4 GiB. The 2.4 GiB covers the CUDA context, display and allocator reserve. Measured on a 32 GiB card: 30,122 MiB usable before any model.

## Calibration

Measured on ComfyUI 0.43.0. Plain weights load at 1.00x the file size. LoRAs patch the model and do not stay resident. The MiniMax audio VAE loads at 0.50x its fp32 file size.

| File | File | Loaded | Ratio |
|---|---:|---:|---:|
| MiniMax H3 text encoder | 25.28 GiB | 25.28 GiB | 1.00 |
| MiniMax H3 main model with turbo LoRA | 19.53 GiB | 19.53 GiB | 1.00 |
| MiniMax H3 video VAE | 4.85 GiB | 4.85 GiB | 1.00 |
| MiniMax H3 audio VAE | 0.56 GiB | 0.28 GiB | 0.50 |
| Qwen 2.1 text encoder | 8.71 GiB | 8.71 GiB | 1.00 |
| Qwen 2.1 main model with LoRAs | 6.76 GiB | 6.76 GiB | 1.00 |
| Qwen 2.1 VAE | 0.63 GiB | 0.63 GiB | 1.00 |

## Per-workflow estimates

| Workflow | VRAM (full speed) | System RAM | Largest phase | Largest file |
|---|---:|---:|---|---|
| FLUX.2 Klein | 16 GB | 24 GB | sampling 10.79 GiB | fp8 UNET 8.79 GiB |
| Ideogram 4 | 24 GB | 32 GB | sampling 19.29 GiB | two UNETs 17.29 GiB together |
| Krea 2 | 24 GB | 24 GB | sampling 14.57 GiB | UNET 12.57 GiB |
| LTX 2.5 | 32 GB | 48 GB | sampling 24.96 GiB | transformer 20.03 GiB |
| MiniMax H3 | 32 GB | 64 GB | text encode 25.78 GiB | text encoder 25.28 GiB, measured |
| MOSS Image | 12 GB | 24 GB | text encode 9.32 GiB | text encoder 8.82 GiB |
| Qwen 2.1 | 12 GB | 24 GB | text encode 9.21 GiB | text encoder 8.71 GiB, measured |
| Wan 2.2 | 24 GB | 48 GB | sampling 18.35 GiB | Q8 UNET 14.35 GiB |
| Z-Image | 12 GB | 16 GB | sampling 8.73 GiB | Q8 UNET 6.73 GiB |

Full speed is the largest phase. Offload is slower and needs system RAM.

## Situations

- The card also drives the display. Reserve VRAM for the desktop with `--reserve-vram` or `--vram-headroom`. Start with 1 GB and add more if the desktop stutters.
- An 8 to 12 GB card needs a smaller file or a smaller size. Use a Q4 or Q5 GGUF, 1K for images, 480p or 720p for video, and one job at a time.
- With 16 GB system RAM, use Z-Image. Other workflows need 24 GB or more.
- When the model file is bigger than system RAM, dynamic VRAM can stream from disk. Use `--fast-disk` on an NVMe disk and keep free space for the cache.
- Video decode can run out of memory on high frame counts. Lower the resolution and the frame count first. Then use tiled decode where the guide offers it, or start ComfyUI with `--cpu-vae`.
- Windows does not oversubscribe GPU memory. A job that asks for more VRAM than the card has fails instead of using system RAM as VRAM. Set the pagefile to 1.5 to 2 times the largest model file on an NVMe disk.
- Apple Silicon uses one memory pool for the CPU and GPU. An MPS out-of-memory error is a hard failure. Keep `PYTORCH_MPS_HIGH_WATERMARK_RATIO` at 1.7.

## Flags

The help text column is the exact ComfyUI 0.43 text.

| Flag | Help text | When to use | Cost |
|---|---|---|---|
| `--reserve-vram` | "Set the amount of vram in GB you want to reserve for use by your OS/other software. By default some amount is reserved depending on your OS." | The card also drives the display. | Less VRAM for the model. |
| `--vram-headroom` | "Set the amount of vram in GB for DynamicVRAM to maintain as extra headroom above default. ComfyUI will try and keep this much VRAM completely free and unused, even counting VRAM from other apps." | Other apps share the card. | Less VRAM for the model. |
| `--cache-none` | "Reduced RAM/VRAM usage at the expense of executing every node for each run." | Tight RAM or VRAM. | Every node runs again, so jobs are slower. |
| `--cache-ram` | "Use RAM pressure caching with the specified headroom thresholds. This is the default caching mode. The first value sets the active-cache threshold; the optional second value sets the inactive-cache/pin threshold. Defaults when no values are provided: active 10% of system RAM (min 2GB, max 10GB), inactive 100% of system RAM (max 128GB)." | Keep the default. | Uses RAM to avoid reloads. |
| `--fast-disk` | "Force disk-backed dynamic loading and offload over unpinned RAM. Can be faster for users with fast NVME disks." | The model file is bigger than RAM. | Needs free NVMe space. Disk can be slower than RAM. |
| `--disable-fast-disk` | "Disable disk-backed dynamic loading and offload over unpinned RAM. Overrides --fast-disk." | Disk streaming is slower or the disk is full. | Back to RAM only. |
| `--high-ram` | "Can improve performance slightly on high RAM or on systems where pagefile use is preferred over model loading." | Plenty of RAM or a fast pagefile. | May use more RAM or pagefile. |
| `--disable-smart-memory` | "Force ComfyUI to agressively offload to regular ram instead of keeping models in vram when it can." | Another app needs VRAM. | More reloads, slower jobs. |
| `--cpu-vae` | "Run the VAE on the CPU." | Image or video decode runs out of memory. | Slower decode. |
| `--novram` | "When lowvram isn't enough." | Very small card and enough system RAM. | Very slow, heavy RAM use. |
| `--lowvram` | "Doesn't do anything if dynamic vram is enabled. If dynamic vram isn't being used this option makes the text encoders run on the CPU." | Only with dynamic VRAM off. | No effect in the default mode. |
| `--disable-dynamic-vram` | "Disable dynamic VRAM and use estimate based model loading." | You need the old loader behavior. | Gives up dynamic VRAM. |
| `--enable-dynamic-vram` | "Enable dynamic VRAM on systems where it's not enabled by default." | Dynamic VRAM is off but you want it. | None beyond dynamic VRAM itself. |
| `--use-split-cross-attention` | "Use the split cross attention optimization. Ignored when xformers is used." | Attention memory is the peak. | Slower sampling. |
| `--use-quad-cross-attention` | "Use the sub-quadratic cross attention optimization . Ignored when xformers is used." | Attention memory is the peak. | Slower sampling. |
| `--force-fp16` | "Force fp16." | A model is fp32 or bf16 and the card supports fp16. | Can corrupt fp8 or int8 files. |
| `--fp8_e4m3fn-text-enc` | "Store text encoder weights in fp8 (e4m3fn variant)." | The text encoder is the largest file. | Some quality loss. |
| `--highvram` | "By default models will be unloaded to CPU memory after being used. This option keeps them in GPU memory." | The model fits and you want speed. | Uses more VRAM and turns dynamic VRAM off. |
| `--gpu-only` | "Store and run everything (text encoders/CLIP models, etc... on the GPU)." | Everything fits and you want speed. | No CPU fallback, turns dynamic VRAM off. |
| `--cpu` | "To use the CPU for everything (slow)." | No usable GPU. | Very slow. |

## Do not

- Do not rely on `--lowvram` in 0.43. Dynamic VRAM ignores it.
- Do not use `--novram` with less RAM than the largest model file.
- Do not use `--force-fp16` on fp8 or int8 files.
- Do not queue several jobs.
- Do not enable previews on a tight machine.

## Pack settings

- Keep UPAI Output [`preview`](nodes/upai-output.md) off.
- Set `max_running` to 1.
- Results are deleted after the app downloads them.
- Offer smaller sizes and fewer frames in [UPAI Settings](nodes/upai-settings.md) so the app shows low-memory choices.

`PYTORCH_ALLOC_CONF=expandable_segments:True` may reduce fragmentation. The variable name for the installed PyTorch 2.15.0 was not confirmed. Check the PyTorch release notes.
