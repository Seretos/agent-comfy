"""Environment-driven configuration and module-level singletons.

All env vars are read once at import time. Consuming modules import the
singletons directly; there is no re-parsing at call time.

Env vars
--------
COMFYUI_URL
    Root URL of the ComfyUI server. Default: ``http://localhost:8188``.
COMFYUI_WORKFLOW_DIR
    Optional path where UI-format workflow JSON files are written for live
    viewing in the ComfyUI canvas. Unset by default (feature disabled).
COMFYUI_ASSET_TTL
    How long (in seconds) to retain fetched assets before they may be
    evicted. Integer, default ``3600`` (one hour).
COMFYUI_SKILLS_DIR
    Optional filesystem path where the generated model-discovery skill file
    (``SKILL.md``) is written at startup.  When unset, the code walks up from
    ``Path.cwd()`` looking for a ``.git`` directory; if found it writes to
    ``<git-root>/.claude/skills/comfy-models/`` and ensures that path is
    listed in ``<git-root>/.gitignore``.  When no ``.git`` ancestor exists and
    the env var is unset the feature is disabled (returns ``None``).
COMFYUI_PROJECT_TEMPLATES_DIR
    Optional filesystem path where project-local ComfyUI templates live.
    When unset, the code walks up from ``Path.cwd()`` looking for a ``.git``
    directory; if found it resolves to
    ``<git-root>/.seretos/comfy/workflows``.  When no ``.git`` ancestor
    exists and the env var is unset the feature is disabled (``None``).
    Unlike ``COMFYUI_SKILLS_DIR``, this directory is never registered in
    ``.gitignore`` — it holds user-authored source the user decides whether
    to commit, not generated output.  Templates found here must already be
    API-format JSON with ``PARAM_*`` placeholders, and a project template
    wins name collisions against a packaged built-in of the same name.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from lib_python_comfy import ComfyClient, FlowRunner, SerializationGuard

# ---------------------------------------------------------------------------
# Env-var parsing
# ---------------------------------------------------------------------------

comfy_url: str = os.environ.get("COMFYUI_URL", "http://localhost:8188")
workflow_dir: str | None = os.environ.get("COMFYUI_WORKFLOW_DIR")
asset_ttl: int = int(os.environ.get("COMFYUI_ASSET_TTL", "3600"))

# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

client: ComfyClient = ComfyClient(comfy_url)
guard: SerializationGuard = SerializationGuard()
runner: FlowRunner = FlowRunner(client, guard)


# ---------------------------------------------------------------------------
# Git-root resolution (shared by skills-dir and project-templates-dir)
# ---------------------------------------------------------------------------


def _find_git_root() -> Path | None:
    """Walk up from ``Path.cwd()`` looking for a ``.git`` directory.

    Returns the first ancestor (including ``Path.cwd()`` itself) that
    contains a ``.git`` entry, or ``None`` if none of them do.
    """
    current = Path.cwd()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Skills-dir resolution
# ---------------------------------------------------------------------------

_GITIGNORE_ENTRY = ".claude/skills/comfy-models/"


def _resolve_skills_dir() -> Path | None:
    """Return the directory where the generated SKILL.md should be written.

    Resolution order:
    1. ``COMFYUI_SKILLS_DIR`` env var — used as-is if set.
    2. Walk up from ``Path.cwd()`` for a ``.git`` directory; if found return
       ``<git-root>/.claude/skills/comfy-models`` and idempotently add the
       path to ``<git-root>/.gitignore``.
    3. Neither found — return ``None`` (feature disabled).
    """
    # 1. Explicit env override.
    env_val = os.environ.get("COMFYUI_SKILLS_DIR")
    if env_val:
        return Path(env_val)

    # 2. Walk up from cwd looking for .git.
    git_root = _find_git_root()
    if git_root is not None:
        skills_dir = git_root / ".claude" / "skills" / "comfy-models"
        # .gitignore update is best-effort; an I/O failure must not
        # disable the feature or crash startup.
        try:
            _ensure_gitignore(git_root)
        except Exception as exc:
            print(
                f"WARNING: Could not update .gitignore ({exc!r}); "
                "skill file will still be written.",
                file=sys.stderr,
            )
        return skills_dir

    # 3. No git root found and env var not set.
    return None


def _ensure_gitignore(git_root: Path) -> None:
    """Idempotently append the skills-dir entry to ``<git_root>/.gitignore``."""
    gitignore_path = git_root / ".gitignore"
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")
    else:
        existing = ""

    if _GITIGNORE_ENTRY not in existing:
        # Append; ensure the file ends with a newline before adding.
        prefix = "\n" if existing and not existing.endswith("\n") else ""
        with gitignore_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{prefix}{_GITIGNORE_ENTRY}\n")


# ---------------------------------------------------------------------------
# Project-local templates dir resolution
# ---------------------------------------------------------------------------


def _resolve_project_templates_dir() -> Path | None:
    """Return the directory where project-local templates are discovered.

    Resolution order:
    1. ``COMFYUI_PROJECT_TEMPLATES_DIR`` env var — used as-is if set.
    2. Walk up from ``Path.cwd()`` for a ``.git`` directory; if found return
       ``<git-root>/.seretos/comfy/workflows``.
    3. Neither found — return ``None`` (feature disabled).

    Unlike ``_resolve_skills_dir``, this never touches ``.gitignore`` — the
    templates dir holds user-authored source, not generated output.
    """
    # 1. Explicit env override.
    env_val = os.environ.get("COMFYUI_PROJECT_TEMPLATES_DIR")
    if env_val:
        return Path(env_val)

    # 2. Walk up from cwd looking for .git.
    git_root = _find_git_root()
    if git_root is not None:
        return git_root / ".seretos" / "comfy" / "workflows"

    # 3. No git root found and env var not set.
    return None


project_templates_dir: Path | None = _resolve_project_templates_dir()


def template_extra_dirs() -> tuple[Path, ...]:
    """Return the ``extra_dirs`` tuple to pass to the lib's template loader.

    Only includes ``project_templates_dir`` when it is set *and* currently
    exists on disk right now; otherwise returns an empty tuple.
    """
    if project_templates_dir is not None and project_templates_dir.is_dir():
        return (project_templates_dir,)
    return ()
