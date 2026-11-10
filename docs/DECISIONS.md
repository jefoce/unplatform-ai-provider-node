# Decisions

Newest first. Format: Decision, Why, Rejected.

## 2026-11-10 - Job progress is aggregate and monotonic

Decision: `tracker_state` keeps `_job_prompts` and `_job_done` next to
`_job_counts`. A job percent is the average over its child prompts: finished
counts 100, not started counts 0, started counts its own percent. `node`,
`value` and `max` come from the running child with the lowest submit index.
Samplers on the output path switch the percent to steps: 0 to 5 before the first
sampler, `5 + 90 * done_steps / total_steps` while sampling, 95 to 99 after the
last sampler, and 100 only on completion. Steps are read from the sampler
`steps` input or the linked primitive `value`; cached samplers leave both the
total and the done count. The done set is limited to path nodes that are not
cached. `_update_progress` stores `max(previous.percent, new.percent)` capped at
99. `JobStore.update` applies the same floor and cap, and `JobStore._finalize`
sets 100 on completion and clears queue position and waiting state.

Why: with several child prompts, per-prompt percentages made the job percent
fall when children interleaved, and a node that gained a progress max changed
its weight and lowered the percent. A step count also maps to time better than
one node out of many for sampler-heavy workflows such as MiniMax H3 and LTX 2.5.

Rejected: per-prompt percentages, which go backwards on interleaving. Node count
only, which jumps at the first sampler and ignores the sampler steps. Clamping
only at the route, which still let the mock driver and the store lower a stored
percent.

## 2026-11-10 - Deleted source is invalid and exports refresh by inode

Decision: `export_registry` adds `DELETED_REASON = "source workflow was deleted"`.
When `source_root` is set and the source stat raises `OSError`, every model in
that export is `invalid` with that reason, before any other status check. The
export cache signature is `(name, st_ino, st_mtime_ns, st_size)` per file. The
export route writes or removes only the current workflow id, so a rename or
save-as leaves the old export on disk and the old id shows as deleted.

Why: two saves in the same mtime tick with the same byte size kept the old
catalog entry. The inode changes on the atomic replace, so including it forces a
reload. A deleted source file should not leave a runnable-looking model behind.
This supersedes the 2026-11-09 manual-export entry for a source path that no
longer exists.

Rejected: dropping the export file on rename, which deletes a valid snapshot the
user did not ask to remove. Leaving the model `ready` when the source stat fails,
which hides a broken source from the catalog.

## 2026-11-09 - Custom node help from web/docs markdown

Decision: node help ships as markdown under `web/docs/<node_id>.md`,
inside the existing `WEB_DIRECTORY = "./web"`. The frontend tries
`web/docs/<node_id>/<locale>.md` first, then `web/docs/<node_id>.md`,
and renders it with marked plus DOMPurify. Node ids are the
`NODE_CLASS_MAPPINGS` keys (`UPAIModel`, `UPAIPrompt`, and so on). No new ComfyUI
import and no new route: the pack static mount `/extensions/<pack_dir>` already
serves `web/`.

Why: frontend 1.57.6 `nodeHelpService.ts` builds those two paths, and
`nodes.EXTENSION_WEB_DIRS` mounts the pack `web/` dir at
`/extensions/unplatform-ai-provider-node`. Core nodes use the separate
`comfyui_embedded_docs` package, which a pack cannot use.

Rejected: a top-level `docs/` folder (not served), raw HTML help (markdown is
rendered), a custom route or import (no new ComfyUI surface).

## 2026-11-09 - Per-kind reference label templates

Decision: `PromptCapability.reference_labels` holds an optional map keyed by
`image`, `video` and `audio` next to the global `reference_label`. The UPAI Model
node gains `prompt_reference_label_image`, `_video` and `_audio` string inputs.
`split_reference_labels` validates the map: unknown kinds are dropped with a
warning, empty values are skipped, non-strings and invalid templates are errors.
The export builds the map from the three node inputs, `protocol/wire.py` emits it
under `prompt` only when non-empty, and `export_capabilities_io.py` decodes it,
logging bad entries at warning level.

Why: one global template cannot label a picture, a clip and a clip's audio
differently. Clients want a per-kind default such as `<Picture {n}>` while still
falling back to the global template and then their own default.

Rejected: a separate capability per kind, which adds three fields for one
concept. Rejecting an unknown kind at the whole-model level, which would make a
forward-compatible extra key break the model.

## 2026-11-09 - Results quota removes only expired results

