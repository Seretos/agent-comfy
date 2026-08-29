"""Driving tests for work package #50 ("Wire up project-local comfy templates").

These tests exercise the not-yet-implemented ``COMFYUI_PROJECT_TEMPLATES_DIR``
wiring: discovery of project-local templates under
``<git-root>/.seretos/comfy/workflows``, origin tagging at every call site,
project-overrides-built-in collision handling, and the disabled/edge-case
paths of ``_resolve_project_templates_dir`` / ``template_extra_dirs``.

All tests mock the lib client/runner where relevant -- no live ComfyUI
required. Mirrors the style of tests/test_startup_hook.py (env-var /
git-root-walk-up resolution pattern) and tests/test_smoke.py (mocked runner).

At this stage (phase=tests) none of ``config._find_git_root``,
``config._resolve_project_templates_dir``, ``config.project_templates_dir``,
or ``config.template_extra_dirs`` exist yet, and the discovery/generation
call sites still use the old built-in-only loader. Tests that call the new
config surface directly therefore fail with AttributeError (the function
does not exist yet); tests that exercise list_templates/get_template_params/
run_template fail with assertion errors showing the old (built-in-only,
un-tagged) shape.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from lib_python_comfy import JobState, RunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_template(directory: Path, name: str, data: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _minimal_project_template() -> dict:
    """A tiny but valid API-format template with one required PARAM_* placeholder."""
    return {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "PARAM_STR_POSITIVE_PROMPT",
                "clip": ["2", 1],
            },
        },
        "2": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "some-model.safetensors"},
        },
    }


def _project_override_txt2img_basic(marker: str = "PROJECT_OVERRIDE_MARKER") -> dict:
    """A project-local txt2img_basic that collides with the built-in of the same
    name, carrying a distinguishing marker (an extra PARAM_* placeholder whose
    default is a literal marker string) so tests can tell which version won."""
    return {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "PARAM_STR_POSITIVE_PROMPT", "clip": ["4", 1]},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "PARAM_OPT_STR_NEGATIVE_PROMPT|default:", "clip": ["4", 1]},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": "PARAM_SEED_SEED",
                "steps": "PARAM_INT_STEPS",
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["1", 0],
                "negative": ["2", 0],
                "latent_image": ["5", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "PARAM_STR_MODEL"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": f"PARAM_OPT_STR_PROJECT_MARKER|default:{marker}",
                "images": ["6", 0],
            },
        },
    }


def _make_run_result(
    prompt_id: str = "pid-1",
    state: JobState = JobState.COMPLETED,
) -> RunResult:
    return RunResult(prompt_id=prompt_id, state=state, outputs={}, history={}, error=None)


# ---------------------------------------------------------------------------
# R1 -- list_templates tags project and built-in origins
# ---------------------------------------------------------------------------


async def test_list_templates_tags_project_and_builtin_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """list_templates() returns {name, origin} entries: a project-dir template
    tagged origin='project' and txt2img_basic tagged origin='built-in'."""
    import comfy_plugin.config as cfg_mod

    project_dir = tmp_path / "workflows"
    _write_template(project_dir, "my_project_widget", _minimal_project_template())

    monkeypatch.setenv("COMFYUI_PROJECT_TEMPLATES_DIR", str(project_dir))
    importlib.reload(cfg_mod)
    try:
        from comfy_plugin.tools import discovery as discovery_mod

        result = await discovery_mod.list_templates()

        assert "templates" in result
        entries = result["templates"]
        assert all(isinstance(e, dict) and "name" in e and "origin" in e for e in entries), (
            f"expected [{{'name', 'origin'}}, ...] entries, got: {entries!r}"
        )

        by_name = {e["name"]: e for e in entries}
        assert by_name.get("my_project_widget") == {
            "name": "my_project_widget",
            "origin": "project",
        }
        assert by_name.get("txt2img_basic") == {
            "name": "txt2img_basic",
            "origin": "built-in",
        }
    finally:
        importlib.reload(cfg_mod)


# ---------------------------------------------------------------------------
# R2 -- get_template_params resolves a project-only template
# ---------------------------------------------------------------------------


async def test_get_template_params_resolves_project_only_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_template_params(<project-only name>) resolves params for a template
    that exists only in the project dir, not in the built-in set."""
    import comfy_plugin.config as cfg_mod

    project_dir = tmp_path / "workflows"
    _write_template(project_dir, "my_project_widget", _minimal_project_template())

    monkeypatch.setenv("COMFYUI_PROJECT_TEMPLATES_DIR", str(project_dir))
    importlib.reload(cfg_mod)
    try:
        from comfy_plugin.tools import discovery as discovery_mod

        result = await discovery_mod.get_template_params("my_project_widget")

        assert "error" not in result, f"expected params, got error: {result!r}"
        assert result["template"] == "my_project_widget"
        params_by_name = {p["name"]: p for p in result["params"]}
        assert "POSITIVE_PROMPT" in params_by_name
        assert params_by_name["POSITIVE_PROMPT"]["type"] == "STR"
        assert params_by_name["POSITIVE_PROMPT"]["required"] is True
    finally:
        importlib.reload(cfg_mod)


