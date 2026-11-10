# UPAI Settings

Describes the sizes, durations and counts a model offers. Add one node per model. The export reads the label lists, defaults and frame rule. At run time the app replaces the `test_*` inputs with the request values.

## Inputs

| Input | Type | Required | Default | Range |
|---|---|---|---|---|
| `resolutions` | string | no | `512,768,1K,1.5K,2K,4K` | comma separated labels, multiline |
| `aspect_ratios` | string | no | full list, see notes | comma separated labels, multiline |
| `default_resolution` | string | no | `1K` | one of `resolutions` |
| `default_aspect_ratio` | string | no | `16:9` | one of `aspect_ratios` |
| `align` | int | no | `16` | 1 to 128 |
| `size_overrides` | string | no | empty | `resolution aspect = WxH` per line, multiline |
| `duration_min` | float | no | `1.0` | 0.0 to 3600.0, step 0.5 |
| `duration_max` | float | no | `10.0` | 0.0 to 3600.0, step 0.5 |
| `duration_default` | float | no | `5.0` | 0.0 to 3600.0, step 0.5 |
| `duration_step` | float | no | `0.5` | 0.01 to 3600.0, step 0.01 |
| `fps` | float | no | `16.0` | 0.01 to 240.0, step 0.01 |
| `frame_mod` | int | no | `4` | 1 to 64 |
| `frame_add` | int | no | `1` | 0 to 64 |
| `count_max` | int | no | `4` | 1 to 64 |
| `count_mode` | combo | no | `batch` | `batch`, `runs` |
| `test_resolution` | string | no | `1K` | one of `resolutions` |
| `test_aspect_ratio` | string | no | `16:9` | one of `aspect_ratios` |
| `test_duration` | float | no | `5.0` | 0.0 to 3600.0, step 0.5 |
| `test_count` | int | no | `1` | 1 to 64 |
| `test_seed` | int | no | `0` | 0 to 4294967295 |

## Outputs

| Output | Type | Meaning |
|---|---|---|
| `width` | int | Width in pixels for the test resolution and aspect ratio. |
| `height` | int | Height in pixels for the test resolution and aspect ratio. |
| `frames` | int | Frame count for the test duration and fps. |
| `fps` | float | Frames per second. |
| `duration` | float | Test duration clamped to the range. |
| `count` | int | Test count clamped to `count_max`. |
| `seed` | int | Test seed. |

## Notes

- Video models must use video resolution labels: `480p`, `720p`, `768p`, `1080p`, `2K`, `4K`. The default list is for image models. A video model with no valid video label is marked invalid.
- The default aspect ratio list is `21:9, 2:1, 16:9, 3:2, 7:5, 4:3, 5:4, 1:1, 4:5, 3:4, 5:7, 2:3, 9:16, 1:2, 9:21, 1:8, 8:1, 1:4, 4:1, 9:19.5, 19.5:9, 9:20, 20:9`.
- `align` rounds width and height to the nearest multiple. The minimum is one step.
- A `size_overrides` line wins over the computed size. Bad lines are skipped.
- `frames` is rounded so that `(frames - frame_add) % frame_mod == 0`.
- `duration` is clamped between `duration_min` and `duration_max`. A `test_duration` of 0 falls back to `duration_default`.
- `count` applies to image models. `count_mode` `batch` sends one prompt with `count` images. `runs` sends one prompt per image and increases the seed by one for each run.
- The node checks that `default_resolution` and `test_resolution` are in `resolutions`, and that `default_aspect_ratio` and `test_aspect_ratio` are in `aspect_ratios`.
- At run time the app replaces `test_resolution`, `test_aspect_ratio`, `test_duration`, `test_count` and `test_seed` with the request values.

## Example

A video model at 720p and 1080p.

- `resolutions`: `720p,1080p`
- `default_resolution`: `720p`
- `aspect_ratios`: `16:9,9:16`
- `duration_min`: `2.0`
- `duration_max`: `8.0`
- `duration_default`: `4.0`
- `fps`: `16.0`
- `frame_mod`: `4`
- `frame_add`: `1`
- `test_resolution`: `720p`
- `test_duration`: `4.0`

The node outputs width 1280 and height 720 for 16:9, 65 frames for 4 seconds at 16 fps with the frame rule, and duration 4.0.

## Common mistakes

- A video model left with the default image resolution labels. The model is marked invalid.
- A default or test label that is not in its list. The node reports an error.
- `duration_default` outside `duration_min` and `duration_max`. The value is clamped, so the app may show a different default.
- A `size_overrides` line without `=` or with the wrong shape. The line is skipped.
- Expecting `count_mode` `runs` to change a video. Count applies to image models.
