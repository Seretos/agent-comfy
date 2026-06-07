"""Smoke and unit tests for the comfy MCP server wrapper.

All tests mock the lib client/runner — no live ComfyUI required.
"""
from __future__ import annotations

import importlib
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib_python_comfy import (
    ComfyConnectionError,
    JobState,
    JobStatus,
    RunResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run_result(
    prompt_id: str = "pid-1",
    state: JobState = JobState.COMPLETED,
    outputs: dict | None = None,
    history: dict | None = None,
    error: str | None = None,
) -> RunResult:
    return RunResult(
        prompt_id=prompt_id,
        state=state,
        outputs=outputs or {},
        history=history or {},
        error=error,
    )


def _make_job_status(
    prompt_id: str = "pid-1",
    state: JobState = JobState.COMPLETED,
    history: dict | None = None,
    error: str | None = None,
) -> JobStatus:
    return JobStatus(
        prompt_id=prompt_id,
        state=state,
        history=history or {},
        error=error,
    )


# ---------------------------------------------------------------------------
# Import / regression test
# ---------------------------------------------------------------------------


def test_import_run_workflow():
    """Regression: run_workflow and run_template must be importable."""
    from comfy_plugin.tools.generation import run_template, run_workflow  # noqa: F401


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def test_all_five_tools_registered():
    """All five generation tools must be registered on the FastMCP app."""
    from comfy_plugin.server import mcp

    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    assert "run_workflow" in tool_names
    assert "run_template" in tool_names
    assert "get_job" in tool_names
    assert "get_queue_status" in tool_names
    assert "cancel_job" in tool_names


# ---------------------------------------------------------------------------
# run_workflow
# ---------------------------------------------------------------------------


async def test_run_workflow_happy_path():
    """run_workflow delegates to runner.run and returns a plain dict."""
    expected = _make_run_result(prompt_id="abc", state=JobState.COMPLETED)

    with patch("comfy_plugin.tools.generation.runner") as mock_runner:
        mock_runner.run = AsyncMock(return_value=expected)
        from comfy_plugin.tools.generation import run_workflow

        result = await run_workflow({"1": {"class_type": "KSampler", "inputs": {}}})

    assert result["prompt_id"] == "abc"
    assert result["state"] == "completed"
    assert isinstance(result["state"], str)


async def test_run_workflow_connection_error():
    """run_workflow catches ComfyConnectionError and returns error dict."""
    with patch("comfy_plugin.tools.generation.runner") as mock_runner:
        mock_runner.run = AsyncMock(side_effect=ComfyConnectionError("refused"))
        from comfy_plugin.tools.generation import run_workflow

        result = await run_workflow({})

    assert "error" in result
    assert "refused" in result["error"]


async def test_run_workflow_running_state_serialises():
    """A still-running job returns state='running' as a plain string."""
    expected = _make_run_result(prompt_id="pid-run", state=JobState.RUNNING)

    with patch("comfy_plugin.tools.generation.runner") as mock_runner:
        mock_runner.run = AsyncMock(return_value=expected)
        from comfy_plugin.tools.generation import run_workflow

        result = await run_workflow({})

    assert result["state"] == "running"
    assert isinstance(result["state"], str)


# ---------------------------------------------------------------------------
# run_template
# ---------------------------------------------------------------------------


async def test_run_template_unknown_template_returns_error():
    """run_template with an unknown template name returns an error dict."""
    from comfy_plugin.tools.generation import run_template

    result = await run_template("no_such_template_xyz", {})

    assert "error" in result


async def test_run_template_missing_param_returns_error():
    """run_template with a missing required param returns an error dict."""
    with (
        patch("comfy_plugin.tools.generation.load_builtin_template") as mock_load,
        patch("comfy_plugin.tools.generation.render") as mock_render,
    ):
        mock_load.return_value = {"1": {}}
        from lib_python_comfy import MissingParameterError

        mock_render.side_effect = MissingParameterError("PROMPT is required")
        from comfy_plugin.tools.generation import run_template

        result = await run_template("txt2img_basic", {})

    assert "error" in result
    assert "PROMPT" in result["error"]


async def test_run_template_connection_error():
    """run_template catches ComfyConnectionError and returns error dict."""
    with (
        patch("comfy_plugin.tools.generation.load_builtin_template") as mock_load,
        patch("comfy_plugin.tools.generation.render") as mock_render,
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
    ):
        mock_load.return_value = {}
        mock_render.return_value = {}
        mock_runner.run = AsyncMock(side_effect=ComfyConnectionError("timeout"))
        from comfy_plugin.tools.generation import run_template

        result = await run_template("txt2img_basic", {"PROMPT": "a dog"})

    assert "error" in result
    assert "timeout" in result["error"]


# ---------------------------------------------------------------------------
# get_job
# ---------------------------------------------------------------------------


async def test_get_job_happy_path():
    """get_job returns a plain dict with state as a string."""
    expected = _make_job_status(prompt_id="pid-2", state=JobState.QUEUED)

    with patch("comfy_plugin.tools.generation.runner") as mock_runner:
        mock_runner.get_job = AsyncMock(return_value=expected)
        from comfy_plugin.tools.generation import get_job

        result = await get_job("pid-2")

    assert result["prompt_id"] == "pid-2"
    assert result["state"] == "queued"
    assert isinstance(result["state"], str)


async def test_get_job_connection_error():
    """get_job catches ComfyConnectionError and returns error dict."""
    with patch("comfy_plugin.tools.generation.runner") as mock_runner:
        mock_runner.get_job = AsyncMock(
            side_effect=ComfyConnectionError("connection refused")
        )
        from comfy_plugin.tools.generation import get_job

        result = await get_job("pid-missing")

    assert "error" in result
    assert "connection refused" in result["error"]


# ---------------------------------------------------------------------------
# get_queue_status
# ---------------------------------------------------------------------------


async def test_get_queue_status_happy_path():
    """get_queue_status returns the raw dict from the client."""
    queue_data = {"queue_running": [], "queue_pending": []}

    with patch("comfy_plugin.tools.generation.client") as mock_client:
        mock_client.get_queue = MagicMock(return_value=queue_data)
        from comfy_plugin.tools.generation import get_queue_status

        result = await get_queue_status()

    assert result == queue_data


async def test_get_queue_status_connection_error():
    """get_queue_status catches ComfyConnectionError and returns error dict."""
    with patch("comfy_plugin.tools.generation.client") as mock_client:
        mock_client.get_queue = MagicMock(
            side_effect=ComfyConnectionError("unreachable")
        )
        from comfy_plugin.tools.generation import get_queue_status

        result = await get_queue_status()

    assert "error" in result
    assert "unreachable" in result["error"]


# ---------------------------------------------------------------------------
# cancel_job
# ---------------------------------------------------------------------------


async def test_cancel_job_happy_path():
    """cancel_job returns {"cancelled": prompt_id} on success."""
    with patch("comfy_plugin.tools.generation.client") as mock_client:
        mock_client.cancel = MagicMock(return_value=None)
        from comfy_plugin.tools.generation import cancel_job

        result = await cancel_job("pid-cancel")

    assert result == {"cancelled": "pid-cancel"}


async def test_cancel_job_connection_error():
    """cancel_job catches ComfyConnectionError and returns error dict."""
    with patch("comfy_plugin.tools.generation.client") as mock_client:
        mock_client.cancel = MagicMock(side_effect=ComfyConnectionError("refused"))
        from comfy_plugin.tools.generation import cancel_job

        result = await cancel_job("pid-cancel")

    assert "error" in result
    assert "refused" in result["error"]


# ---------------------------------------------------------------------------
# Config env-var override
# ---------------------------------------------------------------------------


def test_config_comfy_url_default():
    """COMFYUI_URL defaults to http://localhost:8188."""
    import comfy_plugin.config as cfg

    # _base_url is the only available handle on ComfyClient for the resolved URL.
    # The default is baked in at import time; we verify the client reflects it.
    assert cfg.client._base_url == cfg.comfy_url.rstrip("/")


def test_config_comfy_url_override():
    """COMFYUI_URL env var overrides the base URL used by the client."""
    import importlib
    import os

    import comfy_plugin.config as cfg_mod

    custom_url = "http://192.168.1.100:8188"
    # Reload config with the env var patched, then always restore original state
    # in a finally block so stale singletons cannot leak into later tests.
    # (tools.generation holds module-level references to client/runner; those
    # refs point at the pre-reload objects and are unaffected by the reload —
    # restoring config here prevents any subsequent config-level confusion.)
    try:
        with patch.dict(os.environ, {"COMFYUI_URL": custom_url}):
            importlib.reload(cfg_mod)
            # _base_url is the only available handle on ComfyClient for the URL.
            assert cfg_mod.comfy_url == custom_url
            assert cfg_mod.client._base_url == custom_url.rstrip("/")
    finally:
        # Restore config module to the original (no custom env var) state.
        importlib.reload(cfg_mod)


# ---------------------------------------------------------------------------
# run_scaffold — registration
# ---------------------------------------------------------------------------


def test_run_scaffold_registered():
    """run_scaffold must be registered as an MCP tool."""
    from comfy_plugin.server import mcp

    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    assert "run_scaffold" in tool_names


# ---------------------------------------------------------------------------
# run_scaffold — happy-path & workflow file writing
# ---------------------------------------------------------------------------


async def test_run_scaffold_txt2img_writes_workflow_file(tmp_path):
    """run_scaffold writes a JSON workflow file with expected ui keys."""
    import re

    expected_result = _make_run_result(prompt_id="scaffold-1", state=JobState.COMPLETED)

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", str(tmp_path)),
    ):
        mock_runner.run = AsyncMock(return_value=expected_result)
        from comfy_plugin.tools.generation import run_scaffold

        result = await run_scaffold(
            "txt2img",
            {"model": "v1.safetensors", "positive": "a cat", "negative": ""},
        )

    assert result.get("error") is None, f"unexpected error: {result.get('error')}"
    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1

    import json as _json

    data = _json.loads(json_files[0].read_text(encoding="utf-8"))
    # to_ui always emits these top-level keys
    for key in ("nodes", "links", "groups", "config", "extra", "version"):
        assert key in data, f"missing key: {key}"

    # filename pattern: comfy_YYYYMMDD_HHMMSS_ffffff.json
    assert re.match(r"comfy_\d{8}_\d{6}_\d{6}\.json", json_files[0].name)


