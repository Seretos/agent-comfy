"""Tests for the startup model-discovery hook and skills-dir resolution.

All tests mock the lib client/runner — no live ComfyUI required.
Mirrors the style of tests/test_smoke.py.
"""
from __future__ import annotations

import contextlib
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model(name: str, description: str | None = None, type_: str | None = None) -> Any:
    """Create a minimal ModelInfo stand-in."""
    obj = SimpleNamespace(name=name, description=description)
    if type_ is not None:
        obj.type = type_
    return obj


# ---------------------------------------------------------------------------
# _resolve_skills_dir — config-level tests
# ---------------------------------------------------------------------------


def test_resolve_skills_dir_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """COMFYUI_SKILLS_DIR env var → _resolve_skills_dir returns exactly that path."""
    import comfy_plugin.config as cfg_mod

    target = str(tmp_path / "custom" / "skills")
    with patch.dict(os.environ, {"COMFYUI_SKILLS_DIR": target}):
        importlib.reload(cfg_mod)
        result = cfg_mod._resolve_skills_dir()

    assert result == Path(target)
    # Restore
    importlib.reload(cfg_mod)


def test_resolve_skills_dir_git_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """cwd inside a tmp dir with .git → returns <tmp>/.claude/skills/comfy-models
    and appends the entry to <tmp>/.gitignore."""
    import comfy_plugin.config as cfg_mod

    # Create a fake git root with a .git directory.
    git_root = tmp_path / "myproject"
    git_root.mkdir()
    (git_root / ".git").mkdir()

    monkeypatch.chdir(git_root)
    # Ensure the env var is not set.
    monkeypatch.delenv("COMFYUI_SKILLS_DIR", raising=False)

    importlib.reload(cfg_mod)
    result = cfg_mod._resolve_skills_dir()

    expected = git_root / ".claude" / "skills" / "comfy-models"
    assert result == expected

    # .gitignore must have been created/updated with the entry.
    gitignore = git_root / ".gitignore"
    assert gitignore.exists()
    assert ".claude/skills/comfy-models/" in gitignore.read_text(encoding="utf-8")

    importlib.reload(cfg_mod)


def test_resolve_skills_dir_git_project_idempotent_gitignore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the gitignore entry already exists, a second call must not duplicate it."""
    import comfy_plugin.config as cfg_mod

    git_root = tmp_path / "myproject"
    git_root.mkdir()
    (git_root / ".git").mkdir()
    # Pre-populate .gitignore with the entry.
    gitignore = git_root / ".gitignore"
    gitignore.write_text(".claude/skills/comfy-models/\n", encoding="utf-8")

    monkeypatch.chdir(git_root)
    monkeypatch.delenv("COMFYUI_SKILLS_DIR", raising=False)

    importlib.reload(cfg_mod)
    # Call twice.
    cfg_mod._resolve_skills_dir()
    cfg_mod._resolve_skills_dir()

    content = gitignore.read_text(encoding="utf-8")
    assert content.count(".claude/skills/comfy-models/") == 1

    importlib.reload(cfg_mod)


def test_resolve_skills_dir_no_git_no_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No .git ancestor and env var unset → _resolve_skills_dir returns None."""
    import comfy_plugin.config as cfg_mod

    # Create an isolated directory that has no .git in its ancestor chain.
    # Patch only Path.cwd so the walk starts here and never escapes to the
    # real working tree (which does have a .git).  The real Path constructor
    # is left untouched so all other path operations work normally.
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    monkeypatch.delenv("COMFYUI_SKILLS_DIR", raising=False)
    monkeypatch.setattr(Path, "cwd", staticmethod(lambda: isolated))

    importlib.reload(cfg_mod)
    result = cfg_mod._resolve_skills_dir()

    assert result is None

    importlib.reload(cfg_mod)


# ---------------------------------------------------------------------------
# _resolve_skills_dir — fault-tolerance (blocking 1a regression tests)
# ---------------------------------------------------------------------------


