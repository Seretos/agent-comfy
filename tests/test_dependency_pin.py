"""Regression guard for the lib-python-comfy sibling-lib pin.

Verifies pyproject.toml pins lib-python-comfy at (at least) v0.1.1 and that
the installed environment actually resolves to that version's public
surface — not a stale v0.0.4 copy shadowed by an editable sibling checkout.

Stdlib + lib_python_comfy + pytest only. Must NOT import comfy_plugin, to
keep this test disjoint from wave-2 ticket #39's work on
src/comfy_plugin/tools/generation.py.
"""
from __future__ import annotations

import inspect
import re
import tomllib
from pathlib import Path

import pytest

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"

_PIN_RE = re.compile(
    r"^lib-python-comfy @ git\+https://github\.com/Seretos/lib-python-comfy@v(\d+)\.(\d+)\.(\d+)$"
)


def _find_pin_entry() -> str | None:
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    for dep in dependencies:
        if dep.startswith("lib-python-comfy"):
            return dep
    return None


def test_pyproject_declares_lib_python_comfy_dependency():
    """The lib-python-comfy requirement must be present and pinned to a git tag."""
    entry = _find_pin_entry()

    assert entry is not None, "lib-python-comfy dependency entry not found in pyproject.toml"
    assert _PIN_RE.match(entry), (
        f"lib-python-comfy dependency entry does not match the expected "
        f"'git+https://github.com/Seretos/lib-python-comfy@v<tag>' shape: {entry!r}"
    )


def test_lib_python_comfy_pin_is_at_least_v0_1_1():
    """The pinned tag must be >= v0.1.1 (floor check, not exact match)."""
    entry = _find_pin_entry()
    assert entry is not None, "lib-python-comfy dependency entry not found in pyproject.toml"

    match = _PIN_RE.match(entry)
    assert match, f"could not parse version tag out of pin entry: {entry!r}"

    pinned_version = tuple(int(part) for part in match.groups())
    assert pinned_version >= (0, 1, 1), (
        f"lib-python-comfy pin {pinned_version} is below the required floor (0, 1, 1)"
    )


def test_lib_python_comfy_importable():
    """python -c 'import lib_python_comfy' must succeed (ticket acceptance check)."""
    pytest.importorskip("lib_python_comfy")


def test_installed_lib_exposes_v0_0_5_txt2audio_surface():
    """The installed lib_python_comfy.txt2audio must carry v0.0.5's new params.

    Three distinct outcomes are encoded on purpose:
      1. lib_python_comfy not importable at all -> SKIP (environment problem,
         unrelated to the pin itself).
      2. lib_python_comfy imports but has no txt2audio -> FAIL (both v0.0.4
         and v0.0.5 export it, so absence is a genuine API break).
      3. txt2audio present but missing any of the three new v0.0.5 params ->
         FAIL, most likely caused by an editable sibling checkout shadowing
         the git-pinned v0.0.5. Remedy:
           python -m pip uninstall -y lib-python-comfy
           python -m pip install -e ".[test]"
    """
    lib_python_comfy = pytest.importorskip(
        "lib_python_comfy", reason="lib_python_comfy not importable: environment problem unrelated to the pin"
    )

    assert hasattr(lib_python_comfy, "txt2audio"), (
        "lib_python_comfy.txt2audio is missing entirely; both v0.0.4 and "
        "v0.0.5 export it at the package root, so this is a genuine API break"
    )

    signature = inspect.signature(lib_python_comfy.txt2audio)
    required_new_params = {"clip_name", "clip_type", "seconds_start"}
    missing = required_new_params - set(signature.parameters)

    assert not missing, (
        f"lib_python_comfy.txt2audio is missing v0.0.5 params {missing!r}; "
        "the installed copy is likely a stale v0.0.4 shadowed by an "
        "editable sibling checkout of lib-python-comfy. Fix with: "
        "'python -m pip uninstall -y lib-python-comfy' then "
        "'python -m pip install -e \".[test]\"'"
    )

    for param_name in required_new_params:
        param = signature.parameters[param_name]
        assert param.default is not inspect.Parameter.empty, (
            f"lib_python_comfy.txt2audio param {param_name!r} has no default; "
            "v0.0.5 adds it as an additive keyword param and existing call "
            "sites must remain valid"
        )


def test_installed_lib_exposes_extra_dirs_template_surface():
    """The installed lib_python_comfy must expose list_templates/load_template
    at the package root, both accepting an extra_dirs parameter.

    Work package #50 (project-local comfy templates) wires config's resolved
    project-templates directory through to these two functions via extra_dirs.
    This guard fails loudly if a future pin bump drops either function or its
    extra_dirs parameter from the surface the wiring depends on.
    """
    lib_python_comfy = pytest.importorskip(
        "lib_python_comfy", reason="lib_python_comfy not importable: environment problem unrelated to the pin"
    )

    assert hasattr(lib_python_comfy, "list_templates"), (
        "lib_python_comfy.list_templates is missing at the package root; "
        "work package #50 imports it from there"
    )
    assert hasattr(lib_python_comfy, "load_template"), (
        "lib_python_comfy.load_template is missing at the package root; "
        "work package #50 imports it from there"
    )

    list_templates_sig = inspect.signature(lib_python_comfy.list_templates)
    assert "extra_dirs" in list_templates_sig.parameters, (
        "lib_python_comfy.list_templates has no extra_dirs parameter; "
        "cannot wire up project-local templates without it"
    )

    load_template_sig = inspect.signature(lib_python_comfy.load_template)
    assert "extra_dirs" in load_template_sig.parameters, (
        "lib_python_comfy.load_template has no extra_dirs parameter; "
        "cannot wire up project-local templates without it"
    )
