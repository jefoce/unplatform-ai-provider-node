# UPAI Start Frame

Provides the optional first frame for a video model. Add one node and wire its `image` output to the frame input of the model. Only video models use this node.

## Inputs

| Input | Type | Required | Default | Range |
|---|---|---|---|---|
| `required` | boolean | no | `false` | true, false |
| `image` | combo | no | none | png, jpg, jpeg, webp files in the ComfyUI input directory |

## Outputs

| Output | Type | Meaning |
|---|---|---|
| `image` | Image | The loaded frame. |
| `present` | boolean | True when the test file was loaded. |

## Notes

- The `image` widget is a test file for the editor. At run time the app replaces it with the request frame.
- `required` asks the app to require a first frame. A UPAI Limits node can override this with `off`, `optional` or `required`.
- A missing or unreadable test file gives a 64 by 64 black image and `present` false.
- An end frame needs a start frame. Add this node when the model accepts an end frame.

## Example

A model that requires a first frame.

- `required`: `true`
- `image`: `frame.png`

Wire `image` to the frame input of the model.

## Common mistakes

- `required` true with no test file selected. The export fails with "required test file is missing".
- An end frame without a start frame. The app rejects the request.
- Using the node on an image model. The frame is ignored.
- Two Start Frame nodes in one model. The model is marked invalid.