# ---------------------------------------------------------------------------
# R3 -- run_template runs a project-only template
# ---------------------------------------------------------------------------


async def test_run_template_runs_project_only_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_template(<project-only name>, ...) renders the project file's graph
    and submits it via the (mocked) runner -- no live ComfyUI."""
    import comfy_plugin.config as cfg_mod

    project_dir = tmp_path / "workflows"
    _write_template(project_dir, "my_project_widget", _minimal_project_template())

    monkeypatch.setenv("COMFYUI_PROJECT_TEMPLATES_DIR", str(project_dir))
    importlib.reload(cfg_mod)
    try:
        from comfy_plugin.tools import generation as gen_mod

        expected = _make_run_result(prompt_id="pid-project")

        with patch.object(gen_mod, "runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=expected)
            result = await gen_mod.run_template(
                "my_project_widget", {"POSITIVE_PROMPT": "a cat in a hat"}, timeout=5.0
            )

        assert result.get("error") is None, f"expected a run result, got error: {result!r}"
        assert result["prompt_id"] == "pid-project"
        assert result["state"] == "completed"

        mock_runner.run.assert_awaited_once()
        submitted_prompt = mock_runner.run.await_args.args[0]
        assert submitted_prompt["1"]["inputs"]["text"] == "a cat in a hat"
    finally:
        importlib.reload(cfg_mod)


# ---------------------------------------------------------------------------
# R4 -- project template overrides built-in at all three call sites
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call_site", ["list_templates", "get_template_params", "run_template"]
)
async def test_project_template_overrides_builtin_at_all_call_sites(
    call_site: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project-local txt2img_basic.json wins the name collision against the
    packaged built-in of the same name, at every call site -- not an addition
    (still exactly one list_templates entry), a full override."""
    import comfy_plugin.config as cfg_mod

    project_dir = tmp_path / "workflows"
    _write_template(project_dir, "txt2img_basic", _project_override_txt2img_basic())

    monkeypatch.setenv("COMFYUI_PROJECT_TEMPLATES_DIR", str(project_dir))
    importlib.reload(cfg_mod)
    try:
        if call_site == "list_templates":
            from comfy_plugin.tools import discovery as discovery_mod

            result = await discovery_mod.list_templates()
            matches = [
                e
                for e in result["templates"]
                if isinstance(e, dict) and e.get("name") == "txt2img_basic"
            ]
            assert len(matches) == 1, (
                f"expected exactly one txt2img_basic entry (collision, not "
                f"addition), got: {result['templates']!r}"
            )
            assert matches[0]["origin"] == "project"

        elif call_site == "get_template_params":
            from comfy_plugin.tools import discovery as discovery_mod

            result = await discovery_mod.get_template_params("txt2img_basic")
            assert "error" not in result, f"expected params, got error: {result!r}"
            params_by_name = {p["name"]: p for p in result["params"]}
            assert "PROJECT_MARKER" in params_by_name, (
                "expected the project file's PROJECT_MARKER placeholder, "
                f"got only the built-in's params: {sorted(params_by_name)!r}"
            )

        else:  # run_template
            from comfy_plugin.tools import generation as gen_mod

            expected = _make_run_result(prompt_id="pid-override")

            with patch.object(gen_mod, "runner") as mock_runner:
                mock_runner.run = AsyncMock(return_value=expected)
                result = await gen_mod.run_template(
                    "txt2img_basic",
                    {"POSITIVE_PROMPT": "a cat", "MODEL": "model.safetensors", "STEPS": 20},
                    timeout=5.0,
                )

            assert result.get("error") is None, f"expected a run result, got error: {result!r}"
            mock_runner.run.assert_awaited_once()
            submitted_prompt = mock_runner.run.await_args.args[0]
            assert submitted_prompt["7"]["inputs"]["filename_prefix"] == "PROJECT_OVERRIDE_MARKER", (
                "expected the project file's graph (marker present), got the "
                f"built-in's: {submitted_prompt['7']['inputs']!r}"
            )
    finally:
        importlib.reload(cfg_mod)


