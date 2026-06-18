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
    from comfy_plugin.tools.assets import parse_run_outputs, save_asset, view_image  # noqa: F401


def test_import_discovery_tools():
    """Regression: all five discovery tool functions must be importable."""
    from comfy_plugin.tools.discovery import (  # noqa: F401
        get_node_schema,
        get_template_params,
        list_models,
        list_node_types,
        list_templates,
    )


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def test_all_sixteen_tools_registered():
    """All sixteen tools must be registered; run_scaffold must be absent."""
    from comfy_plugin.server import mcp

    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    # Original generation tools
    assert "run_workflow" in tool_names
    assert "run_template" in tool_names
    assert "get_job" in tool_names
    assert "get_queue_status" in tool_names
    assert "cancel_job" in tool_names
    # Asset tools
    assert "parse_run_outputs" in tool_names
    assert "view_image" in tool_names
    assert "save_asset" in tool_names
    # Discovery tools
    assert "list_models" in tool_names
    assert "list_node_types" in tool_names
    assert "get_node_schema" in tool_names
    # New typed scaffold tools
    assert "run_txt2img" in tool_names
    assert "run_txt2audio" in tool_names
    assert "run_txt2video" in tool_names
    # New template discovery tools
    assert "list_templates" in tool_names
    assert "get_template_params" in tool_names
    # run_scaffold must be gone
    assert "run_scaffold" not in tool_names
    # Verify exact count
    assert len(tool_names) == 16


# ---------------------------------------------------------------------------
# parse_run_outputs
# ---------------------------------------------------------------------------


async def test_parse_run_outputs_happy_path():
    """parse_run_outputs returns a list of asset dicts with url fields."""
    outputs = {
        "1": {
            "images": [
                {"filename": "ComfyUI_00001_.png", "subfolder": "", "type": "output"}
            ]
        }
    }
    from comfy_plugin.tools.assets import parse_run_outputs

    result = await parse_run_outputs(outputs)

    assert "assets" in result
    assert len(result["assets"]) == 1
    asset_dict = result["assets"][0]
    assert asset_dict["filename"] == "ComfyUI_00001_.png"
    assert asset_dict["subfolder"] == ""
    assert asset_dict["folder_type"] == "output"
    assert "url" in asset_dict
    assert "ComfyUI_00001_.png" in asset_dict["url"]


async def test_parse_run_outputs_empty_outputs():
    """parse_run_outputs with empty outputs dict returns empty assets list."""
    from comfy_plugin.tools.assets import parse_run_outputs

    result = await parse_run_outputs({})

    assert result == {"assets": []}


async def test_parse_run_outputs_multiple_assets():
    """parse_run_outputs extracts assets from multiple nodes."""
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
    from comfy_plugin.tools.assets import parse_run_outputs

    result = await parse_run_outputs(outputs)

    assert len(result["assets"]) == 3


async def test_parse_run_outputs_asset_dict_keys():
    """parse_run_outputs asset dicts include all required keys."""
    outputs = {
        "1": {
            "images": [
                {"filename": "test.png", "subfolder": "sub", "type": "temp"}
            ]
        }
    }
    from comfy_plugin.tools.assets import parse_run_outputs

    result = await parse_run_outputs(outputs)

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


# ---------------------------------------------------------------------------
# list_templates
# ---------------------------------------------------------------------------


async def test_list_templates_returns_txt2img_basic():
    """list_templates returns a dict with 'templates' containing 'txt2img_basic'."""
    from comfy_plugin.tools.discovery import list_templates

    result = await list_templates()

    assert "templates" in result
    assert "txt2img_basic" in result["templates"]


async def test_list_templates_returns_list():
    """list_templates always returns a list under the 'templates' key."""
    from comfy_plugin.tools.discovery import list_templates

    result = await list_templates()

    assert isinstance(result["templates"], list)


# ---------------------------------------------------------------------------
# get_template_params
# ---------------------------------------------------------------------------


async def test_get_template_params_txt2img_basic():
    """get_template_params('txt2img_basic') returns expected param schema."""
    from comfy_plugin.tools.discovery import get_template_params

    result = await get_template_params("txt2img_basic")

    assert result["template"] == "txt2img_basic"
    params = {p["name"]: p for p in result["params"]}

    # POSITIVE_PROMPT — required, STR
    assert "POSITIVE_PROMPT" in params
    assert params["POSITIVE_PROMPT"]["type"] == "STR"
    assert params["POSITIVE_PROMPT"]["required"] is True

    # MODEL — required, STR
    assert "MODEL" in params
    assert params["MODEL"]["type"] == "STR"
    assert params["MODEL"]["required"] is True

    # STEPS — required, INT
    assert "STEPS" in params
    assert params["STEPS"]["type"] == "INT"
    assert params["STEPS"]["required"] is True

    # NEGATIVE_PROMPT — optional
    assert "NEGATIVE_PROMPT" in params
    assert params["NEGATIVE_PROMPT"]["required"] is False

    # SEED — optional, SEED type
    assert "SEED" in params
    assert params["SEED"]["type"] == "SEED"
    assert params["SEED"]["required"] is False


async def test_get_template_params_unknown_template_returns_error():
    """get_template_params with an unknown name returns {'error': ...}."""
    from comfy_plugin.tools.discovery import get_template_params

    result = await get_template_params("nonexistent_template")

    assert "error" in result
    assert "nonexistent_template" in result["error"]
