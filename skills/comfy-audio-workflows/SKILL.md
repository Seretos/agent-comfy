---
name: comfy-audio-workflows
description: How to generate audio (music, speech, sound effects) via ComfyUI using the agent-comfy MCP tools.
trigger: Use this skill whenever the user asks to generate, synthesize, or produce any form of audio — music, voice, sound effects, or speech — via ComfyUI.
---

## When to use this skill

Use this skill when:

- The user asks to generate audio of any kind: music, ambient sound, speech, sound effects, or voice-overs.
- ComfyUI is reachable (the server at `COMFYUI_URL`, default `http://localhost:8188`, responds).
- At least one audio-capable model or custom node set is installed in the user's ComfyUI instance.

If ComfyUI is not reachable, all tools return `{"error": "<message>"}`. Report that error to the user and stop — do not retry in a loop.

---

## Prerequisites

1. **ComfyUI must be running.** It is user-managed and external to this plugin. The server URL is read from the `COMFYUI_URL` environment variable (default `http://localhost:8188`). If the user runs ComfyUI on a non-default port or remote host they must set that variable.

2. **An audio-capable model must be installed.** Common choices are AudioCraft (MusicGen/AudioGen), Stable Audio, or any WAV-generating checkpoint. Use `list_models` to confirm what is present before attempting generation.

3. **Audio-capable custom nodes must be installed in ComfyUI.** Nodes such as `MusicgenNode`, `AudioSave`, or equivalent. Use `list_node_types` and `get_node_schema` to verify what is available.

---

## Discover available nodes and models

Always run discovery before constructing a workflow if you have not already done so in this session.

### list_models

Returns all checkpoint names that ComfyUI reports as installed.

```
list_models()
-> {"checkpoints": ["musicgen-small.safetensors", "audio_model_v1.ckpt", ...]}
-> {"error": "<message>"}   # ComfyUI unreachable
```

Only checkpoint-type model files are returned. Look for names containing `audio`, `music`, `speech`, `voice`, or `sound` to identify audio-capable checkpoints. Separate enumeration of other model types (LoRA, VAE, ControlNet, etc.) is not available in this release.

### list_node_types

Returns every registered node class name in the running ComfyUI instance.

```
list_node_types()
-> {"node_types": ["KSampler", "MusicgenNode", "AudioSave", "CLIPTextEncode", ...]}
-> {"error": "<message>"}
```

Scan the list for audio-related node names before deciding which nodes to wire in a manual workflow.

### get_node_schema

Returns the full input schema for one node type so you know exactly which parameters are required versus optional.

```
get_node_schema(node_type="MusicgenNode")
-> {
     "required": {
       "model":      [...],
       "text":       ["STRING", {"multiline": true}],
       "duration":   ["FLOAT",  {"default": 10.0, "min": 1.0, "max": 300.0}]
     },
     "optional": {
       "seed": ["INT", {"default": 0}]
     }
   }
-> {"error": "<message>"}
```

Always call `get_node_schema` on every audio node you plan to use before building a manual workflow (Path B). Node schemas differ across ComfyUI custom-node packages; never assume the field names.

---

## Path A — built-in template (recommended)

`run_template` loads a pre-built workflow template by name, substitutes your parameter values, and submits it to ComfyUI in one call. Use this path whenever the required template is available — it avoids the need to construct and validate a raw API-format workflow dict.

### Signature

```
run_template(name: str, params: dict, timeout: float = 120.0)
-> {
     "prompt_id": "<uuid>",
     "state":     "completed" | "running" | "failed" | ...,
     "outputs":   {...},   # node-id-keyed output dict; pass to parse_run_outputs
     "history":   {...},
     "error":     null | "<message>"
   }
-> {"error": "<message>"}  # template not found, missing param, or ComfyUI unreachable
```

### Parameters

| Parameter | Type | Notes |
|-----------|------|-------|
| `name` | string | Template stem — see below. |
| `params` | dict | Keys are the UPPERCASED `<NAME>` portion of each `PARAM_*` placeholder in the template. Obtain the required keys from the template's documentation or by inspecting a template file directly. |
| `timeout` | float | Seconds to wait before giving up (default 120). Audio generation is substantially slower than image generation — use at least `300` for music clips longer than 10 seconds, and up to `600` for long-form generation. |

### Template name for audio

