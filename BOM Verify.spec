# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the verification-only exe.

Committed rather than generated, because the Qt trimming below cannot be
expressed as command-line flags: --exclude-module filters Python modules, not
the DLLs and data trees PySide6's hook collects.

Built from .buildvenv (see build_verify_exe.bat), which is why there is no
--exclude-module list here for scipy/matplotlib/pyarrow and friends. They are
not installed in that venv, so there is nothing to exclude. Do not re-add such
a list: it would imply this app has a relationship with packages it has never
imported.
"""

import os

# SPECPATH, not getcwd(): the .bat is run from wherever the operator happens to
# be, and PyInstaller injects SPECPATH as this file's own directory.
ROOT = os.path.abspath(SPECPATH)  # noqa: F821 - injected by PyInstaller

# Qt pieces this app never touches. It is a plain QWidget tool: no networking,
# no images beyond the window chrome, no OpenGL, English only.
EXCLUDE_BINARY_NAMES = {
    # Software OpenGL rasteriser, only reached when no GPU driver is present -
    # RDP and VM sessions. Confirmed all local PCs, so it is 19.7 MB of nothing.
    "opengl32sw.dll",
    "Qt6Network.dll",
    "QtNetwork.pyd",
    "Qt6Svg.dll",
    "Qt6Qml.dll",
    "Qt6Quick.dll",
}

EXCLUDE_PATH_PARTS = (
    # Qt's localised strings; the app is English only.
    os.path.join("PySide6", "translations"),
    # No networking, so neither TLS backends nor connectivity probing.
    os.path.join("plugins", "tls"),
    os.path.join("plugins", "networkinformation"),
)

# Image formats: keep only what the window chrome can ask for.
KEEP_IMAGEFORMATS = {"qico.dll", "qjpeg.dll", "qgif.dll"}
# Windows-only tool, so one platform plugin.
KEEP_PLATFORMS = {"qwindows.dll"}


def _drop(dest: str) -> bool:
    name = os.path.basename(dest)
    norm = dest.replace("/", os.sep)

    if name in EXCLUDE_BINARY_NAMES:
        return True
    if any(part in norm for part in EXCLUDE_PATH_PARTS):
        return True
    if os.path.join("plugins", "imageformats") in norm and name not in KEEP_IMAGEFORMATS:
        return True
    if os.path.join("plugins", "platforms") in norm and name not in KEEP_PLATFORMS:
        return True
    return False


a = Analysis(
    [os.path.join(ROOT, "verify_main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "description_rules.csv"), "."),
        (os.path.join(ROOT, "ftq_parts.csv"), "."),
        (os.path.join(ROOT, "nonlaser_tokens.csv"), "."),
        (os.path.join(ROOT, "stock_cut_parts.csv"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython"],
    noarchive=False,
)

a.binaries = [entry for entry in a.binaries if not _drop(entry[1])]
a.datas = [entry for entry in a.datas if not _drop(entry[1])]

pyz = PYZ(a.pure)

# One file: the whole point is handing a colleague a single thing to copy. It
# costs 5-15 s on every launch while the bundle unpacks to temp.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BOM Verify",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
