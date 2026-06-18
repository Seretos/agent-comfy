# ComfyUI Video Workflow Authoring

**Trigger:** When asked to generate a video with ComfyUI.
**Medium:** video
**Prerequisite:** ComfyUI reachable at `COMFYUI_URL` (default `http://localhost:8188`).

---

## Overview

There are two paths for generating video with ComfyUI through this plugin:

**(a) Quick-start via `run_template`** — use the built-in `generate_video` template.
Call `run_template(name="generate_video", params={...})` to submit the template with your prompt. Be aware that `generate_video` is a **minimal scaffold**: it contains a single `VHS_VideoCombine` output node with no upstream generation nodes wired in. It is useful for testing the pipeline end-to-end or as a starting skeleton, but on its own it does not produce a full video generation pipeline.

**(b) Custom raw-graph via `run_workflow`** — build and submit a full API-format workflow dict. This is the right path for a real generative video pipeline (e.g., with a sampling model, motion module, ControlNet, etc.). Use `list_node_types` and `get_node_schema` to discover what nodes are available, then construct the graph and call `run_workflow(prompt, timeout=...)`.

---

## Prerequisites

1. **ComfyUI is running and reachable.** Set `COMFYUI_URL` if ComfyUI is not on the default `http://localhost:8188`. When ComfyUI is unreachable, every tool returns `{"error": "<message>"}` — handle this gracefully rather than treating it as a fatal error.
2. **A video-capable model is installed.** Call `list_models()` to confirm available checkpoints. Only checkpoint-type model files are returned — scan names for substrings like `"video"` to identify video-capable ones. For video generation you typically need a motion-aware or video-specific checkpoint.
3. **The `VHS_VideoCombine` node is available.** Call `list_node_types()` and check that `"VHS_VideoCombine"` appears in the `node_types` list. If it is absent, the VideoHelperSuite ComfyUI custom-node extension is not installed.

---

## Step 1 — Quick-start with `run_template`

Use the built-in `generate_video` template for a minimal end-to-end test:

```python
result = run_template(
    name="generate_video",
    params={"POSITIVE_PROMPT": "a cat walking in the snow"},
)
```

### `run_template` parameters

| Parameter | Type    | Required | Notes                                                              |
|-----------|---------|----------|--------------------------------------------------------------------|
| `name`    | string  | yes      | Built-in template stem name. Use `"generate_video"` for video.    |
| `params`  | dict    | yes      | Template parameter values — see table below.                       |
| `timeout` | float   | no       | Max seconds to wait; default `120.0`. See Step 2 for polling.     |

### `generate_video` template parameters (`params` dict keys)

| Key               | Type    | Required | Notes                                                                    |
|-------------------|---------|----------|--------------------------------------------------------------------------|
| `POSITIVE_PROMPT` | string  | yes      | Maps to the `prompt` input field of the `VHS_VideoCombine` node.         |
| `SEED`            | integer | no       | Explicit seed value. Omit entirely for an auto-randomised seed.          |

### Available built-in template names

| Name               | Description                                                       |
|--------------------|-------------------------------------------------------------------|
| `generate_video`   | Minimal scaffold: single `VHS_VideoCombine` output node.          |
| `generate_audio`   | Minimal scaffold for audio output.                                |
| `txt2img_basic`    | Basic text-to-image pipeline.                                     |

> **Important:** `generate_video` contains only a `VHS_VideoCombine` combiner node with no upstream generation nodes. It validates the submission and retrieval flow, but does not produce a full generative video result without additional upstream nodes. For a full pipeline, use Step 3.

### Return shape

```json
{
  "prompt_id": "<uuid>",
  "state": "completed",
  "outputs": { "<node_id>": { ... } },
  "history": { ... },
  "error": null
}
```

On error: `{"error": "<message>"}`.

---

## Step 2 — Long-running jobs and polling

Both `run_template` and `run_workflow` accept a `timeout` parameter (default `120.0` seconds). When the job is still running when the deadline is reached, the returned `state` is `"running"` rather than blocking indefinitely. In that case, poll until the job completes.

### Polling loop

```python
# Initial submission
result = run_template(
    name="generate_video",
    params={"POSITIVE_PROMPT": "a cat walking in the snow"},
    timeout=120.0,
)
prompt_id = result["prompt_id"]

# Poll until a terminal state (handles intermediate states like "queued"/"pending")
while result["state"] not in ("completed", "failed"):
    result = get_job(prompt_id)
    # wait before next poll (e.g. 5 seconds)

if result["state"] == "completed":
    # proceed to Step 4 — asset retrieval
    pass
elif result["state"] == "failed":
    print(result["error"])
```

### `get_job` — check job status

```python
status = get_job(prompt_id="<uuid>")
```

Returns `{prompt_id, state, history, error}`. Note: `get_job` does **not** include `outputs` — retrieve outputs from the original `run_template`/`run_workflow` result when `state` becomes `"completed"`, or use `history` to extract them.

### `get_queue_status` — inspect the queue

```python
queue = get_queue_status()
# {"queue_running": [...], "queue_pending": [...]}
```

Returns the raw ComfyUI queue dict with `queue_running` and `queue_pending` lists. Useful for seeing how many jobs are ahead of yours.

### `cancel_job` — abort a queued job

```python
response = cancel_job(prompt_id="<uuid>")
# {"cancelled": "<uuid>"} on success
# {"error": "<message>"} on connection failure
```

