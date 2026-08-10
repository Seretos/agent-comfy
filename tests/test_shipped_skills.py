"""Tests for the shipped `comfy-local-resource-cost` skill (ticket #43).

Stdlib only — does not import `comfy_plugin`. Every assertion is scoped to
the new skill directory and to `src/comfy_plugin/tools/__init__.py`; it must
never touch the three skill files owned by ticket #44
(comfy-image-workflows, comfy-audio-workflows, comfy-video-workflows).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = REPO_ROOT / "skills" / "comfy-local-resource-cost" / "SKILL.md"
TOOLS_INIT_PATH = REPO_ROOT / "src" / "comfy_plugin" / "tools" / "__init__.py"

COST_RELEVANT_TOOLS = {
    "run_txt2img",
    "run_txt2audio",
    "run_txt2video",
    "run_workflow",
    "run_template",
    "get_queue_status",
    "get_job",
    "cancel_job",
}


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split *text* into (frontmatter_block, body). Raises AssertionError."""
    assert text.startswith("---\n"), (
        "SKILL.md must start with '---' immediately (no leading blank line "
        "or BOM)"
    )
    # First line is the opening '---'; find the closing '---' line.
    match = re.search(r"\A---\n(.*?)\n---\n", text, flags=re.DOTALL)
    assert match, "could not find closing '---' delimiter for frontmatter block"
    frontmatter = match.group(1)
    body = text[match.end():]
    return frontmatter, body


def _parse_frontmatter(frontmatter: str) -> dict[str, str]:
    """Very small YAML-subset parser: top-level `key: value` pairs only."""
    fields: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s?(.*)$", line)
        assert m, f"unexpected frontmatter line (not a simple key: value): {line!r}"
        key, value = m.group(1), m.group(2)
        fields[key] = value
    return fields


def _registered_tool_names() -> set[str]:
    """Scrape tool names out of the `register()` body in tools/__init__.py."""
    text = TOOLS_INIT_PATH.read_text(encoding="utf-8")
    match = re.search(r"def register\(mcp: FastMCP\) -> None:\n(.*)\Z", text, flags=re.DOTALL)
    assert match, "could not locate register() function body"
    body = match.group(1)
    names = re.findall(r"mcp\.tool\(\)\((\w+)\)", body)
    assert names, "no mcp.tool()(...) registrations found"
    return set(names)


def test_resource_cost_skill_exists_with_matching_frontmatter_name():
    assert SKILL_PATH.exists(), f"expected new skill file at {SKILL_PATH}"

    raw_bytes = SKILL_PATH.read_bytes()
    assert not raw_bytes.startswith(b"\xef\xbb\xbf"), "SKILL.md must not have a BOM"

    text = raw_bytes.decode("utf-8")
    frontmatter, body = _split_frontmatter(text)
    fields = _parse_frontmatter(frontmatter)

    assert fields.get("name") == "comfy-local-resource-cost"
    assert "trigger" not in fields, (
        "'trigger' is not a Claude Code supported frontmatter field; "
        "all trigger vocabulary belongs in 'description'"
    )

    description = fields.get("description", "")
    assert description, "description must be non-empty"
    assert len(description) <= 1024, "description exceeds the 1024-char cap"

    assert body.strip(), "body after frontmatter must be non-empty"


def test_description_names_real_generation_tools():
    assert SKILL_PATH.exists(), f"expected new skill file at {SKILL_PATH}"
    text = SKILL_PATH.read_text(encoding="utf-8")
    frontmatter, _body = _split_frontmatter(text)
    fields = _parse_frontmatter(frontmatter)
    description = fields.get("description", "")

    registered = _registered_tool_names()
    # Guard against a hallucinated tool name: the cost-relevant subset must
    # actually be registered tools.
    assert COST_RELEVANT_TOOLS.issubset(registered), (
        f"cost-relevant tool set contains names not registered in "
        f"tools/__init__.py: {COST_RELEVANT_TOOLS - registered}"
    )

    for tool_name in sorted(COST_RELEVANT_TOOLS):
        assert tool_name in description, (
            f"description must mention tool name {tool_name!r} verbatim"
        )

    for word in ("image", "audio", "video", "ComfyUI"):
        assert word in description, f"description must mention {word!r}"


