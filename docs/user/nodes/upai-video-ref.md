# UPAI Video Ref

Adds one video reference input to a model. Add one node per video slot. Wire the `video` output to the video input of the model. The `index` sets the slot. Slots must be unique and contiguous from 1.

## Inputs

| Input | Type | Required | Default | Range |
|---|---|---|---|---|
| `index` | int | no | `1` | 1 to 16 |
| `required` | boolean | no | `false` | true, false |
| `video` | combo | no | none | mp4, webm, mov, mkv files in the ComfyUI input directory |

## Outputs

| Output | Type | Meaning |
|---|---|---|
| `video` | Video | The loaded video. |
| `present` | boolean | True when the test file was loaded. |
| `fps` | float | Frames per second. |
| `duration` | float | Duration in seconds. |
| `frame_count` | int | Number of frames. |

## Notes

- The `video` widget is a test file for the editor. At run time the app replaces it with the user's upload.
- A missing or unreadable test file gives `present` false and zero fps, duration and frame count.
- `required` asks the app to require this slot. A UPAI Limits node can replace the required counts.
- Image models cannot use video references.

## Example

A video-to-video model with one reference video.

- `index`: `1`
- `required`: `true`

Wire `video` to the video input of the model.

## Common mistakes

- A video format outside the list. Convert the file or use an image reference instead.
- The same `index` on two nodes, or a gap in the indexes. The model is marked invalid.
- `required` true with no test file selected. The export fails with "required test file is missing".
- A video reference on an image model. The model is marked invalid.