async def test_run_scaffold_file_written_before_submit(tmp_path):
    """The workflow file must already exist when runner.run is called."""
    files_present_at_submit: list[bool] = []

    async def _side_effect(prompt, *, timeout):
        files_present_at_submit.append(bool(list(tmp_path.glob("*.json"))))
        return _make_run_result()

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", str(tmp_path)),
    ):
        mock_runner.run = _side_effect
        from comfy_plugin.tools.generation import run_scaffold

        await run_scaffold(
            "txt2img",
            {"model": "v1.safetensors", "positive": "cat", "negative": ""},
        )

    assert files_present_at_submit == [True], "file was not written before runner.run"


async def test_run_scaffold_no_write_when_workflow_dir_none(tmp_path):
    """When workflow_dir is None nothing is written and no error is returned."""
    expected_result = _make_run_result()

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", None),
    ):
        mock_runner.run = AsyncMock(return_value=expected_result)
        from comfy_plugin.tools.generation import run_scaffold

        result = await run_scaffold(
            "txt2img",
            {"model": "v1.safetensors", "positive": "cat", "negative": ""},
        )

    assert result.get("error") is None, f"unexpected error: {result.get('error')}"
    # Canary: tmp_path is a clean directory — nothing must have been written to it.
    assert list(tmp_path.glob("*.json")) == [], "expected no JSON files when workflow_dir is None"


