# upai/1 protocol

Normative specification for version 1 of the upai media generation protocol.

## 1. Scope and versioning

This document defines the HTTP interface between an upai client and an upai server. It covers health, model discovery, uploads, job creation, polling, result content, cancellation and synchronous image generation.

The protocol version is `1`. It appears in the `X-UPAI-Protocol` response header and in the `protocol` field of the health document.

Changes within `upai/1` are additive only. A client must ignore unknown response fields. A server must ignore unknown request fields. Removing a field, renaming a field, changing a type, or changing the meaning of an existing value requires a new protocol version, `upai/2`.

The JSON Schema files in `schema/` and the fixtures in `fixtures/` describe this version.

## 2. Transport

- Requests and responses use JSON encoded as UTF-8.
- Every response carries `X-UPAI-Protocol: 1`, including error responses.
- The protocol base path is `/upai`. Route paths in this document are relative to that base, so the health route is `/upai/api/v1/health`.
- A server integrated with ComfyUI also serves every route under `/api/upai`, so `/api/upai/api/v1/health` is equivalent to `/upai/api/v1/health`.
- Request bodies use `Content-Type: application/json` except uploads, which use `multipart/form-data`.
- HTTP status codes carry the primary result. Error bodies carry a stable code.

## 3. Authentication

Authentication is optional and controlled by the server.

- When the server has no token configured, requests need no `Authorization` header. A supplied header is ignored.
- When the server has a token configured, every route requires `Authorization: Bearer <token>`.
- A missing header, an empty token, or a non-Bearer scheme returns `401` with code `unauthorized` and message `missing bearer token`.
- A wrong token returns `401` with code `unauthorized` and message `invalid bearer token`.

The token is compared in constant time by the reference server. Clients must not treat a token as a capability for routes outside this protocol.

If `config.json` is present but invalid, every route returns `503` with `config_invalid` until the file is fixed. An invalid non-token field falls back to its default with one warning that names the field. A present but invalid `token` field, or a config file that is not a JSON object, fails closed.

## 4. Origin, host and peer access

These checks run before route work.

- A request that carries an `Origin` header must match one entry of the server allowlist. Comparison ignores case and a trailing slash. A non-matching or absent origin in the allowlist returns `403` with code `forbidden` and message `origin is not allowed`.
- The `Host` header must be an IP literal, `localhost`, a name ending in `.local`, or one entry of the server `allowed_hosts` list. Comparison ignores case and a trailing dot. Any other host returns `403` with code `forbidden` and message `host is not allowed`.
- A loopback peer, or a peer equal to the server socket IP, is local and always accepted.
- A peer in a private, link-local, unique local or Tailscale range is LAN. It is accepted when `allow_lan` is true, or when `allow_remote` and a token are both set. Otherwise it returns `403` with code `forbidden` and message `lan access is disabled`.
- Any other peer is public. It is accepted only when `allow_remote` and a token are both set. Otherwise it returns `403` with code `forbidden` and message `remote access is disabled`.
- Router-generated `404` and `405` responses under the base path run the same Origin, Host, peer and token checks.
- Requests without an `Origin` header skip the origin check. Server-side clients normally send no `Origin`.

Server settings for these checks:

| Key | Default | Env |
|---|---|---|
| `allow_lan` | false | `UPAI_ALLOW_LAN` |
| `allowed_hosts` | [] | `UPAI_ALLOWED_HOSTS` (comma separated) |

`allow_lan` lets LAN peers use the pack without a token. Anyone who can reach the port can then upload files and run workflows. A token is recommended on shared networks. When a token is set, LAN peers need it too.

## 5. Identifiers

- Job id: canonical lowercase UUID version 4, matching `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`.
- Model id: matching `^[a-z0-9][a-z0-9._-]{0,128}$`.
- Upload ref: `upai-upload:<sha256>`, where `<sha256>` is 64 lowercase hexadecimal characters.
- Run id: `<job id>_r<run index>`. Run ids are internal to the server and are not part of this protocol.

## 6. Errors

Every error response uses this body:

```json
{
  "error": {
    "code": "workflow_invalid",
    "message": "workflow rejected by the backend",
    "details": {}
  }
}
```

