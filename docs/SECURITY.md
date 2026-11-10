# Security

## 1. Scope

This document covers the pack routes under `/upai`, the internal export route,
and the data the pack owns. It does not cover ComfyUI itself, the ComfyUI UI,
`/prompt`, `/view` or other core routes.

The pack runs real exported workflows on the local ComfyUI instance. Mock mode
remains available with `UPAI_MOCK=1`.

## 2. Assets

- Local ComfyUI execution and the models it can reach.
- The prompt text and request body of every job. They stay in process memory
  until the job is final and are never written to `jobs.json`.
- Materialized input files under `<input>/upai/<job>`.
- Result files under `<temp>/upai/<job>` and their URLs.
- Exported workflow snapshots under `<user>/default/upai/exports`.
- Uploaded media.
- The stable instance id in `instance.json`.
- The pack bearer token.

## 3. Threats and controls

ComfyUI has no authentication. The pack cannot change that.

- Token. When configured, `auth_required` is true and every protocol route
  requires `Authorization: Bearer <token>`. Compare uses `hmac.compare_digest`.
- Origin. A request with an `Origin` header must match `allowed_origins` after
  case and trailing slash normalization. A mismatch returns `403`.
- Host. The `Host` header must be an IP literal, `localhost`, a name ending in
  `.local`, or an entry of `allowed_hosts`. Other names return `403`. This blocks
  DNS rebinding.
- Peer. Loopback and the server socket IP are local and always allowed. Private,
  link-local, unique local and Tailscale peers are LAN. A LAN peer may connect
  when `allow_lan` is on, or when both `allow_remote` and a token are set. Public
  peers need `allow_remote` and a token.
- `allow_lan` meaning. It controls whether LAN peers may connect (`lan_allowed`
  in health). It does not change whether a token is needed. Token need is
  `auth_required`, set by the presence of a token.
- `allow_lan` warning. With `allow_lan` on and no token, anyone who can reach the
  port can upload files and run workflows. Use a trusted network or set a token.
- Config. When `config.json` is present but invalid, every route returns `503`
  with `config_invalid` until it is fixed. A bad non-token field falls back to its
  default with one warning. A present but invalid token, or a file that is not a
  JSON object, fails closed.
- Internal export. `/upai/internal/export` requires `Origin` and `Host` with the
  same netloc, `Content-Type: application/json`, and a peer that passes the
  normal peer policy: local always, LAN only with `allow_lan`, public never. The
  Host allowlist still applies. It skips the token on purpose, because the
  ComfyUI page calls it. See the known limits.
- Export ids. The workflow id is a slug of the source file stem. The source must
  be a relative `.json` path with no parent parts. It is read from the ComfyUI
  user directory when present.
- Output containment. Output validates the job id and per-run name before any
  path join. Each run writes `<job>/<run>-<batch>.<ext>` under `<temp>/upai`. The
  content route resolves each registered result path and serves it only when it
  stays inside `<temp>/upai`.
- Upload cap. The body size is checked before reading and again per chunk while
  the multipart body streams into a pack-owned temp file. The body is hashed while
  streaming, and the temp file is removed on failure or cancellation. Over cap
  returns `413`.
- Upload quota. Total stored bytes are capped by `upload_quota_bytes` from health.
  A request reserves its `Content-Length` before streaming and checks the remaining
  quota per chunk. Temp files of in-flight uploads count as reserved. Over quota
  returns `413` with `details.reason` set to `quota`.
- Directories. Writes stay under `<input>/upai`, `<temp>/upai` and
  `<user>/default/upai`.
- Cleanup. `cleanup_job_files` validates the job id and removes only
  `<input>/upai/<job>` and `<temp>/upai/<job>`. The sweep calls it for expired and
  trimmed jobs. Shared uploads stay untouched.
- Path joins. Job ids, workflow ids and upload hashes are validated against a
  strict pattern before any path join.
