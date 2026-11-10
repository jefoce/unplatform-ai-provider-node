# UPAI End Frame

Provides the optional last frame for a video model. Add one node and wire its `image` output to the frame input of the model. An end frame needs a start frame, so add a UPAI Start Frame node too. Only video models use this node.

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
- `required` asks the app to require a last frame. A UPAI Limits node can override this with `off`, `optional` or `required`.
- A missing or unreadable test file gives a 64 by 64 black image and `present` false.

## Example

A model that accepts an optional last frame.

- `required`: `false`
- `image`: `last.png`

Wire `image` to the frame input of the model and add a Start Frame node.

## Common mistakes

- An end frame without a start frame. The app rejects the request.
- `required` true with no test file selected. The export fails with "required test file is missing".
- Using the node on an image model. The frame is ignored.
- Two End Frame nodes in one model. The model is marked invalid.
