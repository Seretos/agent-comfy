"""ComfyUI introspection / discovery tools.

Each function is an async FastMCP tool that delegates entirely to the
sibling lib (``lib_python_comfy``). No ComfyUI logic lives here — this
module only wires env-driven singletons to lib calls and serialises the
results into plain dicts for the MCP response.

All lib discovery calls are synchronous (blocking network I/O) and are
wrapped in ``asyncio.to_thread`` so the event loop is never blocked.

The lib-level ``list_node_types`` and ``get_node_schema`` functions are
imported under ``_lib_`` aliases to avoid shadowing the identically-named
tool functions defined here.
"""
from __future__ import annotations

import asyncio
from typing import Any

from lib_python_comfy import ComfyConnectionError
from lib_python_comfy import get_node_schema as _lib_get_node_schema
from lib_python_comfy import list_checkpoints as _lib_list_checkpoints
from lib_python_comfy import list_node_types as _lib_list_node_types

from comfy_plugin.config import client


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def list_models() -> dict[str, Any]:
    """Return the list of available checkpoint model names from ComfyUI.

    Returns
    -------
    dict
        ``{"checkpoints": [...]}`` — a list of checkpoint name strings.
        On connection failure: ``{"error": "<message>"}``.
    """
    try:
        checkpoints = await asyncio.to_thread(_lib_list_checkpoints, client)
        return {"checkpoints": checkpoints}
    except ComfyConnectionError as exc:
        return {"error": str(exc)}


async def list_node_types() -> dict[str, Any]:
    """Return the list of all registered node type names from ComfyUI.

    Returns
    -------
    dict
        ``{"node_types": [...]}`` — a list of node type name strings.
        On connection failure: ``{"error": "<message>"}``.
    """
    try:
        node_types = await asyncio.to_thread(_lib_list_node_types, client)
        return {"node_types": node_types}
    except ComfyConnectionError as exc:
        return {"error": str(exc)}


async def get_node_schema(node_type: str) -> dict[str, Any]:
    """Return the input schema for a single ComfyUI node type.

    Parameters
    ----------
    node_type:
        The registered node class name (e.g. ``"KSampler"``).

    Returns
    -------
    dict
        ``{"required": {...}, "optional": {...}}`` with the raw per-input
        values from ``/object_info``.  Both sub-dicts default to ``{}`` when
        the node is absent or the keys are missing.
        On connection failure: ``{"error": "<message>"}``.
    """
    try:
        schema = await asyncio.to_thread(_lib_get_node_schema, client, node_type)
        return schema
    except ComfyConnectionError as exc:
        return {"error": str(exc)}
