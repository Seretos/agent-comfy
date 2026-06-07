"""MCP server entry point for the comfy plugin.

Wires config, lifespan (startup reachability check), and tool registration
together. All ComfyUI logic lives in ``lib_python_comfy``; this module only
orchestrates.

Lifespan note
-------------
The startup reachability check uses the ``lifespan=`` argument to
``FastMCP(...)`` (the correct FastMCP API — there is no ``@mcp.lifespan``
decorator).  If ComfyUI is unreachable the server emits a WARNING to stderr
but always yields so that MCP ``initialize`` still succeeds.
"""
from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP

from comfy_plugin.config import client, comfy_url
from comfy_plugin.tools import register


@contextlib.asynccontextmanager
async def _lifespan(mcp: FastMCP) -> AsyncIterator[None]:
    """Startup hook: probe ComfyUI reachability; warn but never crash."""
    reachable: bool = await asyncio.to_thread(client.is_reachable)
    if not reachable:
        print(
            f"WARNING: ComfyUI is not reachable at {comfy_url!r}. "
            "Generation tools will return errors until ComfyUI is running.",
            file=sys.stderr,
        )
    yield


mcp = FastMCP("comfy", lifespan=_lifespan)
register(mcp)


def main() -> None:
    mcp.run()