`code` is stable. `message` is a short human-readable line and may change. `details` is a JSON object and may be empty. A field error carries `details.field` with the request field name.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_request` | Malformed body, missing required value, value outside the model capabilities. |
| 401 | `unauthorized` | Token missing, malformed or wrong. |
| 403 | `forbidden` | Origin or Host not allowed, or peer access disabled. |
| 404 | `model_not_found` | Unknown model id for the requested kind. |
| 404 | `job_not_found` | Unknown job id or unknown content index. |
| 404 | `upload_not_found` | Unknown upload hash or malformed hash. |
| 404 | `not_found` | Unknown route under the protocol base path. |
| 405 | `method_not_allowed` | Method not allowed for a known route. |
| 413 | `too_large` | Upload exceeds the server cap or total quota, or a JSON body exceeds the server limit. |
| 422 | `workflow_invalid` | The backend rejected the workflow. `details.node_errors` carries backend node errors. |
| 429 | `queue_full` | Non-final jobs reached `max_pending`. |
| 500 | `internal` | Unexpected server failure. |
| 502 | `job_failed` | A synchronous request waited on a job that failed, was cancelled or expired. `details` carries `job_id`, `status` and `error`. |
| 503 | `comfy_unavailable` | The execution backend is unavailable. |
| 503 | `config_invalid` | The server config is invalid. Every route fails until it is fixed. |
| 504 | `timeout` | A synchronous request exceeded the server wait limit. `details.job_id` identifies the job. |
| 507 | `insufficient_storage` | The server lacks free disk space to store an upload, result or job record. |

## 7. Routes

All paths are relative to the base path.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Protocol version, server versions, auth flag, upload cap. |
| GET | `/api/v1/videos/models` | List video models. |
| GET | `/api/v1/images/models` | List image models. |
| POST | `/api/v1/uploads` | Store one file, return an upload ref. |
| HEAD | `/api/v1/uploads/{sha256}` | Check whether an upload exists. |
| POST | `/api/v1/videos` | Create an asynchronous video job. |
| GET | `/api/v1/videos/{id}` | Read one video job. |
| DELETE | `/api/v1/videos/{id}` | Delete one final video job and its files. |
| GET | `/api/v1/videos/{id}/content?index=N` | Read result bytes for a completed video job. |
| POST | `/api/v1/videos/{id}/cancel` | Cancel a video job. |
| POST | `/api/v1/images/jobs` | Create an asynchronous image job. |
| GET | `/api/v1/images/jobs/{id}` | Read one image job. |
| DELETE | `/api/v1/images/jobs/{id}` | Delete one final image job and its files. |
| GET | `/api/v1/images/jobs/{id}/content?index=N` | Read result bytes for a completed image job. |
| POST | `/api/v1/images/jobs/{id}/cancel` | Cancel an image job. |
| POST | `/api/v1/images` | Create an image job and wait for its result. |

## 8. Health

`GET /api/v1/health` returns:

```json
{
  "protocol": 1,
  "server": "comfyui",
  "server_version": "0.43.0",
  "implementation": "unplatform-ai-provider-node",
  "implementation_version": "0.1.0",
  "auth_required": false,
  "lan_allowed": false,
  "max_upload_bytes": 104857600,
  "upload_quota_bytes": 10737418240,
  "instance_id": "11111111-1111-4111-8111-111111111111",
  "max_running": 1,
  "max_pending": 8,
  "max_inline_bytes": 78642432,
  "disk_free_bytes": 107374182400,
  "result_delete": true
}
```

| Field | Type | Meaning |
|---|---|---|
| `protocol` | integer | Always `1`. |
| `server` | string | Server product name. |
| `server_version` | string | Server product version. |
| `implementation` | string | Implementation name. |
| `implementation_version` | string | Implementation version. |
| `auth_required` | boolean | True when requests need a bearer token. |
| `lan_allowed` | boolean | True when LAN mode is on. LAN peers connect without a token unless auth is required. |
| `max_upload_bytes` | integer | Maximum upload size in bytes. |
| `upload_quota_bytes` | integer | Maximum total bytes stored across uploads. |
| `instance_id` | string | Stable UUID4 for this ComfyUI install. Empty when the server has no install identity. |
| `max_running` | integer | Maximum executing pack jobs, from `1` to `8`. |
| `max_pending` | integer | Maximum non-final jobs. |
| `max_inline_bytes` | integer | Informational upper bound for a JSON body that carries one data URL. Per-reference caps still apply. |
| `disk_free_bytes` | integer | Minimum free bytes across the upload, result and data volumes. `0` when unknown. |
| `result_delete` | boolean | True when a client may delete a final job with `DELETE`. |

## 9. Models

`GET /api/v1/videos/models` and `GET /api/v1/images/models` return the same envelope. Each call returns models of one kind.

```json
{
  "data": [
    {
      "id": "wan22.i2v",
      "name": "Wan 2.2 I2V (local)",
      "description": "",
      "kind": "video",
      "status": "ready",
      "status_reason": null,
      "updated_at": "2026-11-05T12:00:00Z",
      "pricing": { "per_run_usd": 0 },
      "capabilities": {},
      "workflow": { "id": "wan22", "name": "Wan 2.2" }
    }
  ]
}
```

Model fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Model id. Exported models use `<workflow-id>.<model id>`. |
| `name` | string | Display name. |
| `description` | string | May be empty. |
| `kind` | `video` or `image` | Model kind. |
| `status` | `ready`, `stale` or `invalid` | Usability. |
| `status_reason` | string or null | One user-facing line for `stale` and `invalid`. |
| `updated_at` | string | ISO 8601 timestamp of the last export. |
| `pricing.per_run_usd` | number | Price per run in US dollars. Local models use `0`. |
| `capabilities` | object | Accepted inputs and limits. |
| `workflow` | object or null | Source workflow `{id, name}` when the model came from an export. |

`status` values:

- `ready`: the model runs the current exported workflow.
- `stale`: the source workflow is newer than the export. The model still runs the exported snapshot.
- `invalid`: the model cannot run. The reason is in `status_reason`.

Capabilities common to every model:

| Field | Type | Meaning |
|---|---|---|
| `prompt.required` | boolean | Prompt must be non-empty. |
| `prompt.max_chars` | integer | Maximum prompt length in characters. |
| `prompt.reference_label` | string or null | Optional template for client reference labels. |
| `prompt.reference_labels` | object or null | Optional per-kind templates keyed by `image`, `video` and `audio`. |
| `negative_prompt` | boolean | Whether a negative prompt is accepted. True only when the model wires a negative prompt output. |
| `references.image` | object | `{max, required}` image reference count limits. |
| `references.video` | object | `{max, required}` video reference count limits. |
| `references.audio` | object | `{max, required}` audio reference count limits. |
| `resolutions` | array of string | Accepted resolution labels. |
| `default_resolution` | string | Resolution used when the request omits `resolution`. |
| `aspect_ratios` | array of string | Accepted aspect ratio labels. |
| `default_aspect_ratio` | string | Aspect ratio used when the request omits `aspect_ratio`. |
| `sizes` | object | Mapping of resolution label to aspect ratio label to `"WIDTHxHEIGHT"`. |
| `seed` | boolean | Whether the model accepts a seed. |
| `reference_limits.image.max_bytes` | integer | Maximum bytes for one image reference. |
| `reference_limits.image.formats` | array of string | Accepted image file extensions without the dot. |

`prompt.reference_label` is an optional template a client may use to build reference labels. Placeholders are `{kind}` for the lowercase kind, `{Kind}` for the capitalized kind, `{n}` for the 1-based slot and `{i}` for the 0-based slot. The template is at most 64 characters and must contain `{n}` or `{i}`. When absent, the client decides the label format. Optional and additive in `upai/1`.

`prompt.reference_labels` is an optional object of per-kind templates, keyed by `image`, `video` and `audio`. Each value follows the same placeholder rules and 64 character bound. A client resolves a reference label in this order: `reference_labels.<kind>`, then `reference_label`, then its own default. An unknown kind key is dropped with a warning. An invalid value marks the model `invalid` with a reason that names the kind. Optional and additive in `upai/1`.

Capabilities present for video models:

| Field | Type | Meaning |
|---|---|---|
| `frames.start` | boolean | A first frame is accepted. |
| `frames.end` | boolean | A last frame is accepted. |
| `frames.start_required` | boolean | A first frame is mandatory. |
| `frames.end_required` | boolean | A last frame is mandatory. |
| `duration.min` | number | Minimum duration in seconds. |
| `duration.max` | number | Maximum duration in seconds. |
| `duration.default` | number | Duration used when the request omits `duration`. |
| `duration.step` | number | Allowed duration step in seconds. |
| `fps` | number | Frames per second used to convert duration to frames. |
| `frame_rule.mod` | integer | Frame count modulus. |
| `frame_rule.add` | integer | Frame count offset. |
| `audio_output` | boolean | Whether the result may contain audio. |

The server derives the frame count from `duration` and `fps` so that `(frames - frame_rule.add) % frame_rule.mod == 0`.

Capabilities present for image models:

| Field | Type | Meaning |
|---|---|---|
| `count.max` | integer | Maximum number of images in one request. |

`count.max` bounds the `n` field of an image request.

### Resolution labels

Resolution labels are model-defined. These lists are recommendations, not protocol values.

- Video: `480p`, `720p`, `768p`, `1080p`, `2K`, `4K`.
- Image: `512`, `768`, `1K`, `1.5K`, `2K`, `4K`.

The server keeps a label when it is in the list for the model kind or when the
model defines a `size_overrides` entry for it, so a server may accept a custom
label such as `0.9`. The app shows the labels from the model list. A label with
neither a list membership nor a size override is dropped with a warning. A model
with no labels left is `invalid`.

## 10. Create video job

`POST /api/v1/videos` accepts:

```json
{
  "model": "wan22-i2v",
  "prompt": "a short prompt",
  "negative_prompt": "blurry",
  "duration": 5,
  "resolution": "480p",
  "aspect_ratio": "16:9",
  "seed": 42,
  "frame_images": [
    {
      "type": "image_url",
      "image_url": { "url": "upai-upload:0123..." },
      "frame_type": "first_frame"
    }
  ],
  "input_references": [
    {
      "type": "image_url",
      "image_url": { "url": "upai-upload:0123..." }
    }
  ]
}
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `model` | string | yes | Video model id. |
| `prompt` | string | yes | Positive prompt. |
| `negative_prompt` | string | no | Negative prompt. Accepted when `capabilities.negative_prompt` is true. |
| `duration` | number | no | Duration in seconds. Must be an integer within `duration.step` from `duration.min` when the model declares a duration. |
| `resolution` | string | no | One value from `capabilities.resolutions`. |
| `aspect_ratio` | string | no | One value from `capabilities.aspect_ratios`. |
| `seed` | integer | no | `0` to `2147483647`. The server picks a random seed when omitted and returns it in the job. |
| `frame_images` | array | no | First and last frame inputs. |
| `input_references` | array | no | Reference media inputs. |

