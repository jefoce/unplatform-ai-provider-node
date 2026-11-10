# AGENTS.md

Rules for coding agents working in this repo. Setup and how-tos are in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Architecture is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Before saying done

```bash
ruff check . && ruff format --check . && pyright && pytest
```

- Also run `pytest -m comfy` (E2E against a real ComfyUI, `UPAI_COMFY_DIR` set) when touching `upai_provider/nodes`, `routes.py`, `jobs.py`, `uploads.py`, `mock_assets.py`, `web/` or the export flow.
- After a change to `web/upai.js`: hard reload the ComfyUI tab (cached extension JS already hides changes) and check the browser console.
- Report what was verified and what was not. Measured numbers say "measured", guesses say "estimate". Name the ComfyUI version and frontend version used.

## Git

- Flow: version branch `X.Y.Z` (no `v`), pull request into `releases`, squash merge. Tag `vX.Y.Z` and the release come from the workflow after checks pass, never by hand.
- `releases` is the default branch and receives version-branch PRs. Never commit to it.
- Work on the branch named after the next version. Create it locally if it does not exist.
- Required checks on the PR: `checks-ok`, `e2e`, `workflows-lint`, `pr-version`.
- Release: open the PR titled `X.Y.Z`, squash merge. After checks the release workflow tags `vX.Y.Z`, creates the GitHub release from the CHANGELOG section, and publishes to the Comfy Registry with `REGISTRY_ACCESS_TOKEN`. Never tag by hand.
- The first commit on a new branch bumps `version` in `pyproject.toml` and `upai_provider/version.py`, and opens `## X.Y.Z - unreleased` in `CHANGELOG.md`. Replace `unreleased` with the date in the last commit before the PR.
- Commit message: `TYPE: Message`. No version in commit messages, the squash commit carries it. Optional description after a blank line. No task ids or review ids.
- Message completes "If applied, this commit will ...", imperative mood, no trailing period.
- Types: CRITICAL (critical fix), FIX (bug fix), HACKFIX (workaround until a proper fix), FEAT (user-facing feature added or removed), CODE (internal feature invisible to users), PERF (performance), SECURITY (security improvement), DOCS (documentation), STYLE (formatting only), REFACTOR (no behavior change), TEST (tests), CHORE (tiny fixes, config, deps), CI (workflows and checks), TEXT (user-facing text only).
- Examples: `FEAT: Add UPAI Settings node`, `SECURITY: Run guard for every route`, `DOCS: Explain the job lifecycle`.
- One commit per item. Bulk tool runs get their own commit, usually STYLE.
- The pull request and its squash commit are titled `X.Y.Z`.
- Before 1.0: patch for fixes only, minor for features, behavior changes, protocol additions or file format changes. Propose the bump in the report.
- Never push, force push, tag, create releases, open pull requests, publish to the Comfy Registry or change remotes unless the user asks for that exact action in the current message.
- Before saying done: `git status` is clean except untracked review files, and the report lists the branch and commit hashes.

## Hard rules

