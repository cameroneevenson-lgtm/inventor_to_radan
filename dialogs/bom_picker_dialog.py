from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from bom_finder import find_recent_boms
from dialogs.tk_base import ACCEPTED, TkDialog, make_label

# Scanned once per process, not once per dialog. verify_main reopens the picker
# after every run, and paying the share walk again each time would make the
# fix-and-recheck loop feel broken.
_SHORTLIST_CACHE: list[tuple[str, float]] | None = None


class BomPickerDialog(TkDialog):
    """Front door for the frozen verification build.

    The .bat launcher takes its BOM by drag-and-drop, but an exe opened from a
    shortcut gets no argument at all, so it has to ask. The shortlist is there
    because the answer is nearly always one of the last few BOMs exported to
    the share, and navigating to it by hand is the slow part.

    The share walk runs on a worker thread and the window polls for it,
    reporting folders scanned as it goes. It takes ~20 s over the network, and
    a frozen window on startup is precisely the "nothing happens" failure this
    app has already worn once.
    """

    title = "Verify Inventor BOM"
    topmost = False

    def __init__(self, data_dir: str, scan: dict, parent=None):
        super().__init__(parent)
        self.selected_path: str | None = None
        self._scan_settings = dict(scan)
        self._search_root = self._scan_settings.get("root", "")
        self._scan_result: list | None = None
        self._scan_progress: tuple[int, int] = (0, 0)
        self._paths: list[str] = []

        make_label(
            self.body,
            "Check an Inventor BOM for missing DXFs and unknown descriptions.\n"
            "Writes a report next to the BOM. No RADAN CSV is produced.",
        ).pack(fill="x", anchor="w")

        self.list_label = make_label(self.body, "")
        self.list_label.pack(fill="x", anchor="w", pady=(8, 2))

        list_frame = ttk.Frame(self.body)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, font=("Consolas", 10), activestyle="none")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", lambda e: self._accept_selected())
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._sync_verify_button())
        self.listbox.bind("<Return>", lambda e: self._accept_selected())

        self.status = make_label(self.body, "No BOM selected.")
        self.status.pack(fill="x", anchor="w", pady=(6, 0))
        make_label(self.body, f"Rule tables: {data_dir}").pack(fill="x", anchor="w")

        buttons = ttk.Frame(self.body)
        buttons.pack(fill="x", pady=(10, 0))
        self.verify_button = ttk.Button(
            buttons, text="Verify Selected", command=self._accept_selected, state="disabled"
        )
        self.verify_button.pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(buttons, text="Select BOM...", command=self.choose_bom).pack(
            side="left", expand=True, fill="x", padx=4
        )
        self.refresh_button = ttk.Button(
            buttons, text="Refresh", command=lambda: self.start_scan(force=True)
        )
        self.refresh_button.pack(side="left", expand=True, fill="x", padx=4)
        ttk.Button(buttons, text="Close", command=self.reject).pack(
            side="left", expand=True, fill="x", padx=(4, 0)
        )

        self.window.geometry("640x460")
        self.start_scan()

    # ---- shortlist

    def _window_label(self) -> str:
        days = self._scan_settings.get("max_age_days")
        window = f"last {days:g} days" if days else "recent"
        return f"BOMs in {os.path.basename(self._search_root)} ({window})"

    def start_scan(self, *, force: bool = False) -> None:
        if not self._search_root:
            self.list_label.configure(text="Recent BOMs: shortlist disabled.")
            return
        if _SHORTLIST_CACHE is not None and not force:
            self._populate(_SHORTLIST_CACHE)
            return

        self.list_label.configure(text=f"{self._window_label()} - scanning...")
        self.refresh_button.configure(state="disabled")
        self._scan_result = None
        self._scan_progress = (0, 0)

        def worker(settings=dict(self._scan_settings)):
            def on_progress(dirs_scanned, hits):
                self._scan_progress = (dirs_scanned, hits)

            try:
                hits = find_recent_boms(progress=on_progress, **settings)
            except Exception:
                hits = []
            self._scan_result = hits

        threading.Thread(target=worker, daemon=True).start()
        self.window.after(100, self._poll_scan)

    def _poll_scan(self) -> None:
        if not self.window.winfo_exists():
            return
        if self._scan_result is None:
            # The share walk takes ~20 s. A status line that says nothing for
            # that long reads as a hang, which this app has been mistaken for
            # before.
            dirs_scanned, hits = self._scan_progress
            self.list_label.configure(
                text=f"{self._window_label()} - scanning... "
                     f"{dirs_scanned} folders, {hits} found"
            )
            self.window.after(150, self._poll_scan)
            return
        global _SHORTLIST_CACHE
        _SHORTLIST_CACHE = self._scan_result
        self.refresh_button.configure(state="normal")
        self._populate(self._scan_result)

    def _populate(self, hits: list[tuple[str, float]]) -> None:
        self.listbox.delete(0, "end")
        self._paths = []
        if not hits:
            self.list_label.configure(
                text=f"{self._window_label()} - none found. "
                     "Use Select BOM... for anything older."
            )
            self._sync_verify_button()
            return

        self.list_label.configure(text=f"{self._window_label()} ({len(hits)}):")
        for path, mtime in hits:
            when = time.strftime("%Y-%m-%d", time.localtime(mtime))
            # The folder path relative to the root, not just the parent: a kit
            # BOM's parent is "PUMP HOUSE", which without "F59808 / PUMP PACK"
            # in front of it does not say which truck.
            folder = os.path.dirname(path)
            try:
                folder = os.path.relpath(folder, self._search_root)
            except ValueError:
                folder = os.path.basename(folder)
            location = folder.replace(os.sep, " / ")
            self.listbox.insert("end", f"{when}   {os.path.basename(path)}   [{location}]")
            self._paths.append(path)
        self._sync_verify_button()

    def _sync_verify_button(self) -> None:
        state = "normal" if self.listbox.curselection() else "disabled"
        self.verify_button.configure(state=state)

    # ---- selection

    def _accept_selected(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        self.selected_path = self._paths[selection[0]]
        self.accept()

    def choose_bom(self) -> None:
        start_dir = self._search_root if os.path.isdir(self._search_root) else ""
        path = filedialog.askopenfilename(
            parent=self.window,
            title="Select an Inventor BOM",
            initialdir=start_dir,
            filetypes=[("BOM files", "*.csv *.xlsx"), ("All files", "*")],
        )
        if not path:
            return
        self.selected_path = os.path.normpath(path)
        self.accept()


def pick_bom(data_dir: str, scan: dict, last_message: str = "") -> str | None:
    """Show the picker and return the chosen BOM, or None if they closed it.

    `scan` is passed straight to `bom_finder.find_recent_boms`, so settings can
    be added there without threading another argument through this call.
    """
    dialog = BomPickerDialog(data_dir, scan)
    if last_message:
        dialog.status.configure(text=last_message)
    if dialog.exec() != ACCEPTED:
        return None
    return dialog.selected_path
