"""MCP server entry point for the comfy plugin.

Wires config, lifespan (startup reachability check + model discovery), and
tool registration together. All ComfyUI logic lives in ``lib_python_comfy``;
this module only orchestrates.

Lifespan note
-------------
The startup reachability check uses the ``lifespan=`` argument to
``FastMCP(...)`` (the correct FastMCP API — there is no ``@mcp.lifespan``
decorator).  If ComfyUI is unreachable the server emits a WARNING to stderr
but always yields so that MCP ``initialize`` still succeeds.

When ComfyUI is reachable, model discovery runs and writes a ``SKILL.md`` to
the resolved skills directory (see ``comfy_plugin.config._resolve_skills_dir``).
The discovery hook is fault-tolerant — any failure degrades to a WARNING.
"""
from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP

from comfy_plugin.config import _resolve_skills_dir, client, comfy_url
from comfy_plugin.startup import run_model_discovery_hook
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
    else:
        # ComfyUI is up — run model discovery and write the skill file.
        # _resolve_skills_dir is wrapped defensively: any unexpected I/O
        # error degrades to "feature disabled" without crashing startup.
        try:
            skills_dir = _resolve_skills_dir()
        except Exception as exc:
            print(
                f"WARNING: Could not resolve skills directory ({exc!r}); "
                "model discovery will be skipped.",
                file=sys.stderr,
            )
            skills_dir = None
        if skills_dir is not None:
            await run_model_discovery_hook(client, skills_dir)
    yield


mcp = FastMCP("comfy", lifespan=_lifespan)
register(mcp)


def main() -> None:
    mcp.run()
