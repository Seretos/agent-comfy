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

---

<!--
EXTEND THIS FILE with plugin-specific sections as the surface area grows.
Common additions seen in sibling plugins:

  ## Intentional shell execution
  If any tool forwards a string into a shell (terminal launchers, command
  fields, etc.), document the contract explicitly. State which fields are
  shell-executed by design vs. which are constrained to a safe charset.
  Pattern: see agent-vdesktop/SECURITY.md ("Intentional shell execution"
  + "Defended fields" sections).

  ## Token / credential handling
  If the plugin reads API tokens or other secrets from the environment,
  document: where they're read from, what they're sent to, whether they
  appear in tool responses or logs, and what response fields expose
  presence-of-token vs. token-value.
  Pattern: see agent-project-issues/SECURITY.md ("Token handling" section).

  ## Permission gating
  If the plugin has read-only vs. write tools, document which gates apply
  to which tools and how they're configured.
  Pattern: see agent-project-issues/SECURITY.md ("Permission gating" table).

  ## AI-attribution markers
  If the plugin writes content visible to third parties (issues, comments,
  files), document any markers that label that content as AI-generated and
  whether those markers are a security control or a transparency feature.
-->
