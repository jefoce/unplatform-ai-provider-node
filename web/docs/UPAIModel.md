# UPAI Model

Defines one model that the app lists and runs. Add one Model node per model in the workflow. The node holds the model id, display name, kind, price and the optional reference label templates. Connect its `model` output to a UPAI Output node. Connect a UPAI Limits node to the optional `limits` input when the model needs tighter limits.

## Inputs

| Input | Type | Required | Default | Range |
|---|---|---|---|---|
| `id` | string | no | empty | lowercase letters, digits, dot, underscore, hyphen, up to 129 characters |
| `name` | string | no | empty | free text |
| `description` | string | no | empty | free text, multiline |
| `kind` | combo | no | `video` | `video`, `image` |
| `enabled` | boolean | no | `true` | true, false |
| `price_per_run_usd` | float | no | `0.0` | 0.0 to 1000.0, step 0.001 |
| `prompt_reference_label` | string | no | empty | up to 64 characters, needs `{n}` or `{i}` |
| `prompt_reference_label_image` | string | no | empty | up to 64 characters, needs `{n}` or `{i}` |
| `prompt_reference_label_video` | string | no | empty | up to 64 characters, needs `{n}` or `{i}` |
| `prompt_reference_label_audio` | string | no | empty | up to 64 characters, needs `{n}` or `{i}` |
| `limits` | UPAI Limits | no | none | output of a UPAI Limits node |

## Outputs

| Output | Type | Meaning |
|---|---|---|
| `model` | UPAI Model | The model definition, consumed by UPAI Output and by the export. |

## Notes

- Leave `id` empty to derive it from `name` or from the workflow file name. A value that does not match the id pattern is slugified and the model is marked invalid.
- `kind` decides what the app asks for. Video models can use start and end frames, video and audio references, duration and fps. Image models use image references and a count.
- A reference label is a template the app may use to name a reference in the prompt. Placeholders are `{kind}` for the lowercase kind, `{Kind}` for the capitalized kind, `{n}` for the 1 based slot and `{i}` for the 0 based slot. A per-kind template wins over the general one.
- `enabled` false hides the model from the app list. The node stays in the workflow.

## Example

An image model for portraits.

- `id`: `flux-portrait`
- `name`: `Flux Portrait`
- `kind`: `image`
- `price_per_run_usd`: `0.02`
- `prompt_reference_label_image`: `Image {n}`

Connect `model` to a UPAI Output node that receives the sampler images.

## Common mistakes

- Two Model nodes with the same `id`. The second model is marked invalid.
- An `id` with uppercase letters or spaces. It is slugified and the model is marked invalid.
- A reference label without `{n}` or `{i}`. The model is marked invalid.
- A reference label longer than 64 characters. The model is marked invalid.
- `kind` set to `image` while the graph wires video or audio references. The model is marked invalid.
