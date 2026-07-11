"""Startup hook: model discovery and skill-file generation.

Calls ``lib_python_comfy``'s ``discover_models`` (L7) and
``enrich_with_huggingface`` (L12) after ComfyUI is confirmed reachable,
then writes a ``SKILL.md`` listing installed models to the resolved skills
directory.

Because L7/L12 are not yet on the pinned ``release/0.x`` lib, the import is
guarded — a missing symbol is treated identically to an offline failure.
The hook is always fault-tolerant: any ``Exception`` is caught, emitted as a
WARNING to stderr, and the server continues without crashing.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional lib import — guarded so an absent symbol is a no-op, not a crash.
# ---------------------------------------------------------------------------

try:
    from lib_python_comfy import discover_models, enrich_with_huggingface  # type: ignore[attr-defined]

    _DISCOVERY_AVAILABLE = True
except ImportError:
    discover_models = None  # type: ignore[assignment]
    enrich_with_huggingface = None  # type: ignore[assignment]
    _DISCOVERY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Skill-file renderer
# ---------------------------------------------------------------------------

def _render_skill_md(models: list[Any]) -> str:
    """Render a Markdown skill file from a list of ModelInfo objects.

    Accesses only ``.name`` and ``.description`` (both required by the assumed
    lib contract).  Groups by ``.type`` / ``.category`` when available — uses
    ``getattr`` defensively so the renderer never crashes on the concrete type.
    """
    if not models:
        return "# Installed ComfyUI Models\n\n_No models discovered._\n"

    # Group by type/category if the attribute is present; fall back to flat.
    groups: dict[str, list[Any]] = {}
    for model in models:
        group_key: str = (
            getattr(model, "type", None)
            or getattr(model, "category", None)
            or "Models"
        )
        groups.setdefault(group_key, []).append(model)

    lines = ["# Installed ComfyUI Models", ""]
    for group_name, group_models in sorted(groups.items()):
        lines.append(f"## {group_name}")
        lines.append("")
        for m in group_models:
            desc = getattr(m, "description", None) or "(no description available)"
            lines.append(f"- **{m.name}**: {desc}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_model_discovery_hook(client: Any, skills_dir: Path) -> None:
    """Discover models and write a ``SKILL.md`` to *skills_dir*.

    Degrades gracefully on every error path — never raises.
    """
    if not _DISCOVERY_AVAILABLE:
        if os.environ.get("COMFYUI_SKILLS_DIR"):
            print(
                "WARNING: COMFYUI_SKILLS_DIR is set, but model discovery is "
                "unavailable (discover_models/enrich_with_huggingface are not "
                "present in the currently pinned lib-python-comfy); SKILL.md "
                "will not be written.",
                file=sys.stderr,
            )
        return

    try:
        # --- Discovery (lib L7) -------------------------------------------
        models: list[Any] = await asyncio.to_thread(discover_models, client)

        # --- HuggingFace enrichment (lib L12) --------------------------------
        # Run in its own try/except so an enrichment failure does NOT discard
        # the already-retrieved discovery results.
        try:
            models = await asyncio.to_thread(enrich_with_huggingface, models)
        except Exception as exc:
            print(
                f"WARNING: HuggingFace enrichment failed ({exc!r}); "
                "writing skill file with un-enriched model list.",
                file=sys.stderr,
            )
            # models already holds the un-enriched list — fall through.

        # --- Atomic skill-file write -----------------------------------------
        skills_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = skills_dir / "SKILL.md.tmp"
        tmp_path.write_text(_render_skill_md(models), encoding="utf-8")
        try:
            tmp_path.replace(skills_dir / "SKILL.md")
        except Exception:
            # replace failed — remove the orphaned temp file so it never
            # lingers, then re-raise so the outer except can warn + swallow.
            tmp_path.unlink(missing_ok=True)
            raise

    except Exception as exc:
        print(
            f"WARNING: Model discovery hook failed ({exc!r}); "
            "skill file not written.",
            file=sys.stderr,
        )
