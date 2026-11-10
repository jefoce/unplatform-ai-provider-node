# FAQ

**What do I need to run a model?**
ComfyUI 0.43.0 or newer, the pack installed, and a saved workflow with a UPAI
Model and UPAI Output pair.

**Where do I get the URL for the app?**
`http://127.0.0.1:8188/upai` on the same computer. Replace 8188 with the ComfyUI
port. See [network](network.md).

**Does the model use my whole workflow?**
Each job runs only the path of the model it was created for. A broken branch
outside that path does not run. A missing node class inside the path still fails.

**Can one workflow hold several models?**
Yes. Each UPAI Model and UPAI Output pair becomes one model. See
[build a workflow](build-a-workflow.md).

**Why is my model still old after I edit the workflow?**
Save the workflow, or click **Publish workflow** on the UPAI Model node. A
`stale` model means the file is newer than the export.

**Do I need a token?**
Only if you share the network or reach ComfyUI from another device. Set a token
for any shared or remote use. See [network](network.md).

**Can I use it from another device?**
Yes. Start ComfyUI with `--listen 0.0.0.0`, turn on `allow_lan`, and use
`http://<lan-ip>:<port>/upai`. Add a token on shared networks.

**Why do results disappear?**
Results expire after the result lifetime (default 24 hours). ComfyUI also wipes
its temp directory on restart.

**Why is the image type different from what I expected?**
The protocol does not restrict the image result format. Read `Content-Type`. It
is `image/png`, `image/jpeg` or `image/webp`.

**Can the app cancel a running job?**
Yes. Cancel handles a pack-queued job, a dispatched job in the ComfyUI queue, and
a running job. The slot frees when ComfyUI confirms the stop.

**Is my prompt stored?**
Prompt text and data URLs stay in memory until the job is final. They are never
written to `jobs.json` or the logs.

**Does it work without a GPU?**
The pack has no GPU requirement of its own. ComfyUI can run on CPU, but slowly.
