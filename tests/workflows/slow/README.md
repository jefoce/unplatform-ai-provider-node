# Slow cancel workflows

Fixtures for live cancel tests against a real ComfyUI. Both use core nodes
only: `EmptyImage`, `ImageInvert`, `StringLength` and `PreviewImage`. No
models, no model files and no downloads.

## slow-cancel.json

Core API prompt. `EmptyImage` at 4096x4096 feeds a chain of 250
`ImageInvert` nodes and ends in `PreviewImage`. 252 nodes in total. Submit
it to `/prompt` with a canonical UUID4 as `prompt_id` to get a run long
enough to cancel.

## slow-cancel-ui.json

UI workflow with one UPAI Model (id `slow`, name `Slow Cancel`, kind
`image`), one UPAI Prompt, one UPAI Settings at 512 resolution and one UPAI
Output. The same 4096x4096 `EmptyImage` and 250 `ImageInvert` chain feeds
the Output `images` input. Save it as `workflows/slow-cancel-ui.json` so the
save hook can export it, or use the Publish workflow button after saving.

The UPAI Prompt reaches the chain through `StringLength` into the
`EmptyImage` color input, and the UPAI Settings count reaches the
`EmptyImage` batch size input. This keeps the prompt and settings in the
Output ancestor graph without changing the 4096x4096 image size.

## Measurement

Measured on ComfyUI 0.43.0 with the CPU backend (`--cpu`) on port 8189,
fresh server, cold execution cache:

| Workflow | Nodes | Wall time |
| --- | --- | --- |
| slow-cancel.json | 252 | 3.3 s |

Repeated runs of the core chain with a cache-busting color ranged from
3.2 s to 3.8 s. Adjust the number of `ImageInvert` nodes in both files
together if a machine needs a different length.

These files are not in `tests/workflows/api` or `tests/workflows/ui`
because the E2E suite scans those directories and expects UPAI outputs in
every workflow there.
