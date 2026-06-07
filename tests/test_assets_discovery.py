"""Tests for the assets and discovery tool modules.

All tests mock the lib functions — no live ComfyUI required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lib_python_comfy import Asset, ComfyConnectionError
from lib_python_comfy.preview import PreviewResult


# ---------------------------------------------------------------------------
# Import / regression tests
# ---------------------------------------------------------------------------


def test_import_assets_tools():
    """Regression: all three asset tool functions must be importable."""
    from comfy_plugin.tools.assets import list_assets, save_asset, view_image  # noqa: F401


def test_import_discovery_tools():
    """Regression: all three discovery tool functions must be importable."""
    from comfy_plugin.tools.discovery import (  # noqa: F401
        get_node_schema,
        list_models,
        list_node_types,
    )


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def test_all_eleven_tools_registered():
    """All five generation tools plus six new tools must be registered."""
    from comfy_plugin.server import mcp

    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    # Original generation tools
    assert "run_workflow" in tool_names
    assert "run_template" in tool_names
    assert "get_job" in tool_names
    assert "get_queue_status" in tool_names
    assert "cancel_job" in tool_names
    # New asset tools
    assert "list_assets" in tool_names
    assert "view_image" in tool_names
    assert "save_asset" in tool_names
    # New discovery tools
    assert "list_models" in tool_names
    assert "list_node_types" in tool_names
    assert "get_node_schema" in tool_names


# ---------------------------------------------------------------------------
# list_assets
# ---------------------------------------------------------------------------


async def test_list_assets_happy_path():
    """list_assets returns a list of asset dicts with url fields."""
    outputs = {
        "1": {
            "images": [
                {"filename": "ComfyUI_00001_.png", "subfolder": "", "type": "output"}
            ]
        }
    }
    from comfy_plugin.tools.assets import list_assets

    result = await list_assets(outputs)

    assert "assets" in result
    assert len(result["assets"]) == 1
    asset_dict = result["assets"][0]
    assert asset_dict["filename"] == "ComfyUI_00001_.png"
    assert asset_dict["subfolder"] == ""
    assert asset_dict["folder_type"] == "output"
    assert "url" in asset_dict
    assert "ComfyUI_00001_.png" in asset_dict["url"]


async def test_list_assets_empty_outputs():
    """list_assets with empty outputs dict returns empty assets list."""
    from comfy_plugin.tools.assets import list_assets

    result = await list_assets({})

    assert result == {"assets": []}


async def test_list_assets_multiple_assets():
    """list_assets extracts assets from multiple nodes."""
    outputs = {
        "1": {
            "images": [
                {"filename": "img1.png", "subfolder": "", "type": "output"},
                {"filename": "img2.png", "subfolder": "sub", "type": "output"},
            ]
        },
        "2": {
            "audio": [
                {"filename": "audio.wav", "subfolder": "", "type": "output"},
            ]
        },
    }
    from comfy_plugin.tools.assets import list_assets

    result = await list_assets(outputs)

    assert len(result["assets"]) == 3


async def test_list_assets_asset_dict_keys():
    """list_assets asset dicts include all required keys."""
    outputs = {
        "1": {
            "images": [
                {"filename": "test.png", "subfolder": "sub", "type": "temp"}
            ]
        }
    }
    from comfy_plugin.tools.assets import list_assets

    result = await list_assets(outputs)

    asset = result["assets"][0]
    for key in ("filename", "subfolder", "folder_type", "url", "mime_type", "width", "height", "bytes_size"):
        assert key in asset


# ---------------------------------------------------------------------------
# view_image
# ---------------------------------------------------------------------------


async def test_view_image_happy_path_fit_true():
    """view_image returns b64 when fit=True."""
    preview = PreviewResult(webp_bytes=b"fake", b64="abc123", fit=True)

    with (
        patch("comfy_plugin.tools.assets.fetch_bytes", return_value=b"imgbytes"),
        patch("comfy_plugin.tools.assets.encode_preview", return_value=preview),
    ):
        from comfy_plugin.tools.assets import view_image

        result = await view_image("test.png", "", "output")

    assert result == {"b64": "abc123", "fit": True, "filename": "test.png"}
    assert "url" not in result


async def test_view_image_fit_false_returns_metadata_only():
    """view_image returns url without b64 when fit=False."""
    preview = PreviewResult(webp_bytes=b"fake", b64="toolong" * 20000, fit=False)

    with (
        patch("comfy_plugin.tools.assets.fetch_bytes", return_value=b"imgbytes"),
        patch("comfy_plugin.tools.assets.encode_preview", return_value=preview),
    ):
        from comfy_plugin.tools.assets import view_image

        result = await view_image("big.png", "", "output")

    assert result["fit"] is False
    assert result["filename"] == "big.png"
    assert "url" in result
    assert "b64" not in result


async def test_view_image_connection_error():
    """view_image catches ComfyConnectionError and returns error dict."""
    with patch(
        "comfy_plugin.tools.assets.fetch_bytes",
        side_effect=ComfyConnectionError("refused"),
    ):
        from comfy_plugin.tools.assets import view_image

        result = await view_image("test.png", "", "output")

    assert "error" in result
    assert "refused" in result["error"]


async def test_view_image_non_image_returns_error():
    """view_image catches ValueError from encode_preview and returns error dict."""
    with (
        patch("comfy_plugin.tools.assets.fetch_bytes", return_value=b"notanimage"),
        patch(
            "comfy_plugin.tools.assets.encode_preview",
            side_effect=ValueError("Cannot decode image"),
        ),
    ):
        from comfy_plugin.tools.assets import view_image

        result = await view_image("file.txt", "", "output")

    assert "error" in result
    assert "Cannot decode image" in result["error"]


# ---------------------------------------------------------------------------
# save_asset
# ---------------------------------------------------------------------------


async def test_save_asset_happy_path():
    """save_asset returns the resolved path as a string."""
    from pathlib import Path

    resolved = Path("/tmp/output/test.png").resolve()

    with patch(
        "comfy_plugin.tools.assets.save_to_path",
        return_value=resolved,
    ):
        from comfy_plugin.tools.assets import save_asset

        result = await save_asset("test.png", "", "output", "/tmp/output/test.png")

    assert result == {"saved": str(resolved)}


async def test_save_asset_connection_error():
    """save_asset catches ComfyConnectionError and returns error dict."""
    with patch(
        "comfy_plugin.tools.assets.save_to_path",
        side_effect=ComfyConnectionError("timeout"),
    ):
        from comfy_plugin.tools.assets import save_asset

        result = await save_asset("test.png", "", "output", "/tmp/test.png")

    assert "error" in result
    assert "timeout" in result["error"]


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


async def test_list_models_happy_path():
    """list_models returns checkpoints list from the lib."""
    checkpoints = ["v1-5-pruned.ckpt", "dreamshaper_8.safetensors"]

    with patch(
        "comfy_plugin.tools.discovery._lib_list_checkpoints",
        return_value=checkpoints,
    ):
        from comfy_plugin.tools.discovery import list_models

        result = await list_models()

    assert result == {"checkpoints": checkpoints}


async def test_list_models_connection_error():
    """list_models catches ComfyConnectionError and returns error dict."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_checkpoints",
        side_effect=ComfyConnectionError("unreachable"),
    ):
        from comfy_plugin.tools.discovery import list_models

        result = await list_models()

    assert "error" in result
    assert "unreachable" in result["error"]


