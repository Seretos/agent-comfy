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
    GraphBuilder,
    JobStatus,
    MissingParameterError,
    RunResult,
    load_builtin_template,
    render,
    to_api,
    to_ui,
    txt2audio,
    txt2img,
    txt2video,
)

from comfy_plugin import config
from comfy_plugin.config import client, runner
from comfy_plugin.workflow_export import maybe_write_workflow

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCAFFOLDS = {
    "txt2img": txt2img,
    "txt2audio": txt2audio,
    "txt2video": txt2video,
}

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


async def run_scaffold(
    medium: str,
    params: dict[str, Any],
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Build a scaffold graph for *medium*, export a UI workflow file, then submit.

    Writes the UI-format workflow JSON to ``COMFYUI_WORKFLOW_DIR`` (if set)
    *before* submitting so the user can open it in the ComfyUI canvas and
    watch live node highlighting as the job executes.

    Parameters
    ----------
    medium:
        One of ``"txt2img"``, ``"txt2audio"``, or ``"txt2video"``.
    params:
        Flat dict of keyword arguments forwarded to the matching scaffold.

        *txt2img* kwargs:
            - ``model`` (str, required) — checkpoint filename.
            - ``positive`` (str, required) — positive prompt.
            - ``negative`` (str, required) — negative prompt.
            - ``width`` (int, default 512)
            - ``height`` (int, default 512)
            - ``steps`` (int, default 20)
            - ``cfg`` (float, default 7.0)
            - ``sampler_name`` (str, default ``"euler"``)
            - ``scheduler`` (str, default ``"normal"``)
            - ``seed`` (int, default 0)

        *txt2audio* kwargs:
            - ``positive`` (str, default ``""``)
            - ``negative`` (str, default ``""``)
            - ``seed`` (int, default 0)

        *txt2video* kwargs:
            - ``positive`` (str, default ``""``)
            - ``negative`` (str, default ``""``)
            - ``width`` (int, default 512)
            - ``height`` (int, default 512)
            - ``seed`` (int, default 0)

    timeout:
        Maximum seconds to wait for completion (same semantics as
        ``run_workflow``).

    Returns
    -------
    dict
        Same shape as ``run_workflow`` on success.
        ``{"error": "<message>"}`` for unknown medium, bad kwargs, or
        connection failure.
    """
    # 1. Dispatch on medium to get a GraphBuilder.
    scaffold_fn = _SCAFFOLDS.get(medium)
    if scaffold_fn is None:
        return {
            "error": (
                f"Unknown scaffold medium: {medium}. "
                "Use 'txt2img', 'txt2audio', or 'txt2video'."
            )
        }

    try:
        graph: GraphBuilder = scaffold_fn(**params)
    except TypeError as exc:
        return {"error": str(exc)}

    # 2. Build the UI dict.
    ui_dict = to_ui(graph)

    # 3. Write UI workflow to disk before submission (best-effort; OSError swallowed).
    await maybe_write_workflow(ui_dict, config.workflow_dir)

    # 4. Build the API prompt.
    prompt = to_api(graph)

    # 5. Submit and wait.
    try:
        result: RunResult = await runner.run(prompt, timeout=timeout)
    except ComfyConnectionError as exc:
        return {"error": str(exc)}

    # 6. Return in the standard shape.
    return _run_result_to_dict(result)
