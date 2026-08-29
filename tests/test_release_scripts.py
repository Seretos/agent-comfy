"""Driving tests for the release-notes-from-main release scripts (package #53).

Covers:
  - R1: .github/scripts/prev-release-tag.sh — resolves the previous
    `agent-comfy--v*` release tag by strict semver order (#52).
  - R2: .github/scripts/marketplace-payload.sh — builds the marketplace
    dispatch JSON payload, including the new `changelog` field, safely
    (#49).

Neither script exists yet in this phase; every test here is expected to
fail RED because the subprocess invocation cannot find the script file.

These tests shell out to `bash`, `git`, `awk`, and `sort`. On a platform
where any of those isn't on PATH (most Windows dev boxes without Git for
Windows/WSL) the whole module is skipped — `ubuntu-22.04` is the
authoritative CI leg for these tests.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("bash", "git", "awk", "sort")),
    reason="bash/git/awk/sort not all present on PATH; ubuntu-22.04 CI is authoritative for these tests",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PREV_TAG_SCRIPT = REPO_ROOT / ".github" / "scripts" / "prev-release-tag.sh"
PAYLOAD_SCRIPT = REPO_ROOT / ".github" / "scripts" / "marketplace-payload.sh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    """Create a throwaway git repo at `path` with one empty commit."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-q", "-m", "init"], cwd=path, check=True
    )


def _tag(path: Path, name: str) -> None:
    subprocess.run(["git", "tag", name], cwd=path, check=True)


