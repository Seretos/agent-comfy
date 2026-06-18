"""Tool registration for the comfy MCP server.

Call ``register(mcp)`` once during server setup to attach all generation,
asset, and discovery tools to the FastMCP instance.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from comfy_plugin.tools.assets import parse_run_outputs, save_asset, view_image
from comfy_plugin.tools.discovery import get_node_schema, list_models, list_node_types
from comfy_plugin.tools.generation import (
    cancel_job,
    get_job,
    get_queue_status,
    run_scaffold,
    run_template,
    run_workflow,
)


def register(mcp: FastMCP) -> None:
    """Register all generation, asset, and discovery tools on *mcp*."""
    mcp.tool()(run_workflow)
    mcp.tool()(run_template)
    mcp.tool()(get_job)
    mcp.tool()(get_queue_status)
    mcp.tool()(cancel_job)
    mcp.tool()(parse_run_outputs)
    mcp.tool()(view_image)
    mcp.tool()(save_asset)
    mcp.tool()(list_models)
    mcp.tool()(list_node_types)
    mcp.tool()(get_node_schema)
    mcp.tool()(run_scaffold)
