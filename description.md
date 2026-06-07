# agent-comfy

MCP server for driving ComfyUI — generate images, control the prompt queue, retrieve outputs, and discover available models and nodes. Connects to a user-run ComfyUI instance (`COMFYUI_URL`, default `http://localhost:8188`); no Python toolchain required for end users.

## Key features

Gives an AI agent programmatic control over a running ComfyUI instance, so it can generate and retrieve images as part of a larger task — no manual clicking in the ComfyUI web UI.

- **Generate images** — use pre-built templates or let the agent construct a workflow graph, queue it, and track execution to completion.
- **Queue / job control** — inspect pending and running prompts; cancel individual jobs or clear the entire queue.
- **Fetch outputs** — retrieve generated images and other artifacts for a completed prompt.
- **Model and node discovery** — enumerate available checkpoints, LoRAs, samplers, and custom nodes so the agent can make informed workflow choices.
- **Self-contained binary** — ships as a single executable (Windows + Linux); end users need no Python toolchain. Connects to a user-run ComfyUI instance (`COMFYUI_URL`, default `http://localhost:8188`).