Decision: `runtime.enforce_results_quota` measures result bytes off the event
loop, removes expired final results oldest first (`status == "expired"` or
`expires_at <= now`), and raises `507` with `insufficient_storage` when the total
still exceeds `results_quota_bytes`. Unexpired results are never removed by the
quota. `job_service.create_job` also checks free space on the result volume.

Why: deleting unexpired results on a create lost work a client could still
fetch. Expired results are already past their TTL, so reclaiming them first
keeps the quota useful without surprising data loss.

Rejected: deleting the oldest final result regardless of expiry, which removes
data the client can still use. Returning `507` without reclaiming expired files,
which leaves space unused.

## 2026-11-09 - Manual export stays listed without a source file

Decision: a stored export whose source workflow file is missing or unreadable
keeps its models in the catalog. `export_registry.resolved()` no longer skips a
model when the source stat fails. `stale` only applies when the source exists and
its mtime is newer than the export.

Why: a manual API-JSON export has no source workflow file, so the failed stat hit
`continue` and the model disappeared from the catalog. That fallback path is the
only way to publish a workflow when the UI save hook cannot run, and a valid
export must not vanish because its source is gone.

Rejected: marking a no-source export `stale`, which hides it behind a status that
asks for a re-export. Dropping it from the catalog, which breaks the fallback.

## 2026-11-09 - Disk guard defaults

Decision: `min_free_disk_bytes` defaults to 5 GiB (`MIN_FREE_DISK_BYTES`) and
`results_quota_bytes` to 20 GiB (`RESULTS_QUOTA_BYTES`) in
`upai_provider/constants.py`. Both can be overridden in `config.json` or with
`UPAI_MIN_FREE_DISK` and `UPAI_RESULTS_QUOTA`. Before an upload, a result or a
job record is written, the pack compares free space on the pack volume and the
total stored results against the two bounds. A write that cannot fit returns
`507` with `insufficient_storage`.

Why: without a guard a full disk fails writes mid-job and can exhaust the host.
5 GiB leaves headroom for ComfyUI outputs and temp files, and 20 GiB caps results
well below a typical desktop disk while still holding many jobs.

Rejected: no default, which never trips. Statting every result file on each
write, which is slow. One combined limit, because uploads and results fail for
different reasons and a client needs to know which.

## 2026-11-09 - Data URLs dedupe into the upload store

Decision: a data URL is decoded, hashed with SHA-256 and stored once in the
content-addressed upload store under `<input>/upai/uploads`. The job materializes
it by reference instead of writing a second copy under `<input>/upai/<job>`. The
same bytes sent through `POST /api/v1/uploads` and inline as a data URL resolve
to one file.

Why: one data URL body can be tens of MB, and copying it per job duplicated
bytes and grew the input folder. Content addressing means the same image costs
one file whether it arrives as an upload or inline, and upload pinning keeps it
while a non-final job uses it.

Rejected: copying each data URL per job, which duplicates bytes and slows
materialize. A separate inline store, which gives the same bytes a second sweep
path.

## 2026-11-09 - Prompt reference label capability

Decision: `prompt.reference_label` is an optional string or null on the prompt
capability, additive in `upai/1`. The UPAI Model node takes a
`prompt_reference_label` string and the export stores the stripped template. The
validator in `upai_provider/protocol/capabilities.py` caps it at 64 characters,
accepts only the placeholders `{kind}`, `{Kind}`, `{n}` and `{i}`, rejects stray
braces, and requires `{n}` or `{i}`. An invalid template marks the model invalid
with the validator reason.

Why: clients need one place to learn how the server expects reference labels,
while existing clients that ignore the field keep working. `{n}` and `{i}` let a
template address either numbering base, and requiring one of them stops a
template that cannot vary per slot.

Rejected: a structured label object (more surface for one string). Making the
field required (breaks old exports). Validating only on the client (the server
already rejects bad exports).

## 2026-11-09 - Video resolution labels

Decision: Video models take any resolution label with a size source. A label is
kept when it is one of `VIDEO_RESOLUTIONS` in `upai_provider/constants.py`
(`480p`, `720p`, `768p`, `1080p`, `2K`, `4K`) or when a `size_overrides` entry
gives it a size. `SHORT_SIDE` maps the pixel short side for `480p`, `720p`, `768p`
and `1080p`. UPAI Settings resolution and aspect inputs are text, validated
against the node lists. At export a label with neither a kind-list membership nor
a size override is dropped with a warning, and a model with no label left is
`invalid`. The MiniMax flows set `480p,720p,768p` with per-aspect `size_overrides`
for 0.4, 0.9 and 0.98 MP.