# ---------------------------------------------------------------------------
# R5 -- disabled without git root or env; missing-on-disk dir is a no-op
# ---------------------------------------------------------------------------


async def test_project_templates_disabled_without_git_root_or_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No COMFYUI_PROJECT_TEMPLATES_DIR and no .git ancestor -> feature disabled:
    _resolve_project_templates_dir() is None, template_extra_dirs() is (), and
    list_templates() returns only built-ins."""
    import comfy_plugin.config as cfg_mod

    isolated = tmp_path / "isolated"
    isolated.mkdir()
    monkeypatch.delenv("COMFYUI_PROJECT_TEMPLATES_DIR", raising=False)
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: isolated))

    importlib.reload(cfg_mod)
    try:
        assert cfg_mod._resolve_project_templates_dir() is None
        assert cfg_mod.template_extra_dirs() == ()

        from comfy_plugin.tools import discovery as discovery_mod

        result = await discovery_mod.list_templates()
        names = [e["name"] if isinstance(e, dict) else e for e in result["templates"]]
        assert names == ["txt2img_basic"]
    finally:
        importlib.reload(cfg_mod)


async def test_template_extra_dirs_empty_when_dir_not_created_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resolved-but-not-yet-created project dir -> template_extra_dirs()
    returns () without raising."""
    import comfy_plugin.config as cfg_mod

    missing_dir = tmp_path / "does-not-exist" / "workflows"
    monkeypatch.setenv("COMFYUI_PROJECT_TEMPLATES_DIR", str(missing_dir))
    importlib.reload(cfg_mod)
    try:
        assert cfg_mod.project_templates_dir == Path(str(missing_dir))
        assert cfg_mod.template_extra_dirs() == ()
    finally:
        importlib.reload(cfg_mod)


# ---------------------------------------------------------------------------
# R6 -- _resolve_project_templates_dir: env/git-root resolution, no .gitignore write
# ---------------------------------------------------------------------------


def test_resolve_project_templates_dir_env_and_git_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Env var wins verbatim when set; otherwise resolves to
    <git-root>/.seretos/comfy/workflows."""
    import comfy_plugin.config as cfg_mod

    env_target = str(tmp_path / "custom" / "templates")
    monkeypatch.setenv("COMFYUI_PROJECT_TEMPLATES_DIR", env_target)
    importlib.reload(cfg_mod)
    try:
        assert cfg_mod._resolve_project_templates_dir() == Path(env_target)
    finally:
        importlib.reload(cfg_mod)

    git_root = tmp_path / "myproject"
    git_root.mkdir()
    (git_root / ".git").mkdir()
    monkeypatch.delenv("COMFYUI_PROJECT_TEMPLATES_DIR", raising=False)
    monkeypatch.chdir(git_root)

    importlib.reload(cfg_mod)
    try:
        expected = git_root / ".seretos" / "comfy" / "workflows"
        assert cfg_mod._resolve_project_templates_dir() == expected
    finally:
        importlib.reload(cfg_mod)


def test_resolve_project_templates_dir_does_not_touch_gitignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolving the project templates dir must never write '.seretos' into
    <git-root>/.gitignore -- it is user-authored source, not generated output."""
    import comfy_plugin.config as cfg_mod

    git_root = tmp_path / "myproject"
    git_root.mkdir()
    (git_root / ".git").mkdir()

    monkeypatch.chdir(git_root)
    monkeypatch.delenv("COMFYUI_PROJECT_TEMPLATES_DIR", raising=False)

    importlib.reload(cfg_mod)
    try:
        cfg_mod._resolve_project_templates_dir()

        gitignore = git_root / ".gitignore"
        if gitignore.exists():
            assert ".seretos" not in gitignore.read_text(encoding="utf-8")
    finally:
        importlib.reload(cfg_mod)
