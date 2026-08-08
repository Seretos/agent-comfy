"""Regression guard for the mcp<2 dependency cap.

mcp 2.0.0 shipped as a breaking release that restructures
mcp.server.fastmcp. An unbounded "mcp>=1.2" specifier lets a clean install
resolve 2.0.0 and take down the whole import graph
(src/comfy_plugin/tools/__init__.py imports mcp.server.fastmcp.FastMCP).
This file verifies pyproject.toml's mcp dependency specifier carries an
upper bound that excludes the 2.x series, and that the installed
environment actually resolves to a 1.x release.

Stdlib + packaging + pytest only. Must NOT import comfy_plugin — a guard
that imports the package would itself be taken down by the very failure
it is meant to report.
"""
from __future__ import annotations

import importlib.metadata as metadata
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _find_mcp_entry() -> str | None:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    for dep in dependencies:
        req = Requirement(dep)
        if req.name == "mcp":
            return dep
    return None


def test_mcp_entry_present():
    """An mcp dependency entry must exist in project.dependencies."""
    entry = _find_mcp_entry()
    assert entry is not None, "mcp dependency entry not found in pyproject.toml"
    assert Requirement(entry).name == "mcp"


def test_mcp_specifier_excludes_2_x():
    """The mcp specifier must not admit the breaking 2.0.0 release.

    This is the driving regression test: mcp 2.0.0 restructures
    mcp.server.fastmcp and breaks the whole import graph.
    """
    entry = _find_mcp_entry()
    assert entry is not None, "mcp dependency entry not found in pyproject.toml"

    req = Requirement(entry)
    assert not req.specifier.contains("2.0.0"), (
        f"mcp dependency entry {entry!r} admits 2.0.0, the breaking release "
        "that restructures mcp.server.fastmcp; it must carry an upper bound "
        "(e.g. 'mcp>=1.2,<2')"
    )


def test_mcp_specifier_still_admits_1_x():
    """The cap must not overcorrect into excluding valid 1.x releases."""
    entry = _find_mcp_entry()
    assert entry is not None, "mcp dependency entry not found in pyproject.toml"

    req = Requirement(entry)
    assert req.specifier.contains("1.2.0"), (
        f"mcp dependency entry {entry!r} unexpectedly excludes 1.2.0"
    )
    assert req.specifier.contains("1.9.0"), (
        f"mcp dependency entry {entry!r} unexpectedly excludes 1.9.0"
    )


def test_mcp_specifier_excludes_all_of_2_x_and_beyond():
    """The cap must exclude the whole 2.x+ series, including pre-releases."""
    entry = _find_mcp_entry()
    assert entry is not None, "mcp dependency entry not found in pyproject.toml"

    req = Requirement(entry)
    assert not req.specifier.contains("2.5.1"), (
        f"mcp dependency entry {entry!r} unexpectedly admits 2.5.1"
    )
    assert not req.specifier.contains("3.0.0"), (
        f"mcp dependency entry {entry!r} unexpectedly admits 3.0.0"
    )
    assert not req.specifier.contains("2.0.0rc1", prereleases=True), (
        f"mcp dependency entry {entry!r} unexpectedly admits the 2.0.0rc1 pre-release"
    )


def test_installed_mcp_is_1_x():
    """The installed mcp package must actually resolve to a 1.x release."""
    try:
        installed_version = metadata.version("mcp")
    except metadata.PackageNotFoundError:
        pytest.skip("mcp not installed: environment problem, unrelated to the pin")

    assert Version(installed_version).major == 1, (
        f"installed mcp version {installed_version!r} is not 1.x; a clean "
        "install resolved a version outside the intended cap"
    )