Why: the app shows the labels from the model list and accepts any custom
resolution label since VideoGen `5d21641f`. A Combo input rejects a value outside
its list, so the old `0.9` default ended every MiniMax job with `422
workflow_invalid`. Text inputs accept the label the app sends, and the export
still drops a label with no size source.

Rejected: keeping megapixel buckets and mapping them in the app, which changes
app types, pricing keys and the picker. A Combo with every label, which still
rejects a value the app derives later. Restricting video to the app list, which
hides an override-backed label the app can send.

## 2026-11-09 - Video encoder fallback

Decision: the video writer opens the first available encoder in this order:
`libx264`, `h264_nvenc`, `h264_videotoolbox`, `libopenh264`, `mpeg4`. The choice
is cached for the process and logged once.

Why: the PyAV wheel on macOS may not ship `libx264`, so the first open failed and
every video job failed. The order prefers x264 when present, then a hardware
encoder per platform, and ends with the always-present `mpeg4`.

Rejected: pinning one encoder, which fails where that encoder is missing.
Probing on every job, which repeats the log and the cost.

## 2026-11-09 - Audio reference paths stay inside the input directory

Decision: an audio reference is a text field. The pack resolves the name inside
the ComfyUI input directory and rejects an absolute path or a `..` part. The
upload button stays removed for now.

Why: free text reached `resolve_file`, which accepted absolute paths and `..`,
so any readable file on the ComfyUI host could be loaded as audio by whoever
edits the workflow. The upload combo crash root cause is still unknown. Checked:
core `LoadAudio` uses the same Combo plus `UploadType.audio` and works in the
same frontend; our options come from `input_files(AUDIO_SUFFIXES)` and may be
empty; core builds its list with `filter_files_content_types`. None of these
proves the crash, so the text field stays with containment.

Rejected: restoring the upload combo without the root cause, which can crash the
editor again. Accepting paths outside the input directory, which widens file
read.

## 2026-11-09 - Atomic replace retries and platform CI

Decision: `upai_provider/fileutil.py` `replace_file` retries `os.replace` on
`PermissionError` up to `REPLACE_RETRIES` (5) times with a short backoff capped
at 0.5 s. File replacement goes through it. Unit CI runs Ubuntu, macOS and
Windows on Python 3.10 and 3.12. E2E stays on Ubuntu.

Why: on Windows, `os.replace` raises `PermissionError` when another process
holds the target open, so a save could fail without a retry. The pack targets any
OS, and only a Windows runner proves the path and file behavior.

Rejected: catching the error and dropping the write, which loses data. Adding
Windows as one extra job, which leaves one Python version untested.

## 2026-11-06 - Create returns before background dispatch

Decision: `Scheduler.enqueue` starts `tick()` as a background task and returns. The
create route sends its 202 before materialize and submit. `execute_job` re-reads the
job after the prompt is built and before every submit, and aborts when the job is
final.

Why: awaiting dispatch in the route blocked the create response for the whole media
build. Measured with a 4 s URL fetch, create took 4.01 s before the change and
0.001 s after, so a cancel can now land while the build runs.

Rejected: awaiting dispatch inside the route, which makes cancel during build
impossible through the API.

## 2026-11-06 - Request stored before the job is dispatchable

Decision: `job_service.create_job` calls `remember_request` before
`store.create_pending`, and forgets the entry when the queue rejects the job.

Why: a scheduler tick could see the pending job between the store insert and the
request insert, fail it with `job request is missing`, and lose the work. Measured
in 2 of 4 live max_running=2 runs before the change, 0 of 4 after.

Rejected: retrying dispatch until the request appears, which hides an ordering bug.

## 2026-11-06 - Shutdown through atexit

Decision: root `__init__.py` registers `atexit` in `on_load`. The handler stops
the scheduler and tracker, cancels and gathers `runtime.tasks`, and closes
`runtime.session` and `runtime.fetch_session` once each.

Why: ComfyUI 0.43.0 exposes only `on_load` and `get_node_list` on an extension.
No shutdown hook exists, so sessions and background tasks would leak until the
process exits.

Rejected: monkeypatching ComfyUI to add a shutdown hook. Leaving cleanup out,
which keeps sockets and tasks open during a reload.

## 2026-11-06 - TLS loopback through comfy.cli_args.args