The audio built-in template stem is `"audio_basic"` — this follows the same naming convention as the image template `"txt2img_basic"`.

> **Note:** Replace `audio_basic` with the actual template stem once `lib-python-comfy` v0.0.2+ (lib issue #13) is installed. Until that release, the template file does not exist and the tool will return `{"error": "... not found ..."}`. If you receive that error, fall back to Path B.

### Example call

```python
run_template(
    name="audio_basic",
    params={
        "PROMPT":   "upbeat jazz piano, bright, 120 bpm",
        "DURATION": 15.0,
        "MODEL":    "musicgen-small.safetensors",
        "SEED":     42
    },
    timeout=300.0
)
```

### Failure modes

| `error` content | Cause | Action |
|-----------------|-------|--------|
| `"... not found ..."` | Template stem does not exist (lib issue #13 not yet shipped) | Fall back to Path B |
| `"Missing required parameter: ..."` | A required `PARAM_*` key was omitted from `params` | Add the missing key |
| `"Connection refused"` / `"Cannot connect"` | ComfyUI is not running or `COMFYUI_URL` is wrong | Ask the user to start ComfyUI |

---

## Path B — manual API-format workflow (advanced)

Use `run_workflow` when no built-in template covers your use case, or when the user needs fine-grained control over the node graph. You are responsible for constructing a valid API-format prompt dict.

### Signature

```
run_workflow(prompt: dict, timeout: float = 120.0)
-> {
     "prompt_id": "<uuid>",
     "state":     "completed" | "running" | "failed" | ...,
     "outputs":   {...},
     "history":   {...},
     "error":     null | "<message>"
   }
-> {"error": "<message>"}  # ComfyUI unreachable
```

### API-format prompt structure

The `prompt` dict is node-id-keyed. Each entry must contain `class_type` and `inputs`. Node outputs are referenced as `[<node_id>, <output_index>]` pairs.

```python
{
  "1": {
    "class_type": "MusicgenNode",
    "inputs": {
      "model":    "musicgen-small.safetensors",
      "text":     "ambient forest sounds, birds chirping, light rain",
      "duration": 20.0,
      "seed":     0
    }
  },
  "2": {
    "class_type": "AudioSave",
    "inputs": {
      "audio":    ["1", 0],   # output index 0 of node "1"
      "filename_prefix": "ComfyUI_audio"
    }
  }
}
```

### Steps to build a valid prompt

1. Call `list_node_types` to confirm the node class names you plan to use are registered.
2. Call `get_node_schema` for each node to learn the exact required and optional input names and their types.
3. Construct the dict using string node IDs (`"1"`, `"2"`, …). IDs must be unique within the prompt.
4. Wire node outputs with `[<source_node_id>, <output_port_index>]` — check the schema to know how many outputs each node exposes and in what order.
5. Set `timeout` generously — audio can take several minutes on CPU or an under-loaded GPU.

---

## Polling long-running jobs

When `run_template` or `run_workflow` returns with `"state": "running"` (the timeout was reached before completion), poll with `get_job` until the job reaches a terminal state.

### Signature

```
get_job(prompt_id: str)
-> {
     "prompt_id": "<uuid>",
     "state":     "completed" | "running" | "failed" | "pending" | ...,
     "history":   {...},
     "error":     null | "<message>"
   }
-> {"error": "<message>"}  # ComfyUI unreachable
```

### Polling pattern

1. Call `run_template` or `run_workflow` with a reasonable `timeout` (e.g. 60 seconds as a progress heartbeat).
2. If `state == "running"`, wait a few seconds, then call `get_job(prompt_id)`.
3. Repeat until `state` is `"completed"` or `"failed"`.
4. On `"completed"`:
   - If the job completed synchronously (returned by `run_template` or `run_workflow`), use the top-level `outputs` field directly with `parse_run_outputs`.
   - If the job completed after polling with `get_job`, there is **no** top-level `outputs` key in the `get_job` response — only `prompt_id`, `state`, `history`, and `error`. The `history` value is the raw ComfyUI history payload whose internal structure is not documented here. In this case, prefer re-submitting with a longer `timeout` to obtain a synchronous result with a top-level `outputs` field, or extract output file references from `history` according to the ComfyUI history format if you are familiar with it.
5. On `"failed"`, inspect `error` and report it to the user.

Do not call `get_job` in a tight loop — a 3–5 second pause between polls is courteous to the ComfyUI server.

---

## Retrieve and save generated audio

Once a job completes, the generated audio file lives in ComfyUI's output directory. Use the asset tools to locate and retrieve it.

### parse_run_outputs

Parse the `outputs` dict from the run result to enumerate generated files. Does NOT list server files — it only parses the caller-supplied dict.

```
parse_run_outputs(outputs: dict)
-> {
     "assets": [
       {
         "filename":    "ComfyUI_audio_00001_.wav",
         "subfolder":   "",
         "folder_type": "output",
         "url":         "http://localhost:8188/view?filename=...&type=output",
         "mime_type":   null,
         "width":       null,
         "height":      null,
         "bytes_size":  null
       },
       ...
     ]
   }
-> {"error": "<message>"}
```

Note: `mime_type`, `width`, `height`, and `bytes_size` are always `null` — they are not populated by `parse_run_outputs` (no separate fetch is performed here).

Pass the `outputs` value from the `run_template` or `run_workflow` response. These tools return a top-level `outputs` key that can be passed directly to `parse_run_outputs`. Note: `get_job` does **not** return a top-level `outputs` key — see the polling section above for how to handle that case.

### save_asset

Download an asset from ComfyUI and write it to a local path on the machine running the MCP server.

```
save_asset(
    filename:    str,   # from parse_run_outputs entry
    subfolder:   str,   # from parse_run_outputs entry
    folder_type: str,   # from parse_run_outputs entry
    dest_path:   str    # absolute or relative destination path; parent dirs created automatically
)
-> {"saved": "<resolved-absolute-path>"}
-> {"error": "<message>"}
```

### view_image

`view_image` is designed for images and returns a base-64 WebP preview. It is not appropriate for audio assets — use `save_asset` instead to retrieve audio files.

### Typical retrieval sequence

```python
# 1. Get the assets from the completed run result
assets_result = parse_run_outputs(outputs=run_result["outputs"])

# 2. Find audio files
audio_assets = [
    a for a in assets_result["assets"]
    if a["mime_type"].startswith("audio/")
]

# 3. Save each one locally
for asset in audio_assets:
    saved = save_asset(
        filename=asset["filename"],
        subfolder=asset["subfolder"],
        folder_type=asset["folder_type"],
        dest_path=f"/tmp/generated/{asset['filename']}"
    )
    print(saved["saved"])  # absolute path on disk
```

---

## Error handling

Every tool in this plugin returns a plain dict. A missing or `null` `"error"` key means success; a non-null `"error"` string means the operation failed. Always check before proceeding.

```python
result = run_template(name="audio_basic", params={...}, timeout=300.0)
if result.get("error"):
    # surface the error to the user; do not attempt asset retrieval
    raise RuntimeError(result["error"])
```

### Common errors

| Error text pattern | Likely cause | Recommended action |
|--------------------|-------------|-------------------|
| `"not found"` in `run_template` | Template stem does not exist yet (lib issue #13) | Use Path B (`run_workflow`) |
| `"Missing required parameter"` | A `PARAM_*` key was omitted from `params` | Add the missing key per the template's spec |
| `"Connection refused"` / `"Cannot connect"` | ComfyUI is not running or `COMFYUI_URL` is wrong | Ask the user to start ComfyUI or set `COMFYUI_URL` |
| `"error"` in `parse_run_outputs` | The `outputs` dict was empty or malformed | Confirm the job state is `"completed"` before calling |
| `"error"` in `save_asset` | Network failure fetching from ComfyUI | Retry once; then report to user |

---

## Queue management

ComfyUI processes one prompt at a time. If you need to inspect or clean the queue, use these tools.

### get_queue_status

```
get_queue_status()
-> {
     "queue_running": [...],   # prompts currently executing (0 or 1)
     "queue_pending": [...]    # prompts waiting
   }
-> {"error": "<message>"}
```

Call this before submitting a long audio job if you suspect the queue is backed up. If `queue_pending` is non-empty, warn the user that their job will wait.

### cancel_job

```
cancel_job(prompt_id: str)
-> {"cancelled": "<prompt_id>"}
-> {"error": "<message>"}  # ComfyUI unreachable
```

`cancel_job` only removes a job from the **pending** queue. A job that is already running (in `queue_running`) cannot be interrupted this way — the user must stop ComfyUI manually to abort an in-progress generation.
