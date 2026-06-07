"""Workflow export helper for live-view sync.

Writes a UI-format workflow JSON file to disk before each scaffold submission
so the user can open it in the ComfyUI canvas and watch live node highlighting.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path


async def maybe_write_workflow(ui_dict: dict, workflow_dir: str | None) -> None:
    """Write *ui_dict* as a JSON file inside *workflow_dir* if it is set.

    Parameters
    ----------
    ui_dict:
        UI-format workflow dict as returned by ``to_ui(graph)``.
    workflow_dir:
        Filesystem path to the directory where the file should be written.
        When ``None`` the function returns immediately without doing anything.

    Notes
    -----
    ``json.dumps`` runs outside the error handler: if *ui_dict* is not
    JSON-serialisable that is a bug in ``to_ui`` and the ``TypeError``
    should propagate.

    Only the filesystem I/O (mkdir + write_text) is wrapped; ``OSError``
    is caught, logged to ``sys.stderr`` as a ``WARNING:`` line, and
    swallowed so a disk problem never aborts a generation run.

    Both mkdir and write_text are dispatched in a single
    ``asyncio.to_thread`` hop to avoid blocking the event loop.
    """
    if workflow_dir is None:
        return

    payload = json.dumps(ui_dict, indent=2)  # propagate TypeError — non-serializable ui_dict is a bug

    try:
        now = datetime.now()
        filename = "comfy_" + now.strftime("%Y%m%d_%H%M%S_") + f"{now.microsecond:06d}.json"
        dest = Path(workflow_dir)

        def _write() -> None:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / filename).write_text(payload, encoding="utf-8")

        await asyncio.to_thread(_write)
    except OSError as exc:
        print(f"WARNING: failed to write workflow file: {exc!r}", file=sys.stderr)
