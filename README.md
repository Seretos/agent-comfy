# agent-comfy

MCP server for driving ComfyUI - submit workflows, manage the prompt queue, and fetch generated images

## Quick install

**Claude Code:**

```
/plugin marketplace add Seretos/agent-marketplace
/plugin install agent-comfy@agent-marketplace
```

Self-contained binary — no Python, no `pip install`, no dependencies. The release zip ships native binaries for both Windows (`comfy.exe`) and Linux (`comfy`); the host OS auto-selects the right one.

## Alternative installs

### From the GitHub Releases page

1. Download `agent-comfy-<version>.zip` from [Releases](https://github.com/Seretos/agent-comfy/releases).
2. Unpack to a stable folder (e.g. `C:\Users\<you>\.claude\plugins\agent-comfy\` on Windows, `~/.claude/plugins/agent-comfy/` on Linux).
3. In Claude Code:
   ```
   /plugin install <path-to-unpacked-folder>
   ```

### From the release branch

The `release` branch always carries the latest install-ready files (no zip step):

```
git clone --branch release --depth 1 https://github.com/Seretos/agent-comfy.git
```

Then `/plugin install <cloned-path>` in Claude Code.

### Build from source

Requires Python 3.11+ (standard python.org installer with the `py` launcher on Windows; `python3` on Linux).

```powershell
git clone https://github.com/Seretos/agent-comfy.git
cd agent-comfy
pwsh -File scripts/build.ps1 -Clean -Package
```

Output on Windows: `bin/comfy.exe`. On Linux: `bin/comfy`. Then install via `/plugin install <path>`.

## Project-local templates

A repository can ship its own ComfyUI workflow templates alongside its code, discoverable and runnable with no manual setup step. Drop template files into the project templates directory and they show up in `list_templates()` immediately.

**Location:** `COMFYUI_PROJECT_TEMPLATES_DIR` env var if set, otherwise `<git-root>/.seretos/comfy/workflows` (resolved by walking up from the working directory for a `.git` ancestor). If neither resolves, project-local templates are disabled and only the built-in templates are available.

**Format requirement:** files in this directory must already be API-format ComfyUI workflow JSON (node-id-keyed `class_type`/`inputs`, the same shape `POST /prompt` accepts) with `PARAM_*` placeholders in place of the values callers should supply — the same convention the built-in templates use. A raw UI-format export from the ComfyUI canvas needs manual conversion first; this plugin does not convert or validate the shape beyond parsing JSON.

**Collision rule:** a project-local template whose filename stem matches a built-in template's name wins the collision at every call site (`list_templates`, `get_template_params`, `run_template`) — it fully replaces the built-in, not adds alongside it.

See the `comfy-template-selection` skill for a fuller decision guide, including per-built-in-template guidance on when to use it.
