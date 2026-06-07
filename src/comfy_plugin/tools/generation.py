"""Generation and job-management tools.

Each function is an async FastMCP tool that delegates entirely to the
sibling lib (``lib_python_comfy``). No ComfyUI logic lives here — this
module only wires env-driven singletons to lib calls and serialises the
results into plain dicts for the MCP response.

JobState enum values are always serialised to their ``.value`` string so
the MCP client receives plain JSON strings rather than enum objects.
"""
from __future__ import annotations

import asyncio
from typing import Any

from lib_python_comfy import (
    ComfyConnectionError,
    JobStatus,
    MissingParameterError,
    RunResult,
    load_builtin_template,
    render,
)

from comfy_plugin.config import client, runner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_result_to_dict(result: RunResult) -> dict[str, Any]:
    """Convert a RunResult to a plain dict with state as a string."""
    return {
        "prompt_id": result.prompt_id,
        "state": result.state.value,
        "outputs": result.outputs,
        "history": result.history,
        "error": result.error,
    }


def _job_status_to_dict(status: JobStatus) -> dict[str, Any]:
    """Convert a JobStatus to a plain dict with state as a string."""
    return {
        "prompt_id": status.prompt_id,
        "state": status.state.value,
        "history": status.history,
        "error": status.error,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def run_workflow(prompt: dict, timeout: float = 120.0) -> dict[str, Any]:
    """Submit an API-format ComfyUI workflow and wait for it to complete.

    Parameters
    ----------
    prompt:
        API-format workflow dict (node-id-keyed with ``class_type``/``inputs``).
    timeout:
        Maximum seconds to wait for completion. When the deadline is reached
        and the job is still running, the returned ``state`` is ``"running"``
        and the agent should re-poll via ``get_job``.

    Returns
    -------
    dict
        Keys: ``prompt_id``, ``state`` (string), ``outputs``, ``history``,
        ``error``.  On connection failure: ``{"error": "<message>"}``.
    """
    try:
        result: RunResult = await runner.run(prompt, timeout=timeout)
        return _run_result_to_dict(result)
    except ComfyConnectionError as exc:
        return {"error": str(exc)}


async def run_template(
    name: str, params: dict[str, Any], timeout: float = 120.0
) -> dict[str, Any]:
    """Load a built-in template, render it with *params*, then submit.

    Parameters
    ----------
    name:
        Built-in template stem name (e.g. ``"txt2img_basic"``).
    params:
        Parameter values keyed by the uppercased ``<NAME>`` segment of the
        template's ``PARAM_*`` placeholders.
    timeout:
        Maximum seconds to wait for completion (same semantics as
        ``run_workflow``).

    Returns
    -------
    dict
        Same shape as ``run_workflow``.  On unknown template or missing
        required parameter: ``{"error": "<message>"}``.
    """
    try:
        template = load_builtin_template(name)
        rendered = render(template, params)
        result: RunResult = await runner.run(rendered, timeout=timeout)
        return _run_result_to_dict(result)
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    except MissingParameterError as exc:
        return {"error": str(exc)}
    except ComfyConnectionError as exc:
        return {"error": str(exc)}


async def get_job(prompt_id: str) -> dict[str, Any]:
    """Return the current status of a previously submitted job.

    Parameters
    ----------
    prompt_id:
        The ``prompt_id`` returned by ``run_workflow`` or ``run_template``.

    Returns
    -------
    dict
        Keys: ``prompt_id``, ``state`` (string), ``history``, ``error``.
        On connection failure: ``{"error": "<message>"}``.
    """
    try:
        status: JobStatus = await runner.get_job(prompt_id)
        return _job_status_to_dict(status)
    except ComfyConnectionError as exc:
        return {"error": str(exc)}


async def get_queue_status() -> dict[str, Any]:
    """Return the raw ComfyUI queue status dict.

    Returns
    -------
    dict
        The queue dict from ComfyUI (``queue_running`` and ``queue_pending``
        lists).  On connection failure: ``{"error": "<message>"}``.
    """
    try:
        # FlowRunner exposes no get_queue method; call client directly.
        # get_queue is a read-only probe — it must not queue behind the
        # submission guard, so bypassing the runner is intentional.
        return await asyncio.to_thread(client.get_queue)
    except ComfyConnectionError as exc:
        return {"error": str(exc)}


async def cancel_job(prompt_id: str) -> dict[str, Any]:
    """Remove *prompt_id* from the pending queue.

    Parameters
    ----------
    prompt_id:
        The prompt identifier to cancel.

    Returns
    -------
    dict
        ``{"cancelled": prompt_id}`` on success.
        On connection failure: ``{"error": "<message>"}``.
    """
    try:
        # FlowRunner exposes no cancel method; call client directly.
        # cancel is a control op that intentionally must not queue behind
        # the submission guard (would risk deadlock if a run is in flight).
        await asyncio.to_thread(client.cancel, prompt_id)
        return {"cancelled": prompt_id}
    except ComfyConnectionError as exc:
        return {"error": str(exc)}