async def test_run_scaffold_write_failure_is_swallowed(tmp_path):
    """An OSError during file write must not propagate — result is still returned."""
    expected_result = _make_run_result()

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", str(tmp_path)),
        patch(
            "comfy_plugin.workflow_export.asyncio.to_thread",
            side_effect=OSError("disk full"),
        ),
    ):
        mock_runner.run = AsyncMock(return_value=expected_result)
        from comfy_plugin.tools.generation import run_scaffold

        result = await run_scaffold(
            "txt2img",
            {"model": "v1.safetensors", "positive": "cat", "negative": ""},
        )

    assert result.get("error") is None, f"unexpected error: {result.get('error')}"
    assert result["state"] == "completed"


async def test_run_scaffold_mkdir_creates_missing_directory(tmp_path):
    """workflow_dir may be a non-existent nested path; it must be created."""
    nested = tmp_path / "a" / "b" / "c"
    assert not nested.exists()

    expected_result = _make_run_result()

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", str(nested)),
    ):
        mock_runner.run = AsyncMock(return_value=expected_result)
        from comfy_plugin.tools.generation import run_scaffold

        await run_scaffold(
            "txt2img",
            {"model": "v1.safetensors", "positive": "cat", "negative": ""},
        )

    assert nested.exists()
    assert list(nested.glob("*.json")), "expected a JSON file inside the created directory"


