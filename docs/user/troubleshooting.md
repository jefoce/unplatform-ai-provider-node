# Troubleshooting

Start with the health route: `http://127.0.0.1:8188/upai/api/v1/health`. It
returns JSON when the pack is loaded.

## Model is invalid or stale

| Status | Meaning | Fix |
|---|---|---|
| `stale` | The workflow file is newer than the last export. | Save the workflow. The old export still runs. |
| `invalid` | The model cannot run. | Read `status_reason`, fix the graph, save again. |

Common invalid reasons:

- A missing node class inside the model path.
- Reference indexes that are not unique and contiguous from 1.
- A required start or end frame with no node.
- No resolution or aspect label left after Limits.
- An image model with a video or audio reference.
- An invalid reference label template.
- The source workflow file was deleted.

If the app shows an old model list, save the workflow or click **Publish
workflow** on the UPAI Model node. Hard reload the ComfyUI tab after an extension
change.

## HTTP errors

| Status | Code | Meaning | Fix |
|---|---|---|---|
| 401 | `unauthorized` | Missing or wrong token. | Set the same token in the app. |
| 403 | `forbidden` | Origin, Host, LAN or remote check failed. | See the table below. |
| 413 | `too_large` | Body over the upload cap, or upload quota full. | Use a smaller file. Free storage. |
| 415 | `invalid_request` | Wrong content type. | Send `application/json`. |
| 429 | `queue_full` | Too many pending jobs. | Wait, or raise `max_pending`. |
| 503 | `config_invalid` | `config.json` is invalid. | Fix or remove the file. |
| 507 | `insufficient_storage` | Free disk too low, or results over quota. | Free disk space. |

403 detail:

| Message | Cause | Fix |
|---|---|---|
| `origin is not allowed` | Browser `Origin` not allowed. | Add it to `allowed_origins`. |
| `host is not allowed` | `Host` name not allowed. | Use an IP, `localhost`, a `.local` name, or add it to `allowed_hosts`. |
| `lan access is disabled` | LAN peer, `allow_lan` off. | Turn on `allow_lan`. |
| `remote access is disabled` | Public peer without `allow_remote` and a token. | Use a private network, or set both. |

## Out of memory

ComfyUI stops with an out-of-memory error when the model, text encoder and decode peak do not fit.

- Start with the [memory guide](memory.md) for flags and per-workflow numbers.
- `--reserve-vram` keeps the desktop from taking VRAM the model needs.
- `--cache-none` lowers RAM and VRAM use. Every node runs again.
- `--cpu-vae` moves the final image or video decode to system RAM.
- Each workflow guide has a Memory section with sizes, lower quant files and exact settings for that workflow.

## Video fails with no encoder

The pack writes MP4 with the first H.264 encoder that opens: `libx264`,
`h264_nvenc`, `h264_videotoolbox`, `libopenh264`, `mpeg4`. When none opens, the
job fails.

- Look for `UPAI video encoder: <name>` in the ComfyUI log to see the choice.
- Install an FFmpeg build with an H.264 encoder if no encoder opens.
- Reinstall the pack if the `av` package is missing.

## Logs

ComfyUI prints pack logs to its own console and log file.

- Config warnings name the bad field. An invalid `config.json` logs one warning
  and returns `503`.
- Export warnings name a skipped model or a dropped label.
- The chosen video encoder is logged once per process.
- The pack never logs the token, prompt text, data URLs or upload bytes. Prompt
  length may appear.

Check the browser console on the ComfyUI tab for frontend export errors.

## Queue

- `max_pending` bounds non-final jobs. Over it returns `429` with `queue_full`.
- `max_running` bounds executing pack jobs, 1 to 8.
- A job waits behind pack jobs in FIFO order, or behind a prompt from the ComfyUI
  UI. `progress.waiting_on` reports `pack_queue` or `comfyui_busy`.
- Cancel is state aware. A pack-queued job is marked cancelled. A running job
  stops after ComfyUI confirms it.

## Results

- Only completed jobs serve bytes.
- Image results use the real type: `image/png`, `image/jpeg` or `image/webp`.
  Read `Content-Type`, do not assume.
- Video results are `video/mp4`.
- Results expire after the result lifetime (default 24 hours) and on ComfyUI
  restart.
