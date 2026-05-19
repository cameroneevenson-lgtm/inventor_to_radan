from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
)


def make_label(text: str, bold=False, wrap=True) -> QLabel:
    lab = QLabel(text)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    if wrap:
        lab.setWordWrap(True)
    if bold:
        f = lab.font()
        f.setBold(True)
        lab.setFont(f)
    return lab


class MissingDxfDialog(QDialog):
    """
    Step through UNKNOWN missing-DXF descriptions and force a classification:
      - Non-Laser: store FIRST TOKEN to nonlaser_tokens.csv
      - Expected Laser: store FULL DESCRIPTION to expected_laser_descriptions.csv (+ optionally add material to laser_materials.csv)
    Writes immediately to disk on each click.

    Sanity feature: shows current Non-Laser token list from disk inside the dialog.
    """
    def __init__(
        self,
        items: list[dict],
        *,
        nonlaser_tokens_csv: str,
        expected_laser_desc_csv: str,
        laser_materials_csv: str,
        load_set: Callable[[str, str], set[str]],
        append_unique: Callable[[str, list[str], list[str]], None],
        parent=None,
    ):
        super().__init__(parent)
        self.nonlaser_tokens_csv = nonlaser_tokens_csv
        self.expected_laser_desc_csv = expected_laser_desc_csv
        self.laser_materials_csv = laser_materials_csv
        self._load_set = load_set
        self._append_unique = append_unique
        self.setWindowTitle("DXF Accountability: Missing DXF Classification")
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)

        self.items = items
        self.i = 0

        self.lbl_progress = make_label("")
        self.lbl_desc = make_label("", bold=True)
        self.lbl_token = make_label("")
        self.lbl_mat = make_label("")
        self.lbl_count = make_label("")

        note = (
            "No DXF exists for this BOM entry.\n\n"
            "• Mark as Non-Laser → stores FIRST TOKEN only (family-level) in nonlaser_tokens.csv\n"
            "• Expected Laser → stores FULL DESCRIPTION (exact) in expected_laser_descriptions.csv\n"
            "   and will be listed as an expected missing DXF in the final report.\n"
        )
        self.lbl_note = make_label(note)

        self.chk_add_mat = QCheckBox("Also add this Material to known LASER materials (helps future missing-DXF checks)")
        self.chk_add_mat.setChecked(False)

        self.lbl_nonlaser_title = make_label("Current Non-Laser token list (from disk):", bold=True)
        self.lbl_nonlaser_list = make_label("", wrap=True)
        self.lbl_nonlaser_list.setMinimumHeight(90)

        self.btn_nonlaser = QPushButton("Mark as Non-Laser")
        self.btn_expected = QPushButton("Expected Laser (DXF missing)")

        self.btn_nonlaser.clicked.connect(self.choose_nonlaser)
        self.btn_expected.clicked.connect(self.choose_expected)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_nonlaser)
        btn_row.addWidget(self.btn_expected)

        lay = QVBoxLayout()
        lay.addWidget(self.lbl_progress)
        lay.addWidget(self.lbl_desc)
        lay.addWidget(self.lbl_token)
        lay.addWidget(self.lbl_mat)
        lay.addWidget(self.lbl_count)
        lay.addSpacing(8)
        lay.addWidget(self.lbl_note)
        lay.addWidget(self.chk_add_mat)
        lay.addSpacing(10)
        lay.addWidget(self.lbl_nonlaser_title)
        lay.addWidget(self.lbl_nonlaser_list)
        lay.addItem(QSpacerItem(10, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        lay.addLayout(btn_row)
        self.setLayout(lay)

        self.resize(760, 620)
        self.load_step()

    def _refresh_nonlaser_list(self):
        toks = sorted(self._load_set(self.nonlaser_tokens_csv, "Token"))
        if not toks:
            self.lbl_nonlaser_list.setText("(none yet)")
            return
        if len(toks) <= 40:
            text = ", ".join(toks)
        else:
            text = ", ".join(toks[:40]) + f" ... (+{len(toks)-40} more)"
        self.lbl_nonlaser_list.setText(text)

    def load_step(self):
        it = self.items[self.i]
        desc = it["desc"]
        tok = it["token"]
        mat = it.get("material", "")
        cnt = it.get("count", 0)

        self.lbl_progress.setText(f"{self.i+1} of {len(self.items)}")
        self.lbl_desc.setText(f"Description (full):\n{desc}")
        self.lbl_token.setText(f"Non-laser family key (first token): {tok if tok else '(blank)'}")
        self.lbl_mat.setText(f"Material (from BOM): {mat if mat else '(blank)'}")
        self.lbl_count.setText(f"Occurrences (missing DXF): {cnt}")

        known_laser_mats = self._load_set(self.laser_materials_csv, "Material")
        if mat and (mat not in known_laser_mats):
            self.chk_add_mat.setEnabled(True)
            self.chk_add_mat.setChecked(True)
        else:
            self.chk_add_mat.setEnabled(False)
            self.chk_add_mat.setChecked(False)

        self._refresh_nonlaser_list()

    def choose_nonlaser(self):
        it = self.items[self.i]
        tok = it["token"]
        if not tok:
            QMessageBox.critical(self, "Missing token", "Cannot classify as non-laser because the first token is blank.")
            return
        self._append_unique(self.nonlaser_tokens_csv, ["Token"], [tok])
        self.next_step()

    def choose_expected(self):
        it = self.items[self.i]
        desc = it["desc"]
        mat = it.get("material", "")

        self._append_unique(self.expected_laser_desc_csv, ["Description"], [desc])
        if mat and self.chk_add_mat.isEnabled() and self.chk_add_mat.isChecked():
            self._append_unique(self.laser_materials_csv, ["Material"], [mat])
        self.next_step()

    def next_step(self):
        self.i += 1
        if self.i >= len(self.items):
            self.accept()
        else:
            self.load_step()
