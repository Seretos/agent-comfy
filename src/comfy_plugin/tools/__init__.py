"""Tool registration for the comfy MCP server.

Call ``register(mcp)`` once during server setup to attach all generation
tools to the FastMCP instance.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from comfy_plugin.tools.generation import (
    cancel_job,
    get_job,
    get_queue_status,
    run_template,
    run_workflow,
)


def register(mcp: FastMCP) -> None:
    """Register all generation tools on *mcp*."""
    mcp.tool()(run_workflow)
    mcp.tool()(run_template)
    mcp.tool()(get_job)
    mcp.tool()(get_queue_status)
    mcp.tool()(cancel_job)
