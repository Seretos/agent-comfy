"""Tests for the list_node_types name_filter parameter.

All tests mock the lib function — no live ComfyUI required.
"""
from __future__ import annotations

from unittest.mock import patch

from lib_python_comfy import ComfyConnectionError


_ALL_NODE_TYPES = [
    "KSampler",
    "KSamplerAdvanced",
    "CLIPTextEncode",
    "CheckpointLoaderSimple",
    "VAEDecode",
    "VAEEncode",
    "EmptyLatentImage",
    "LoraLoader",
]


# ---------------------------------------------------------------------------
# list_node_types with name_filter
# ---------------------------------------------------------------------------


async def test_list_node_types_no_filter_returns_all():
    """list_node_types with no filter (default) returns all node types."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_node_types",
        return_value=_ALL_NODE_TYPES,
    ):
        from comfy_plugin.tools.discovery import list_node_types

        result = await list_node_types()

    assert result == {"node_types": _ALL_NODE_TYPES}


async def test_list_node_types_empty_filter_returns_all():
    """list_node_types with an explicit empty string returns all node types."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_node_types",
        return_value=_ALL_NODE_TYPES,
    ):
        from comfy_plugin.tools.discovery import list_node_types

        result = await list_node_types(name_filter="")

    assert result == {"node_types": _ALL_NODE_TYPES}


async def test_list_node_types_filter_ksampler():
    """list_node_types with name_filter='KSampler' returns only KSampler variants."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_node_types",
        return_value=_ALL_NODE_TYPES,
    ):
        from comfy_plugin.tools.discovery import list_node_types

        result = await list_node_types(name_filter="KSampler")

    assert result == {"node_types": ["KSampler", "KSamplerAdvanced"]}


async def test_list_node_types_filter_case_insensitive():
    """list_node_types name_filter is case-insensitive."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_node_types",
        return_value=_ALL_NODE_TYPES,
    ):
        from comfy_plugin.tools.discovery import list_node_types

        result_lower = await list_node_types(name_filter="ksampler")
        result_upper = await list_node_types(name_filter="KSAMPLER")
        result_mixed = await list_node_types(name_filter="kSaMpLeR")

    expected = {"node_types": ["KSampler", "KSamplerAdvanced"]}
    assert result_lower == expected
    assert result_upper == expected
    assert result_mixed == expected


async def test_list_node_types_filter_vae():
    """list_node_types with name_filter='VAE' returns only VAE-related nodes."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_node_types",
        return_value=_ALL_NODE_TYPES,
    ):
        from comfy_plugin.tools.discovery import list_node_types

        result = await list_node_types(name_filter="VAE")

    assert result == {"node_types": ["VAEDecode", "VAEEncode"]}


async def test_list_node_types_filter_no_match_returns_empty():
    """list_node_types with a non-matching filter returns an empty list."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_node_types",
        return_value=_ALL_NODE_TYPES,
    ):
        from comfy_plugin.tools.discovery import list_node_types

        result = await list_node_types(name_filter="NonExistentNodeXYZ")

    assert result == {"node_types": []}


async def test_list_node_types_filter_connection_error():
    """list_node_types with a filter still propagates connection errors correctly."""
    with patch(
        "comfy_plugin.tools.discovery._lib_list_node_types",
        side_effect=ComfyConnectionError("refused"),
    ):
        from comfy_plugin.tools.discovery import list_node_types

        result = await list_node_types(name_filter="KSampler")

    assert "error" in result
    assert "refused" in result["error"]
