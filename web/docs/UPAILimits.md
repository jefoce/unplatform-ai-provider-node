# UPAI Limits

Narrows what a model accepts. The node is optional. Connect its `limits` output to the `limits` input on UPAI Model. A value can only make the model stricter. Values that would widen the model are ignored with a warning.

## Inputs

| Input | Type | Required | Default | Range |
|---|---|---|---|---|
| `image_max` | int | no | `-1` | -1 to 16 |
| `image_required` | int | no | `0` | 0 to 16 |
| `video_max` | int | no | `-1` | -1 to 16 |
| `video_required` | int | no | `0` | 0 to 16 |
| `audio_max` | int | no | `-1` | -1 to 16 |
| `audio_required` | int | no | `0` | 0 to 16 |
| `start_frame` | combo | no | `off` | `off`, `optional`, `required` |
| `end_frame` | combo | no | `off` | `off`, `optional`, `required` |
| `duration_min` | float | no | `0.0` | 0.0 to 3600.0, step 0.5 |
| `duration_max` | float | no | `0.0` | 0.0 to 3600.0, step 0.5 |
| `count_max` | int | no | `0` | 0 to 64 |

## Outputs

| Output | Type | Meaning |
|---|---|---|
| `limits` | UPAI Limits | Limit overrides, consumed by UPAI Model. |

## How each value applies

Reference counts:

- `image_max`, `video_max` and `audio_max` set the maximum. `-1` keeps the number of wired reference nodes. `0` or more sets a lower maximum. A value above the number of wired nodes is clamped with a warning.
- `image_required`, `video_required` and `audio_required` set how many references the app must supply. `0` means none required. A required count above the matching max is invalid.
- When a Limits node is wired, these required counts replace the `required` flags on the reference nodes.

Frames:

- `start_frame` and `end_frame` control the frame nodes. `off` drops the frame even when a node is wired. `optional` keeps it but does not require it. `required` makes it required. `required` with no wired node is invalid.

Duration:

- `duration_min` and `duration_max` narrow the range from UPAI Settings. `0` means no change. A minimum above the Settings minimum is used. A maximum below the Settings maximum is used. A minimum above the maximum is invalid. A value that tries to widen the range is ignored with a warning.

Count:

- `count_max` lowers the Settings `count_max`. `0` means no change. A value above the Settings value is ignored with a warning.

## Example

A video model wires two UPAI Image Ref nodes. Set `image_max` to `2`, `image_required` to `1`, `start_frame` to `required` and `duration_max` to `5`. The app then requires one image and a start frame, and caps duration at 5 seconds.

## Common mistakes

- Wiring a Limits node and expecting the `required` flags on the reference nodes to still apply. The Limits required counts replace them.
- Setting a required count above its max. The model is marked invalid.
- Setting `duration_max` above the Settings value to widen the range. The value is ignored.
- Setting `start_frame` to `required` without a UPAI Start Frame node. The model is marked invalid.
- Setting `count_max` above the Settings value to raise the image count. The value is ignored.
