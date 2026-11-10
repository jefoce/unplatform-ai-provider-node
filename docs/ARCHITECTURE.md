# Architecture

P2 state. Exported workflows run on ComfyUI through the pack. Mock mode remains
available with `UPAI_MOCK=1`.

## Overview

```
upai/1 client (Unplatform AI first)
        | HTTP JSON, optional Bearer
        v
ComfyUI process (127.0.0.1:8188)
  custom_nodes/unplatform-ai-provider-node
    routes          /upai/api/v1/*   (also /api/upai/api/v1/*)
    export route    /upai/internal/export
    export registry model catalog from exported workflows
    job store       jobs.json, one asyncio lock
    scheduler       FIFO dispatch to the local ComfyUI queue
    execution       loopback /prompt with partial_execution_targets
    tracker         loopback /ws, polling fallback
    nodes           UPAI Model, Limits, Prompt, refs, Settings, Output
    web/upai.js     save hook, publish action, settings panel
```

Base URL the user types in a client: `http://127.0.0.1:8188/upai`. The client
appends `/api/v1/...`, so the health route is `/upai/api/v1/health`.

ComfyUI copies every pack route under `/api`, so `/api/upai/api/v1/health` is
equivalent. The standalone mock serves only `/upai/api/v1/*`.

When ComfyUI runs with `--tls-keyfile` and `--tls-certfile`, the pack uses
`https` and `wss` for loopback and skips certificate checks for loopback only, so
a self-signed certificate works.

## Modules

```
__init__.py        ComfyUI entry, builds the runtime, registers routes, starts tasks
upai_provider/
  routes.py        HTTP only, guards and route table
  runtime.py       shared state, mock driver, sweep, content URL builder
  registry.py      model lookup in one catalog
  jobs.py          job store and boot repair
  jobs_file.py     jobs file load, atomic save, quarantine, boot rules
  jobs_output.py   worker-thread output registration
  jobs_sweep.py    expiry and trim sweep
  job_service.py   job creation, queue cap, sync wait
  execution.py     materialize, dispatch, submit loop
  execution_patch.py  deep-copy and patch one prompt
  execution_runs.py   one prompt or one child prompt per run
  execution_errors.py  workflow, rejection and unavailable errors
  execution_types.py   outcome and store/tracker protocols
  execution_submit.py  loopback prompt POST and node error text
  execution_cancel.py  cancel and untrack submitted runs
  materialize.py   request media entry and materialized input types
  materialize_decode.py  data URL and uploaded file decode
  materialize_store.py   reference stored uploads, fetch media into input/upai/<job>
  materialize_cleanup.py remove job input and result dirs
  scheduler.py     FIFO dispatch within max_running and the foreign queue
  tracker.py       loopback websocket coordinator and reconnect
  tracker_state.py shared tracker state and per-job prompt ids
  tracker_events.py  websocket event handling
  tracker_messages.py  progress and finalization
  tracker_poll.py  /api/jobs polling fallback
  instance.py      stable UUID4 in instance.json
  export_graph.py  graph walk, model membership, export build
  export_rules.py  per-model graph rules and node collection
  export_capabilities.py  per-model capabilities from graph and Limits
  export_capability_limits.py  UPAI Limits overrides and node input readers
  export_capabilities_io.py  capability encode and decode
  export_fields.py  typed field readers
  export_sizing.py  size table for exported models
  export_serialize.py  export file (de)serialization
  export_registry.py      model status and catalog from export files
  export_file.py   export file read and atomic write
  export_types.py  export build dataclasses
  fileutil.py      atomic replace with retry
  diskutil.py      free disk space for a path
  encoder.py       H.264 encoder selection and MP4 encode
  sizing.py        resolution, aspect ratio and size override math
  uploads.py       upload storage, quota ledger, sweep
  mock_assets.py   mock PNG and MP4 generation
  validation.py    shared request validation helpers
  validation_image.py  image request validation
  validation_video.py  video request validation
  media_sniff.py   magic-byte format check
  config.py        config file, env overrides, peer and Host checks
  mock.py          mock timeline, mock model capabilities
  mock_server.py   standalone aiohttp server, no ComfyUI import
  textutil.py      one-line error text helper
  content_urls.py  client-facing result URLs
  timeutil.py      ISO timestamps from an injectable clock
  endpoints/
    system.py      health and model catalog
    create.py      shared create flow
    videos.py      asynchronous video routes
    images.py      asynchronous and synchronous image routes
    jobs.py        job lookup, cancel and delete
    uploads.py     upload storage and mock content
    content.py     real result files with containment check
    export.py      internal workflow export
  nodes/
    extension.py   node list for the ComfyUI extension
    model.py       UPAI Model
    limits.py      UPAI Limits
    prompt.py      UPAI Prompt
    refs.py        image, video and audio refs
    refs_common.py reference and frame validation and result helpers
    frames.py      UPAI Start Frame and UPAI End Frame
    settings.py    UPAI Settings
    settings_math.py  size, frame and count math
    media.py       test media loading
    output.py      UPAI Output, file writing, register_output
    io_types.py    custom UPAI_MODEL and UPAI_LIMITS types
  protocol/        frozen dataclasses, parsers, wire shapes (MIT)
    capabilities.py  capability shape
    constants.py     protocol-owned bounds, stdlib only
    errors.py        error codes
    export.py        export, model and binding shapes
    ids.py           id patterns and run id helpers
    parse_common.py  shared field parsers
    parse_files.py   config and jobs file parsers
    parse_requests.py  create request parsers
    shapes.py        protocol dataclasses
    status.py        job status tuples and guards
    wire.py          wire shapes
  version.py
  constants.py     bounds and tunables
web/upai.js        save hook, publish command, settings panel
protocol/          spec, schema, fixtures (MIT)
```

