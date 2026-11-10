# UPAI Audio Ref

Adds one audio reference input to a model. Add one node per audio slot. Wire the `audio` output to the audio input of the model. The `index` sets the slot. Slots must be unique and contiguous from 1.

## Inputs

| Input | Type | Required | Default | Range |
|---|---|---|---|---|
| `index` | int | no | `1` | 1 to 16 |
| `required` | boolean | no | `false` | true, false |
| `audio` | string | no | empty | file name in the ComfyUI input directory |

## Outputs

| Output | Type | Meaning |
|---|---|---|
| `audio` | Audio | The decoded audio. |
| `present` | boolean | True when the test file was loaded. |
| `duration` | float | Duration in seconds. |

## Notes

- `audio` is a text field, not a file picker. Type the name of a file that sits in the ComfyUI input directory.
- At run time the app replaces the test file with the user's upload.
- A missing or unreadable test file gives `present` false and duration 0.
- `required` asks the app to require this slot. A UPAI Limits node can replace the required counts.
- Image models cannot use audio references.

## Example

A video model that accepts one audio track.

- `index`: `1`
- `required`: `false`
- `audio`: `voice.wav`

Wire `audio` to the audio input of the model.

## Common mistakes

- A full path instead of a file name. A path outside the input directory is rejected.
- A corrupt or unsupported audio file. It loads with `present` false.
- The same `index` on two nodes, or a gap in the indexes. The model is marked invalid.
- An audio reference on an image model. The model is marked invalid.
