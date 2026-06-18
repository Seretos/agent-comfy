"""Tests for the typed scaffold generation tools.

All tests mock the lib runner — no live ComfyUI required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from lib_python_comfy import (
    ComfyConnectionError,
    JobState,
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


# ---------------------------------------------------------------------------
# run_txt2img
# ---------------------------------------------------------------------------


async def test_run_txt2img_happy_path():
    """run_txt2img returns the _run_result_to_dict shape on success."""
    expected = _make_run_result(prompt_id="img-1", state=JobState.COMPLETED)

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", None),
    ):
        mock_runner.run = AsyncMock(return_value=expected)

        from comfy_plugin.tools.generation import Txt2ImgParams, run_txt2img

        params = Txt2ImgParams(
            model="v1.safetensors",
            positive="a beautiful landscape",
            negative="ugly",
        )
        result = await run_txt2img(params)

    assert result["prompt_id"] == "img-1"
    assert result["state"] == "completed"
    assert isinstance(result["state"], str)
    assert "outputs" in result
    assert "history" in result
    assert "error" in result


async def test_run_txt2img_connection_error():
    """run_txt2img catches ComfyConnectionError and returns error dict."""
    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", None),
    ):
        mock_runner.run = AsyncMock(side_effect=ComfyConnectionError("refused"))

        from comfy_plugin.tools.generation import Txt2ImgParams, run_txt2img

        params = Txt2ImgParams(
            model="v1.safetensors",
            positive="a cat",
            negative="",
        )
        result = await run_txt2img(params)

    assert "error" in result
    assert "refused" in result["error"]


async def test_run_txt2img_writes_workflow_file(tmp_path):
    """run_txt2img writes a UI workflow JSON file when workflow_dir is set."""
    expected = _make_run_result(prompt_id="img-wf")

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", str(tmp_path)),
    ):
        mock_runner.run = AsyncMock(return_value=expected)

        from comfy_plugin.tools.generation import Txt2ImgParams, run_txt2img

        params = Txt2ImgParams(
            model="v1.safetensors",
            positive="a dog",
            negative="",
        )
        result = await run_txt2img(params)

    assert result.get("error") is None
    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1


async def test_run_txt2img_defaults_accepted():
    """run_txt2img accepts only required fields; defaults fill in the rest."""
    expected = _make_run_result()

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", None),
    ):
        mock_runner.run = AsyncMock(return_value=expected)

        from comfy_plugin.tools.generation import Txt2ImgParams, run_txt2img

        # Only the three required fields
        params = Txt2ImgParams(model="model.ckpt", positive="sky", negative="")
        result = await run_txt2img(params)

    assert result.get("error") is None
    assert result["state"] == "completed"


# ---------------------------------------------------------------------------
# run_txt2audio
# ---------------------------------------------------------------------------


async def test_run_txt2audio_happy_path():
    """run_txt2audio returns the _run_result_to_dict shape on success."""
    expected = _make_run_result(prompt_id="audio-1", state=JobState.COMPLETED)

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", None),
    ):
        mock_runner.run = AsyncMock(return_value=expected)

        from comfy_plugin.tools.generation import Txt2AudioParams, run_txt2audio

        params = Txt2AudioParams(
            model="audio_model.safetensors",
            positive="rain on the roof",
        )
        result = await run_txt2audio(params)

    assert result["prompt_id"] == "audio-1"
    assert result["state"] == "completed"
    assert isinstance(result["state"], str)
    assert "outputs" in result
    assert "history" in result
    assert "error" in result


async def test_run_txt2audio_connection_error():
    """run_txt2audio catches ComfyConnectionError and returns error dict."""
    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", None),
    ):
        mock_runner.run = AsyncMock(side_effect=ComfyConnectionError("timeout"))

        from comfy_plugin.tools.generation import Txt2AudioParams, run_txt2audio

        params = Txt2AudioParams(model="audio_model.safetensors", positive="thunder")
        result = await run_txt2audio(params)

    assert "error" in result
    assert "timeout" in result["error"]


async def test_run_txt2audio_defaults_accepted():
    """run_txt2audio accepts only required fields (model+positive); defaults fill the rest."""
    expected = _make_run_result()

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", None),
    ):
        mock_runner.run = AsyncMock(return_value=expected)

        from comfy_plugin.tools.generation import Txt2AudioParams, run_txt2audio

        params = Txt2AudioParams(model="audio.ckpt", positive="forest ambience")
        result = await run_txt2audio(params)

    assert result.get("error") is None
    assert result["state"] == "completed"


async def test_run_txt2audio_missing_positive_returns_error():
    """Regression: omitting positive from Txt2AudioParams raises ValidationError (required field)."""
    import pytest
    from pydantic import ValidationError

    from comfy_plugin.tools.generation import Txt2AudioParams

    with pytest.raises(ValidationError):
        Txt2AudioParams(model="audio.ckpt")  # positive is required


# ---------------------------------------------------------------------------
# run_txt2video
# ---------------------------------------------------------------------------


async def test_run_txt2video_always_returns_error():
    """run_txt2video always returns an error dict (NotImplementedError from lib)."""
    from comfy_plugin.tools.generation import Txt2VideoParams, run_txt2video

    params = Txt2VideoParams(positive="ocean waves", negative="")
    result = await run_txt2video(params)

    assert "error" in result
    assert len(result["error"]) > 0


async def test_run_txt2video_does_not_call_runner():
    """run_txt2video must not submit to ComfyUI — runner.run must not be called."""
    with patch("comfy_plugin.tools.generation.runner") as mock_runner:
        mock_runner.run = AsyncMock()

        from comfy_plugin.tools.generation import Txt2VideoParams, run_txt2video

        params = Txt2VideoParams()
        result = await run_txt2video(params)

    assert "error" in result
    mock_runner.run.assert_not_called()


async def test_run_txt2video_all_defaults():
    """run_txt2video accepts no required fields (all have defaults)."""
    from comfy_plugin.tools.generation import Txt2VideoParams, run_txt2video

    # All defaults — should not raise; must return error dict
    params = Txt2VideoParams()
    result = await run_txt2video(params)

    assert "error" in result


# ---------------------------------------------------------------------------
# maybe_write_workflow regression tests (ported from removed smoke tests)
# ---------------------------------------------------------------------------


async def test_run_txt2img_workflow_file_written_before_submit(tmp_path):
    """The workflow JSON must exist on disk at the moment runner.run is called."""
    files_present_at_submit: list[bool] = []

    async def _side_effect(prompt, *, timeout):
        files_present_at_submit.append(bool(list(tmp_path.glob("*.json"))))
        return _make_run_result()

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", str(tmp_path)),
    ):
        mock_runner.run = _side_effect

        from comfy_plugin.tools.generation import Txt2ImgParams, run_txt2img

        params = Txt2ImgParams(
            model="v1.safetensors", positive="cat", negative=""
        )
        await run_txt2img(params)

    assert files_present_at_submit == [True], "file was not written before runner.run"


async def test_run_txt2img_oserror_swallowed(tmp_path):
    """An OSError during workflow export must not propagate — result still returned."""
    expected = _make_run_result()

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", str(tmp_path)),
        patch(
            "comfy_plugin.workflow_export.asyncio.to_thread",
            side_effect=OSError("disk full"),
        ),
    ):
        mock_runner.run = AsyncMock(return_value=expected)

        from comfy_plugin.tools.generation import Txt2ImgParams, run_txt2img

        params = Txt2ImgParams(
            model="v1.safetensors", positive="cat", negative=""
        )
        result = await run_txt2img(params)

    assert result.get("error") is None, f"unexpected error: {result.get('error')}"
    assert result["state"] == "completed"


# ---------------------------------------------------------------------------
# _run_result_to_dict: timed_out field
# ---------------------------------------------------------------------------


async def test_run_workflow_timed_out_true():
    """run_workflow returns timed_out=True when state is RUNNING (timeout reached)."""
    expected = _make_run_result(prompt_id="pid-timeout", state=JobState.RUNNING)

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
    ):
        mock_runner.run = AsyncMock(return_value=expected)
        from comfy_plugin.tools.generation import run_workflow

        result = await run_workflow({})

    assert result["state"] == "running"
    assert result["timed_out"] is True


async def test_run_workflow_timed_out_false_on_completed():
    """run_workflow returns timed_out=False when state is COMPLETED."""
    expected = _make_run_result(prompt_id="pid-done", state=JobState.COMPLETED)

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
    ):
        mock_runner.run = AsyncMock(return_value=expected)
        from comfy_plugin.tools.generation import run_workflow

        result = await run_workflow({})

    assert result["state"] == "completed"
    assert result["timed_out"] is False


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


async def test_get_config_returns_expected_shape():
    """get_config returns a dict with comfy_url, workflow_dir, and asset_ttl."""
    import comfy_plugin.config as cfg_mod

    with (
        patch.object(cfg_mod, "comfy_url", "http://test-host:9000"),
        patch.object(cfg_mod, "workflow_dir", "/tmp/workflows"),
        patch.object(cfg_mod, "asset_ttl", 7200),
    ):
        from comfy_plugin.tools.generation import get_config

        result = await get_config()

    assert result == {
        "comfy_url": "http://test-host:9000",
        "workflow_dir": "/tmp/workflows",
        "asset_ttl": 7200,
    }


async def test_get_config_workflow_dir_none():
    """get_config returns workflow_dir=None when COMFYUI_WORKFLOW_DIR is unset."""
    import comfy_plugin.config as cfg_mod

    with (
        patch.object(cfg_mod, "comfy_url", "http://localhost:8188"),
        patch.object(cfg_mod, "workflow_dir", None),
        patch.object(cfg_mod, "asset_ttl", 3600),
    ):
        from comfy_plugin.tools.generation import get_config

        result = await get_config()

    assert result["workflow_dir"] is None
    assert result["asset_ttl"] == 3600


async def test_run_txt2img_mkdir_creates_missing_directory(tmp_path):
    """workflow_dir may be a non-existent nested path; mkdir must create it."""
    nested = tmp_path / "a" / "b" / "c"
    assert not nested.exists()

    expected = _make_run_result()

    with (
        patch("comfy_plugin.tools.generation.runner") as mock_runner,
        patch("comfy_plugin.config.workflow_dir", str(nested)),
    ):
        mock_runner.run = AsyncMock(return_value=expected)

        from comfy_plugin.tools.generation import Txt2ImgParams, run_txt2img

        params = Txt2ImgParams(
            model="v1.safetensors", positive="cat", negative=""
        )
        await run_txt2img(params)

    assert nested.exists()
    assert list(nested.glob("*.json")), "expected a JSON file inside the created directory"
