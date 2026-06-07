# Security Policy

## Threat model

`comfy_plugin` is a **local** MCP server. It runs as a process launched
by an MCP client (typically Claude Code) on the same machine as the user,
with the user's own privileges. It does not listen on a network socket and
is not designed to be exposed beyond the host.

The trust boundary is the MCP client: anything that can reach the server's
stdio already runs as the user. The tools exposed here are accordingly
authority-equivalent to "the user runs commands themselves" — within the
scope of whatever credentials or filesystem permissions the user has.

## External service (ComfyUI)

The plugin connects to an external ComfyUI instance over HTTP. Two environment
variables govern this surface:

**`COMFYUI_URL`** — read from the environment (default `http://localhost:8188`),
used as the base URL for all HTTP calls to ComfyUI. The plugin sends workflow
graphs and retrieves outputs from this endpoint. The operator is responsible
for ensuring only a trusted ComfyUI instance is reachable at that URL.

**`COMFYUI_WORKFLOW_DIR`** — read from the environment (optional). When set,
the plugin writes UI-format workflow JSON files to this directory for live
viewing in the ComfyUI canvas. The path must point to a directory the process
user has write access to; the plugin does not validate that the path stays
within any sandbox.

**Trust boundary.** ComfyUI is a user-run, user-trusted GPU service. The plugin
authenticates no requests to it and applies no transport-layer security (TLS)
by default — it sends to whatever URL `COMFYUI_URL` names. Workflow data (node
graphs, prompts, parameters) is transmitted to that endpoint in plaintext unless
the operator fronts ComfyUI with HTTPS. This is the documented and expected
deployment model.

## Out of scope

- Compromise of the host machine where the plugin runs (the user already
  owns it).
- Misuse of the plugin's tools by a malicious local MCP client — that client
  already runs as the user.

## Credential handling

- **No tokens are read.** `comfy_plugin` reads no API keys, bearer tokens, or
  credentials of any kind from the environment or configuration files.
- **`COMFYUI_URL` is the only outbound endpoint** and is entirely
  user-controlled (default `http://localhost:8188`). The server never opens
  connections to any other host.
- **Env values do not appear in tool responses or logs.** The values of
  `COMFYUI_URL`, `COMFYUI_WORKFLOW_DIR`, and `COMFYUI_ASSET_TTL` are read at
  startup and are not echoed back in any MCP tool response.
- **Startup WARNING prints the URL to stderr only.** When ComfyUI is
  unreachable at startup, the server prints a human-readable warning that
  includes `COMFYUI_URL` to `stderr`. This is intentional — the URL is not
  secret — and the warning never appears in MCP tool response payloads.

## Reporting a vulnerability

For unexpected authority escalation, input validation gaps that escape the
documented contract of a tool, or any other security concern, open a GitHub
issue with the label `security` (or a private security advisory if the
repository supports them).
