# agent-comfy

PyInstaller-frozen Python MCP server, shipped as a self-contained binary (`bin/comfy` on Linux, `bin/comfy.exe` on Windows). End users need no Python toolchain. It lets an agent drive ComfyUI (an external, user-run GPU service) to generate images/audio/video.

## Architecture & responsibilities

- **This repo is a thin MCP wrapper — all real logic lives in `lib-python-comfy`.** `agent-comfy` only reads config, registers FastMCP tools, calls `lib_python_comfy` functions, and formats results. The ComfyUI HTTP client, queue/poll/retrieve run-flow, asset handling, workflow graph-builder, and model/node discovery all belong in the sibling library `libs/lib-python-comfy`. New functionality goes into the lib first; the wrapper just wires it up.
- **Lib dependency follows the sibling-lib convention.** `lib-python-comfy` is pulled as `lib-python-comfy @ git+https://github.com/Seretos/lib-python-comfy@release/0.x` (floating minor/patch). For local development run `pip install -e ../../libs/lib-python-comfy` **before** `pip install -e .` so the editable sibling checkout overrides the git-pinned copy.
- **ComfyUI is external and user-managed.** The plugin only connects, via `COMFYUI_URL` (default `http://localhost:8188`); it never starts or supervises ComfyUI. When ComfyUI is unreachable, degrade cleanly instead of crashing the MCP server.
- **Single-flight is a hard constraint, not an optimization.** Never let more than one request be in flight to ComfyUI at a time (the user's machine processes only one). Submissions are serialized through a lock in the lib.
- **Two graph formats, identical node IDs.** The graph-builder emits both the **API format** (node-id-keyed `class_type`/`inputs`, sent to `POST /prompt`) and the **UI workflow format** (`nodes`/`links`/positions, openable in the ComfyUI canvas) from one source. The IDs must match across both, or live execution highlighting (driven by the `/ws` socket matching the executing node ID) won't line up with the opened workflow.
- **Env vars** (document each as it lands):
  - `COMFYUI_URL` — root URL of the ComfyUI server (default `http://localhost:8188`). Set this if ComfyUI runs on a non-default port or remote host.
  - `COMFYUI_WORKFLOW_DIR` — optional filesystem path where UI-format workflow JSON files are written for live viewing in the ComfyUI canvas. Unset by default (feature disabled).
  - `COMFYUI_ASSET_TTL` — how long (in integer seconds) to retain fetched assets before they may be evicted. Default `3600` (one hour).
- **Skills ship via `skills/`.** Per-medium workflow-authoring skills (image first; audio/video later) live in `skills/` and are bundled into the release zip automatically.

## Contracts an agent won't infer from the tree

- **Release is orphan-branch + marketplace dispatch.** `release.yml` (manual: Actions → release → `version=X.Y.Z`) stamps the version, matrix-builds per OS, then force-pushes an orphan `release` branch holding only install-ready files and POSTs a dispatch to `Seretos/agent-marketplace`. `main` and `release` share no history — never merge between them. Clients install at the tag `agent-comfy--vX.Y.Z`.
- **Version is pipeline-owned.** The `version` in `pyproject.toml` and both manifests is a placeholder; the workflow input is the source of truth and the stamp never lands on `main`. Don't hand-bump it.
- **Two host manifests, no `.mcp.json`.** `.claude-plugin/plugin.json` resolves its `command` via `${CLAUDE_PLUGIN_ROOT}`; `.codex-plugin/plugin.json` via `${PLUGIN_ROOT}`. Both carry an inline `mcpServers` block because neither placeholder expands in the other host. Keep the two in sync.
- **Required secret:** `MARKETPLACE_DISPATCH_TOKEN` — fine-grained PAT, `Contents: RW` + `Pull requests: RW` on `Seretos/agent-marketplace` only.
- **`assets/icon.png` is a release artifact, not just a repo file.** The dispatch payload sends a `raw.githubusercontent.com/${repo}/${TAG}/assets/icon.png` URL to the marketplace, so the file must live on the orphan `release` branch at the tagged commit — `release.yml` copies `stamped/assets/` into the staging tree for exactly that reason. Ship `assets/icon.png` from day one or the marketplace listing has no image.
- **`description.md` is a release artifact, not just a repo file.** The dispatch payload sends a `raw.githubusercontent.com/${repo}/${TAG}/description.md` URL in the `description_url` field, so the file must live on the orphan `release` branch at the tagged commit — `release.yml` copies it into the staging tree alongside `assets/`. Fill in its Key Features before cutting v0.0.1.

## OS targets

Default is multi-OS (`[windows, linux]`) and the shipped wiring already does it — you do nothing. Flip to **Windows-only** only for a genuinely Win32-bound plugin (COM / `pyvda` / `pywin32` / `comtypes`). To flip: drop `ubuntu-22.04` from the `build` matrix in `release.yml` and from `matrix.os` in `test.yml`; drop the Linux-binary assertion, `chmod +x`, and `git add` for `bin/comfy` in `release.yml`'s assembly + push steps; and append `.exe` to `command` in both manifests.

## Gotchas (the "why" behind the code)

- **`build.ps1` runs under Windows PowerShell 5.1, PS7, and Linux `pwsh`.** It derives `$IsWindows` from `$env:OS` (5.1 lacks the auto variable) and sets no global `$ErrorActionPreference='Stop'` (PyInstaller floods stderr, which 5.1 wraps as ErrorRecords and would trip a global Stop). The smoke step gates the build on a real MCP `initialize` handshake.
- **Native bindings need `collect_all(...)` in `comfy.spec`** — PyInstaller misses their lazily-generated submodules otherwise. The runtime deps that pull this in here are `httpx`, `pydantic`, and `Pillow` (via `lib-python-comfy`); add a `collect_all(...)` for each. (For genuinely Win32-bound native bindings this would also imply `OS_TARGETS=[windows]`, but these three are cross-platform.)