A `frame_images` item has:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `type` | string | yes | Must be `image_url`. |
| `image_url.url` | string | yes | Image URL or upload ref. |
| `frame_type` | string | yes | `first_frame` or `last_frame`. |

At most one first frame and one last frame are accepted. A last frame requires a first frame. The server rejects frames the model does not declare.

An `input_references` item has:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `type` | string | yes | `image_url`, `video_url` or `audio_url`. |
| `image_url.url` | string | for `image_url` | Image URL or upload ref. |
| `video_url.url` | string | for `video_url` | Video URL or upload ref. |
| `audio_url.url` | string | for `audio_url` | Audio URL or upload ref. |

Reference slots are positional within each kind. The first `image_url` item is image slot 1, the second is image slot 2, and likewise for video and audio. The server validates each kind against `capabilities.references`.

Accepted URL values:

- `data:<media-type>;base64,<payload>` for inline media.
- `upai-upload:<sha256>` for a file stored by `POST /api/v1/uploads`.
- `http://` or `https://` URLs only when the server enables URL fetching. The default is disabled.

The server rejects missing required values, unsupported reference kinds, and values outside the model capabilities with `400` and `invalid_request`. `details.field` names the request field.

When `capabilities.seed` is false, a request that carries `seed` returns `400` with `invalid_request` and `details.field` set to `seed`.

