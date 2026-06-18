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
