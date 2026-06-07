# PyInstaller spec for the agent-comfy MCP server.
#
# Produces a single-file self-contained binary that bundles the Python
# interpreter, the MCP runtime, and the package itself. Output extension is
# host-OS-dependent — `.exe` on Windows, no extension on Linux. PyInstaller
# handles the per-OS suffix automatically; this spec is OS-agnostic.
#
# Build:    pwsh -File scripts/build.ps1 -Clean
# Output:   dist/comfy.exe on Windows, dist/comfy on Linux
# Copy to:  bin/comfy(.exe)  (handled by scripts/build.ps1)

# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
ROOT = Path(SPECPATH)

# `mcp.cli` requires optional `typer`/`rich` deps the server doesn't need.
# Collect mcp manually, filtering out the CLI subpackage so PyInstaller doesn't
# fail trying to import it.
def _not_cli(name: str) -> bool:
    return not name.startswith("mcp.cli")

mcp_hiddenimports = collect_submodules("mcp", filter=_not_cli)

# Collect native/lazily-generated submodules for each dep that needs it.
pydantic_d, pydantic_b, pydantic_h = collect_all("pydantic")
pydantic_core_d, pydantic_core_b, pydantic_core_h = collect_all("pydantic_core")
httpx_d, httpx_b, httpx_h = collect_all("httpx")
pillow_d, pillow_b, pillow_h = collect_all("PIL")
lib_d, lib_b, lib_h = collect_all("lib_python_comfy")

extra_hidden = ["anyio", "starlette"]
extra_hidden += collect_submodules("comfy_plugin")
extra_hidden += pydantic_h + pydantic_core_h + httpx_h + pillow_h + lib_h

a = Analysis(
    ["src/comfy_plugin/__main__.py"],
    pathex=[str(ROOT / "src")],
    binaries=[] + pydantic_b + pydantic_core_b + httpx_b + pillow_b + lib_b,
    datas=[] + pydantic_d + pydantic_core_d + httpx_d + pillow_d + lib_d,
    hiddenimports=mcp_hiddenimports + extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "test",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="comfy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # don't compress — slower startup, no real size win on stdio binaries
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # MUST be console=True for stdio MCP transport
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