Decision: root `__init__.py` reads `comfy.cli_args.args.tls_keyfile` and
`tls_certfile` to decide the loopback scheme. The pack reads only these two
paths from `comfy.cli_args.args`. When both are set, `_comfy_base_url()`
returns `https://127.0.0.1:<port>` and `Runtime.tls_enabled` is true. Loopback
HTTPS runs with certificate checks off for the loopback address only. This is
the only new entry in the ComfyUI surface allowlist.

Why: ComfyUI serves loopback over HTTPS when both `--tls-keyfile` and
`--tls-certfile` are passed. Plain HTTP loopback calls would fail. The
certificate is self-signed and used only on 127.0.0.1, so checking it adds no
security against a local attacker who already controls loopback.

Rejected: probing the port or parsing `sys.argv`, which duplicates ComfyUI
argument handling. Disabling certificate checks for every host, which would
weaken other calls. A pack TLS setting, which would drift from the ComfyUI
process.

## 2026-11-06 - Cancel by job state through ComfyUI public routes

Decision: `Scheduler.cancel(job_id)` marks a pack-queued job `cancelled` and
leaves ComfyUI untouched. A dispatched job that is still in the ComfyUI queue is
removed with `POST /api/jobs/{id}/cancel`. A running job is stopped with
`POST /interrupt` and `{"prompt_id": id}`. The scheduler slot stays taken until
the tracker sees `execution_interrupted`, `execution_error` or
`execution_success`, or `/api/jobs/{id}` no longer lists the prompt. With
`count_mode=runs`, cancel every child prompt.

Why: marking the store row alone left the prompt running on the GPU while the
scheduler started the next job. The public routes target one prompt and need no
ComfyUI patch.

Rejected: marking the store only, which doubles GPU load. A global `/interrupt`,
which also kills a foreign prompt. Reading the queue or executor internals.

## 2026-11-06 - Internal export same-origin, JSON, peer checked

Decision: `/upai/internal/export` accepts a request only when `Origin` is present
and its host:port equals `Host`, `Content-Type` is `application/json`, and the
peer passes the normal peer policy: local always, LAN only with `allow_lan`,
public never. The Host allowlist still applies. The route has no token, because
the ComfyUI frontend cannot hold one.

Why: a JSON content type forces a CORS preflight from another origin, so a web
page cannot post a plain form. With `--listen`, the earlier route let any LAN
host post exports.

Rejected: a token on this route, which the frontend cannot set. Skipping the
peer check, which exposed the route on a LAN.

## 2026-11-06 - Wire model id accepts 129 characters

Decision: model ids on the wire match `^[a-z0-9][a-z0-9._-]{0,128}$`, a 64-char
workflow id, a dot and a 64-char model id. This is additive within `upai/1`.

Why: each part caps at 64 characters, so the combined id needs 129. The earlier
pattern rejected valid exports.

Rejected: shortening either part, which loses the stable workflow or model id. A
breaking `upai/2` change for a length bound.

## 2026-11-06 - negative_prompt request and capability

Decision: create bodies accept an optional `negative_prompt` string. Dispatch
patches it into the UPAI Prompt node `negative` input. The model capability
`negative_prompt` is true only when that Prompt node has its `negative` output
wired.

Why: models with a negative prompt path need it to run. Advertising the
capability only when wired stops a client from sending text that the graph drops.

Rejected: always advertising it, which promises a field the workflow ignores. A
separate model flag, which duplicates graph state.

## 2026-11-06 - Runs mode names each child and batch file

Decision: with `count_mode=runs`, `upai_job` is patched as
`<job_id>_r<run index>`. UPAI Output writes `<job>/<run>-<batch index>.<ext>`.
Result URLs are ordered by run, then by batch index.

Why: every child prompt received the same job id and wrote `<job>/0.<ext>`, so
later files overwrote earlier ones. The `<job>_r<run>` separator keeps the name
valid on Windows, where `:` is reserved for a drive letter.

Rejected: a random UUID4 as the output folder, which loses the parent job link.
One file per run with no batch suffix, which cannot name a batch. A `:` separator,
which Windows rejects in the run directory name.

## 2026-11-06 - Request body kept in memory only

Decision: the raw create body is kept in `Runtime.requests` in memory, never
written to `jobs.json`, and dropped when the job becomes final.

Why: data URLs make one body tens of MB. Persisting it made every status write
rewrite the body and could grow `jobs.json` to GBs. A non-final job fails at boot
after a restart, so the body is never needed on disk.

