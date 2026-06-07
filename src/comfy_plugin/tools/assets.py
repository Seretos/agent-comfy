"""Asset management tools.

Each function is an async FastMCP tool that delegates entirely to the
sibling lib (``lib_python_comfy``). No ComfyUI logic lives here — this
module only wires env-driven singletons to lib calls and serialises the
results into plain dicts for the MCP response.

Blocking lib calls (``fetch_bytes``, ``save_to_path``, ``encode_preview``)
are wrapped in ``asyncio.to_thread`` because they perform I/O or CPU work
on the calling thread.  ``extract_assets`` and ``view_url`` are pure
computation and are called directly.
"""
from __future__ import annotations

import asyncio
from typing import Any

from lib_python_comfy import (
    Asset,
    ComfyConnectionError,
    encode_preview,
    extract_assets,
    fetch_bytes,
    save_to_path,
    view_url,
)

from comfy_plugin.config import client, comfy_url


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def list_assets(outputs: dict) -> dict[str, Any]:
    """Parse a ComfyUI history outputs dict and return a list of asset dicts.

    Parameters
    ----------
    outputs:
        The ``outputs`` sub-dict from a ``RunResult`` or ``get_history``
        response — a mapping from node ID to that node's output dictionary.

    Returns
    -------
    dict
        ``{"assets": [...]}`` where each entry has keys ``filename``,
        ``subfolder``, ``folder_type``, ``url``, ``mime_type``, ``width``,
        ``height``, ``bytes_size``.  On connection failure (URL construction
        uses the live ``comfy_url`` singleton):
        ``{"error": "<message>"}``.  Empty *outputs* returns
        ``{"assets": []}``.
    """
    try:
        assets = extract_assets(outputs)
        result = []
        for asset in assets:
            url = view_url(asset, comfy_url)
            result.append(
                {
                    "filename": asset.filename,
                    "subfolder": asset.subfolder,
                    "folder_type": asset.folder_type,
                    "url": url,
                    "mime_type": asset.mime_type,
                    "width": asset.width,
                    "height": asset.height,
                    "bytes_size": asset.bytes_size,
                }
            )
        return {"assets": result}
    except ComfyConnectionError as exc:
        return {"error": str(exc)}


async def view_image(
    filename: str,
    subfolder: str,
    folder_type: str,
    max_dim: int = 512,
    max_b64_chars: int = 100_000,
) -> dict[str, Any]:
    """Fetch a ComfyUI output image and return an inline base-64 WebP preview.

    Parameters
    ----------
    filename:
        Bare filename as returned by ComfyUI (e.g. ``"ComfyUI_00001_.png"``).
    subfolder:
        Sub-directory within the output root, often an empty string.
    folder_type:
        ComfyUI folder type (e.g. ``"output"``).
    max_dim:
        Maximum width and height of the downscaled preview (default 512).
    max_b64_chars:
        Maximum base-64 string length (default 100 000).

    Returns
    -------
    dict
        ``{"b64": <str>, "fit": True, "filename": <str>}`` when the encoded
        result fits within *max_b64_chars*; ``{"fit": False, "filename":
        <str>, "url": <str>}`` when the budget was exceeded even at minimum
        quality.  On connection failure: ``{"error": "<message>"}``.  When
        the file is not a recognisable image format: ``{"error":
        "<message>"}``.
    """
    asset = Asset(filename=filename, subfolder=subfolder, folder_type=folder_type)
    try:
        image_bytes: bytes = await asyncio.to_thread(fetch_bytes, asset, client)
        preview = await asyncio.to_thread(
            encode_preview,
            image_bytes,
            max_dim=max_dim,
            max_b64_chars=max_b64_chars,
        )
    except ComfyConnectionError as exc:
        return {"error": str(exc)}
    except ValueError as exc:
        return {"error": str(exc)}

    if preview.fit:
        return {"b64": preview.b64, "fit": True, "filename": filename}
    url = view_url(asset, comfy_url)
    return {"fit": False, "filename": filename, "url": url}


async def save_asset(
    filename: str,
    subfolder: str,
    folder_type: str,
    dest_path: str,
) -> dict[str, Any]:
    """Download a ComfyUI output asset and save it to a local path.

    Parameters
    ----------
    filename:
        Bare filename as returned by ComfyUI.
    subfolder:
        Sub-directory within the output root, often an empty string.
    folder_type:
        ComfyUI folder type (e.g. ``"output"``).
    dest_path:
        Destination file path.  Parent directories are created automatically.

    Returns
    -------
    dict
        ``{"saved": "<resolved-absolute-path>"}`` on success.
        On connection failure: ``{"error": "<message>"}``.
    """
    asset = Asset(filename=filename, subfolder=subfolder, folder_type=folder_type)
    try:
        resolved = await asyncio.to_thread(save_to_path, asset, dest_path, client)
        return {"saved": str(resolved)}
    except ComfyConnectionError as exc:
        return {"error": str(exc)}