# ---------------------------------------------------------------------------
# run_scaffold — error paths
# ---------------------------------------------------------------------------


async def test_run_scaffold_unknown_medium():
    """An unknown medium returns an error dict containing the bad medium name."""
    from comfy_plugin.tools.generation import run_scaffold

    result = await run_scaffold("txt2gif", {})

    assert "error" in result
    assert "txt2gif" in result["error"]


async def test_run_scaffold_missing_required_param():
    """Calling txt2img without 'model' returns an error dict (TypeError caught)."""
    from comfy_plugin.tools.generation import run_scaffold

    result = await run_scaffold("txt2img", {"positive": "cat", "negative": ""})

    assert "error" in result


async def test_run_scaffold_connection_error():
    """ComfyConnectionError from runner.run is caught and returned as error dict."""
    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", None),
    ):
        mock_runner.run = AsyncMock(
            side_effect=ComfyConnectionError("connection refused")
        )
        from comfy_plugin.tools.generation import run_scaffold

        result = await run_scaffold(
            "txt2img",
            {"model": "v1.safetensors", "positive": "cat", "negative": ""},
        )

    assert "error" in result
    assert "connection refused" in result["error"]


# ---------------------------------------------------------------------------
# run_scaffold — txt2audio and txt2video dispatch
# ---------------------------------------------------------------------------


async def test_run_scaffold_txt2audio_and_txt2video(tmp_path):
    """txt2audio and txt2video both dispatch correctly, produce no error, write file."""
    expected_result = _make_run_result()

    for medium, params in [
        ("txt2audio", {"positive": "rain", "negative": "", "seed": 1}),
        ("txt2video", {"positive": "wave", "negative": "", "width": 256, "height": 256, "seed": 2}),
    ]:
        subdir = tmp_path / medium
        with (
            patch("comfy_plugin.tools.generation.runner") as mock_runner,
            patch("comfy_plugin.config.workflow_dir", str(subdir)),
        ):
            mock_runner.run = AsyncMock(return_value=expected_result)
            from comfy_plugin.tools.generation import run_scaffold

            result = await run_scaffold(medium, params)

        assert result.get("error") is None, f"{medium} returned error: {result.get('error')}"
        json_files = list(subdir.glob("*.json"))
        assert len(json_files) == 1, f"{medium}: expected 1 JSON file, got {len(json_files)}"