- Audio reference paths. An audio reference is a text name resolved inside the
  ComfyUI input directory. An absolute path or a `..` part is rejected, so the
  workflow cannot load any readable file as audio.
- File replace. Writes that replace an existing file retry a transient
  `PermissionError` (a Windows file lock) with a short backoff before they fail.
- Materialize. Upload refs and data URLs are stored once under
  `<input>/upai/uploads` and referenced in place, and a shared upload is pinned
  for a non-final job. Remote URLs are fetched only with `allow_url_fetch` and
  land under `<input>/upai/<job>`. Image inputs are re-checked by size and magic
  bytes after they land. Video and audio inputs are checked by size.
- Queue bounds. `max_pending` bounds non-final jobs and returns `429` when full.
  `max_running` bounds executing pack jobs. A foreign ComfyUI prompt keeps pack
  jobs waiting instead of competing with it.
- Execution. The pack submits through public `POST /prompt` and reads public
  `/ws` and `/api/jobs`. Cancel uses public `/interrupt` and
  `/api/jobs/{id}/cancel`. It does not patch `send_sync`, the queue or the
  executor.
- TLS loopback. When ComfyUI runs with `--tls-keyfile` and `--tls-certfile`,
  pack loopback calls use `https` and `wss` and skip certificate verification
  for loopback only. A self-signed certificate is normal there. The pack does not
  add TLS to a plain ComfyUI.
- Request bodies. The raw create body, data URLs included, is kept in memory
  only. It is never written to `jobs.json` and is dropped when the job becomes
  final.
- Logs. Never the token, prompt text, data URLs or upload bytes. Prompt length
  may be logged. Health reports only whether auth is required. No route returns
  any part of the token.
- Results. Finished jobs expire after `result_ttl_hours`. The sweep removes their
  job input and result directories. The content route only serves `completed`
  jobs, so an expired record exposes no bytes. Result files live under ComfyUI
  temp, which ComfyUI wipes on restart. Uploads older than the same TTL are
  swept.
- URL fetch. `allow_url_fetch` defaults to false, so `http(s)` references are not
  fetched. This blocks SSRF through a crafted reference URL.

## 4. Known limits

- The ComfyUI UI and core routes stay unauthenticated. A token on `/upai` protects
  only `/upai`.
- The internal export route skips the token. A non-browser client that can reach
  the port can forge a matching `Origin`, `Host` and JSON content type. The
  same-origin check stops a browser drive-by, and the peer policy keeps public
  peers out, but a local process or a LAN peer with `allow_lan` can still post.
  The Host allowlist still applies. Do not expose the pack to an untrusted
  network.
- Prompt text and data URLs live in process memory until the job is final. A core
  dump or a process inspector can read them. They are never written to
  `jobs.json` or logs.
- Behind a reverse proxy the peer address is the proxy, so the peer class is the
  proxy's. A loopback proxy counts as local. Set a token and review the Host
  allowlist.
- Any `Host` name ending in `.local` passes the check, including names that are
  not an mDNS name owned by the server. Measured: `attacker.local` returns 200.
  The suffix is meant for LAN-only names, so DNS rebinding protection relies on
  the LAN boundary, not on who owns the name.
- TLS depends on ComfyUI. Without `--tls-keyfile` and `--tls-certfile`, traffic
  is plain HTTP. With them, the pack's loopback calls use `https` and `wss`, but
  the ComfyUI UI and core routes are only as protected as ComfyUI makes them. Use
  a tunnel or a local network for remote access.
- The token is stored in `config.json` in plaintext.
- No per-user isolation. One token, one job store and one export catalog per
  ComfyUI instance.
- URL fetch is off by default. When on, the pack fetches the reference URL from
  the ComfyUI host.
- No Range support for result content.
- The pack does not protect ComfyUI from a local process. A local process can call
  ComfyUI directly.

## 5. Reporting

Report a vulnerability with a private security advisory on the GitHub repository.
Do not open a public issue for an exploitable report.