- Runtime imports only what ComfyUI `requirements.txt` guarantees: stdlib, `aiohttp`, `yarl`, `av`, `numpy`, `torch`, `Pillow`. `pydantic` is "non essential" there, so not used. Dev tools (`pytest`, `pytest-aiohttp`, `jsonschema`, `ruff`, `pyright`) stay in the `dev` extra.
- Python floor 3.10 (ComfyUI `requires-python`). No `ExceptionGroup`, `TaskGroup`, `tomllib`, `typing.Self`.
- ComfyUI surface allowlist. Imports from ComfyUI only: `server.PromptServer` (routes, `instance.address`, `instance.port`), `comfy_api.latest` (`io`, `ui`, `ComfyExtension`, `Input`, `Types`), `folder_paths` (`get_input_directory`, `get_temp_directory`, `get_user_directory`), `nodes.NODE_CLASS_MAPPINGS` (read only), `comfy.cli_args.args`, `comfyui_version`. Everything else goes through public HTTP (`/prompt`, `/ws`, `/api/jobs`). A new entry needs a DECISIONS.md record.
- ComfyUI app middleware is limited to `/upai` and `/api/upai` paths. It re-raises every other path unchanged.
- Never monkeypatch ComfyUI. No wrapping of `send_sync`, queue or executor.
- `upai_provider/mock_server.py` and `upai_provider/protocol/` import no ComfyUI module.
- Every protocol route runs `guard(request)` first: Origin check, remote peer check, token check. The internal export route runs `internal_guard` instead: same-origin `Origin` and `Host`, `Content-Type: application/json`, and the peer policy without a token.
- Never log the token, data URLs, upload bytes or prompt text. Log prompt length. Status may show the last four characters of the token.
- Every filesystem write goes under the pack-owned dirs (`<input>/upai`, `<temp>/upai`, `<user>/default/upai`). Ids are validated before any path join. Never delete outside them. Never `shutil.rmtree` on a path built from request data without the id check.
- Bounds and tunables live in `upai_provider/constants.py`. Docs tables are tested against them.
- Protocol changes are additive within `upai/1`: new optional fields, new routes. A rename or removal is `upai/2`. Every protocol change updates `protocol/spec.md`, `protocol/schema/`, `protocol/fixtures/` and the CHANGELOG in the same commit.
- `protocol/` stays MIT and holds no code copied from ComfyUI or the pack.
- Error texts describe the current workflow only. Never suggest another workflow or model.
- ComfyUI error text is stored raw, cut to one line and `ERROR_TEXT_MAX_CHARS`.
- Never put ComfyUI or model files in the repo. Test workflows use core nodes and no models.

## Mock first

- `UPAI_MOCK=1` inside ComfyUI, or `python -m upai_provider.mock_server` standalone, for any change that touches routes, jobs or the protocol. Mock covers pending, in progress, completed, `[fail]`, `[slow]`, `[invalid]`.
- One suite: `pytest tests/test_access.py tests/test_health.py tests/test_jobs_routes.py tests/test_uploads.py tests/test_images.py tests/test_videos.py`.
- Real model runs only when asked. Say which workflow, settings, inputs, GPU and run time.

## Python

- Type hints everywhere, `pyright` basic mode clean. No `Any` in pack code except at the ComfyUI boundary, narrowed right after.
- Data from outside (request bodies, JSON on disk, WS messages, ComfyUI responses) is parsed by one function per shape in `upai_provider/protocol/` that returns a frozen dataclass or raises `ProtocolError`. No raw dict access past the parser.
- Fixed string sets come from one tuple: `JOB_STATUSES = ('pending', 'in_progress', ...)`, `JobStatus = Literal[...]`, a guard built on the tuple. No `Enum` in pack code. ComfyUI enums (`io.FolderType`) are used as ComfyUI requires.
- Stored JSON changes are additive: new fields optional with a default. No version fields. The first breaking change adds `schema_version: 2` (files without it are version 1) and a migration next to the parser. An invalid file is skipped and logged, never raised at boot.
- Writes to JSON files are atomic (temp file in the same dir, then `os.replace`).
- Up to 2 arguments positional. 3 or more: keyword-only after `*`.
- Boolean names start with `is_`, `has_`, `can_`, `should_` or `did_`.
- Async code never blocks the loop. File and `av` work over a few ms goes to `asyncio.to_thread`. Node `execute` code runs on ComfyUI's worker, not the loop.
- One `aiohttp.ClientSession` per pack instance, closed on shutdown.
- Shared state (job store, registry) has one owner module and one `asyncio.Lock`. Never read-modify-write a job without it.
- Long work never runs inside a route handler beyond media materialize and the loopback submit.
- Catch narrow exceptions. A broad `except Exception` only at a route or task boundary, logged with the job id.

## Modules

