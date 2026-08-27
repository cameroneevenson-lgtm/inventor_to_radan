# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the verification-only exe.

Committed rather than generated so the exclusions below are reviewable.

Built from .buildvenv (see build_verify_exe.bat), which holds only openpyxl
and pyinstaller. There is deliberately no exclude list for pandas, numpy or
PySide6: the app no longer imports them and they are not installed in that
venv, so there is nothing to exclude. Do not re-add such a list - it would
imply a relationship with packages this app has never had.

The excludes that remain are stdlib modules Python's own machinery drags in
by association. openpyxl needs none of them, and the golden-file runs prove
nothing else does either.
"""

import os

# SPECPATH, not getcwd(): the .bat is run from wherever the operator happens to
# be, and PyInstaller injects SPECPATH as this file's own directory.
ROOT = os.path.abspath(SPECPATH)  # noqa: F821 - injected by PyInstaller


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
    excludes=[
        # No database, no networking, no terminal UI, no docs tooling.
        "sqlite3",
        "_sqlite3",
        "ssl",
        "_ssl",
        "curses",
        "_curses",
        # openpyxl imports hashlib (it hashes sheet-protection passwords, which
        # this app never sets). _hashlib is the OpenSSL binding and drags in
        # libcrypto - 5.2 MB, half the exe. Without it hashlib falls back to
        # Python's built-in _sha1/_sha256/etc, which is all openpyxl can need
        # here. Verified by running real BOMs through the built exe.
        "_hashlib",
        "lib2to3",
        "pydoc_data",
        "unittest",
        "email",
        "http",
        "xmlrpc",
        # Belt and braces: these are gone from the code and the venv, and an
        # accidental reintroduction should fail the build loudly rather than
        # quietly add 40 MB.
        "pandas",
        "numpy",
        "PySide6",
        "PyQt5",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# Shown by the bootloader while the onefile bundle unpacks, which is the few
# seconds before any of our code runs and so the only part a splash can cover.
# It uses the Tcl/Tk already in the bundle, so it costs nothing extra.
splash = Splash(  # noqa: F821 - injected by PyInstaller
    os.path.join(ROOT, "splash.png"),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(20, 120),
    text_size=10,
    text_color="#F8FAFC",
    always_on_top=False,
)

# One file: the whole point is handing a colleague a single thing to copy. It
# costs a few seconds on every launch while the bundle unpacks to temp.
exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.datas,
    [],
    name="BOM Verify",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # No console. The app is dialogs only, and a black window flashing up
    # behind them looks broken. Everything that used to print now routes
    # through bom_converter.tell(), which shows a message box when frozen -
    # print() raises in a windowed build, where sys.stdout is None.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