def test_resolve_skills_dir_gitignore_write_failure_still_returns_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """REGRESSION (blocking 1a): .gitignore write failure must not propagate —
    _resolve_skills_dir still returns the resolved path and emits a WARNING."""
    import comfy_plugin.config as cfg_mod

    git_root = tmp_path / "myproject"
    git_root.mkdir()
    (git_root / ".git").mkdir()

    monkeypatch.chdir(git_root)
    monkeypatch.delenv("COMFYUI_SKILLS_DIR", raising=False)

    importlib.reload(cfg_mod)

    # Force _ensure_gitignore to raise to simulate a permission-denied scenario.
    with patch.object(cfg_mod, "_ensure_gitignore", side_effect=OSError("read-only")):
        result = cfg_mod._resolve_skills_dir()

    expected = git_root / ".claude" / "skills" / "comfy-models"
    assert result == expected

    captured = capsys.readouterr()
    assert "WARNING" in captured.err

    importlib.reload(cfg_mod)


async def test_lifespan_resolve_skills_dir_raises_does_not_crash(
    capsys: pytest.CaptureFixture,
) -> None:
    """REGRESSION (blocking 1b): _resolve_skills_dir raising must NOT crash
    _lifespan — startup completes and a WARNING is emitted."""
    import comfy_plugin.server as server_mod

    async def _fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("comfy_plugin.server.asyncio.to_thread", side_effect=_fake_to_thread),
        patch("comfy_plugin.server.client") as mock_client,
        patch(
            "comfy_plugin.server._resolve_skills_dir",
            side_effect=OSError("permission denied"),
        ),
    ):
        mock_client.is_reachable = MagicMock(return_value=True)
        # Must not raise — the asynccontextmanager must yield normally.
        async with server_mod._lifespan(MagicMock()):
            pass

    captured = capsys.readouterr()
    assert "WARNING" in captured.err


# ---------------------------------------------------------------------------
# run_model_discovery_hook — unit tests
# ---------------------------------------------------------------------------


async def test_hook_degrades_when_lib_missing(tmp_path: Path) -> None:
    """_DISCOVERY_AVAILABLE=False → hook returns without writing any file."""
    import comfy_plugin.startup as startup_mod

    mock_client = MagicMock()
    skills_dir = tmp_path / "skills"

    with patch.object(startup_mod, "_DISCOVERY_AVAILABLE", False):
        await startup_mod.run_model_discovery_hook(mock_client, skills_dir)

    assert not (skills_dir / "SKILL.md").exists()


async def test_hook_degrades_when_lib_missing_and_skills_dir_set_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """_DISCOVERY_AVAILABLE=False AND COMFYUI_SKILLS_DIR set (explicit opt-in)
    → hook returns without writing, and a WARNING is emitted to stderr."""
    import comfy_plugin.startup as startup_mod

    mock_client = MagicMock()
    skills_dir = tmp_path / "skills"

    with (
        patch.object(startup_mod, "_DISCOVERY_AVAILABLE", False),
        patch.dict(os.environ, {"COMFYUI_SKILLS_DIR": str(skills_dir)}),
    ):
        await startup_mod.run_model_discovery_hook(mock_client, skills_dir)

    assert not (skills_dir / "SKILL.md").exists()
    captured = capsys.readouterr()
    assert "WARNING" in captured.err


async def test_hook_degrades_when_lib_missing_and_skills_dir_unset_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """_DISCOVERY_AVAILABLE=False AND COMFYUI_SKILLS_DIR unset (default,
    auto-resolved via git-root walk-up) → hook returns without writing, and
    stderr stays silent (no WARNING) since this is the common case."""
    import comfy_plugin.startup as startup_mod

    mock_client = MagicMock()
    skills_dir = tmp_path / "skills"

    monkeypatch.delenv("COMFYUI_SKILLS_DIR", raising=False)
    with patch.object(startup_mod, "_DISCOVERY_AVAILABLE", False):
        await startup_mod.run_model_discovery_hook(mock_client, skills_dir)

    assert not (skills_dir / "SKILL.md").exists()
    captured = capsys.readouterr()
    assert "WARNING" not in captured.err