Import direction. An arrow means "may import". `mock_server.py` also imports
`routes.py`, the one exception to the table below, because duplicating the routes
would drift.

| From | May import |
|---|---|
| `__init__.py` | `upai_provider.*` |
| `routes.py` | `endpoints`, `runtime`, `config`, `protocol`, `constants` |
| `endpoints/` | `routes`, `runtime`, `registry`, `job_service`, `validation`, `validation_image`, `validation_video`, `protocol`, `constants`, `version`, `uploads`, `export_file`, `export_graph`, `timeutil`, sibling `endpoints.*` |
| `job_service.py` | `runtime`, `protocol`, `timeutil` |
| `runtime.py` | `jobs`, `uploads`, `mock_assets`, `mock`, `export_registry`, `scheduler`, `tracker`, `content_urls`, `textutil`, `materialize_cleanup`, `config`, `protocol`, `constants`, `timeutil` |
| `jobs.py` | `jobs_file`, `jobs_sweep`, `protocol`, `constants`, `timeutil` |
| `jobs_file.py` | `protocol`, `timeutil`, `fileutil` |
| `jobs_output.py` | `jobs`, `protocol`, `constants` |
| `jobs_sweep.py` | `protocol` |
| `scheduler.py` | `jobs`, `protocol` |
| `tracker.py` | `tracker_events`, `tracker_messages`, `tracker_poll`, `tracker_state` |
| `tracker_state.py` | `protocol` |
| `tracker_events.py` | `tracker_state` |
| `tracker_messages.py` | `tracker_state`, `content_urls`, `textutil`, `timeutil`, `protocol` |
| `tracker_poll.py` | `tracker_state`, `textutil`, `constants` |
| `execution.py` | `execution_cancel`, `execution_errors`, `execution_patch`, `execution_runs`, `execution_submit`, `execution_types`, `materialize`, `uploads`, `protocol`, `textutil` |
| `execution_patch.py` | `execution_errors`, `materialize`, `protocol` |
| `execution_runs.py` | `execution_patch`, `materialize`, `protocol` |
| `execution_errors.py` | stdlib only |
| `execution_types.py` | `protocol` |
| `execution_submit.py` | `aiohttp`, `execution_errors`, `execution_patch`, `materialize` |
| `execution_cancel.py` | `execution_patch`, `execution_types` |
| `materialize.py` | `materialize_store`, `uploads`, `protocol` |
| `materialize_decode.py` | `media_sniff`, `protocol`, `constants` |
| `materialize_store.py` | `materialize_decode`, `uploads`, `protocol`, `fileutil`, type-only `materialize` |
| `materialize_cleanup.py` | `protocol` |
| `instance.py` | stdlib, `fileutil` |
| `fileutil.py` | stdlib only |
| `diskutil.py` | stdlib only |
| `encoder.py` | stdlib, `av`, `numpy` |
| `sizing.py` | `constants` |
| `export_graph.py` | `export_capabilities`, `export_rules`, `export_types`, `protocol`, `constants` |
| `export_capabilities.py` | `export_capability_limits`, `export_sizing`, `export_types`, `protocol`, `constants` |
| `export_capability_limits.py` | `export_types`, `protocol` |
| `export_capabilities_io.py` | `export_fields`, `protocol`, `constants` |
| `export_fields.py` | stdlib only |
| `export_rules.py` | `export_graph`, `export_types`, `protocol`, `constants` |
| `export_sizing.py` | `sizing` |
| `export_serialize.py` | `export_capabilities_io`, `export_fields`, `export_types`, `protocol` |
| `export_file.py` | `export_serialize`, `export_types`, `protocol`, `fileutil` |
| `export_registry.py` | `export_file`, `export_graph`, `export_types`, `protocol` |
| `export_types.py` | `protocol`, `constants` |
| `validation.py` | `protocol`, `media_sniff` |
| `validation_image.py`, `validation_video.py` | `validation`, `protocol` |
| `media_sniff.py` | stdlib only |
| `registry.py` | `protocol` |
| `uploads.py` | `protocol`, `constants`, `fileutil` |
| `config.py` | `constants`, `protocol` |
| `mock_assets.py` | stdlib, `av`, `Pillow`, `fileutil`, `encoder` |
| `nodes/` | `jobs_output`, `constants`, `fileutil`, `protocol`, `encoder`, `sizing`, sibling `nodes.*`, ComfyUI APIs |
| `textutil.py` | `constants` |
| `content_urls.py` | stdlib only |
| `timeutil.py` | stdlib only |
| `version.py` | stdlib only |
| `mock.py` | `protocol`, `constants` |
| `mock_server.py` | `routes`, `runtime`, `jobs`, `uploads`, `mock`, `config`, `protocol`, `constants` |
| `protocol/` | stdlib only |