- No re-exports, except `__init__.py` at repo root (ComfyUI entry) and `upai_provider/protocol/__init__.py` (public parse functions).
- `routes.py` holds HTTP only. Logic lives in `endpoints/`, `registry.py`, `jobs.py`, `jobs_file.py`, `jobs_output.py`, `jobs_sweep.py`, `job_service.py`, `uploads.py`, `mock_assets.py`, `validation*.py`, `execution*.py`, `materialize*.py`, `tracker*.py`, `export*.py`, `scheduler.py`, `textutil.py`, `content_urls.py`, `fileutil.py`, `diskutil.py`, `encoder.py`, `sizing.py`, `runtime.py`.
- `nodes/` never imports `routes.py`. Nodes talk to the job store through `jobs_output.register_output`.
- Direction, where an arrow means "may import":

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
| `mock.py` | `protocol`, `constants` |
| `mock_server.py` | `routes`, `runtime`, `jobs`, `uploads`, `mock`, `config`, `protocol`, `constants` |
| `protocol/` | stdlib only |
| `protocol/capabilities.py`, `protocol/constants.py`, `protocol/status.py`, `protocol/ids.py`, `protocol/errors.py`, `protocol/wire.py` | stdlib and sibling `protocol` modules |
| `protocol/export.py` | `capabilities`, `shapes` |
| `protocol/shapes.py` | `capabilities`, `constants`, `status` |
| `protocol/parse_common.py` | `errors`, `ids`, `shapes` |
| `protocol/parse_requests.py` | `parse_common`, `shapes` |
| `protocol/parse_files.py` | `constants`, `errors`, `ids`, `parse_common`, `shapes`, `status` |
| `textutil.py` | `constants` |
| `content_urls.py` | stdlib only |
| `timeutil.py` | stdlib only |
| `version.py` | stdlib only |

## Style

- Terse. Short sentences. No hype, no filler, no em dashes in prose, comments or docstrings.
- Comments explain why, not what. Docstrings for public functions only, one line when possible.
- Early returns over nested branches. Lookup dicts over if/elif chains that only return.
- Formatting is `ruff format`. Import order is ruff `I`. Never hand-format around it.
- Blank line before `return`, `if`, `raise` and loops when the block above is not empty.
- Smallest diff that solves the problem. No drive-by refactors outside the files you touch.
- Fix every rule violation in the files you touch in one pass.
- Files stay near 200 lines, split by job.
- Never put review item ids in code, test names, comments, docs or commit messages. Review ids live only in review files.

## Docs

| Topic | Document |
|---|---|
| Setup, scripts, mock modes, running ComfyUI for tests, debugging, release | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) |
| Runtime, data, job lifecycle, bounds, edge cases | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Threat model and controls | [docs/SECURITY.md](docs/SECURITY.md) |
| Why a design exists | [docs/DECISIONS.md](docs/DECISIONS.md) |
| Protocol for clients | [protocol/spec.md](protocol/spec.md) |
| User-facing behavior | [README.md](README.md) |

DECISIONS.md entry format, newest first:

```
## YYYY-MM-DD - Title

Decision: what was chosen, with names of files and values.

Why: the reason, with measured numbers when there are any.

Rejected: alternatives and why not.
```

SECURITY.md sections: 1. Scope, 2. Assets, 3. Threats and controls, 4. Known limits, 5. Reporting.

CHANGELOG.md: `## X.Y.Z - date`, one summary line, then `### Added`, `### Changed`, `### Fixed`, `### Security` as needed. User-facing words, no file names.

## Quick map

- ComfyUI entry: `__init__.py` (`comfy_entrypoint`, `WEB_DIRECTORY = "./web"`)
- Nodes: `upai_provider/nodes/`
- Routes: `upai_provider/routes.py`
- Exports and capabilities: `upai_provider/registry.py`
- Jobs: `upai_provider/jobs.py`, `jobs_output.py`, `jobs_sweep.py`
- Jobs file: `upai_provider/jobs_file.py`
- Progress: `upai_provider/tracker.py` (planned)
- Uploads and quota: `upai_provider/uploads.py`
- Mock assets: `upai_provider/mock_assets.py`
- Media format check: `upai_provider/media_sniff.py`
- Config: `upai_provider/config.py`
- Bounds: `upai_provider/constants.py`
- Clock: `upai_provider/timeutil.py`
- Mock: `upai_provider/mock.py`, `upai_provider/mock_server.py`
- Frontend: `web/upai.js`
- Protocol: `protocol/` (MIT)
- Tests: `tests/` (unit, contract), `tests/e2e/` (marker `comfy`), `tests/workflows/` (CPU test workflows)
