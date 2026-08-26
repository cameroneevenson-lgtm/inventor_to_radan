from __future__ import annotations

from collections.abc import Callable
from tkinter import messagebox, ttk

from dialogs.tk_base import TkDialog, make_label


class MissingDxfDialog(TkDialog):
    """
    Step through UNKNOWN missing-DXF descriptions and force a classification:
      - Non-Laser: store FIRST TOKEN to nonlaser_tokens.csv
      - Expected Laser: collect the description for a complete RADAN rule
    Non-laser choices write immediately; expected-laser choices are returned
    to the caller so material, thickness, and strategy can be collected next.

    Sanity feature: shows current Non-Laser token list from disk inside the dialog.
    """

    title = "DXF Accountability: Missing DXF Classification"

    def __init__(
        self,
        items: list[dict],
        *,
        nonlaser_tokens_csv: str,
        load_set: Callable[[str, str], set[str]],
        append_unique: Callable[[str, list[str], list[str]], None],
        parent=None,
    ):
        super().__init__(parent)
        self.nonlaser_tokens_csv = nonlaser_tokens_csv
        self._load_set = load_set
        self._append_unique = append_unique

        self.items = items
        self.i = 0
        self.expected_descriptions: list[str] = []

        self.lbl_progress = make_label(self.body, "")
        self.lbl_desc = make_label(self.body, "", bold=True)
        self.lbl_token = make_label(self.body, "")
        self.lbl_count = make_label(self.body, "")

        note = (
            "No DXF exists for this BOM entry.\n\n"
            "- Mark as Non-Laser: stores FIRST TOKEN only (family-level) in nonlaser_tokens.csv\n"
            "- Expected Laser: defines a complete description_rules.csv entry next\n"
            "  and lists this part as an expected missing DXF in the final report.\n"
        )
        self.lbl_note = make_label(self.body, note)

        self.lbl_nonlaser_title = make_label(
            self.body, "Current Non-Laser token list (from disk):", bold=True
        )
        self.lbl_nonlaser_list = make_label(self.body, "")

        for widget in (
            self.lbl_progress,
            self.lbl_desc,
            self.lbl_token,
            self.lbl_count,
            self.lbl_note,
            self.lbl_nonlaser_title,
            self.lbl_nonlaser_list,
        ):
            widget.pack(fill="x", pady=2, anchor="w")

        btn_row = ttk.Frame(self.body)
        btn_row.pack(side="bottom", fill="x", pady=(10, 0))
        self.btn_nonlaser = ttk.Button(
            btn_row, text="Mark as Non-Laser", command=self.choose_nonlaser
        )
        self.btn_expected = ttk.Button(
            btn_row, text="Expected Laser - Define RADAN Rule", command=self.choose_expected
        )
        self.btn_nonlaser.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.btn_expected.pack(side="left", expand=True, fill="x", padx=(4, 0))

        self.window.geometry("760x620")
        self.load_step()

    def _refresh_nonlaser_list(self):
        toks = sorted(self._load_set(self.nonlaser_tokens_csv, "Token"))
        if not toks:
            self.lbl_nonlaser_list.configure(text="(none yet)")
            return
        if len(toks) <= 40:
            text = ", ".join(toks)
        else:
            text = ", ".join(toks[:40]) + f" ... (+{len(toks)-40} more)"
        self.lbl_nonlaser_list.configure(text=text)

    def load_step(self):
        it = self.items[self.i]
        desc = it["desc"]
        tok = it["token"]
        cnt = it.get("count", 0)

        self.lbl_progress.configure(text=f"{self.i+1} of {len(self.items)}")
        self.lbl_desc.configure(text=f"Description (full):\n{desc}")
        self.lbl_token.configure(
            text=f"Non-laser family key (first token): {tok if tok else '(blank)'}"
        )
        self.lbl_count.configure(text=f"Occurrences (missing DXF): {cnt}")

        self._refresh_nonlaser_list()

    def choose_nonlaser(self):
        it = self.items[self.i]
        tok = it["token"]
        if not tok:
            messagebox.showerror(
                "Missing token",
                "Cannot classify as non-laser because the first token is blank.",
                parent=self.window,
            )
            return
        self._append_unique(self.nonlaser_tokens_csv, ["Token"], [tok])
        self.next_step()

    def choose_expected(self):
        it = self.items[self.i]
        desc = it["desc"]

        self.expected_descriptions.append(desc)
        self.next_step()

    def next_step(self):
        self.i += 1
        if self.i >= len(self.items):
            self.accept()
        else:
            self.load_step()