## Storage

All paths are pack-owned.

| Data | Path |
|---|---|
| Uploads | `<ComfyUI input dir>/upai/uploads/<sha256>.<ext>` |
| Job inputs | `<ComfyUI input dir>/upai/<job>` |
| Results | `<ComfyUI temp dir>/upai/<job>` |
| Exports | `<ComfyUI user dir>/default/upai/exports/<workflow-id>.json` |
| Instance id | `<ComfyUI user dir>/default/upai/instance.json` |
| Jobs | `<ComfyUI user dir>/default/upai/jobs.json` |
| Config | `<ComfyUI user dir>/default/upai/config.json` |
| Mock assets | `<ComfyUI user dir>/default/upai/assets/mock.png`, `mock.mp4` |

The standalone mock uses one data dir, `--data-dir` or `<temp>/upai-mock`:
`jobs.json` at the root, uploads under `uploads/`, assets under `assets/`.

Job writes are atomic: temp file in the same directory, then `os.replace`.
Upload writes, export writes and the instance file use the same rule. Each
replace goes through `fileutil.replace_file`, which retries a transient
`PermissionError` (a Windows file lock) with a short backoff before it fails.

Uploads are content-addressed by SHA-256 and stored once under
`<input>/upai/uploads`. The same bytes sent twice, or sent as a data URL, resolve
to one file: a data URL is decoded, hashed and stored in the upload store and
then referenced in place. Remote URLs fetched for a job land under
`<input>/upai/<job>`. A stored upload referenced by a non-final job is pinned, so
the expiry sweep skips it until the job is final and its files are gone.

