"""Shared tkinter plumbing for the app's dialogs.

The dialogs moved from PySide6 to tkinter for one reason: Qt was ~30 MB of
the frozen exe for four plain forms, and tkinter ships inside Python. The
Qt-era protocol is kept - construct with the same arguments, call `.exec()`,
compare the result to ACCEPTED - so `bom_converter` and the tests did not
have to change shape.

One hidden root window owns every dialog. Sequential `tk.Tk()` roots leak
Tcl interpreters; `Toplevel` children of a single withdrawn root are the
supported way to run dialogs one after another in one process.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

ACCEPTED = 1
REJECTED = 0

_root: tk.Tk | None = None


def _enable_dpi_awareness() -> None:
    """Without this, Windows bitmap-stretches the window on HiDPI displays
    and every label renders blurry."""
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def ensure_root() -> tk.Tk:
    global _root
    if _root is None or not _root.winfo_exists():
        _enable_dpi_awareness()
        _root = tk.Tk()
        _root.withdraw()
    return _root


def make_label(parent, text: str, bold: bool = False, wrap: bool = True) -> ttk.Label:
    label = ttk.Label(parent, text=text, justify="left", anchor="w")
    if wrap:
        label.configure(wraplength=700)
    if bold:
        base = tkfont.nametofont("TkDefaultFont")
        label.configure(font=(base.actual("family"), base.actual("size"), "bold"))
    return label


class TkDialog:
    """Modal dialog with the Qt result protocol.

    Subclasses build their widgets in `build(body)` and call `self.accept()`
    or `self.reject()`; `exec()` blocks until one of them runs (or the window
    is closed, which routes through `on_close`, default reject).
    """

    title = ""
    topmost = True

    def __init__(self, parent=None):
        self._result = REJECTED
        root = ensure_root()
        self.window = tk.Toplevel(root)
        self.window.title(self.title)
        self.window.withdraw()
        if self.topmost:
            self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        self.body = ttk.Frame(self.window, padding=12)
        self.body.pack(fill="both", expand=True)

    def exec(self) -> int:
        self.window.deiconify()
        self.window.lift()
        self.window.grab_set()
        self.window.focus_force()
        self.window.wait_window(self.window)
        return self._result

    def accept(self) -> None:
        self._result = ACCEPTED
        self.window.destroy()

    def reject(self) -> None:
        self._result = REJECTED
        self.window.destroy()

    def on_close(self) -> None:
        self.reject()
