# UPAI Image Ref

Adds one image reference input to a model. Add one node per image slot the model accepts. Wire the `image` output to the image input of the model. The `index` sets the slot. Slots must be unique and contiguous from 1.

## Inputs

| Input | Type | Required | Default | Range |
|---|---|---|---|---|
| `index` | int | no | `1` | 1 to 16 |
| `required` | boolean | no | `false` | true, false |
| `image` | combo | no | none | png, jpg, jpeg, webp files in the ComfyUI input directory |

## Outputs

| Output | Type | Meaning |
|---|---|---|
| `image` | Image | The loaded image. |
| `mask` | Mask | Alpha mask. Empty when the image has no alpha channel. |
| `present` | boolean | True when the test file was loaded. |
| `width` | int | Image width in pixels. |
| `height` | int | Image height in pixels. |

## Notes

- The `image` widget is a test file for the editor. At run time the app replaces it with the user's upload.
- A missing or unreadable test file gives a 64 by 64 black image, `present` false and width and height 64.
- `required` asks the app to require this slot. A UPAI Limits node can replace the required counts.
- The test file must sit in the ComfyUI input directory.

## Example

A model that accepts two images.

- Node 1: `index` 1, `required` true.
- Node 2: `index` 2, `required` false.

Wire each `image` output to the image input of the model.

## Common mistakes

- The same `index` on two nodes, or a gap such as 1 and 3. The model is marked invalid.
- `required` true with no test file selected. The export fails with "required test file is missing".
- A test file outside the ComfyUI input directory. It is not loaded.
- More than 16 image slots. The index range stops at 16.
