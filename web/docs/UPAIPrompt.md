# UPAI Prompt

Carries the positive prompt and an optional negative prompt. Connect `prompt` to the text input of the sampler or the text encoder. Connect `negative` only when the workflow uses a negative prompt. The text fields are placeholders for the editor. At run time the app replaces them with the request prompt.

## Inputs

| Input | Type | Required | Default | Range |
|---|---|---|---|---|
| `text` | string | no | empty | free text, multiline |
| `negative` | string | no | empty | free text, multiline |
| `required` | boolean | no | `false` | true, false |
| `max_chars` | int | no | `2000` | 1 to 100000 |

## Outputs

| Output | Type | Meaning |
|---|---|---|
| `prompt` | string | Positive prompt text. |
| `negative` | string | Negative prompt text. |

## Notes

- `required` true makes the app reject a request with an empty prompt.
- `max_chars` is the maximum prompt length the app accepts. A longer request is rejected.
- The model only advertises a negative prompt when the `negative` output is connected to something in the graph. If it is not used, the app rejects a request that carries a negative prompt.

## Example

A model with a negative prompt.

- `required`: `true`
- `max_chars`: `1200`

Connect `prompt` to the positive CLIP Text Encode input and `negative` to the negative one.

## Common mistakes

- Leaving `negative` unconnected but expecting the app to accept a negative prompt. The model does not advertise one.
- Setting `max_chars` lower than the prompts users write. Longer requests are rejected.
- Setting `required` true when the app user may send an empty prompt. The request is rejected.