The disk guard runs before an upload, a result or a job record is written. It
compares free space on the pack volume with `min_free_disk_bytes` and the total
stored results with `results_quota_bytes`. When results exceed the quota, the
pack removes expired final results oldest first, then returns `507` with
`insufficient_storage` if the total still does not fit. An unexpired result is
never removed by the quota. `max_inline_bytes` is an informational upper bound
for a JSON body that carries one data URL. The server does not enforce it before
decode, and per-reference caps still apply.

## Export flow

1. Save. `web/upai.js` wraps `api.fetchApi`. A successful workflow save calls
   `app.graphToPrompt()` and posts `{source, prompt, saved_at}` to
   `/upai/internal/export`.
2. Guard. The internal route requires `Origin` with the same host:port as
   `Host`, `Content-Type: application/json`, and a peer that passes the normal
   peer policy: local always, LAN only with `allow_lan`, public never. An
   `allow_remote` + token pair does not open this route. The `Host` allowlist
   still applies. The bearer token is not required here, because the ComfyUI page
   calls it.
3. Derive. The workflow id is the slug of the workflow file stem. The graph walk
   finds every UPAI Model and its Output, the nodes each model owns, and the
   capabilities of each model.
4. Write. One export file holds one entry per model plus the shared API prompt
   once. A workflow with no model writes nothing and returns `invalid`.
5. Publish. The export registry loads every export file on each catalog call.
   Model wire id is `<workflow-id>.<model id>`. The model entry carries a
   `workflow` object `{ id, name }`.

Status is per model. `ready` means the exported snapshot runs. `stale` means the
source workflow is newer than the export. `invalid` means the model cannot run,
for example a missing node class, a bad ref index, a forced frame with no node,
or a source workflow file that was deleted. One invalid model does not hide the
other models in the same export.

UPAI Limits override the graph-derived capabilities per field. Limits can lower
reference counts and duration or count ranges, never raise them. A frame hidden
by Limits is allowed even when its node exists. A required frame with no node is
an export error.

UPAI Settings resolution and aspect inputs are text. The pack validates the
default and test values against the node's `resolutions` and `aspect_ratios`
lists. At export, a label outside the kind's list (image labels for image, video
labels for video) is dropped with a warning. A model with no label left in a
list is `invalid`.

The UPAI Model node carries optional per-kind reference label templates for
image, video and audio. At export the pack builds the `prompt.reference_labels`
map from the three node inputs, drops empty values and warns on an unknown kind.
A client resolves a label from the per-kind template first, then the global
`prompt.reference_label`, then its own default. An invalid template makes the
model `invalid` with a reason that names the kind.

The UPAI Model node carries an optional prompt reference label template. Export
validates the stripped template with `validate_reference_label` and stores it.
An invalid template marks the model invalid.

At create time an optional frame may be absent. The pack substitutes a blank
frame and reports `present=false` from the frame node. A required frame that is
absent from the request returns `400`.

The server does not convert UI workflow JSON. The frontend `graphToPrompt()`
output is the only export source.

## Job lifecycle

1. Create. `guard` checks Origin, Host, peer class and token. The body is parsed
   into a frozen request dataclass. The model id must exist in the export
   catalog and must not be `invalid`. The loopback base URL is read from the
   running ComfyUI server at call time.
