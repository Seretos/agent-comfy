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
from lib_python_comfy import discover_params
from lib_python_comfy import get_node_schema as _lib_get_node_schema
from lib_python_comfy import list_checkpoints as _lib_list_checkpoints
from lib_python_comfy import list_node_types as _lib_list_node_types
from lib_python_comfy import list_templates as _lib_list_templates
from lib_python_comfy import load_template as _lib_load_template

from comfy_plugin import config
from comfy_plugin.config import client

# Maps the lib's origin vocabulary to the plugin's public wording. Any
# unmapped origin value passes through unchanged.
_ORIGIN_LABELS = {"packaged": "built-in", "external": "project"}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def list_models() -> dict[str, Any]:
    """Return the list of available checkpoint model names from ComfyUI.

    Scope: only checkpoint-type model files are returned (those registered
    under the ``checkpoints`` folder in ComfyUI).  Audio- or video-capable
    checkpoints appear in this same list when installed — scan names for
    substrings like ``"audio"``, ``"music"``, or ``"video"`` to identify them.
    Separate enumeration of other model types (LoRA, VAE, ControlNet, etc.) is
    not available in this release.

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


async def list_node_types(name_filter: str = "") -> dict[str, Any]:
    """Return the list of all registered node type names from ComfyUI.

    Parameters
    ----------
    name_filter:
        Optional substring to filter results by.  When non-empty, only node
        type names containing this string (case-insensitive) are returned.
        When omitted or empty, all node types are returned.

    Returns
    -------
    dict
        ``{"node_types": [...]}`` — a list of node type name strings.
        On connection failure: ``{"error": "<message>"}``.
    """
    try:
        node_types = await asyncio.to_thread(_lib_list_node_types, client)
        if name_filter:
            lower = name_filter.lower()
            node_types = [n for n in node_types if lower in n.lower()]
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


async def list_templates() -> dict[str, Any]:
    """Return the names of all discoverable templates, built-in and project-local.

    Project-local templates are discovered under the directory resolved by
    ``comfy_plugin.config.template_extra_dirs()`` (see
    ``COMFYUI_PROJECT_TEMPLATES_DIR``) and win name collisions against a
    built-in template of the same name. No ComfyUI connection required.

    Returns
    -------
    dict
        ``{"templates": [{"name": str, "origin": str}, ...]}`` — ``origin``
        is ``"built-in"`` for a packaged template or ``"project"`` for one
        found in the project-local templates directory.
    """
    infos = _lib_list_templates(extra_dirs=config.template_extra_dirs())
    return {
        "templates": [
            {"name": info.name, "origin": _ORIGIN_LABELS.get(info.origin, info.origin)}
            for info in infos
        ]
    }


async def get_template_params(name: str) -> dict[str, Any]:
    """Return the parameter schema for a named template, built-in or project-local.

    Discovers all PARAM_* placeholders and returns name/type/required per
    param. Call before ``run_template`` to know which keys to supply.

    Note naming: keys use the uppercased <NAME> segment of PARAM_* (e.g.
    POSITIVE_PROMPT), differing from the snake_case scaffold-tool params.
    Type tags: STR, INT, FLOAT, BOOL, SEED (SEED is always optional,
    auto-randomised when absent).

    No ComfyUI connection required.

    Parameters
    ----------
    name:
        Template stem name (e.g. ``"txt2img_basic"``), resolved against the
        built-in set first, then the project-local templates directory (see
        ``comfy_plugin.config.template_extra_dirs()``); a project-local
        template of the same name wins the collision.

    Returns
    -------
    dict
        ``{"template": name, "params": [{name, type, required}, ...]}`` on
        success; ``{"error": "<message>"}`` on unknown template.
    """
    try:
        loaded = _lib_load_template(name, extra_dirs=config.template_extra_dirs())
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    params = discover_params(loaded.data)
    return {
        "template": name,
        "params": [
            {"name": p.name, "type": p.type, "required": p.required}
            for p in params
        ],
    }