def _paragraphs(body: str) -> list[str]:
    """Split *body* into blank-line-delimited paragraphs (markdown blocks)."""
    return [p for p in re.split(r"\n\s*\n", body) if p.strip()]


def test_body_does_not_claim_get_config_reports_gpu_availability():
    """Pin fix: get_config() returns only comfy_url/workflow_dir/asset_ttl.

    There is no GPU-availability field anywhere in the codebase
    (src/comfy_plugin/config.py, tools/generation.py:455-481). The body must
    not pair a `get_config()` mention with a GPU-availability claim in the
    same markdown block — that would mean instructing an agent to inspect a
    field that does not exist.
    """
    assert SKILL_PATH.exists(), f"expected new skill file at {SKILL_PATH}"
    text = SKILL_PATH.read_text(encoding="utf-8")
    _frontmatter, body = _split_frontmatter(text)

    for para in _paragraphs(body):
        if "get_config" in para:
            assert not re.search(r"gpu", para, re.IGNORECASE), (
                "body must not pair get_config() with a GPU-availability "
                "claim -- get_config() only returns "
                "comfy_url/workflow_dir/asset_ttl, it has no GPU field. "
                f"offending block: {para!r}"
            )


def test_body_states_run_txt2video_is_currently_a_stub():
    """Pin fix: run_txt2video always raises NotImplementedError, at zero
    cost, and can therefore never be `timed_out: true` / `state: "running"`.

    src/comfy_plugin/tools/generation.py:484-520 shows run_txt2video calls
    txt2video(**params.model_dump()), catches NotImplementedError, and
    always returns a bare {"error": "<message>"} -- it never reaches
    _run_result_to_dict, so its response dict never contains a `state` or
    `timed_out` key under any `timeout` value. It can never be "running"
    and can never burn GPU in the background.

    The body must say so wherever it discusses run_txt2video's cost (at
    least one block), AND -- the stricter pin -- EVERY block that mentions
    run_txt2video together with a timeout/running signal (`timed_out` or
    `state: "running"` / `"running"`) must also carry a stub marker in that
    same block. A single correct paragraph elsewhere is not enough: an
    "any qualifying paragraph passes" heuristic let a real bug through
    where two other paragraphs still claimed run_txt2video returns
    `timed_out: true` with `state: "running"` and "keeps running ... in the
    background", directly contradicting the stub paragraphs.

    Same stricter pin for GPU/CPU cost claims: EVERY block that lists
    run_txt2video alongside another run_* submit tool (run_txt2img,
    run_txt2audio, run_workflow, run_template) while making a GPU/CPU
    cost-or-load claim (mentioning "gpu", "cpu", "cost", "tie up", or
    "borrow") must also carry a stub marker in that same block. This
    catches the H1-intro paragraph, which lumped `run_txt2video` in with
    the other four tools under "that job's GPU and CPU cost lands on the
    user's own hardware ... tie up the machine for minutes ... borrow this
    person's computer" with no stub/exclusion clause -- contradicting the
    cost table's "none -- it is currently a stub" entry for the same tool.
    """
    assert SKILL_PATH.exists(), f"expected new skill file at {SKILL_PATH}"
    text = SKILL_PATH.read_text(encoding="utf-8")
    _frontmatter, body = _split_frontmatter(text)

    stub_markers = ("notimplementederror", "not implemented", "stub")
    running_signal_markers = ("timed_out", '"running"')
    other_submit_tools = ("run_txt2img", "run_txt2audio", "run_workflow", "run_template")
    cost_load_markers = ("gpu", "cpu", "cost", "tie up", "borrow")

    found_stub_mention = False
    for para in _paragraphs(body):
        if "run_txt2video" not in para:
            continue
        para_lower = para.lower()
        has_stub_marker = any(marker in para_lower for marker in stub_markers)
        if has_stub_marker:
            found_stub_mention = True
        has_running_signal = any(
            marker in para_lower for marker in running_signal_markers
        )
        if has_running_signal:
            assert has_stub_marker, (
                "block mentions run_txt2video together with a "
                "timeout/running signal (timed_out / state: \"running\") "
                "but carries no stub marker (NotImplementedError / not "
                "implemented / stub) in the same block -- this "
                "contradicts run_txt2video always erroring immediately at "
                f"zero cost, before ever reaching ComfyUI. offending "
                f"block: {para!r}"
            )
        has_other_submit_tool = any(tool in para for tool in other_submit_tools)
        has_cost_load_claim = any(marker in para_lower for marker in cost_load_markers)
        if has_other_submit_tool and has_cost_load_claim:
            assert has_stub_marker, (
                "block lists run_txt2video alongside another run_* submit "
                "tool (run_txt2img / run_txt2audio / run_workflow / "
                "run_template) while making a GPU/CPU cost-or-load claim, "
                "but carries no stub marker (NotImplementedError / not "
                "implemented / stub) in the same block -- this implies "
                "run_txt2video costs GPU/CPU time like the other tools, "
                "contradicting it being a zero-cost stub that always "
                f"errors before reaching ComfyUI. offending block: {para!r}"
            )

    assert found_stub_mention, (
        "body must state, in a block mentioning run_txt2video, that it is "
        "currently a stub / not implemented (e.g. NotImplementedError) -- "
        "it always errors before reaching ComfyUI, at zero cost"
    )


