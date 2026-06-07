# agent-comfy

MCP server for driving ComfyUI - submit workflows, manage the prompt queue, and fetch generated images.

## Key features

Gives an AI agent programmatic control over a running ComfyUI instance, so it can generate and retrieve images as part of a larger task — no manual clicking in the ComfyUI web UI.

- **Submit workflows** — queue a ComfyUI graph (prompt) for execution and track it by id.
- **Manage the queue** — inspect pending/running prompts and clear or cancel work.
- **Fetch outputs** — pull the generated images/artifacts for a completed prompt.
- **Self-contained binary** — ships as a single executable (Windows + Linux); end users need no Python toolchain.