Rejected: storing the body on the job record, which was the P2 behavior.
Re-parsing a file copy at dispatch, which adds a second copy.

## 2026-11-06 - partial_execution_targets for per-model isolation

Decision: every job submits `POST /prompt` with
`partial_execution_targets: [<model output node>]`.

Why: one workflow holds several Model and Output pairs. Measured on 0.43.0, the
chosen path runs and validates alone while an unrelated broken link is ignored.
Only a missing node class anywhere in the prompt still rejects the whole POST
with 400, so export validation checks classes before dispatch.

Rejected: removing other branches from the prompt, which rewrites the exported
graph. Separate workflows per model, which forces a file copy per model.

## 2026-11-06 - Stable instance id in instance.json

Decision: `instance.py` creates one UUID4 at
`<user>/default/upai/instance.json` and reuses it for the life of the install.
Health returns it and the pack uses `upai-<instance>` as the ComfyUI client id.

Why: two endpoints that report the same id are one machine, so a client can show
one queue. A stable client id also makes the pack traceable in the ComfyUI queue
after a restart.

Rejected: a random id per process, which makes two connections look like two
machines. A ComfyUI core id, which does not exist.

## 2026-11-06 - Scheduler queue, FIFO and foreign job detection

Decision: `scheduler.py` dispatches pending jobs in `sequence` order. It runs a
job only when running pack jobs are below `max_running` and no foreign ComfyUI
prompt is pending or running. Foreign ids come from
`/api/jobs?status=pending,in_progress` and are compared with stored pack ids.
`max_pending` bounds every non-final job.

Why: the local ComfyUI queue is shared with the UI and other clients. FIFO keeps
pack order stable, and the `/api/jobs` check prevents a pack job from competing
with a foreign prompt. `queue_position` and `waiting_on` tell the client why a
job waits.

Rejected: dispatching on `status` WS `queue_remaining` alone, which also counts
pack jobs. A strict global queue lock, which would leave ComfyUI idle when the
pack queue is empty.

## 2026-11-06 - Job request snapshot in jobs.json

Decision: the parsed create body is stored on the job record as `request` at
create time. Dispatch reparses that snapshot and materializes media then.
Superseded by "Request body kept in memory only" above.

Why: a job must survive a restart with the same inputs, and a queued job waits
behind other work. Storing the raw request keeps validation and dispatch on one
shape and avoids a second client call.

Rejected: holding the request in memory only, which loses queued work on restart.
Materializing media at create time, which fills the input folder for jobs that
may never run.

## 2026-11-06 - Tracker reconnect and server URL update

Decision: the tracker keeps one loopback websocket, polls `/api/jobs/{id}` every
second while the socket is down, and reconnects with backoff. The first create
request updates the server URL and calls `Tracker.set_server_url`.

Why: ComfyUI can restart or bind a different port. The page that calls the pack
knows the live address, so the first request is the reliable source. Polling
keeps progress and completion working during a socket outage.

Rejected: a fixed URL from startup, which breaks after a port change. Websocket
only, which stalls during a reconnect.

## 2026-11-06 - Limits may hide image frames even when nodes exist

Decision: a Limits setting that turns image frames off hides them from the model
capabilities even when Start Frame or End Frame nodes are present. A required
frame without a node remains an export error.

Why: the node is a reusable template. Limits is the published contract, so it
must be able to hide an optional capability without rewiring the graph.

Rejected: deriving frames from nodes alone, which forces a graph edit to remove
an optional input.

## 2026-11-06 - Custom websocket types for UPAI links

Decision: inter-node links use `io.Custom("UPAI_MODEL")` and
`io.Custom("UPAI_LIMITS")`. The API prompt carries the same link types.

Why: a model handle and a limits object are not ComfyUI core types. Measured on
frontend 1.57.6, the custom types register, link in the UI and survive
`app.graphToPrompt()`.

Rejected: encoding links as strings, which loses type safety. Reusing an IMAGE
or LATENT slot, which would collide with real media inputs.

## 2026-11-06 - Export every model, no source conversion

Decision: an export holds one entry per UPAI Model and the shared API prompt once.
The registry exposes each model independently with its own status. The server
never converts the saved workflow JSON.

Why: one broken model must not hide the others. `graphToPrompt()` is the measured
frontend path to the API map, and ComfyUI has no server-side converter.

Rejected: one export per workflow, which would fail all models together. A
server-side converter, which would duplicate frontend behavior and drift.

## 2026-11-05 - ComfyUI app middleware limited to pack prefixes

