from __future__ import annotations

import html
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dialogs.missing_dxf_dialog import make_label


class ReportReviewDialog(QDialog):
    REVIEW_SECTION_LEVELS = {
        "Expected laser but missing DXF": "red",
        "Orphan DXFs": "yellow",
        "DXFs missing PDFs": "yellow",
        "Non-laser parts": "yellow",
    }

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self._acknowledged = False
        self.setWindowTitle("Review Inventor-to-RADAN Report")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        title = make_label("Review required before production use", bold=True)
        warning_count = (
            len(result.expected_missing_dxfs)
            + len(result.orphan_dxfs)
            + len(result.missing_pdfs)
            + len(result.nonlaser_parts)
        )
        critical_count = len(result.expected_missing_dxfs)
        if critical_count:
            detail_text = (
                f"This report contains {critical_count} critical item(s) and "
                f"{warning_count - critical_count} review item(s). "
                "Read the report below before acknowledging completion."
            )
            detail_style = "color: #B91C1C;"
        elif warning_count:
            detail_text = (
                f"This report contains {warning_count} item(s) to check. "
                "Read the yellow sections below before acknowledging completion."
            )
            detail_style = "color: #A16207;"
        else:
            detail_text = (
                "No report warnings were found. Review the green confirmation sections before closing this conversion."
            )
            detail_style = "color: #15803D;"
        detail = make_label(detail_text, bold=True)
        detail.setStyleSheet(detail_style)

        path_label = make_label(f"Report: {result.report_path}")

        self.viewer = QTextEdit()
        self.viewer.setReadOnly(True)
        self.viewer.setLineWrapMode(QTextEdit.NoWrap)
        try:
            report_text = open(result.report_path, encoding="utf-8").read()
        except OSError as exc:
            report_text = f"Could not read report file:\n{exc}"
        self.viewer.setHtml(self._report_html(report_text))

        # One checkbox per warning line, not one for the whole report. A
        # single "I reviewed this" box let a five-line report and a
        # fifty-line one take the same one click - F59270 Pump House was one
        # of the lines that click skipped past. Ticking each line by hand is
        # deliberately slower than reading a summary count.
        self.line_checkboxes: list[QCheckBox] = []
        checklist_layout = QVBoxLayout()
        checklist_colors = {"red": "#B91C1C", "yellow": "#A16207"}
        for level, line in self._warning_lines(report_text):
            checkbox = QCheckBox(line)
            checkbox.setStyleSheet(f"color: {checklist_colors[level]}; font-weight: 700;")
            checkbox.stateChanged.connect(self._update_ack_button)
            checklist_layout.addWidget(checkbox)
            self.line_checkboxes.append(checkbox)

        checklist_widget = QWidget()
        checklist_widget.setLayout(checklist_layout)
        checklist_scroll = QScrollArea()
        checklist_scroll.setWidget(checklist_widget)
        checklist_scroll.setWidgetResizable(True)
        checklist_scroll.setMaximumHeight(200)

        self.chk_ack = QCheckBox("I have reviewed this report and understand any warnings before production.")
        self.chk_ack.stateChanged.connect(self._update_ack_button)

        self.btn_open = QPushButton("Open Report File")
        self.btn_open.clicked.connect(self.open_report)
        self.btn_ack = QPushButton("Acknowledge Report")
        self.btn_ack.setEnabled(False)
        self.btn_ack.clicked.connect(self.accept)
        self.btn_discard = QPushButton("Discard CSV/Report")
        self.btn_discard.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_open)
        btn_row.addWidget(self.btn_discard)
        btn_row.addWidget(self.btn_ack)

        lay = QVBoxLayout()
        lay.addWidget(title)
        lay.addWidget(detail)
        lay.addWidget(path_label)
        lay.addWidget(self.viewer, 1)
        if self.line_checkboxes:
            lay.addWidget(make_label("Check off every item below - each one, not just the box underneath:", bold=True))
            lay.addWidget(checklist_scroll)
        lay.addWidget(self.chk_ack)
        lay.addLayout(btn_row)
        self.setLayout(lay)
        self.resize(920, 680)

    @classmethod
    def _report_html(cls, report_text: str) -> str:
        colors = {
            "base": "#111827",
            "muted": "#475569",
            "green": "#15803D",
            "yellow": "#A16207",
            "red": "#B91C1C",
        }
        active_level = ""
        rows: list[str] = []
        for line in report_text.splitlines():
            stripped = line.strip()
            if stripped.endswith(":"):
                active_level = ""
                for section, level in cls.REVIEW_SECTION_LEVELS.items():
                    if stripped.startswith(section):
                        active_level = level
                        break
                color = colors.get(active_level, colors["base"])
                weight = "700" if active_level else "600"
            elif stripped == "(none)" and active_level:
                color = colors["green"]
                weight = "700"
            elif stripped and active_level:
                color = colors[active_level]
                weight = "700"
            elif stripped:
                color = colors["base"]
                weight = "400"
            else:
                color = colors["muted"]
                weight = "400"
            rows.append(
                "<div style='white-space: pre-wrap; "
                f"color: {color}; font-weight: {weight};'>"
                f"{html.escape(line) or '&nbsp;'}</div>"
            )
        body = "\n".join(rows)
        return (
            "<html><body style='font-family: Consolas, monospace; "
            "font-size: 10pt; background: #FFFFFF;'>"
            f"{body}</body></html>"
        )

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

    def _update_ack_button(self):
        all_lines_checked = all(cb.isChecked() for cb in self.line_checkboxes)
        self.btn_ack.setEnabled(self.chk_ack.isChecked() and all_lines_checked)

    def open_report(self):
        try:
            os.startfile(self.result.report_path)  # type: ignore[attr-defined]
        except Exception as exc:
            QMessageBox.warning(self, "Open Report", str(exc))

    def accept(self):
        unchecked = sum(1 for cb in self.line_checkboxes if not cb.isChecked())
        if unchecked or not self.chk_ack.isChecked():
            detail = f"{unchecked} item(s) above are still unchecked. " if unchecked else ""
            QMessageBox.warning(
                self,
                "Review Required",
                f"{detail}Check off every item and the acknowledgement box before continuing.",
            )
            return
        self._acknowledged = True
        super().accept()

    def reject(self):
        if not self._acknowledged:
            choice = QMessageBox.question(
                self,
                "Discard Inventor Output?",
                "Close without acknowledging this report?\n\n"
                "The generated RADAN CSV and report will be deleted.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                return
            super().reject()
            return
        super().reject()

    def closeEvent(self, event):
        if self._acknowledged:
            event.accept()
            return
        choice = QMessageBox.question(
            self,
            "Discard Inventor Output?",
            "Close without acknowledging this report?\n\n"
            "The generated RADAN CSV and report will be deleted.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if choice == QMessageBox.Yes:
            event.accept()
            return
        event.ignore()
