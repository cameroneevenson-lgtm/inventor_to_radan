from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class BomPickerDialog(QDialog):
    """Front door for the frozen verification build.

    The .bat launcher takes its BOM by drag-and-drop, but an exe handed to a
    designer is opened from a shortcut with no argument at all, so it has to
    ask. Staying open after a run matters: checking a BOM, fixing what the
    report flagged and checking it again is the normal loop, and relaunching
    a 170 MB exe for each pass is not.
    """

    def __init__(self, data_dir: str, parent=None):
        super().__init__(parent)
        self.selected_path: str | None = None
        self.setWindowTitle("Verify Inventor BOM")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Check an Inventor BOM for missing DXFs and unknown descriptions.\n"
            "Writes a report next to the BOM. No RADAN CSV is produced."
        ))

        self.status = QLabel("No BOM selected.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        rules = QLabel(f"Rule tables: {data_dir}")
        rules.setWordWrap(True)
        layout.addWidget(rules)

        buttons = QHBoxLayout()
        select = QPushButton("Select BOM...")
        select.setDefault(True)
        select.clicked.connect(self.choose_bom)
        buttons.addWidget(select)

        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def choose_bom(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select an Inventor BOM",
            "",
            "BOM files (*.csv *.xlsx);;All files (*)",
        )
        if not path:
            return
        self.selected_path = path
        self.accept()

    def report_outcome(self, message: str) -> None:
        self.status.setText(message)
        self.selected_path = None


def pick_bom(data_dir: str, last_message: str = "") -> str | None:
    """Show the picker and return the chosen BOM, or None if they closed it."""
    dialog = BomPickerDialog(data_dir)
    if last_message:
        dialog.status.setText(last_message)
    if dialog.exec() != QDialog.Accepted:
        return None
    return dialog.selected_path