2. Validate. Upload refs must exist. Audio reference paths are confined to the
   ComfyUI input directory: a name is resolved there, and an absolute path or a
   `..` part is rejected. Prompt, negative prompt, reference count, duration,
   resolution, aspect ratio, frame rules and image count must fit the model
   capabilities. Media URLs are fetched only when `allow_url_fetch` is on. A
   non-final queue over `max_pending` returns `429`. A body over the aiohttp
   client cap returns `413` with `too_large`. `max_inline_bytes` is
   informational, and per-reference caps still apply after decode. A write the
   disk guard rejects returns `507` with `insufficient_storage`. The raw request
   body is kept in memory only and is never written to `jobs.json`.
3. Queue. A `pending` job enters the store with a sequence number. The scheduler
   ticks every 0.5 s and on enqueue. It dispatches in FIFO sequence order only
   when running pack jobs are below `max_running` and no foreign ComfyUI prompt
   is pending or running.
4. Wait state. A pending job reports `queue_position` and `waiting_on`.
   `waiting_on` is `pack_queue` when pack jobs are ahead and `comfyui_busy` when
   a prompt from the ComfyUI UI or another client is active. Foreign jobs are
   found with `/api/jobs?status=pending,in_progress` and compared with stored
   pack job ids.
5. Dispatch. The scheduler calls `execute_job`. The in-memory request body is
   parsed again, media is materialized under `<input>/upai/<job>`, the exported
   prompt is copied and patched with prompt text, negative prompt, settings, ref
   paths, frame paths and the job id. With `count_mode=runs` it builds one child
   prompt per run, each with its own seed and `upai_job` value
   `<job>_r<run>`. The seed increases by one per run and the job reports the first
   run seed. Identical result bytes are workflow-dependent: a workflow that
   ignores the seed can produce the same output on every run. The pack submits
   each prompt with `client_id` set to `upai-<instance>` and
   `partial_execution_targets` set to the model output node. The first child uses
   the job id as `prompt_id`, later children use a UUID4. Only that model path
   validates and runs. A missing node class anywhere
   in the prompt still rejects the whole POST with 400.
6. Track. The tracker opens one loopback `/ws` connection. It reads
   `execution_start`, `executing`, `progress_state`, `progress`,
   `execution_success`, `execution_error` and `execution_interrupted`. While the
    socket is down it polls `/api/jobs/{id}` every two seconds and reconnects
    with backoff.
   Progress is aggregated per job, not per child prompt. A child that has not
   started counts 0, a running child counts its own percent and a finished child
   counts 100. The job percent is the average of the children, and `node`,
   `value` and `max` come from the running child with the lowest submit index.
   When a sampler node is on the output path, the percent is step based. It
   reads each sampler `steps` input, follows a link to its primitive value, and
   sums the steps of the samplers that are not cached. `KSamplerAdvanced` counts
   only its usable range, `end_at_step - start_at_step` capped at `steps`, where
   `end_at_step` of 10000 means the full steps. Before the first sampler
   step the range is 0 to 5 by node weight, across the sampler steps it is
   `5 + 90 * done_steps / total_steps`, after the last sampler it is 95 to 99 by
   node weight, and 100 only on completion. Without a sampler or with zero
   total steps the percent falls back to a weighted node count. Only nodes in
   the output path and not in the cached set count as done.
   The store never lowers the stored percent while the job is in progress. The
   tracker takes `max(previous.percent, new.percent)` and caps it at 99, and
   `JobStore.update` applies the same floor so the mock driver and any other
   writer cannot move progress backwards. `JobStore._finalize` sets 100 on a
   completed job and clears the queue position and waiting state.
7. Output. UPAI Output writes `<run>-<batch>.<ext>` under `<temp>/upai/<job>`
   and calls `jobs_output.register_output` from the ComfyUI worker thread. The handoff
   uses `asyncio.run_coroutine_threadsafe` with a 10 s timeout. The file list is
   merged into the job record. Video uses the first encoder that opens, in this
   order: `libx264`, `h264_nvenc`, `h264_videotoolbox`, `libopenh264`, `mpeg4`.
   The choice is cached for the process and logged once.