Removes the job from the pending queue. Has no effect on a job that is already executing.

---

## Step 3 — Custom raw-graph with `run_workflow`

For a full generative video pipeline, build an API-format workflow dict and submit it directly:

```python
result = run_workflow(
    prompt={
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "your_video_model.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "a cat walking in the snow",
                "clip": ["1", 1],
            },
        },
        # ... additional nodes ...
        "10": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "filename_prefix": "ComfyUI",
                "format": "video/h264-mp4",
                "images": ["<upstream_node_id>", 0],
                "prompt": "a cat walking in the snow",
                "seed": 42,
            },
        },
    },
    timeout=300.0,
)
```

### `run_workflow` parameters

| Parameter | Type  | Required | Notes                                                                 |
|-----------|-------|----------|-----------------------------------------------------------------------|
| `prompt`  | dict  | yes      | API-format workflow: node-ID-keyed, each entry has `class_type` + `inputs`. |
| `timeout` | float | no       | Max seconds to wait; default `120.0`.                                 |

### Discovering available nodes

```python
# List all registered node type names
node_list = list_node_types()
# {"node_types": ["KSampler", "CLIPTextEncode", "VHS_VideoCombine", ...]}

# Get the input schema for a specific node
schema = get_node_schema(node_type="VHS_VideoCombine")
# {"required": {"images": [...], "format": [...], ...}, "optional": {...}}
```

### Two-graph constraint (AGENTS.md)

The API-format `prompt` dict (sent to `POST /prompt`) and the UI-format workflow JSON (openable in the ComfyUI canvas) **must share identical node IDs**. If they differ, live execution highlighting — driven by the WebSocket stream matching executing node IDs against the open canvas — will not line up with the workflow that is actually running.

If `COMFYUI_WORKFLOW_DIR` is set, the plugin writes the UI-format workflow JSON to that directory so it can be opened directly in the ComfyUI canvas for live viewing.

---

## Step 4 — Asset retrieval

Once a job completes, the `outputs` field of the result contains raw ComfyUI node output. Pass it to `parse_run_outputs` to extract typed asset entries:

```python
asset_list = parse_run_outputs(outputs=result["outputs"])
# {"assets": [{...}, ...]}
```

### Asset entry fields

Each entry in `asset_list["assets"]` has these keys:

| Field         | Type    | Description                                                   |
|---------------|---------|---------------------------------------------------------------|
| `filename`    | string  | Bare filename as returned by ComfyUI (e.g. `"ComfyUI.mp4"`). |
| `subfolder`   | string  | Sub-directory within the output root; often an empty string.  |
| `folder_type` | string  | ComfyUI folder type (e.g. `"output"`).                        |
| `url`         | string  | Direct URL to fetch the file from ComfyUI.                    |
| `mime_type`   | null    | Always `null` — not populated by `parse_run_outputs`.         |
| `width`       | null    | Always `null` — not populated by `parse_run_outputs`.         |
| `height`      | null    | Always `null` — not populated by `parse_run_outputs`.         |
| `bytes_size`  | null    | Always `null` — not populated by `parse_run_outputs`.         |

### Saving a video asset to disk

Use `filename`, `subfolder`, and `folder_type` from the asset entry directly:

```python
saved = save_asset(
    filename=asset["filename"],
    subfolder=asset["subfolder"],
    folder_type=asset["folder_type"],
    dest_path="/local/path/output.mp4",
)
# {"saved": "/local/path/output.mp4"} on success
# {"error": "<message>"} on connection failure
```

Parent directories of `dest_path` are created automatically. Returns `{"saved": "<resolved-absolute-path>"}`.

### Inline preview for image frames

For individual image frames (e.g. `mime_type` starts with `"image/"`), use `view_image` to get an inline base-64 WebP preview:

```python
preview = view_image(
    filename=asset["filename"],
    subfolder=asset["subfolder"],
    folder_type=asset["folder_type"],
    max_dim=512,          # default; max width and height of downscaled preview
    max_b64_chars=100_000,  # default; max base-64 string length
)
# Fits within budget: {"b64": "<base64-webp>", "fit": True, "filename": "<name>"}
# Exceeds budget:    {"fit": False, "filename": "<name>", "url": "<url>"}
# Error:             {"error": "<message>"}
```

---

## Error reference

| Response shape                          | Likely cause                                        | Recovery                                                      |
|-----------------------------------------|-----------------------------------------------------|---------------------------------------------------------------|
| `{"error": "Connection refused ..."}`   | ComfyUI is not running or `COMFYUI_URL` is wrong.   | Start ComfyUI; verify `COMFYUI_URL`.                          |
| `{"error": "... not found ..."}`        | Unknown template name passed to `run_template`.     | Use a valid built-in name: `generate_video`, `generate_audio`, `txt2img_basic`. |
| `{"error": "Missing parameter ..."}`    | Required `params` key absent in `run_template` call.| Supply `POSITIVE_PROMPT` in the `params` dict.                |
| `{"state": "failed", "error": "..."}` | ComfyUI executed the workflow but a node failed.    | Inspect `error` and `history` fields; check node inputs and model availability. |
| `{"state": "running"}`                  | Job did not complete within `timeout` seconds.      | Poll with `get_job(prompt_id)` until `state` changes.         |
| `{"assets": []}`                        | `outputs` dict was empty or contained no assets.    | Check that `VHS_VideoCombine` (or other output nodes) ran successfully. |
