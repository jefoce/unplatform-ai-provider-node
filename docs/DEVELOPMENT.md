# Development

Setup for the pack repo and the ComfyUI test install. Measured on macOS arm64,
2026-11-05. `<repo>` is this checkout and `<comfyui-dir>` is a separate ComfyUI
checkout, for example `~/comfyui-dev`.

## Repo layout

```bash
cd <repo>
git status
find . -path ./.venv -prune -o -path ./.git -prune -o -type f -print | sort
```

The module layout is in [docs/ARCHITECTURE.md](ARCHITECTURE.md). The repo holds
`upai_provider/`, `web/`, `protocol/`, `docs/`, `tests/` and the top-level
project files.

## Dev venv

```bash
cd <repo>
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]" aiohttp av numpy Pillow
source .venv/bin/activate
```

Measured versions:

- Python 3.12.12
- pytest 9.2.0
- ruff 0.17.3
- pyright 1.1.414
- aiohttp 3.14.5
- av 19.0.2
- numpy 2.5.4
- Pillow 13.0.0

`pyproject.toml` sets `[tool.setuptools] packages = ["upai_provider",
"upai_provider.protocol", "upai_provider.endpoints", "upai_provider.nodes"]`.
Without an explicit list, setuptools refuses the editable build because
`protocol/` is also a top-level directory.

## ComfyUI test install

Path: `<comfyui-dir>`

Measured:

- ComfyUI 0.43.0
- Commit `ab08f7b2caa6d4007ecde3762116c6193613f43b`
- Frontend `comfyui-frontend-package` 1.57.6
- torch 2.15.0
- MPS available: true
- ComfyUI Python 3.12.12

Recreate the checkout:

```bash
mkdir -p <comfyui-dir>
cd <comfyui-dir>
git init
git remote add origin https://github.com/comfyanonymous/ComfyUI.git
git fetch --depth 1 origin ab08f7b2caa6d4007ecde3762116c6193613f43b
git checkout FETCH_HEAD
git rev-parse HEAD
```

Use the full commit hash. `git fetch origin ab08f7b` fails with
`couldn't find remote ref ab08f7b`.

Install ComfyUI dependencies:

```bash
cd <comfyui-dir>
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

No ComfyUI source file is modified. No model files are downloaded.

## Pack symlink

```bash
ln -s <repo> \
  <comfyui-dir>/custom_nodes/unplatform-ai-provider-node
ls -l <comfyui-dir>/custom_nodes/unplatform-ai-provider-node
```

Measured target:
`<comfyui-dir>/custom_nodes/unplatform-ai-provider-node -> <repo>`

## Run ComfyUI in real mode

Real mode is the default. Do not set `UPAI_MOCK`. The pack builds the export
catalog, starts the sweep loop, the tracker and the scheduler when ComfyUI loads
the custom node.

```bash
cd <comfyui-dir>
./.venv/bin/python main.py --port 8189 --disable-auto-launch
```

Leave the user install on port 8188 untouched.

CPU fallback, if device init fails:

```bash
cd <comfyui-dir>
./.venv/bin/python main.py --port 8189 --disable-auto-launch --cpu
```

Measured startup on MPS:

```
Device: mps
ComfyUI version: 0.43.0
Starting server
To see the GUI go to: http://127.0.0.1:8189
```

HTTP check while running:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8189/
```

Measured status: 200.

The root `__init__.py` is the ComfyUI entry. A symlinked repo is loaded from it
through the `custom_nodes` directory.

Capture a startup log:

```bash
cd <comfyui-dir>
./.venv/bin/python main.py --port 8189 --disable-auto-launch \
  > /tmp/upai-comfy-startup.log 2>&1 &
```

Stop it with `kill` on the background PID.

## Real mode settings

The pack writes `<user>/default/upai/instance.json` on first load. The file holds
one UUID4 and stays stable. Health returns it as `instance_id`.

`max_running` bounds executing pack jobs. Set it in
`<user>/default/upai/config.json` or with `UPAI_MAX_RUNNING`. Default 1, range 1
to 8. Jobs over `max_pending` return `429` with `queue_full`.

## Config file and environment