def _run_prev_tag(repo: Path, new_tag: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(PREV_TAG_SCRIPT), new_tag],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def _run_payload(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    # Drop CHANGELOG unless explicitly provided by the caller, so "unset"
    # tests aren't accidentally polluted by the ambient environment.
    env.pop("CHANGELOG", None)
    env.update(env_overrides)
    return subprocess.run(
        ["bash", str(PAYLOAD_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# R1 — prev-release-tag.sh
# ---------------------------------------------------------------------------


def test_prev_tag_basic_resolution(tmp_path: Path):
    """Given two prior release tags, resolves the immediate predecessor of a new one."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _tag(repo, "agent-comfy--v0.0.1")
    _tag(repo, "agent-comfy--v0.0.2")

    result = _run_prev_tag(repo, "agent-comfy--v0.0.3")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "agent-comfy--v0.0.2"


def test_prev_tag_no_tags_at_all(tmp_path: Path):
    """First release ever: no agent-comfy--v* tags exist -> empty stdout, exit 0."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    result = _run_prev_tag(repo, "agent-comfy--v0.0.1")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_prev_tag_rerun_never_returns_itself(tmp_path: Path):
    """If the tag being created already exists (re-run), the predecessor is returned, not itself."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _tag(repo, "agent-comfy--v0.0.1")
    _tag(repo, "agent-comfy--v0.0.2")

    result = _run_prev_tag(repo, "agent-comfy--v0.0.2")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "agent-comfy--v0.0.1"


def test_prev_tag_semver_numeric_not_lexicographic(tmp_path: Path):
    """v0.0.10 outranks v0.0.9 numerically, not lexicographically."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _tag(repo, "agent-comfy--v0.0.9")
    _tag(repo, "agent-comfy--v0.0.10")

    result = _run_prev_tag(repo, "agent-comfy--v0.0.11")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "agent-comfy--v0.0.10"


def test_prev_tag_prerelease_sorts_before_release(tmp_path: Path):
    """A prerelease tag sorts before its corresponding final release tag."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _tag(repo, "agent-comfy--v0.1.0-rc.1")
    _tag(repo, "agent-comfy--v0.1.0")

    result = _run_prev_tag(repo, "agent-comfy--v0.2.0")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "agent-comfy--v0.1.0"


def test_prev_tag_prerelease_numeric_ordering(tmp_path: Path):
    """rc.2 sorts after rc.1 (numeric prerelease component, not lexicographic)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _tag(repo, "agent-comfy--v0.1.0-rc.1")
    _tag(repo, "agent-comfy--v0.1.0-rc.2")

    result = _run_prev_tag(repo, "agent-comfy--v0.1.0-rc.3")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "agent-comfy--v0.1.0-rc.2"


def test_prev_tag_ignores_foreign_and_marker_tags(tmp_path: Path):
    """Non-matching tags -- bare v*, short semver, and src/* markers -- are never returned."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _tag(repo, "v0.0.9")  # no plugin prefix
    _tag(repo, "agent-comfy--v1.0")  # invalid semver (only two components)
    _tag(repo, "src/agent-comfy--v0.0.1")  # marker-tag namespace, must not match the release glob
    _tag(repo, "agent-comfy--v0.0.1")  # the one genuine predecessor

    result = _run_prev_tag(repo, "agent-comfy--v0.0.2")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "agent-comfy--v0.0.1"


# ---------------------------------------------------------------------------
# R2 — marketplace-payload.sh
# ---------------------------------------------------------------------------

_BASE_ENV = {
    "NAME": "agent-comfy",
    "DESC": 'a plugin with a "quoted" description',
    "REPO": "Seretos/agent-comfy",
    "VERSION": "0.0.3",
    "TAG": "agent-comfy--v0.0.3",
}

_EXPECTED_KEYS = {
    "name",
    "description",
    "repo",
    "category",
    "version",
    "ref",
    "icon",
    "description_url",
    "changelog",
}


def test_payload_with_hostile_changelog_round_trips_exactly():
    """A changelog with newlines, quotes, backticks, backslashes, $() and a leading # survives byte-for-byte."""
    hostile_changelog = (
        'line one\n'
        'has a "double quote" and a `backtick`\n'
        'a backslash \\ and a command sub $(whoami)\n'
        '# looks like a comment but is just changelog text\n'
        'final line'
    )
    env = dict(_BASE_ENV)
    env["CHANGELOG"] = hostile_changelog

    result = _run_payload(env)

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    assert data["event_type"] == "plugin-release"
    payload = data["client_payload"]

    assert payload["name"] == "agent-comfy"
    assert payload["description"] == env["DESC"]
    assert payload["repo"] == "Seretos/agent-comfy"
    assert payload["category"] == "mcp"
    assert payload["version"] == "0.0.3"
    assert payload["ref"] == "agent-comfy--v0.0.3"
    assert (
        payload["icon"]
        == "https://raw.githubusercontent.com/Seretos/agent-comfy/agent-comfy--v0.0.3/assets/icon.png"
    )
    assert (
        payload["description_url"]
        == "https://raw.githubusercontent.com/Seretos/agent-comfy/agent-comfy--v0.0.3/description.md"
    )
    assert payload["changelog"] == hostile_changelog

    assert set(payload.keys()) == _EXPECTED_KEYS


def test_payload_empty_changelog_key_omitted():
    """When CHANGELOG is empty/unset, the changelog key is absent (not sent as an empty string)."""
    env = dict(_BASE_ENV)
    env["CHANGELOG"] = ""

    result = _run_payload(env)

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    payload = data["client_payload"]

    assert "changelog" not in payload
    assert set(payload.keys()) == _EXPECTED_KEYS - {"changelog"}


def test_payload_unset_changelog_key_omitted():
    """When CHANGELOG is entirely unset (not just empty), the changelog key is still absent."""
    env = dict(_BASE_ENV)
    # Deliberately do not set CHANGELOG at all.

    result = _run_payload(env)

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    payload = data["client_payload"]

    assert "changelog" not in payload
    assert set(payload.keys()) == _EXPECTED_KEYS - {"changelog"}


def test_payload_plain_single_line_changelog():
    """Sanity case: a simple single-line changelog with no special characters round-trips."""
    env = dict(_BASE_ENV)
    env["CHANGELOG"] = "Fixed a minor bug."

    result = _run_payload(env)

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    payload = data["client_payload"]

    assert payload["changelog"] == "Fixed a minor bug."
    assert set(payload.keys()) == _EXPECTED_KEYS
