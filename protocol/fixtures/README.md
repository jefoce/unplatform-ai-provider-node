# upai/1 fixtures

Example documents for `upai/1`. Every file is valid JSON and validates against the schema listed here.

| Fixture | Schema |
|---|---|
| `health.json` | `../schema/health.schema.json` |
| `models-video.json` | `../schema/models.schema.json` |
| `models-image.json` | `../schema/models.schema.json` |
| `job-pending.json` | `../schema/job.schema.json` |
| `job-in_progress.json` | `../schema/job.schema.json` |
| `job-completed.json` | `../schema/job.schema.json` |
| `job-failed.json` | `../schema/job.schema.json` |
| `job-cancelled.json` | `../schema/job.schema.json` |
| `job-expired.json` | `../schema/job.schema.json` |
| `upload.json` | `../schema/upload.schema.json` |
| `create-job-video.json` | `../schema/create-job.schema.json` |
| `create-job-image.json` | `../schema/create-job.schema.json` |
| `sync-images.json` | `../schema/sync-images.schema.json` |
| `error-invalid_request.json` | `../schema/error.schema.json` |
| `error-unauthorized.json` | `../schema/error.schema.json` |
| `error-forbidden.json` | `../schema/error.schema.json` |
| `error-config_invalid.json` | `../schema/error.schema.json` |
| `error-model_not_found.json` | `../schema/error.schema.json` |
| `error-job_not_found.json` | `../schema/error.schema.json` |
| `error-upload_not_found.json` | `../schema/error.schema.json` |
| `error-not_found.json` | `../schema/error.schema.json` |
| `error-method_not_allowed.json` | `../schema/error.schema.json` |
| `error-too_large.json` | `../schema/error.schema.json` |
| `error-insufficient_storage.json` | `../schema/error.schema.json` |
| `error-workflow_invalid.json` | `../schema/error.schema.json` |
| `error-queue_full.json` | `../schema/error.schema.json` |
| `error-comfy_unavailable.json` | `../schema/error.schema.json` |
| `error-job_failed.json` | `../schema/error.schema.json` |
| `error-internal.json` | `../schema/error.schema.json` |
| `error-timeout.json` | `../schema/error.schema.json` |

All model and job fixtures use fixed timestamps. `models-video.json` and `models-image.json` are generated from the reference mock catalog with `updated_at` set to `2026-11-05T12:00:00Z`. Job fixtures use the fixed id `11111111-1111-4111-8111-111111111111`.

Validate with a Draft 2020-12 validator, for example:

```python
import json
from pathlib import Path
from jsonschema import Draft202012Validator

schema = json.loads(Path("schema/job.schema.json").read_text())
document = json.loads(Path("fixtures/job-completed.json").read_text())
Draft202012Validator(schema).validate(document)
```