Image references and frame images are checked against `capabilities.reference_limits.image`. A reference over `max_bytes` returns `413` with `too_large`. A format that is unsupported, or whose magic bytes are unknown, returns `400` with `invalid_request`. Formats are file extensions without the dot. `jpg` and `jpeg` both mean JPEG. The server reads magic bytes and does not trust the declared data URL media type or the upload filename extension.

A successful creation returns `202`:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "pending",
  "polling_url": "/upai/api/v1/videos/11111111-1111-4111-8111-111111111111"
}
```

`polling_url` is the server path for `GET /api/v1/videos/{id}`. It is relative unless the server documents otherwise.

## 11. Create image job

`POST /api/v1/images/jobs` accepts the same shape as the synchronous image route:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `model` | string | yes | Image model id. |
| `prompt` | string | yes | Positive prompt. |
| `negative_prompt` | string | no | Negative prompt. Accepted when `capabilities.negative_prompt` is true. |
| `n` | integer | no | Number of images, from `1` to `capabilities.count.max`. Default `1`. |
| `resolution` | string | no | One value from `capabilities.resolutions`. |
| `aspect_ratio` | string | no | One value from `capabilities.aspect_ratios`. |
| `seed` | integer | no | `0` to `2147483647`. The server picks a random seed when omitted and returns it in the job. |
| `input_references` | array | no | Image references only. |

Image references use `type: "image_url"` and `image_url.url`, with the same URL rules and slot ordering as video references.

When `capabilities.seed` is false, a supplied `seed` is rejected. Image references are checked against `capabilities.reference_limits.image` by size and magic-byte format, with the same `413` and `400` responses as video references.

A successful creation returns `202`:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "pending",
  "polling_url": "/upai/api/v1/images/jobs/11111111-1111-4111-8111-111111111111"
}
```