Decision: `upai_middleware` is appended to the ComfyUI aiohttp app and touches
only paths starting `/upai` or `/api/upai`. Every other path is re-raised
unchanged.

Why: router-generated 404 and 405 responses under the pack prefixes need the
protocol header and JSON error envelope, and ComfyUI's static catch-all shadows
unknown `/upai` paths.

Rejected: per-handler headers only, which misses router errors. Rewriting or
monkeypatching `PromptServer`, which AGENTS forbids.

## 2026-11-05 - Module table extensions for the P1 split

Decision: the module table gains three edges: `routes` imports `runtime`,
`endpoints.*` imports `runtime` and `registry`, and `mock_server` imports
`routes` and `runtime`.

Why: the P1 split moved handlers into `endpoints/` and shared state into
`runtime.py`. Reusing that wiring keeps one route table and one runtime for the
real server and the mock.

Rejected: duplicating the 14 routes and their wiring inside `mock_server.py`.
See the "Standalone mock reuses the real routes" entry below for the original
mock-server exception.

## 2026-11-05 - Loopback /prompt instead of queue internals

Decision: the pack submits jobs with a loopback `POST /prompt` and sets
`prompt_id` to the job id.

Why: `/prompt` is the stable public entry and accepts `prompt_id`. The internal
queue tuple changed shape and is not a contract.

Rejected: `prompt_queue.put`, which reaches into private state and breaks on
ComfyUI updates.

## 2026-11-05 - No pydantic, stdlib dataclasses only

Decision: protocol shapes are frozen dataclasses parsed by one function per shape.

Why: pydantic is not guaranteed by ComfyUI `requirements.txt`, and the Python
floor is 3.10. Dataclasses plus explicit parsers cover the protocol without a new
runtime dependency.

Rejected: pydantic models, attrs, hand-written dict checks scattered through
routes.

## 2026-11-05 - protocol/ under MIT inside the GPL repo

Decision: the spec, schemas and fixtures in `protocol/` are MIT while the pack is
GPL-3.0.

Why: clients of any license can copy the protocol material. MIT is GPL-compatible,
so it may sit inside the GPL repo. The protocol code is written fresh and copies
no ComfyUI code.

Rejected: GPL for the protocol, which would limit client reuse. A separate repo,
which would drift from the implementation.

## 2026-11-05 - Tracker uses public WS and /api/jobs only

Decision: the P2 tracker opens one loopback `/ws` connection and falls back to
`/api/jobs/{id}` polling. It does not monkeypatch ComfyUI.

Why: public routes survive ComfyUI updates. WS carries progress, `/api/jobs`
carries status. The module allowlist forbids patching `send_sync`, the queue or
the executor.

Rejected: wrapping `send_sync`, reading internal executor state.

## 2026-11-05 - Export through the frontend save hook and graphToPrompt

Decision: `web/upai.js` wraps `api.fetchApi`, reacts to a successful workflow save
and calls `app.graphToPrompt()` before posting to the internal export route.

Why: ComfyUI stores the UI format and has no server-side converter. `graphToPrompt`
is the measured frontend path that produces the API map.

Rejected: converting workflow JSON on the server. Manual API JSON drops as the
only path.

## 2026-11-05 - Standalone mock reuses the real routes

Decision: `mock_server.py` imports `routes.py` and serves the same route table.

Why: duplicating 14 routes would drift from the real server. This is the one
import-direction exception to the AGENTS module table, and it is documented there.

Rejected: a separate mock router, a second route table.

## 2026-11-05 - Content index is zero-based

Decision: result content uses `index=0` for the first item.

Why: it matches the URL array and the client reference. Video exposes only index
0, image checks the index against the result count.

Rejected: one-based indexes, which are off by one against `urls`.

## 2026-11-05 - Job urls is an array of absolute URL strings

Decision: a job exposes `urls` as a tuple of absolute URL strings.

Why: it matches the app shape measured in the reference and the OpenRouter video
contract. The client can fetch each URL without knowing the pack base.

Rejected: relative paths, which force the client to rebuild the base. A single
URL string, which cannot describe multiple images.

## 2026-11-05 - Mock assets generated once and cached

Decision: the mock PNG and MP4 are generated with Pillow and av on first use and
cached under the pack data dir. They are never committed.

Why: no binaries in the repo, deterministic bytes, and no per-request generation
cost.

Rejected: committing small fixtures, which adds binary churn. Generating on every
request, which wastes CPU.