async def test_list_models_empty():
    """list_models returns empty list when no checkpoints found."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_checkpoints",
        return_value=[],
    ):
        from comfy_plugin.tools.discovery import list_models

        result = await list_models()

    assert result == {"checkpoints": []}


# ---------------------------------------------------------------------------
# list_node_types
# ---------------------------------------------------------------------------


async def test_list_node_types_happy_path():
    """list_node_types returns node_types list from the lib."""
    node_types = ["KSampler", "CLIPTextEncode", "CheckpointLoaderSimple"]

    with patch(
        "comfy_plugin.tools.discovery._lib_list_node_types",
        return_value=node_types,
    ):
        from comfy_plugin.tools.discovery import list_node_types

        result = await list_node_types()

    assert result == {"node_types": node_types}


async def test_list_node_types_connection_error():
    """list_node_types catches ComfyConnectionError and returns error dict."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_node_types",
        side_effect=ComfyConnectionError("refused"),
    ):
        from comfy_plugin.tools.discovery import list_node_types

        result = await list_node_types()

    assert "error" in result
    assert "refused" in result["error"]


# ---------------------------------------------------------------------------
# get_node_schema
# ---------------------------------------------------------------------------


async def test_get_node_schema_happy_path():
    """get_node_schema returns required/optional schema dict from the lib."""
    schema = {
        "required": {"ckpt_name": [["v1-5.ckpt"], {}]},
        "optional": {},
    }

    with patch(
        "comfy_plugin.tools.discovery._lib_get_node_schema",
        return_value=schema,
    ):
        from comfy_plugin.tools.discovery import get_node_schema

        result = await get_node_schema("CheckpointLoaderSimple")

    assert result == schema
    assert "required" in result
    assert "optional" in result


async def test_get_node_schema_connection_error():
    """get_node_schema catches ComfyConnectionError and returns error dict."""
    with patch(
        "comfy_plugin.tools.discovery._lib_get_node_schema",
        side_effect=ComfyConnectionError("refused"),
    ):
        from comfy_plugin.tools.discovery import get_node_schema

        result = await get_node_schema("KSampler")

    assert "error" in result
    assert "refused" in result["error"]


async def test_get_node_schema_unknown_node():
    """get_node_schema returns empty required/optional for unknown node types."""
    schema = {"required": {}, "optional": {}}

    with patch(
        "comfy_plugin.tools.discovery._lib_get_node_schema",
        return_value=schema,
    ):
        from comfy_plugin.tools.discovery import get_node_schema

        result = await get_node_schema("NonExistentNode")

    assert result == {"required": {}, "optional": {}}
