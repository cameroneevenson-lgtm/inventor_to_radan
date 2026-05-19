from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
)

from dialogs.missing_dxf_dialog import make_label


class RadanRuleDialog(QDialog):
    """
    Step through missing RADAN rules (for descriptions that DO have DXFs).
    Writes immediately to description_rules.csv on each Save.
    """
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
        self.setWindowTitle("Define RADAN Rule (by Description)")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        self.descs = descs
        self.ftq_descs = ftq_descs
        self.i = 0

        self.lbl_progress = make_label("")
        self.lbl_desc = make_label("", bold=True)

        self.inp_mat = QLineEdit()
        self.inp_thk = QLineEdit()
        self.inp_strat = QLineEdit()

        self.lbl_mat = make_label("Material:")
        self.lbl_thk = make_label("Thickness:")
        self.lbl_strat = make_label("Strategy:")

        form = QVBoxLayout()
        row1 = QHBoxLayout(); row1.addWidget(self.lbl_mat); row1.addWidget(self.inp_mat)
        row2 = QHBoxLayout(); row2.addWidget(self.lbl_thk); row2.addWidget(self.inp_thk)
        row3 = QHBoxLayout(); row3.addWidget(self.lbl_strat); row3.addWidget(self.inp_strat)
        form.addLayout(row1); form.addLayout(row2); form.addLayout(row3)

        self.btn_save = QPushButton("Save & Next")
        self.btn_save.clicked.connect(self.save_next)

        lay = QVBoxLayout()
        lay.addWidget(self.lbl_progress)
        lay.addWidget(self.lbl_desc)
        lay.addSpacing(8)
        lay.addLayout(form)
        lay.addItem(QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        lay.addWidget(self.btn_save)
        self.setLayout(lay)

        self.resize(640, 360)
        self.load_step()

    def load_step(self):
        desc = self.descs[self.i]
        self.lbl_progress.setText(f"{self.i+1} of {len(self.descs)}")
        self.lbl_desc.setText(f"Description:\n{desc}")

        self.inp_mat.setText("")
        self.inp_thk.setText("")
        self.inp_strat.setText("")

        if desc in self.ftq_descs:
            self.inp_mat.setText("Aluminum 3003 CHK FTQ")
            self.inp_mat.setEnabled(False)
        else:
            self.inp_mat.setEnabled(True)

    def save_next(self):
        desc = self.descs[self.i]
        mat = self.inp_mat.text().strip()
        thk = self.inp_thk.text().strip()
        strat = self.inp_strat.text().strip()

        if not mat or not thk or not strat:
            QMessageBox.critical(self, "Missing data", "Material, Thickness, and Strategy are all required.")
            return

        self._append_rule(desc, mat, thk, strat)

        self.i += 1
        if self.i >= len(self.descs):
            self.accept()
        else:
            self.load_step()
