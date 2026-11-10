# Build a workflow

You can add UPAI nodes to any existing ComfyUI workflow. A job runs only the
model path it was created for.

## Add the UPAI nodes

At minimum, one pair:

1. Add a **UPAI Model** node. Set the model kind, name and limits.
2. Add a **UPAI Output** node.
3. Wire the end of the model path to the UPAI Output.

Then add the nodes the model uses:

| Node | Use |
|---|---|
| UPAI Prompt | Prompt text and optional negative prompt. |
| UPAI Settings | Sizes, resolution labels, duration, frame rule, count mode. |
| UPAI Image Ref | One image reference. |
| UPAI Video Ref | One video reference. |
| UPAI Audio Ref | One audio reference. |
| UPAI Start Frame | Optional or required start frame for video. |
| UPAI End Frame | Optional or required end frame for video. |
| UPAI Limits | Lowers reference counts, duration and count ranges. Optional. |

See [nodes](nodes/README.md) for the inputs of each node.

## Several models in one file

One workflow can hold several models. Each **UPAI Model** and **UPAI Output**
pair becomes one model.

- The workflow id is the slug of the workflow file name.
- The model id is `<workflow-id>.<model id>`.
- The display name is the UPAI Model `name`.
- One invalid model does not hide the others in the same file.

## Test in the editor

1. Pick a size and write a prompt in the editor.
2. Run the prompt with the normal ComfyUI Run button.
3. Check the result in the UPAI Output preview.

Only the model path of the pair runs. A broken branch outside that path does not
stop the run. A missing node class inside the path still fails it.

## Publish

Saving the workflow publishes it. To publish again without saving, click
**Publish workflow** on the UPAI Model node, or run the command
"Unplatform: Publish workflow".

After a change to the nodes or the extension, hard reload the ComfyUI tab.
Cached extension JavaScript hides changes.

## Model status

The app and the model routes report one status per model.

| Status | Meaning | Fix |
|---|---|---|
| `ready` | The exported snapshot runs. | None. |
| `stale` | The source workflow is newer than the export. | Save the workflow. The old snapshot still runs. |
| `invalid` | The model cannot run. | Read `status_reason`, fix the graph, save again. |

`GET /upai/api/v1/images/models` and `/upai/api/v1/videos/models` list the models
and their status.
