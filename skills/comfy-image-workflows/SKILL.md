---
name: comfy-image-workflows
description: Generate an image via ComfyUI — submit a txt2img template or build a custom ComfyUI workflow with a checkpoint and KSampler, then save or preview the generated image. Load this skill whenever the user asks to generate an image, create artwork, or run a ComfyUI workflow.
---

# ComfyUI Image Workflow Skill

Load this skill when the user asks to generate an image, create artwork, run a ComfyUI workflow, or produce visual output via ComfyUI. It covers both paths: submitting a ready-made template and building a bespoke node graph from scratch. Audio and video are out of scope here.

## Overview

This plugin connects to an external, user-managed ComfyUI instance. You discover what models and nodes are available, then either submit a named template (fast, parameters only) or build a custom API-format prompt dict and submit it as a raw workflow. Either way the submission is asynchronous: you get back a `prompt_id` and a `state`, then poll until complete, then fetch assets.

All tools return `{"error": "<message>"}` when ComfyUI is unreachable (`ComfyConnectionError`). Always check for the `"error"` key before proceeding.

---

## Tools reference

### Discovery

**`list_models()`**

Returns the checkpoint model names installed in ComfyUI.

```
{"checkpoints": ["v1-5-pruned-emaonly.ckpt", "sd_xl_base_1.0.safetensors", ...]}
```

Only checkpoint-type model files are returned. Audio- or video-capable checkpoints appear in this same list when installed — scan names for substrings like `"audio"`, `"music"`, or `"video"` to identify them. Separate enumeration of other model types (LoRA, VAE, ControlNet, etc.) is not available in this release.

Use this to pick a value for the checkpoint input of a sampler node or template parameter.

---

**`list_node_types()`**

Returns all registered node class names in the running ComfyUI instance.

```
{"node_types": ["KSampler", "CLIPTextEncode", "VAEDecode", "CheckpointLoaderSimple", ...]}
```

Use this before `get_node_schema` to verify a node type name exists.

---

**`get_node_schema(node_type: str)`**

Returns the input schema for a single node type, queried from `/object_info`.

Parameters:
- `node_type` — registered node class name (e.g. `"KSampler"`)

Returns:
```
{
  "required": { "model": [...], "seed": [...], ... },
  "optional": { "latent_image": [...], ... }
}
```

Both sub-dicts default to `{}` when absent. Use this to learn exactly which inputs a node expects before wiring it in a custom graph.

---

### Generation — template path

**`run_template(name: str, params: dict, timeout: float = 120.0)`**

Loads a built-in template by stem name, substitutes `params`, and submits it to ComfyUI.

Parameters:
- `name` — built-in template stem (e.g. `"txt2img_basic"`)
- `params` — parameter values keyed by the uppercased `<NAME>` segment of the template's `PARAM_*` placeholders (e.g. `{"PROMPT": "a cat", "CHECKPOINT": "v1-5-pruned-emaonly.ckpt"}`)
- `timeout` — maximum seconds to wait for completion (default `120.0`); when exceeded with the job still running, `state` will be `"running"` — re-poll via `get_job`

Returns on success (same shape as `run_workflow`):
```
{
  "prompt_id": "abc123",
  "state": "completed",
  "outputs": { "<node_id>": { "images": [{"filename": "...", "subfolder": "", "type": "output"}] } },
  "history": { ... },
  "error": null
}
```

Returns on error (unknown template, missing required parameter, or connection failure):
```
{"error": "<message>"}
```

`state` is one of: `"pending"`, `"running"`, `"completed"`, `"failed"`.

---

### Generation — custom graph path

**`run_workflow(prompt: dict, timeout: float = 120.0)`**

Submits an API-format workflow dict directly to ComfyUI.

Parameters:
- `prompt` — API-format dict: node-id-keyed, each entry has `class_type` and `inputs` (see format below)
- `timeout` — maximum seconds to wait (default `120.0`); same semantics as `run_template`

Returns:
```
{
  "prompt_id": "abc123",
  "state": "completed",
  "outputs": { "<node_id>": { "images": [...] } },
  "history": { ... },
  "error": null
}
```

Returns on connection failure:
```
{"error": "<message>"}
```

`state` values: `"pending"`, `"running"`, `"completed"`, `"failed"`.

#### API-format prompt shape

Each key is a string node ID. Each value has exactly two keys: `class_type` (the node type name) and `inputs` (a dict of input values). Node-to-node wiring uses `[<source_node_id>, <output_index>]` arrays.