8. Complete. `execution_success` finalizes the job as `completed` with result
   URLs ordered by run, then batch. A rejected prompt becomes `failed` with the
   first node error. An unreachable prompt route becomes `failed` with the
   one-line reason. Cancel marks a pack-queued job `cancelled` without touching
   ComfyUI, removes a dispatched job from the ComfyUI queue, and interrupts a
   running prompt. The slot stays taken until the tracker sees the stop or the
   prompt leaves `/api/jobs`.
9. Content. Only completed jobs serve bytes. The response uses the real media
   type: `video/mp4` for video results and `image/png`, `image/jpeg` or
   `image/webp` for image results. The protocol does not restrict the result
   image format. Video accepts index 0 only. Image index must be inside the
   registered file list. The content route resolves the stored path to its real
   path and rejects anything outside `<temp>/upai`, so a symlink cannot redirect
   a read out of the pack directory. This works on Windows, which has no
   `O_NOFOLLOW`.
10. Sweep and boot. Every 600 s, final jobs past `expires_at` become `expired`,
    their job input and result directories are removed, and old uploads are
    swept. Orphan directories whose job is missing or expired are removed
    independent of sweep order. Uploads still referenced by a non-final job are
    pinned and skipped. At boot a non-final job becomes `failed` with
    `ComfyUI restarted`. A completed job whose files are gone becomes `expired`.
11. Delete. `DELETE` on a final video or image job removes its record and its
    pack-owned input and result files, then returns `204`. A job that is not
    final returns `409` with `invalid_request`. Shared uploads stay untouched, so
    another job that references the same content keeps working.

## Health

`GET /api/v1/health` reports the values a client uses to size a request and
decide what it may do. Identity fields are `protocol`, `server`,
`server_version`, `implementation`, `implementation_version` and `instance_id`.
Access fields are `auth_required` and `lan_allowed`.

| Field | Meaning |
|---|---|
| `max_upload_bytes` | Cap for one upload: the smaller of the store cap and the aiohttp body cap. |
| `upload_quota_bytes` | Total bytes stored across uploads. |
| `max_pending` | Bound on non-final jobs. A create over it returns `429`. |
| `max_running` | Bound on executing pack jobs, from 1 to 8. |
| `max_inline_bytes` | Informational upper bound for a JSON body that carries one data URL. Per-reference caps still apply. |
| `disk_free_bytes` | Minimum free bytes across the upload, result and data volumes, cached and refreshed every 5 s, `0` when unknown. |
| `result_delete` | True when a client may delete a final job with `DELETE`. |

## Measured facts

Measured on macOS arm64, 2026-11-05: ComfyUI 0.43.0 commit
`ab08f7b2caa6d4007ecde3762116c6193613f43b`, frontend
`comfyui-frontend-package` 1.57.6, torch 2.15.0, MPS.

- Save. Frontend 1.57.6 saves with
  `POST /api/userdata/workflows%2F<name>.json?overwrite=false&full_info=true`.
  A hook can wrap `api.fetchApi` and call `app.graphToPrompt()` on a successful
  save.
- `app.graphToPrompt()` returns `{workflow, output}`. Subgraph inner ids are
  `parent:child`. Bypassed nodes (mode 4) and muted nodes (mode 2) are dropped.
  Converted widgets become scalar inputs, not links.
- Loopback. `POST /prompt` accepts `prompt_id`, and `/ws?clientId=...` opened
  before the POST reports the run. A core `EmptyImage` to `PreviewImage` run
  completed in 90.7 ms measured.
- Video. `VideoInput.save_to` with mp4 h264 from 81 frames at 832x480, 16 fps
  took 283.5 ms median, 239382 bytes.
