# UPAI Output

Writes the model result into the pack temp folder and registers it with the pack. Every model needs exactly one Output node. Connect the `model` output of UPAI Model to `model`, then connect the result media to `images`, `video` or `audio`. This node has no outputs. It is the end of the model graph.

## Inputs

| Input | Type | Required | Default | Range |
|---|---|---|---|---|
| `model` | UPAI Model | yes | none | output of a UPAI Model node |
| `images` | Image or Video | no | none | one media input is needed |
| `video` | Video | no | none | one media input is needed |
| `audio` | Audio | no | none | one media input is needed |
| `fps` | float | no | `24.0` | 0.01 to 240.0 |
| `format` | combo | no | `auto` | `auto`, `mp4`, `png`, `webp`, `jpeg` |
| `crf` | int | no | `18` | 0 to 51, step 1 |
| `preview` | boolean | no | `false` | true, false |
| `upai_job` | string | no | empty | set by the job route |

## Outputs

None. The node writes files and, when `preview` is on, shows them in the editor.

## What gets written

- A video model writes one mp4. Frames come from `video`, a video valued `images`, or image frames plus `audio`.
- An image model writes one image per frame, in the chosen `format`. `auto` writes png. `mp4` falls back to png.
- Audio only output writes one wav per audio item.
- Files go under the ComfyUI temp directory, in `upai/<job id>/`.
- The pack registers the files so the app can fetch them. The `upai_job` value is filled by the job route. Leave it empty in the editor.
- `crf` controls mp4 quality. Lower is better quality and a larger file.

## Example

An image model.

- `model`: wired to the UPAI Model node.
- `images`: wired to the sampler image output.
- `format`: `png`
- `preview`: `true`

Run the workflow in the editor to see the image. A job from the app writes the image and registers it.

## Common mistakes

- No Output node connected to the model. The model is marked invalid.
- `model` not connected to a UPAI Model node. The model is marked invalid.
- Two Output nodes connected to one model. The model is marked invalid.
- A video model with no image, video or audio input. The run fails with "UPAI Output needs images, video or audio".
- `preview` off and expecting a result in the editor. Turn `preview` on.
- Expecting `format` to change a video. Video is always mp4.