```json
{
  "1": {
    "class_type": "CheckpointLoaderSimple",
    "inputs": {
      "ckpt_name": "<checkpoint-name-from-list_models>"
    }
  },
  "2": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "a photorealistic cat sitting on a windowsill",
      "clip": ["1", 1]
    }
  },
  "3": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "ugly, blurry, low quality",
      "clip": ["1", 1]
    }
  },
  "4": {
    "class_type": "EmptyLatentImage",
    "inputs": {
      "width": 512,
      "height": 512,
      "batch_size": 1
    }
  },
  "5": {
    "class_type": "KSampler",
    "inputs": {
      "model": ["1", 0],
      "positive": ["2", 0],
      "negative": ["3", 0],
      "latent_image": ["4", 0],
      "seed": 42,
      "steps": 20,
      "cfg": 7.0,
      "sampler_name": "euler",
      "scheduler": "normal",
      "denoise": 1.0
    }
  },
  "6": {
    "class_type": "VAEDecode",
    "inputs": {
      "samples": ["5", 0],
      "vae": ["1", 2]
    }
  },
  "7": {
    "class_type": "SaveImage",
    "inputs": {
      "images": ["6", 0],
      "filename_prefix": "ComfyUI"
    }
  }
}
```

Use `get_node_schema(node_type)` to discover the exact required and optional inputs for any node before wiring it. The node IDs (`"1"`, `"2"`, ...) are arbitrary strings — they must be unique within the prompt. Note: `run_workflow` does not itself write a `COMFYUI_WORKFLOW_DIR` UI-format file (only `run_txt2img`/`run_txt2audio` do); if you build and export a matching UI workflow by other means, keep its node IDs consistent with the API dict.

---

### Job control and polling

**`get_job(prompt_id: str)`**

Returns the current status of a previously submitted job.

Parameters:
- `prompt_id` — the `prompt_id` returned by `run_workflow` or `run_template`

Returns:
```
{
  "prompt_id": "abc123",
  "state": "completed",
  "history": { ... },
  "error": null
}
```

Note: `get_job` does not return an `outputs` key. Once `state` is `"completed"`, the node output data is available in the `history` field of the `get_job` result. On the fast path (generation call already returned `state == "completed"`), use `result["outputs"]` directly. On the slow/timeout path (generation call returned `state == "running"`), take outputs from the final `get_job(...)["history"]`.

Returns on connection failure: `{"error": "<message>"}`.

---

**`get_queue_status()`**

Returns the raw ComfyUI queue status.

Returns:
```
{
  "queue_running": [...],
  "queue_pending": [...]
}
```

Returns on connection failure: `{"error": "<message>"}`.

---

**`cancel_job(prompt_id: str)`**

Removes a job from the pending queue.

Parameters:
- `prompt_id` — the prompt identifier to cancel

Returns:
```
{"cancelled": "abc123"}
```

Returns on connection failure: `{"error": "<message>"}`.

---

### Asset retrieval

**`parse_run_outputs(outputs: dict)`**

Parses a run's `outputs` dict and returns a flat list of asset descriptors. Does NOT list server files — it only parses the caller-supplied dict.

Parameters:
- `outputs` — the outputs dict to parse. On the fast path this is `result["outputs"]` from `run_workflow` / `run_template` (when that call returned `state == "completed"`). On the slow/timeout path this is `job["history"]` from the final `get_job(...)` call (when the generation call returned `state == "running"`).

Returns:
```
{
  "assets": [
    {
      "filename": "ComfyUI_00001_.png",
      "subfolder": "",
      "folder_type": "output",
      "url": "http://localhost:8188/view?filename=...",
      "mime_type": null,
      "width": null,
      "height": null,
      "bytes_size": null
    }
  ]
}
```

Note: `mime_type`, `width`, `height`, and `bytes_size` are always `null` — they are not populated by `parse_run_outputs` (no separate fetch is performed here).

Returns `{"assets": []}` for empty outputs. Returns `{"error": "<message>"}` on connection failure.

---

**`view_image(filename: str, subfolder: str, folder_type: str, max_dim: int = 512, max_b64_chars: int = 100000)`**

Fetches a ComfyUI output image and returns a downscaled inline base-64 WebP preview.

Parameters:
- `filename` — bare filename as returned by ComfyUI (e.g. `"ComfyUI_00001_.png"`)
- `subfolder` — sub-directory within the output root, often `""`
- `folder_type` — ComfyUI folder type (e.g. `"output"`)
- `max_dim` — maximum width and height of the downscaled preview (default `512`)
- `max_b64_chars` — maximum base-64 string length (default `100000`)