async def test_hook_degrades_when_discovery_raises(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """discover_models raises → hook returns without raising, WARNING printed."""
    import comfy_plugin.startup as startup_mod

    mock_client = MagicMock()
    skills_dir = tmp_path / "skills"

    with (
        patch.object(startup_mod, "_DISCOVERY_AVAILABLE", True),
        patch.object(startup_mod, "discover_models", side_effect=RuntimeError("boom")),
    ):
        await startup_mod.run_model_discovery_hook(mock_client, skills_dir)

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert not (skills_dir / "SKILL.md").exists()


async def test_hook_degrades_when_enrichment_raises_still_writes_skill(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """enrichment raises → SKILL.md written with un-enriched model names."""
    import comfy_plugin.startup as startup_mod

    mock_client = MagicMock()
    skills_dir = tmp_path / "skills"
    models = [_make_model("model-a"), _make_model("model-b")]

    with (
        patch.object(startup_mod, "_DISCOVERY_AVAILABLE", True),
        patch.object(startup_mod, "discover_models", return_value=models),
        patch.object(
            startup_mod, "enrich_with_huggingface", side_effect=RuntimeError("hf-down")
        ),
    ):
        await startup_mod.run_model_discovery_hook(mock_client, skills_dir)

    captured = capsys.readouterr()
    assert "WARNING" in captured.err

    skill_file = skills_dir / "SKILL.md"
    assert skill_file.exists()
    content = skill_file.read_text(encoding="utf-8")
    assert "model-a" in content
    assert "model-b" in content
    assert "(no description available)" in content


async def test_skill_file_content(tmp_path: Path) -> None:
    """Both callables return known data → SKILL.md has correct names + descriptions."""
    import comfy_plugin.startup as startup_mod

    mock_client = MagicMock()
    skills_dir = tmp_path / "skills"
    models = [
        _make_model("sd-1.5", "Stable Diffusion 1.5 base model", type_="checkpoints"),
        _make_model("lora-anime", "Anime style LoRA", type_="loras"),
    ]

    with (
        patch.object(startup_mod, "_DISCOVERY_AVAILABLE", True),
        patch.object(startup_mod, "discover_models", return_value=models),
        patch.object(startup_mod, "enrich_with_huggingface", return_value=models),
    ):
        await startup_mod.run_model_discovery_hook(mock_client, skills_dir)

    content = (skills_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "sd-1.5" in content
    assert "Stable Diffusion 1.5 base model" in content
    assert "lora-anime" in content
    assert "Anime style LoRA" in content
    assert "checkpoints" in content
    assert "loras" in content


async def test_skill_file_written_atomically(tmp_path: Path) -> None:
    """The .tmp intermediate file must be absent after the hook completes."""
    import comfy_plugin.startup as startup_mod

    mock_client = MagicMock()
    skills_dir = tmp_path / "skills"
    models = [_make_model("mymodel", "A model")]

    with (
        patch.object(startup_mod, "_DISCOVERY_AVAILABLE", True),
        patch.object(startup_mod, "discover_models", return_value=models),
        patch.object(startup_mod, "enrich_with_huggingface", return_value=models),
    ):
        await startup_mod.run_model_discovery_hook(mock_client, skills_dir)

    assert (skills_dir / "SKILL.md").exists()
    assert not (skills_dir / "SKILL.md.tmp").exists()


async def test_tmp_file_cleaned_up_when_replace_raises(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """REGRESSION (blocking 2): if Path.replace raises after write_text, the
    .tmp file must be removed and the hook must not propagate the exception."""
    import comfy_plugin.startup as startup_mod
    from pathlib import Path as RealPath

    mock_client = MagicMock()
    skills_dir = tmp_path / "skills"
    models = [_make_model("mymodel", "A model")]

    original_replace = RealPath.replace

    def _replace_raises(self, target):
        raise OSError("simulated replace failure")

    with (
        patch.object(startup_mod, "_DISCOVERY_AVAILABLE", True),
        patch.object(startup_mod, "discover_models", return_value=models),
        patch.object(startup_mod, "enrich_with_huggingface", return_value=models),
        patch.object(RealPath, "replace", _replace_raises),
    ):
        await startup_mod.run_model_discovery_hook(mock_client, skills_dir)

    # The hook must not have raised.
    # The .tmp file must have been cleaned up.
    assert not (skills_dir / "SKILL.md.tmp").exists()
    # The final SKILL.md was never produced (replace failed).
    assert not (skills_dir / "SKILL.md").exists()
    # A WARNING must have been emitted.
    captured = capsys.readouterr()
    assert "WARNING" in captured.err


# ---------------------------------------------------------------------------
# _lifespan integration tests
# ---------------------------------------------------------------------------


async def test_lifespan_calls_discovery_when_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REGRESSION: mock client reachable → discover_models + enrich called, SKILL.md written."""
    import comfy_plugin.startup as startup_mod
    import comfy_plugin.server as server_mod

    skills_dir = tmp_path / "skills"
    models = [_make_model("checkpoint-v1", "A fine checkpoint")]

    # Patch asyncio.to_thread in server so the reachability call is intercepted
    # before the real ComfyClient.is_reachable is invoked (which would fail in CI).
    async def _fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    mock_is_reachable = MagicMock(return_value=True)

    with (
        patch("comfy_plugin.server.asyncio.to_thread", side_effect=_fake_to_thread),
        patch("comfy_plugin.server.client") as mock_client,
        patch.object(startup_mod, "_DISCOVERY_AVAILABLE", True),
        patch.object(startup_mod, "discover_models", return_value=models),
        patch.object(startup_mod, "enrich_with_huggingface", return_value=models),
        patch("comfy_plugin.server._resolve_skills_dir", return_value=skills_dir),
    ):
        mock_client.is_reachable = MagicMock(return_value=True)
        async with server_mod._lifespan(MagicMock()):
            pass

    skill_file = skills_dir / "SKILL.md"
    assert skill_file.exists()
    content = skill_file.read_text(encoding="utf-8")
    assert "checkpoint-v1" in content
    assert "A fine checkpoint" in content


async def test_lifespan_skips_discovery_when_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """is_reachable=False → neither discover_models nor enrich_with_huggingface called."""
    import comfy_plugin.startup as startup_mod
    import comfy_plugin.server as server_mod

    skills_dir = tmp_path / "skills"
    mock_discover = MagicMock()
    mock_enrich = MagicMock()

    async def _fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("comfy_plugin.server.asyncio.to_thread", side_effect=_fake_to_thread),
        patch("comfy_plugin.server.client") as mock_client,
        patch.object(startup_mod, "_DISCOVERY_AVAILABLE", True),
        patch.object(startup_mod, "discover_models", mock_discover),
        patch.object(startup_mod, "enrich_with_huggingface", mock_enrich),
        patch("comfy_plugin.server._resolve_skills_dir", return_value=skills_dir),
    ):
        mock_client.is_reachable = MagicMock(return_value=False)
        async with server_mod._lifespan(MagicMock()):
            pass

    mock_discover.assert_not_called()
    mock_enrich.assert_not_called()
    assert not (skills_dir / "SKILL.md").exists()


async def test_lifespan_skills_dir_none_skips_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_skills_dir returns None → run_model_discovery_hook never called."""
    import comfy_plugin.server as server_mod

    mock_hook = AsyncMock()

    async def _fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with (
        patch("comfy_plugin.server.asyncio.to_thread", side_effect=_fake_to_thread),
        patch("comfy_plugin.server.client") as mock_client,
        patch("comfy_plugin.server._resolve_skills_dir", return_value=None),
        patch("comfy_plugin.server.run_model_discovery_hook", mock_hook),
    ):
        mock_client.is_reachable = MagicMock(return_value=True)
        async with server_mod._lifespan(MagicMock()):
            pass

    mock_hook.assert_not_called()
