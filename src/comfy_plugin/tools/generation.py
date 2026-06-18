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

from pydantic import BaseModel

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
# Pydantic parameter models
# ---------------------------------------------------------------------------


class Txt2ImgParams(BaseModel):
    model: str
    positive: str
    negative: str
    width: int = 512
    height: int = 512
    steps: int = 20
    cfg: float = 7.0
    sampler_name: str = "euler"
    scheduler: str = "normal"
    seed: int = 0


class Txt2AudioParams(BaseModel):
    model: str
    positive: str
    negative: str = ""
    seconds: float = 47.0
    batch_size: int = 1
    sample_rate: int = 44100
    steps: int = 20
    cfg: float = 3.5
    sampler_name: str = "dpmpp_3m_sde_gpu"
    scheduler: str = "exponential"
    seed: int = 0


class Txt2VideoParams(BaseModel):
    positive: str = ""
    negative: str = ""
    width: int = 512
    height: int = 512
    seed: int = 0


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

        Parameter keys use the PARAM_* placeholder naming convention: keys are
        the uppercased <NAME> segment of each placeholder (e.g.
        POSITIVE_PROMPT, STEPS, MODEL), not the snake_case names used by the
        scaffold tools. Call get_template_params(name) first to discover the
        exact keys, types, and required/optional status for any template.
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


async def run_txt2img(params: Txt2ImgParams, timeout: float = 120.0) -> dict[str, Any]:
    """Build a text-to-image scaffold graph and submit it to ComfyUI.

    All fields except ``model``, ``positive``, and ``negative`` have defaults,
    so only those three are required. The scaffold builds a complete KSampler
    pipeline graph internally. The UI-format workflow is written to
    ``COMFYUI_WORKFLOW_DIR`` (if set) before submission so the user can open
    it in the ComfyUI canvas and watch live node highlighting.

    ``timeout`` has the same semantics as ``run_workflow``: maximum seconds to
    wait before returning a ``state="running"`` response for re-polling via
    ``get_job``.

    Note: ``params`` is a nested object — pass it as ``{"params": {"model":
    "...", "positive": "...", ...}}``, not as flat top-level keys.

    Parameters
    ----------
    params:
        ``Txt2ImgParams`` with fields: model (str, required), positive (str,
        required), negative (str, required), width (int, default 512), height
        (int, default 512), steps (int, default 20), cfg (float, default 7.0),
        sampler_name (str, default "euler"), scheduler (str, default "normal"),
        seed (int, default 0).
    timeout:
        Maximum seconds to wait for completion.

    Returns
    -------
    dict
        Keys: ``prompt_id``, ``state`` (string), ``outputs``, ``history``,
        ``error``. On connection failure: ``{"error": "<message>"}``.
    """
    try:
        graph: GraphBuilder = txt2img(**params.model_dump())
    except TypeError as exc:
        return {"error": str(exc)}
    ui_dict = to_ui(graph)
    await maybe_write_workflow(ui_dict, config.workflow_dir)
    prompt = to_api(graph)
    try:
        result: RunResult = await runner.run(prompt, timeout=timeout)
    except ComfyConnectionError as exc:
        return {"error": str(exc)}
    return _run_result_to_dict(result)


async def run_txt2audio(
    params: Txt2AudioParams, timeout: float = 120.0
) -> dict[str, Any]:
    """Build a text-to-audio scaffold graph and submit it to ComfyUI.

    ``model`` and ``positive`` are required; all other fields have defaults.
    The scaffold builds a complete audio-generation pipeline graph internally.
    The UI-format workflow is written to ``COMFYUI_WORKFLOW_DIR`` (if set)
    before submission so the user can open it in the ComfyUI canvas.

    ``timeout`` has the same semantics as ``run_workflow``: maximum seconds to
    wait before returning a ``state="running"`` response for re-polling via
    ``get_job``.

    Note: ``params`` is a nested object — pass it as ``{"params": {"model":
    "...", "positive": "...", ...}}``, not as flat top-level keys.

    Parameters
    ----------
    params:
        ``Txt2AudioParams`` with fields: model (str, required), positive (str,
        required), negative (str, default ""), seconds (float, default 47.0),
        batch_size (int, default 1), sample_rate (int, default 44100), steps
        (int, default 20), cfg (float, default 3.5), sampler_name (str, default
        "dpmpp_3m_sde_gpu"), scheduler (str, default "exponential"), seed (int,
        default 0).
    timeout:
        Maximum seconds to wait for completion.

    Returns
    -------
    dict
        Keys: ``prompt_id``, ``state`` (string), ``outputs``, ``history``,
        ``error``. On connection failure: ``{"error": "<message>"}``.
    """
    try:
        graph: GraphBuilder = txt2audio(**params.model_dump())
    except TypeError as exc:
        return {"error": str(exc)}
    ui_dict = to_ui(graph)
    await maybe_write_workflow(ui_dict, config.workflow_dir)
    prompt = to_api(graph)
    try:
        result: RunResult = await runner.run(prompt, timeout=timeout)
    except ComfyConnectionError as exc:
        return {"error": str(exc)}
    return _run_result_to_dict(result)


async def run_txt2video(
    params: Txt2VideoParams, timeout: float = 120.0
) -> dict[str, Any]:
    """Build a text-to-video scaffold graph and submit it to ComfyUI.

    Note: ``txt2video`` always raises ``NotImplementedError`` because it
    requires a custom video-generation node not present in stock ComfyUI.
    This tool is exposed for completeness and will always return
    ``{"error": "<NotImplementedError message>"}``.

    All fields have defaults; none are required.

    ``timeout`` has the same semantics as ``run_workflow``.

    Note: ``params`` is a nested object — pass it as ``{"params": {"positive":
    "...", ...}}``, not as flat top-level keys.

    Parameters
    ----------
    params:
        ``Txt2VideoParams`` with fields: positive (str, default ""), negative
        (str, default ""), width (int, default 512), height (int, default 512),
        seed (int, default 0).
    timeout:
        Maximum seconds to wait for completion (unused in practice since
        txt2video never submits).

    Returns
    -------
    dict
        Always ``{"error": "<message>"}`` — txt2video is not implemented.
    """
    try:
        txt2video(**params.model_dump())
    except NotImplementedError as exc:
        return {"error": str(exc)}
    return {"error": "txt2video scaffold is not implemented."}
