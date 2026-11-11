# Getting started

Three steps from a fresh ComfyUI to a model in the app.

## 1. Install the pack

Install one of these ways, in this order.

### ComfyUI Manager

Open ComfyUI Manager, search for "Unplatform AI Provider" and install it. On new
ComfyUI installs the Manager is separate. In the ComfyUI venv run:

```bash
pip install -U --pre comfyui-manager
```

Start ComfyUI with `--enable-manager`.

### comfy node

```bash
comfy node install unplatform-ai-provider-node
```

### git clone

```bash
git clone https://github.com/jefoce/unplatform-ai-provider-node custom_nodes/unplatform-ai-provider-node
```

Restart ComfyUI after the install. ComfyUI 0.43.0 or newer is required.

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