- Restart. ComfyUI wipes the temp directory at startup, so completed jobs from
  before a restart become `expired`.
- Isolation. With `partial_execution_targets: ["3"]`, only nodes 1, 2 and 3 ran
  while node 4 held a broken link. A missing node class anywhere in the prompt
  still rejects the whole POST with 400.
- Foreign queue. A pack `/ws` client receives `status` for prompts queued by
  another client. `/api/jobs?status=pending,in_progress` lists the foreign ids.
- Output handoff. `run_coroutine_threadsafe(...).result()` measured p50 0.160 ms
  over 200 calls, max event loop tick gap 1.749 ms.
- Custom types. `io.Custom("UPAI_MODEL")` and `io.Custom("UPAI_LIMITS")`
  register, link and appear in `app.graphToPrompt()` output.

## Bounds

Values live in `upai_provider/constants.py`.

| Name | Value |
|---|---|
| Max pending jobs | 8 |
| Max running | 1 |
| Result TTL | 24 h |
| Sync wait | 600 s |
| Max upload | 104857600 bytes (100 MiB) |
| Upload quota | 10737418240 bytes (10 GiB) |
| Min free disk | 5368709120 bytes (5 GiB) |
| Results quota | 21474836480 bytes (20 GiB) |
| Inline JSON margin | 1024 bytes |
| Stored jobs | 500 |
| Sweep interval | 600 s (10 min) |
| Disk free refresh | 5 s |
| Scheduler tick | 0.5 s |
| Register output timeout | 10 s |
| Error text | 300 chars |
| Missing poll | 3 |
| Reference max | 20971520 bytes (20 MiB) |
| Mock complete | 6 s |
| Mock fail | 3 s |
| Mock slow | 60 s |
| Mock pending | 0.5 s |
| Mock tick | 0.5 s |

## Config

`<ComfyUI user dir>/default/upai/config.json`, overridden by environment
variables. A bad non-token field falls back to its default with one warning that
names the field. A present but invalid `token`, or a file that is not a JSON
object, marks the config invalid, and every route returns `503` with
`config_invalid` until the file is fixed.

| Key | Env | Default | Meaning |
|---|---|---|---|
| `token` | `UPAI_TOKEN` | empty | Bearer token. Empty means auth off. |
| `allow_remote` | `UPAI_ALLOW_REMOTE` | false | Public peers, and LAN peers when a token is set. |
| `allow_lan` | `UPAI_ALLOW_LAN` | false | LAN peers may connect. It does not change the token requirement. |
| `allowed_origins` | | empty | Extra allowed `Origin` values. |
| `allowed_hosts` | `UPAI_ALLOWED_HOSTS` | empty | Extra `Host` names, comma separated. IP literals, `localhost` and names ending in `.local` always pass. |
| `allow_url_fetch` | | false | Fetch `http(s)` reference URLs. |
| `result_ttl_hours` | | 24 | Result lifetime before expiry. |
| `max_pending` | | 8 | Bound on non-final jobs. |
| `max_running` | `UPAI_MAX_RUNNING` | 1 | Bound on executing pack jobs, 1 to 8. |
| `sync_timeout_sec` | | 600 | Sync create wait. |
| `min_free_disk_bytes` | `UPAI_MIN_FREE_DISK` | 5368709120 (5 GiB) | Minimum free disk before a write is rejected with `insufficient_storage`. |
| `results_quota_bytes` | `UPAI_RESULTS_QUOTA` | 21474836480 (20 GiB) | Bound on stored result bytes. |

LAN peers are addresses in `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`,
`169.254.0.0/16`, `fe80::/10`, `fc00::/7` and `100.64.0.0/10` (Tailscale).
Loopback and the server socket IP are local.

`allow_lan` and auth are separate. `lan_allowed` in health mirrors `allow_lan`
and means LAN mode is on. LAN peers connect without a token unless
`auth_required`.