def test_body_does_not_claim_cancel_job_stops_a_running_job():
    """Pin fix: cancel_job cannot abort a job that is already running.

    lib_python_comfy.ComfyClient.cancel only removes a prompt from the
    PENDING queue via POST /queue {"delete": [id]}; it returns False (a
    no-op) when the job is already running. generation.py's cancel_job
    discards that boolean and always reports {"cancelled": prompt_id},
    even when the running job was not actually stopped.

    The body must not describe cancel_job as able to stop/abandon a job
    that is already `state: "running"` without, in the same block, also
    saying cancel_job only removes PENDING work.
    """
    assert SKILL_PATH.exists(), f"expected new skill file at {SKILL_PATH}"
    text = SKILL_PATH.read_text(encoding="utf-8")
    _frontmatter, body = _split_frontmatter(text)

    stop_markers = ("abandon", "cancel the job", "abort", "stop the job")
    pending_caveat_markers = ("pending", "queue_pending", '"queued"', "queued")

    for para in _paragraphs(body):
        if "cancel_job" not in para:
            continue
        para_lower = para.lower()
        mentions_running = '"running"' in para_lower or "running job" in para_lower
        mentions_stopping = any(marker in para_lower for marker in stop_markers)
        if mentions_running and mentions_stopping:
            assert any(marker in para_lower for marker in pending_caveat_markers), (
                "block describes cancel_job stopping/abandoning a running "
                "job without stating that cancel_job only removes PENDING "
                "queue entries -- ComfyClient.cancel is a no-op against an "
                "already-running job (it only posts a queue-delete), and "
                "cancel_job's {\"cancelled\": prompt_id} response does not "
                f"confirm the job actually stopped. offending block: {para!r}"
            )


def test_skill_body_covers_cost_protocol():
    assert SKILL_PATH.exists(), f"expected new skill file at {SKILL_PATH}"
    text = SKILL_PATH.read_text(encoding="utf-8")
    _frontmatter, body = _split_frontmatter(text)
    body_lower = body.lower()

    for term in (
        "get_queue_status",
        "mandatory",
        "advisory",
        "cancel_job",
        "timed_out",
        "order of magnitude",
        "1024",
        "steps",
        "batch_size",
        "seconds",
    ):
        assert term.lower() in body_lower, f"body must mention {term!r}"

    expected_headings = [
        "What a job actually costs",
        "How to tell the machine is already busy",
        "Pre-flight check: mandatory vs. advisory",
        "Timeouts are not cancellations",
        "What to do instead of queuing blindly",
        "Related skills",
    ]
    for heading in expected_headings:
        assert heading in body, f"body must contain heading text {heading!r}"