`<user>/default/upai/config.json` is overridden by environment variables.
Defaults and meanings are in [ARCHITECTURE.md](ARCHITECTURE.md#config) and
`upai_provider/constants.py`.

| Env | Key |
|---|---|
| `UPAI_TOKEN` | `token` |
| `UPAI_ALLOW_REMOTE` | `allow_remote` |
| `UPAI_ALLOW_LAN` | `allow_lan` |
| `UPAI_ALLOWED_HOSTS` | `allowed_hosts` |
| `UPAI_MAX_RUNNING` | `max_running` |
| `UPAI_MIN_FREE_DISK` | `min_free_disk_bytes` |
| `UPAI_RESULTS_QUOTA` | `results_quota_bytes` |

A bad non-token field falls back to its default with one warning that names the
field. A present but invalid `token`, or a file that is not a JSON object, marks
the config invalid and every route returns `503` with `config_invalid` until the
file is fixed. The ComfyUI Settings panel under Unplatform AI writes `token`,
`allow_lan` and `max_running` through the config route.

## Video encoder

`upai_provider/encoder.py` picks the first H.264 encoder that opens: `libx264`,
`h264_nvenc`, `h264_videotoolbox`, `libopenh264`, `mpeg4`. The choice is cached
per process and logged once as `UPAI video encoder: <name>`. When no encoder
opens, `select_encoder` raises and the video job fails.

## Runs mode, negative prompts and cancel

Set `count_mode` to `runs` on the UPAI Settings node to send one prompt per run.
Each run gets a distinct seed, `upai_job` is `<job id>_r<run index>`, and files
are written as `<run>-<batch>.<ext>`. URLs are ordered by run, then batch.

Wire the UPAI Prompt `negative` output to advertise `negative_prompt` for the
model. A create body may then send `negative_prompt`, which dispatch patches into
that input.

Cancel is state aware. A pack-queued job is marked `cancelled`. A dispatched job
still in the ComfyUI queue is removed with `POST /api/jobs/{id}/cancel`. A
running job is stopped with `POST /interrupt` and `{"prompt_id": id}`. The slot
stays taken until ComfyUI reports the stop. With `count_mode=runs`, every child
prompt is cancelled.

Save a workflow with a UPAI Model node and a UPAI Output node. On save,
`web/upai.js` calls `app.graphToPrompt()` and publishes the export through
`/upai/internal/export`. The model appears in `/upai/api/v1/videos/models` or
`/upai/api/v1/images/models` as `<workflow-id>.<model id>`. Use the Publish
workflow button on the UPAI Model node to republish without saving again.

If the export changes, hard reload the ComfyUI tab. Cached extension JS hides the
change. Check the browser console for export errors.

## Tests

```bash
cd <repo>
source .venv/bin/activate
ruff check . && ruff format --check . && pyright --pythonpath .venv/bin/python && pytest
```

Layout:

- `tests/conftest.py` builds a mock runtime and an aiohttp test client in a temp
  dir. `tests/helpers.py` holds shared request helpers.
- `tests/test_access.py` covers guard, Origin, Host, peer classes and token.
- `tests/test_health.py` covers health and model catalog routes.
- `tests/test_jobs_routes.py` covers create, get, cancel, content and sync wait.
- `tests/test_uploads.py` covers upload storage and quota.
- `tests/test_images.py` covers image create and content.
- `tests/test_videos.py` covers video create and content.
- `tests/test_config.py` covers config file and env overrides.
- `tests/test_validation.py` covers shared validation helpers.
- `tests/test_socket.py` covers socket-level peer and Host checks.
- `tests/test_jobs.py` covers the store, output registration, boot repair and
  sweep.
- `tests/test_protocol.py` covers request and response parsers.
- `tests/test_schema.py` validates every fixture against its JSON Schema.
- `tests/test_consistency.py` covers protocol, docs and constants agreement.
- `tests/test_nodes_*.py` covers the UPAI nodes, sizes, frames, refs and Output.
- `tests/test_export_*.py` covers the graph walk, capabilities, registry, files
  and the internal export route.
- `tests/test_scheduler*.py` covers FIFO dispatch, limits, foreign jobs and the
  instance id.
- `tests/test_exec_*.py` covers materialize, prompt patching, submit and content.
- `tests/test_tracker*.py` covers progress, reconnect, completion and cancel.
- `tests/e2e/` runs against a real ComfyUI started by the harness.

Tests never import ComfyUI, except `tests/e2e/`, which starts ComfyUI as a
subprocess. Unit tests exercise `upai_provider` and `protocol/` only.

Fixtures use shortened mock timings from `tests/conftest.py`: complete 0.15 s,
fail 0.10 s, slow 0.40 s, pending 0.02 s, tick 0.01 s.

Validate one protocol fixture with `jsonschema`:

```bash
.venv/bin/python -c "import json, jsonschema; jsonschema.validate(json.load(open('protocol/fixtures/health.json')), json.load(open('protocol/schema/health.schema.json')))"
```

`pytest tests/test_schema.py` runs the same check for every fixture and schema.

## End-to-end tests

```bash
UPAI_COMFY_DIR=<comfyui-dir> pytest -m comfy
```

The harness starts ComfyUI itself with `--cpu`, a temporary base directory and
port 8189. It symlinks this repo into that base directory, writes a frame image
into the temp input directory, waits for `/object_info`, then runs the workflows.
It stops the process at the end. Do not start another ComfyUI on 8189. Set
`UPAI_COMFY_PORT` to use a free port instead.

Workflow fixtures live in `tests/workflows/ui/` and `tests/workflows/api/`:
single image, single video, two models, shared prompt, lowered Limits, required
Limits frames, bypassed and muted nodes, and a subgraph. They use core nodes and
no model files.

## Live checks

Run these in real mode on port 8189 before a release. The slow workflow uses core
nodes only, so no model files are downloaded.

- `count_mode=runs` with count 3 returns three distinct files with different
  seeds and three URLs in run order.
- Cancel the slow workflow while it runs. The ComfyUI log shows the interrupt,
  the job becomes `cancelled`, and the next pack job waits for ComfyUI.
- Cancel a dispatched job still in `/api/jobs`. It disappears from the queue.
- Real sync `POST /upai/api/v1/images` returns the same bytes as `/content`.
- A prompt containing `[invalid]` runs normally in real mode.
- Export with a foreign `Origin`, or with `Content-Type: text/plain`, returns
  `403` or `415`. A save from the ComfyUI UI returns `200`.
- Re-export after deleting every UPAI Model node removes those models from
  `/models`.
- A job with a 5 MB data URL keeps `jobs.json` under 100 KB.
- After the sweep, an expired job has no `<input>/upai/<job>` or
  `<temp>/upai/<job>` directory.
- TLS: start ComfyUI with `--tls-keyfile` and `--tls-certfile`, then create and
  complete a job. The pack calls ComfyUI over loopback with `https` and skips
  certificate checks for loopback only.

The slow cancel files are `tests/workflows/slow/slow-cancel-ui.json` (UI) and
`slow-cancel.json` (API). The UI workflow uses a 4096x4096 `EmptyImage` and 250
`ImageInvert` nodes, measured at 3.3 s on CPU ComfyUI 0.43.0. Save it as
`workflows/slow-cancel-ui.json`, or publish it from the UPAI Model node.

## Lint, types and CI

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright --pythonpath .venv/bin/python
.venv/bin/pytest -m "not comfy"
```

CI is `.github/workflows/checks.yml`. The `checks` job runs on push and pull
request on Ubuntu, macOS and Windows with Python 3.10 and 3.12, fail-fast false.
It creates `.venv` with the matrix Python, installs `-e ".[dev]"`, numpy and the
ComfyUI floors `aiohttp>=3.11.8`, `Pillow>=10.1.0` and `av>=17.0.0`, then runs the
same four commands. It prints the resolved versions of those three packages and
the Python running pyright.

A separate `e2e` job stays on Ubuntu with Python 3.12. It checks out ComfyUI at
commit `ab08f7b2caa6d4007ecde3762116c6193613f43b`, installs CPU torch and the
ComfyUI requirements, symlinks this repo into `custom_nodes`, sets
`UPAI_COMFY_DIR` and runs `pytest -m comfy`. The pip cache and the venv are
cached. No model files are downloaded and there is no GPU. Actions are pinned by
full commit SHA.

## Release

`releases` is the default branch. It receives version-branch PRs and never a
direct commit. The first PR needs the bootstrap `releases` branch at `b6f846e`.

Flow:

1. Work on the version branch `X.Y.Z` (no `v`). Bump `version` in
   `pyproject.toml` and `__version__` in `upai_provider/version.py`. Open the
   CHANGELOG section `## X.Y.Z - unreleased`, then replace `unreleased` with the
   date in the last commit before the PR.
2. Open a PR titled exactly `X.Y.Z` into `releases` and squash merge it once the
   required checks pass.
3. The release workflow runs after the merge.

Required checks: `checks-ok`, `e2e`, `workflows-lint`, `pr-version`.

`.github/workflows/pr-version.yml` runs `.github/scripts/version-check.sh` on
PRs into `releases`. It requires the PR title, `pyproject.toml` and
`version.py` to agree on `X.Y.Z`, a dated CHANGELOG section
`## X.Y.Z - YYYY-MM-DD` (no `unreleased`), and a version greater than the newest
`v*` tag. A Dependabot PR into `releases` is instead labeled `apply-on-next`
and gets one marker comment; close it and apply the updates on the next version
branch.

`.github/workflows/release.yml` runs on push to `releases` and on
`workflow_dispatch`. A `guard` job skips the release job unless `GITHUB_REF` is
`refs/heads/releases`. The release job first runs the full checks workflow, then
resolves the version with `.github/scripts/release-version.sh`. It tags `vX.Y.Z`
at the merge commit only when checks pass, creates the GitHub release with the
notes from the matching CHANGELOG section, and publishes to the Comfy Registry
with `REGISTRY_ACCESS_TOKEN`. An unreleased CHANGELOG section logs a notice and
skips the tag and publish instead of failing. A tag that already points at HEAD
is a re-run: the workflow continues, skips the "must be greater" check and reuses
the existing tag and release. A tag at another commit fails. A missing token
fails after the tag and release exist, so adding the secret and re-running the
workflow publishes. Before publishing, the workflow reads the registry versions
endpoint and skips the publish when the version is already published. The publish
step installs `comfy-cli==1.25.0`, sets `DO_NOT_TRACK=1` and runs
`comfy node publish --token "$REGISTRY_ACCESS_TOKEN"`. Never tag or release by
hand.

First release:

1. The publisher id is `jefoce` in `[tool.comfy]`.
2. Create an API key at `https://registry.comfy.org`, on the publisher page under
   API keys, and store it as the `REGISTRY_ACCESS_TOKEN` repository secret.
3. Let the release workflow publish. Never run `comfy node publish` locally.
   Registry versions are immutable.
4. A new version stays `NodeVersionStatusPending` until the registry scan passes.
   Check it with
   `curl -s https://api.comfy.org/nodes/unplatform-ai-provider-node/versions`.
   ComfyUI Manager installs only active versions, so a pending or failed version
   is not offered there.

The `validate` job runs `comfy node validate` with `comfy-cli==1.25.0`, and
`checks-ok` requires it.

## Social preview

`docs/images/social-preview.png` is the GitHub social preview, 1280x640. Upload
it under repo Settings > Social preview. It is generated by
`scripts/make_hero.py`.

The Comfy Registry icon is `docs/images/registry-icon.png`, 400x400, generated by
`scripts/make_icons.py`. `[tool.comfy] Icon` points at the raw URL on the
`releases` branch.

Verify a release with:

- `curl -sS https://api.comfy.org/nodes/unplatform-ai-provider-node/versions`
  and check the version list and `latest_version`.
- The registry page for `unplatform-ai-provider-node`.
- `comfy node install unplatform-ai-provider-node`.

## Image assets

The image scripts are dev-only. All three are deterministic. Rerunning them
reproduces the committed bytes.

- `scripts/make_icons.py` builds the model, app and ComfyUI tiles and the
  registry icon. Needs Pillow only.
- `scripts/make_shots.py` crops, rounds and shadows the workflow screenshots
  from `docs/images/src/shots/`. Needs Pillow only.
- `scripts/make_hero.py` builds `hero-dark.svg`, `hero-dark.png`, the full MP4
  loop, the 6 s cut and `social-preview.png`. It needs Playwright, ffmpeg and
  fontTools. The Inter font and its OFL license live in `docs/images/fonts/`.
  The card text and Lucide icons are converted to static paths.

## Mock server

Mock mode is still available. Inside ComfyUI set `UPAI_MOCK=1` to serve the three
mock models through the pack routes without real execution.

Standalone mock on port 8190:

```bash
cd <repo>
source .venv/bin/activate
python -m upai_provider.mock_server --port 8190 --data-dir /tmp/upai-mock-dev
```

The data dir holds `jobs.json`, `uploads/` and `assets/`. Without `--data-dir` it
uses `<temp>/upai-mock`.

`--host` sets the bind address (default `127.0.0.1`). `--allow-lan` accepts LAN
peers. To serve another device use `--host 0.0.0.0 --allow-lan`, or `--host ::`
for IPv6. Without a token, `--allow-lan` logs a warning.

Prompt markers: `[fail]` fails at 3 s, `[slow]` runs for 60 s, `[invalid]` returns
`422 workflow_invalid`. The default run completes at 6 s. Tests override the
timings through `MockTimings`.

The mock imports no ComfyUI module.

## Ports

- 8188: user ComfyUI install. Never used by this project.
- 8189: ComfyUI test install and the E2E harness.
- 8190: standalone mock server.

## Models

No model downloads are used for development or tests. Test workflows use core
nodes and no model files.
