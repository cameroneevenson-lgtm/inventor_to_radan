from __future__ import annotations

from collections.abc import Callable
from tkinter import messagebox, ttk

from dialogs.tk_base import TkDialog, make_label


class RadanRuleDialog(TkDialog):
    """
    Step through missing RADAN rules (for descriptions that DO have DXFs).
    Writes immediately to description_rules.csv on each Save.
    """

    title = "Define RADAN Rule (by Description)"

    def __init__(
        self,
        descs: list[str],
        ftq_descs: set[str],
        *,
        append_rule: Callable[[str, str, str, str], None],
        parent=None,
    ):
        super().__init__(parent)
        self._append_rule = append_rule

        self.descs = descs
        self.ftq_descs = ftq_descs
        self.i = 0

        self.lbl_progress = make_label(self.body, "")
        self.lbl_desc = make_label(self.body, "", bold=True)
        self.lbl_progress.pack(fill="x", pady=2, anchor="w")
        self.lbl_desc.pack(fill="x", pady=2, anchor="w")

        form = ttk.Frame(self.body)
        form.pack(fill="x", pady=8)
        form.columnconfigure(1, weight=1)

        self.inp_mat = ttk.Entry(form)
        self.inp_thk = ttk.Entry(form)
        self.inp_strat = ttk.Entry(form)

        for row, (label, entry) in enumerate(
            (("Material:", self.inp_mat), ("Thickness:", self.inp_thk), ("Strategy:", self.inp_strat))
        ):
            make_label(form, label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            entry.grid(row=row, column=1, sticky="ew", pady=2)

        self.btn_save = ttk.Button(self.body, text="Save & Next", command=self.save_next)
        self.btn_save.pack(side="bottom", fill="x", pady=(10, 0))

        self.window.geometry("640x360")
        self.load_step()

    def load_step(self):
        desc = self.descs[self.i]
        self.lbl_progress.configure(text=f"{self.i+1} of {len(self.descs)}")
        self.lbl_desc.configure(text=f"Description:\n{desc}")

        for entry in (self.inp_mat, self.inp_thk, self.inp_strat):
            entry.configure(state="normal")
            entry.delete(0, "end")

        if desc in self.ftq_descs:
            self.inp_mat.insert(0, "Aluminum 3003 CHK FTQ")
            self.inp_mat.configure(state="disabled")

    def save_next(self):
        desc = self.descs[self.i]
        mat = self.inp_mat.get().strip()
        thk = self.inp_thk.get().strip()
        strat = self.inp_strat.get().strip()

        if not mat or not thk or not strat:
            messagebox.showerror(
                "Missing data",
                "Material, Thickness, and Strategy are all required.",
                parent=self.window,
            )
            return

        self._append_rule(desc, mat, thk, strat)

        self.i += 1
        if self.i >= len(self.descs):
            self.accept()
        else:
            self.load_step()
