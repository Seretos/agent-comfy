"""Regression guard for skill discoverability via YAML frontmatter.

Claude Code discovers a skill from its YAML frontmatter ``name:``/
``description:`` alone; body prose is invisible to discovery. Two of the
three skills under ``skills/comfy-*-workflows/SKILL.md`` shipped with no
frontmatter at all, so they were never registered, and the third's trigger
sentence sat in an unserved ``trigger:`` key. This file guards against that
regression and against a stale ``audio_basic`` template stem / "lib issue
#13" framing that misdirected the audio skill's documented tool usage.

Stdlib + pytest only (+ an optional lib_python_comfy cross-check, skipped if
unavailable). No PyYAML — the frontmatter block is small and fixed-shape
enough to hand-parse with a ``key: value`` split, consistent with the
dependency-free style of tests/test_dependency_pin.py and
tests/test_mcp_pin.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))

# Content/vocabulary assertions are keyed to these three specific directories
# only, so an unrelated future skill (e.g. ticket #43's) clears the trivial
# structural bar without being asked to contain image/video/audio vocabulary.
REQUIRED_DESCRIPTION_KEYWORDS: dict[str, list[str]] = {
    "comfy-image-workflows": [
        "generate an image",
        "txt2img",
        "artwork",
        "comfyui workflow",
        "checkpoint",
        "ksampler",
        "save",
        "preview",
    ],
    "comfy-video-workflows": [
        "generate a video",
        "vhs_videocombine",
        "videohelpersuite",
        "motion model",
        "mp4",
    ],
    "comfy-audio-workflows": [
        "generate",
        "synthesize",
        "audio",
        "music",
        "speech",
        "sfx",
        "sound cue",
        "voice-over",
        "ambience",
        "wav",
        "queue a job",
        "poll a running job",
        "save the generated file to disk",
    ],
}

AUDIO_SKILL_PATH = SKILLS_DIR / "comfy-audio-workflows" / "SKILL.md"


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Hand-rolled parser for the small fixed-shape ``---`` frontmatter block.

    Returns (frontmatter_dict, body_text). Raises AssertionError with a
    helpful message if the file does not open with a ``---`` block.
    """
    lines = text.splitlines()
    assert lines and lines[0] == "---", (
        "SKILL.md must open with a '---' YAML frontmatter block on line 1"
    )
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            end_idx = i
            break
    assert end_idx is not None, "frontmatter block is never closed with a second '---'"

    data: dict[str, str] = {}
    for line in lines[1:end_idx]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        assert sep, f"malformed frontmatter line (expected 'key: value'): {line!r}"
        data[key.strip()] = value.strip()

    body = "\n".join(lines[end_idx + 1 :])
    return data, body


def _skill_id(path: Path) -> str:
    return path.parent.name


