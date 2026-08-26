from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk

from dialogs.tk_base import TkDialog, make_label

_COLORS = {
    "base": "#111827",
    "muted": "#475569",
    "green": "#15803D",
    "yellow": "#A16207",
    "red": "#B91C1C",
}


class ReportReviewDialog(TkDialog):
    # Non-laser parts are green, not yellow: every line there matched a token
    # the operator already put in nonlaser_tokens.csv, so it confirms the
    # classification rather than asking for a decision. One BOM produced 18 of
    # them, and 18 checkboxes with nothing behind them is the click-through
    # fatigue that made the old single blanket checkbox worthless.
    REVIEW_SECTION_LEVELS = {
        "Expected laser but missing DXF": "red",
        # A verification run cannot resolve these itself; somebody with the
        # RADAN vocabulary has to add the rule before the parts can be nested.
        "New descriptions": "yellow",
        "Orphan DXFs": "yellow",
        "DXFs missing PDFs": "yellow",
        "Non-laser parts": "green",
        "Cut to length from stock": "green",
    }

    title = "Review Inventor-to-RADAN Report"

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self._acknowledged = False

        make_label(self.body, "Review required before production use", bold=True).pack(
            fill="x", anchor="w"
        )
        warning_count = (
            len(result.expected_missing_dxfs)
            + len(result.orphan_dxfs)
            + len(result.missing_pdfs)
        )
        critical_count = len(result.expected_missing_dxfs)
        if critical_count:
            detail_text = (
                f"This report contains {critical_count} critical item(s) and "
                f"{warning_count - critical_count} review item(s). "
                "Read the report below before acknowledging completion."
            )
            detail_color = _COLORS["red"]
        elif warning_count:
            detail_text = (
                f"This report contains {warning_count} item(s) to check. "
                "Read the yellow sections below before acknowledging completion."
            )
            detail_color = _COLORS["yellow"]
        else:
            detail_text = (
                "No report warnings were found. Review the green confirmation sections before closing this conversion."
            )
            detail_color = _COLORS["green"]
        detail = make_label(self.body, detail_text, bold=True)
        detail.configure(foreground=detail_color)
        detail.pack(fill="x", anchor="w", pady=(2, 0))

        make_label(self.body, f"Report: {result.report_path}").pack(fill="x", anchor="w", pady=(2, 6))

        try:
            report_text = open(result.report_path, encoding="utf-8").read()
        except OSError as exc:
            report_text = f"Could not read report file:\n{exc}"

        viewer_frame = ttk.Frame(self.body)
        viewer_frame.pack(fill="both", expand=True)
        self.viewer = tk.Text(
            viewer_frame,
            wrap="none",
            font=("Consolas", 10),
            background="#FFFFFF",
            foreground=_COLORS["base"],
        )
        yscroll = ttk.Scrollbar(viewer_frame, orient="vertical", command=self.viewer.yview)
        xscroll = ttk.Scrollbar(viewer_frame, orient="horizontal", command=self.viewer.xview)
        self.viewer.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self.viewer.pack(side="left", fill="both", expand=True)
        self._render_report(report_text)

        # One checkbox per warning line, not one for the whole report. A
        # single "I reviewed this" box let a five-line report and a
        # fifty-line one take the same one click - F59270 Pump House was one
        # of the lines that click skipped past. Ticking each line by hand is
        # deliberately slower than reading a summary count.
        self.line_vars: list[tk.BooleanVar] = []
        self._line_labels: list[str] = []
        warning_lines = self._warning_lines(report_text)
        if warning_lines:
            make_label(
                self.body,
                "Check off every item below - each one, not just the box underneath:",
                bold=True,
            ).pack(fill="x", anchor="w", pady=(8, 2))

            list_holder = ttk.Frame(self.body)
            list_holder.pack(fill="x")
            canvas = tk.Canvas(list_holder, height=min(200, 28 * len(warning_lines)))
            scroll = ttk.Scrollbar(list_holder, orient="vertical", command=canvas.yview)
            inner = ttk.Frame(canvas)
            inner.bind(
                "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            canvas.pack(side="left", fill="x", expand=True)

            for level, line in warning_lines:
                var = tk.BooleanVar(master=self.window, value=False)
                box = tk.Checkbutton(
                    inner,
                    text=line,
                    variable=var,
                    command=self._update_ack_button,
                    foreground=_COLORS[level],
                    activeforeground=_COLORS[level],
                    font=("TkDefaultFont", 9, "bold"),
                    anchor="w",
                    justify="left",
                )
                box.pack(fill="x", anchor="w")
                self.line_vars.append(var)
                self._line_labels.append(line)

        self.ack_var = tk.BooleanVar(master=self.window, value=False)
        tk.Checkbutton(
            self.body,
            text="I have reviewed this report and understand any warnings before production.",
            variable=self.ack_var,
            command=self._update_ack_button,
            anchor="w",
            justify="left",
        ).pack(fill="x", anchor="w", pady=(6, 0))

        btn_row = ttk.Frame(self.body)
        btn_row.pack(fill="x", pady=(10, 0))
        ttk.Button(btn_row, text="Open Report File", command=self.open_report).pack(
            side="left", expand=True, fill="x", padx=(0, 4)
        )
        ttk.Button(btn_row, text="Discard CSV/Report", command=self.reject).pack(
            side="left", expand=True, fill="x", padx=4
        )
        self.btn_ack = ttk.Button(
            btn_row, text="Acknowledge Report", command=self.accept, state="disabled"
        )
        self.btn_ack.pack(side="left", expand=True, fill="x", padx=(4, 0))

        self.window.geometry("920x680")

    def _render_report(self, report_text: str) -> None:
        for name, color in _COLORS.items():
            self.viewer.tag_configure(name, foreground=color)
            self.viewer.tag_configure(
                name + "_bold", foreground=color, font=("Consolas", 10, "bold")
            )

        active_level = ""
        for line in report_text.splitlines():
            stripped = line.strip()
            if stripped.endswith(":"):
                active_level = ""
                for section, level in self.REVIEW_SECTION_LEVELS.items():
                    if stripped.startswith(section):
                        active_level = level
                        break
                tag = (active_level + "_bold") if active_level else "base_bold"
            elif stripped == "(none)" and active_level:
                tag = "green_bold"
            elif stripped and active_level:
                tag = active_level + "_bold"
            elif stripped:
                tag = "base"
            else:
                tag = "muted"
            self.viewer.insert("end", line + "\n", tag)
        self.viewer.configure(state="disabled")

    @classmethod
    def _warning_lines(cls, report_text: str) -> list[tuple[str, str]]:
        """(level, line) for every red/yellow item in the report - the
        individual things that need their own checkbox, not the section
        header above them or a "(none)" that has nothing to acknowledge."""
        active_level = ""
        lines: list[tuple[str, str]] = []
        for line in report_text.splitlines():
            stripped = line.strip()
            if stripped.endswith(":"):
                active_level = ""
                for section, level in cls.REVIEW_SECTION_LEVELS.items():
                    if stripped.startswith(section):
                        active_level = level
                        break
                continue
            if not stripped or stripped == "(none)":
                continue
            if active_level in ("red", "yellow"):
                lines.append((active_level, stripped))
        return lines

    # ---- behaviour accessors
    #
    # The review gate is the app's most load-bearing UI rule (see the F59270
    # Pump House regression), so it is tested directly. These keep those tests
    # about the rule - which lines need a tick, when the button unlocks -
    # rather than about whichever toolkit is drawing it this year.

    def checklist_labels(self) -> list[str]:
        return list(self._line_labels)

    def set_line_checked(self, index: int, checked: bool = True) -> None:
        self.line_vars[index].set(checked)
        self._update_ack_button()

    def set_acknowledged(self, checked: bool = True) -> None:
        self.ack_var.set(checked)
        self._update_ack_button()

    def ack_enabled(self) -> bool:
        return str(self.btn_ack.cget("state")) == "normal"

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()

    def _update_ack_button(self):
        all_lines_checked = all(var.get() for var in self.line_vars)
        state = "normal" if (self.ack_var.get() and all_lines_checked) else "disabled"
        self.btn_ack.configure(state=state)

    def open_report(self):
        try:
            os.startfile(self.result.report_path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showwarning("Open Report", str(exc), parent=self.window)

    def accept(self):
        unchecked = sum(1 for var in self.line_vars if not var.get())
        if unchecked or not self.ack_var.get():
            detail = f"{unchecked} item(s) above are still unchecked. " if unchecked else ""
            messagebox.showwarning(
                "Review Required",
                f"{detail}Check off every item and the acknowledgement box before continuing.",
                parent=self.window,
            )
            return
        self._acknowledged = True
        super().accept()

    def reject(self):
        if not self._acknowledged:
            if not messagebox.askyesno(
                "Discard Inventor Output?",
                "Close without acknowledging this report?\n\n"
                "The generated RADAN CSV and report will be deleted.",
                default="no",
                parent=self.window,
            ):
                return
        super().reject()

    def on_close(self):
        self.reject()
