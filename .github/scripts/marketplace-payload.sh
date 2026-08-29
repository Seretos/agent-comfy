#!/usr/bin/env bash
# Build the agent-marketplace `repository_dispatch` JSON payload, safely.
#
# Reads NAME / DESC / REPO / VERSION / TAG / CHANGELOG from the environment
# and prints the full request body (event_type + client_payload) to stdout
# via a single `jq -n --arg` call, so hostile content in any of these values
# (quotes, backticks, newlines, `$()`, a leading `#`, ...) round-trips
# byte-for-byte instead of being interpolated into a shell heredoc.
#
# CHANGELOG is optional: when unset or empty, the `changelog` key is omitted
# entirely from client_payload rather than sent as an empty string.
#
# Usage: NAME=... DESC=... REPO=... VERSION=... TAG=... [CHANGELOG=...] \
#          marketplace-payload.sh
set -euo pipefail

: "${NAME:?NAME env var required}"
: "${DESC:?DESC env var required}"
: "${REPO:?REPO env var required}"
: "${VERSION:?VERSION env var required}"
: "${TAG:?TAG env var required}"
CHANGELOG="${CHANGELOG:-}"

jq -n \
  --arg name "$NAME" \
  --arg description "$DESC" \
  --arg repo "$REPO" \
  --arg category "mcp" \
  --arg version "$VERSION" \
  --arg ref "$TAG" \
  --arg icon "https://raw.githubusercontent.com/${REPO}/${TAG}/assets/icon.png" \
  --arg description_url "https://raw.githubusercontent.com/${REPO}/${TAG}/description.md" \
  --arg changelog "$CHANGELOG" \
  '{
    event_type: "plugin-release",
    client_payload: (
      {
        name: $name,
        description: $description,
        repo: $repo,
        category: $category,
        version: $version,
        ref: $ref,
        icon: $icon,
        description_url: $description_url
      } + (if $changelog == "" then {} else { changelog: $changelog } end)
    )
  }'