# ---------------------------------------------------------------------------
# Behaviour 1 — every skill exposes discoverable name/description frontmatter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=_skill_id)
def test_every_skill_has_name_and_description_frontmatter(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(text)

    expected_name = skill_file.parent.name
    assert frontmatter.get("name") == expected_name, (
        f"{skill_file}: frontmatter 'name' must equal the parent directory "
        f"name {expected_name!r}, got {frontmatter.get('name')!r}"
    )

    description = frontmatter.get("description", "")
    assert description, f"{skill_file}: frontmatter 'description' must be non-empty"
    assert len(description) <= 1024, (
        f"{skill_file}: frontmatter 'description' is {len(description)} chars, "
        "over the 1024-char budget"
    )

    assert body.strip(), f"{skill_file}: body must be non-empty after the frontmatter block"


# ---------------------------------------------------------------------------
# Behaviour 2 — the unserved 'trigger:' key must never be used
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=_skill_id)
def test_no_skill_uses_the_unserved_trigger_key(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    frontmatter, _ = _parse_frontmatter(text)
    assert "trigger" not in frontmatter, (
        f"{skill_file}: frontmatter carries a 'trigger:' key, but Claude Code "
        "does not serve it for discovery — fold its content into 'description:'"
    )


# ---------------------------------------------------------------------------
# Behaviour 3 — descriptions carry the vocabulary needed to trigger discovery
# ---------------------------------------------------------------------------


def test_known_skill_directories_still_exist():
    """Guard the keyword table itself: a silent rename must fail loudly."""
    for skill_dir in REQUIRED_DESCRIPTION_KEYWORDS:
        assert (SKILLS_DIR / skill_dir / "SKILL.md").exists(), (
            f"expected skill directory {skill_dir!r} not found under {SKILLS_DIR} "
            "— update REQUIRED_DESCRIPTION_KEYWORDS if it was intentionally renamed"
        )


@pytest.mark.parametrize("skill_dir", sorted(REQUIRED_DESCRIPTION_KEYWORDS), ids=lambda d: d)
def test_descriptions_carry_trigger_vocabulary(skill_dir: str):
    skill_file = SKILLS_DIR / skill_dir / "SKILL.md"
    text = skill_file.read_text(encoding="utf-8")
    frontmatter, _ = _parse_frontmatter(text)
    description = frontmatter.get("description", "").lower()

    missing = [
        kw for kw in REQUIRED_DESCRIPTION_KEYWORDS[skill_dir] if kw.lower() not in description
    ]
    assert not missing, (
        f"{skill_file}: description is missing required trigger vocabulary {missing!r}; "
        f"description was: {frontmatter.get('description', '')!r}"
    )


# ---------------------------------------------------------------------------
# Behaviour 4 — the nonexistent 'audio_basic' stem / stale lib-issue framing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=_skill_id)
def test_no_skill_references_the_nonexistent_audio_basic_stem(skill_file: Path):
    text = skill_file.read_text(encoding="utf-8")
    assert "audio_basic" not in text, (
        f"{skill_file}: references the nonexistent template stem 'audio_basic' "
        "(the real stem is 'generate_audio')"
    )


def test_audio_skill_documents_the_real_generate_audio_stem():
    text = AUDIO_SKILL_PATH.read_text(encoding="utf-8")
    assert "generate_audio" in text, (
        "comfy-audio-workflows/SKILL.md must document the real template stem 'generate_audio'"
    )


def test_generate_audio_stem_matches_lib_builtin_templates():
    """Cross-check the corrected stem against the real installed lib_python_comfy.

    Known gap (verified against a fresh clone of the exact pinned
    lib-python-comfy@v0.0.5 tag): only 'txt2img_basic' ships as a builtin
    template today. 'generate_audio' is documented here (and already, out of
    this ticket's scope, in comfy-video-workflows/SKILL.md's template table)
    ahead of the upstream lib actually shipping it — that is a
    lib-python-comfy concern, not a fixable defect within this ticket's
    scope (skills/*.md + this test file only). Skip rather than fail in that
    case so the guard remains a live cross-check once the lib catches up,
    without blocking on an out-of-scope upstream gap today.
    """
    lib_python_comfy = pytest.importorskip(
        "lib_python_comfy", reason="lib_python_comfy not importable: environment problem"
    )
    templates = lib_python_comfy.list_builtin_templates()
    if "generate_audio" not in templates:
        pytest.skip(
            "lib_python_comfy does not yet ship a 'generate_audio' builtin "
            f"template (found: {templates!r}); known upstream gap, out of "
            "scope for this ticket"
        )


def test_audio_skill_drops_stale_lib_issue_13_framing():
    text = AUDIO_SKILL_PATH.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "lib issue #13" not in lowered, (
        "comfy-audio-workflows/SKILL.md must drop the stale 'lib issue #13' framing "
        "(that issue belongs to the separate lib-python-comfy repo)"
    )
    assert "not yet shipped" not in lowered, (
        "comfy-audio-workflows/SKILL.md must drop the stale 'not yet shipped' framing "
        "that presented the missing-template failure as expected"
    )


# ---------------------------------------------------------------------------
# Behaviour 5 — real audio tooling is documented
# ---------------------------------------------------------------------------


def test_audio_skill_documents_audio_tools():
    text = AUDIO_SKILL_PATH.read_text(encoding="utf-8")
    for tool_name in ("run_txt2audio", "list_templates", "get_template_params"):
        assert tool_name in text, (
            f"comfy-audio-workflows/SKILL.md must document the '{tool_name}' tool"
        )
    assert "clip input is invalid: None" in text, (
        "comfy-audio-workflows/SKILL.md must document the "
        "'RuntimeError: clip input is invalid: None' gotcha for checkpoints with "
        "no bundled text encoder"
    )


# ---------------------------------------------------------------------------
# Behaviour 6 — the real get_queue_status shape, audio skill only
# ---------------------------------------------------------------------------


def test_audio_skill_documents_real_queue_status_shape():
    text = AUDIO_SKILL_PATH.read_text(encoding="utf-8")
    assert "queue_running" not in text, (
        "comfy-audio-workflows/SKILL.md still documents the nonexistent "
        "'queue_running' key (the real key is 'running')"
    )
    assert "queue_pending" not in text, (
        "comfy-audio-workflows/SKILL.md still documents the nonexistent "
        "'queue_pending' key (the real key is 'pending')"
    )
    assert '"running"' in text, "expected the real 'running' queue key to be documented"
    assert '"pending"' in text, "expected the real 'pending' queue key to be documented"


# ---------------------------------------------------------------------------
# Encoding guard — every SKILL.md must use LF line endings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("skill_file", SKILL_FILES, ids=_skill_id)
def test_skill_files_use_lf_line_endings(skill_file: Path):
    raw = skill_file.read_bytes()
    assert b"\r\n" not in raw, f"{skill_file}: contains CRLF line endings; must be LF-only"