Returns when the encoded result fits within `max_b64_chars`:
```
{"b64": "<base64-webp-string>", "fit": true, "filename": "ComfyUI_00001_.png"}
```

Returns when the budget is exceeded even at minimum quality:
```
{"fit": false, "filename": "ComfyUI_00001_.png", "url": "http://localhost:8188/view?..."}
```

Returns on connection failure or unrecognised image format: `{"error": "<message>"}`.

---

**`save_asset(filename: str, subfolder: str, folder_type: str, dest_path: str)`**

Downloads a ComfyUI output asset and saves it to a local filesystem path. Parent directories are created automatically.

Parameters:
- `filename` — bare filename as returned by ComfyUI
- `subfolder` — sub-directory within the output root, often `""`
- `folder_type` — ComfyUI folder type (e.g. `"output"`)
- `dest_path` — destination file path (absolute or relative; resolved to absolute)

Returns:
```
{"saved": "/absolute/path/to/ComfyUI_00001_.png"}
```

Returns on connection failure: `{"error": "<message>"}`.

---

## End-to-end flows

### Template path (recommended for standard txt2img)

1. Call `list_models()` to get available checkpoints. Pick one for the `CHECKPOINT` parameter.
2. Call `run_template(name="txt2img_basic", params={"PROMPT": "<positive prompt>", "CHECKPOINT": "<name>"}, timeout=120.0)`.
3. Check the result:
   - If `"error"` key is present: report the error to the user.
   - If `state == "completed"`: proceed to step 5.
   - If `state == "running"`: the timeout was reached before completion — go to step 4.
   - If `state == "failed"`: the job failed; check `error` field for details.
4. Poll: call `get_job(prompt_id=result["prompt_id"])` in a loop (e.g. every 5 seconds) until `state` is `"completed"` or `"failed"`. When `state == "completed"`, take outputs from `job["history"]` where `job` is the final `get_job(...)` result — do NOT use `result["outputs"]` from the timed-out generation call, as it is unpopulated when `state` was `"running"`.
5. Call `parse_run_outputs(outputs=<outputs>)` where `<outputs>` is: `result["outputs"]` if the generation call already returned `state == "completed"` (fast path), or `job["history"]` from the final `get_job` call if the generation call returned `state == "running"` (slow path). Assign the return value: `assets_result = parse_run_outputs(outputs=<outputs>)`.
6. For each asset in `assets_result["assets"]`: call `view_image(filename=asset["filename"], subfolder=asset["subfolder"], folder_type=asset["folder_type"])` to show an inline preview, or `save_asset(filename=..., subfolder=..., folder_type=..., dest_path="<local-path>")` to save to disk.

### Custom graph path

1. Call `list_node_types()` to confirm the node types you plan to use exist in this ComfyUI instance.
2. For each node type: call `get_node_schema(node_type="<NodeType>")` to learn its required and optional inputs.
3. Build the API-format `prompt` dict (node-id-keyed, `class_type`/`inputs`). Wire outputs between nodes using `["<source_node_id>", <output_index>]` arrays. See the annotated example in the `run_workflow` section above.
4. Call `run_workflow(prompt=<your_dict>, timeout=120.0)`.
5. Follow the same check/poll/asset steps as the template path (steps 3–6 above), substituting `run_workflow` for `run_template`.

---

## Environment variables

**`COMFYUI_WORKFLOW_DIR`** (optional) — when set to a filesystem path, `run_txt2img` and `run_txt2audio` write a UI-format workflow JSON file there before submission (`run_workflow`, `run_template`, and `run_txt2video` do not). This file can be opened directly in the ComfyUI canvas for live viewing. The node IDs in the UI file match the API-format IDs. This is an environment-level opt-in; no MCP tool controls it.

---

## Notes

- ComfyUI processes one job at a time. The plugin serialises submissions through a lock — do not attempt parallel `run_workflow` / `run_template` calls.
- `timeout` is a client-side deadline, not a cancellation. If the job is still running when the deadline passes, ComfyUI continues executing. Use `cancel_job(prompt_id)` to explicitly remove a pending job from the queue.
- `get_job` does not return an `outputs` key. On the fast path (generation call returned `state == "completed"`), use `result["outputs"]` directly with `parse_run_outputs`. On the slow/timeout path (generation call returned `state == "running"`), the generation result's `outputs` is unpopulated — instead, take outputs from `job["history"]` of the final completed `get_job` call and pass that to `parse_run_outputs`.
- Use `list_models()` to see the installed checkpoints, LoRAs, and other model files available in this ComfyUI instance before picking a model name for a workflow.
