"""Environment-driven configuration and module-level singletons.

All env vars are read once at import time. Consuming modules import the
singletons directly; there is no re-parsing at call time.

Env vars
--------
COMFYUI_URL
    Root URL of the ComfyUI server. Default: ``http://localhost:8188``.
COMFYUI_WORKFLOW_DIR
    Optional path where UI-format workflow JSON files are written for live
    viewing in the ComfyUI canvas. Unset by default (feature disabled).
COMFYUI_ASSET_TTL
    How long (in seconds) to retain fetched assets before they may be
    evicted. Integer, default ``3600`` (one hour).
"""
from __future__ import annotations

import os

from lib_python_comfy import ComfyClient, FlowRunner, SerializationGuard

# ---------------------------------------------------------------------------
# Env-var parsing
# ---------------------------------------------------------------------------

comfy_url: str = os.environ.get("COMFYUI_URL", "http://localhost:8188")
workflow_dir: str | None = os.environ.get("COMFYUI_WORKFLOW_DIR")
asset_ttl: int = int(os.environ.get("COMFYUI_ASSET_TTL", "3600"))

# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

client: ComfyClient = ComfyClient(comfy_url)
guard: SerializationGuard = SerializationGuard()
runner: FlowRunner = FlowRunner(client, guard)
