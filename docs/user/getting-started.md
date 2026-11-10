# Getting started

Three steps from a fresh ComfyUI to a model in the app.

## 1. Install the pack

- Open ComfyUI Manager, search for "Unplatform AI Provider" and install it.
- Restart ComfyUI after the install.

ComfyUI 0.43.0 or newer is required. Without the registry, clone or symlink the
repo into `custom_nodes/unplatform-ai-provider-node` and restart.

## 2. Save a workflow

- Open one of the workflows in `workflows/`, or build your own. See
  [build a workflow](build-a-workflow.md).
- Check the workflow has a UPAI Model node wired to a UPAI Output node.
- Save the workflow in ComfyUI.

The save publishes the workflow as a model. The model id is
`<workflow-id>.<model id>`.

## 3. Connect the app

- In Unplatform AI, add a ComfyUI server.
- Use the base URL `http://127.0.0.1:8188/upai`. Change the port to the one
  ComfyUI shows. ComfyUI Desktop shows its port in Settings.
- If you set a token, add the same token in the app.

Check the server first in a browser. The health route
`http://127.0.0.1:8188/upai/api/v1/health` returns JSON when the pack is loaded.

Next: [build a workflow](build-a-workflow.md), or [network](network.md) for
another device.