## 12. Job object

`GET /api/v1/videos/{id}` and `GET /api/v1/images/jobs/{id}` return:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "kind": "video",
  "model": "wan22-i2v",
  "status": "in_progress",
  "progress": {
    "percent": 42,
    "node": "MockSampler",
    "value": 42,
    "max": 100,
    "queue_position": null,
    "waiting_on": null
  },
  "seed": 42,
  "urls": null,
  "error": null,
  "usage": { "cost": 0 },
  "created_at": "2026-11-05T12:00:00Z",
  "started_at": "2026-11-05T12:00:01Z",
  "finished_at": null,
  "expires_at": null
}
```

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Job id. |
| `kind` | `video` or `image` | Job kind. |
| `model` | string | Model id used for the job. |
| `status` | enum | One of the status values below. |
| `progress` | object or null | Progress estimate. |
| `seed` | integer or null | Seed used for the job. |
| `urls` | array of string or null | Absolute result URLs. |
| `error` | string or null | One-line failure reason. |
| `usage.cost` | number | Cost in US dollars. Local models use `0`. |
| `created_at` | string | ISO 8601 creation time. |
| `started_at` | string or null | ISO 8601 execution start time. |
| `finished_at` | string or null | ISO 8601 final time. |
| `expires_at` | integer or null | Unix epoch seconds after which the result may be removed. |

Status values:

| Status | Meaning |
|---|---|
| `pending` | Accepted and waiting in the backend queue. |
| `in_progress` | Executing. |
| `completed` | Finished with at least one result URL. |
| `failed` | Finished with an error. |
| `cancelled` | Cancelled by the client or the backend. |
| `expired` | Result or record is past its lifetime. |

`progress` fields:

| Field | Type | Meaning |
|---|---|---|
| `percent` | integer | Estimate from `0` to `100`. |
| `node` | string or null | Backend node currently running. |
| `value` | integer or null | Current progress value. |
| `max` | integer or null | Progress value at completion. |
| `queue_position` | integer or null | Zero-based queue position while pending. |
| `waiting_on` | string or null | Why the job waits: `pack_queue`, `comfyui_busy` or null. |

`urls` is null until the server registers result files. `completed` jobs carry an array of absolute URLs. An `expired` job keeps URLs it had at expiry, but the content may no longer be available. `error` is one line, capped by the server, and null unless the job failed.

### Queue and limits

A pending job may wait on the pack queue or on a foreign ComfyUI prompt. `waiting_on` reports which. `max_running` bounds executing pack jobs. `max_pending` bounds non-final jobs. A job over the limit returns `429` with `queue_full`. `queue_position` counts pack jobs ahead plus foreign ComfyUI jobs.

Real ComfyUI execution submits work with `partial_execution_targets`, so only one model path runs for a job.

With `count_mode=runs` on an exported image model, the server submits one child prompt per run. The seed increases by one for each run, and the job reports the first run seed. Result bytes may be identical across runs when the exported workflow does not use the seed.

## 13. Polling, content and cancellation

Clients poll the job route from `polling_url` until `status` is final: `completed`, `failed`, `cancelled` or `expired`.

Content routes:

- `GET /api/v1/videos/{id}/content?index=N`
- `GET /api/v1/images/jobs/{id}/content?index=N`

`index` is zero-based and defaults to `0`. A video result has one content item, so only `index=0` is valid. An image result accepts `0` up to the number of result URLs minus one.

Rules:

- Unknown job id or unknown content index returns `404` with `job_not_found`.
- A job that is not `completed` returns `400` with `invalid_request`.
- A successful response carries the result bytes.
- `Content-Type` is the real result media type: `video/mp4` for video results and `image/png`, `image/jpeg` or `image/webp` for image results. The protocol does not restrict the result image format. Clients must use the response header rather than assume a type.
- `Content-Length` is set to the result size.
- `Range` requests are not part of `upai/1` phase 1. Clients must not rely on partial content.

Cancel routes:

- `POST /api/v1/videos/{id}/cancel`
- `POST /api/v1/images/jobs/{id}/cancel`

Cancellation is idempotent. A pending or running job becomes `cancelled`. A job already in a final status is returned unchanged. Both cases return `200` with the job object. An unknown job id returns `404` with `job_not_found`.

Delete routes:

- `DELETE /api/v1/videos/{id}`
- `DELETE /api/v1/images/jobs/{id}`

A delete removes a final job record and its pack-owned files. It returns `204` with no body. The result is no longer readable and a later request returns `404` with `job_not_found`. A job that is not final returns `409` with `invalid_request` and `details.field` set to `status`. An unknown job id, or a job of the other kind, returns `404` with `job_not_found`. Shared uploads are not deleted.

## 14. Uploads

`POST /api/v1/uploads` takes `multipart/form-data` with one file part. The part name `file` is conventional. The server stores the bytes by SHA-256 and returns `201`:

```json
{
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "ref": "upai-upload:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "size": 1024,
  "content_type": "image/png",
  "filename": "frame.png"
}
```

| Field | Type | Meaning |
|---|---|---|
| `sha256` | string | Lowercase SHA-256 of the bytes. |
| `ref` | string | `upai-upload:<sha256>`. |
| `size` | integer | Stored size in bytes. |
| `content_type` | string | Detected or supplied media type. |
| `filename` | string | Original filename or a server fallback. |

Storing the same bytes twice is allowed. The server deduplicates by hash and keeps one copy. The returned `ref` is then usable in `frame_images` and `input_references`.

Clients should call `HEAD /api/v1/uploads/{sha256}` first. Dedupe does not add stored bytes, but a re-upload still reserves its `Content-Length` and can return `413` near quota.

The upload cap is `max_upload_bytes` from the health document. A body over the cap returns `413` with `too_large`. An empty file returns `400` with `invalid_request`.

The total upload quota is `upload_quota_bytes` from health. A request reserves its `Content-Length` before streaming when present and checks the remaining quota per chunk. Temp files of other in-flight uploads count as reserved, not stored. A request over quota returns `413` with `too_large` and `details.reason` set to `quota`.

`HEAD /api/v1/uploads/{sha256}` returns `200` with no body when the hash is known and matches the hash pattern. An unknown hash or a malformed hash returns `404` with `upload_not_found`.

## 15. Synchronous images

`POST /api/v1/images` accepts the same body as `POST /api/v1/images/jobs`.

The server creates the job and waits for it to complete, up to its configured timeout. On success it returns `200`:

```json
{
  "data": [
    {
      "b64_json": "iVBORw0KGgo=",
      "media_type": "image/png"
    }
  ],
  "usage": { "cost": 0 }
}
```

| Field | Type | Meaning |
|---|---|---|
| `data` | array | At least one image. Length equals `n`. |
| `data[].b64_json` | string | Base64 encoding of the image bytes. |
| `data[].media_type` | string | Media type of the decoded bytes: `image/png`, `image/jpeg` or `image/webp`, the same set as the content route. |
| `usage.cost` | number | Cost in US dollars. |

If the wait limit is reached, the server returns `504` with `timeout` and `details.job_id`. The job continues and the client may poll `GET /api/v1/images/jobs/{id}`. If the job fails, is cancelled or expires while the request waits, the server returns `502` with `job_failed` and `details` carrying `job_id`, `status` and `error`.

## 16. Server-specific behavior

Servers may add fields and may identify themselves. A mock server may return `"server": "mock"` and `"server_version": "mock"` in health.

The mock server recognizes prompt markers: `[fail]`, `[slow]` and `[invalid]`. These markers are mock behavior only. They are not part of `upai/1`, are not guaranteed by any server, and clients must not depend on them.

## 17. Compatibility

- Clients must ignore unknown response fields and unknown error detail fields.
- Clients must tolerate null for optional job fields.
- Servers must ignore unknown request fields.
- New response fields are additive and do not change the version.
- New routes may be added with `/api/v1` paths that do not collide with the table in section 7.
- A client discovers the protocol version from `GET /api/v1/health` or the `X-UPAI-Protocol` header.
- Clients should parse loosely: require only the fields they use, validate types where they depend on them, and keep the raw response for unknown data.
