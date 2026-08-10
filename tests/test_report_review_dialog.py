from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from PySide6.QtWidgets import QApplication

from dialogs.report_review_dialog import ReportReviewDialog


@dataclass(frozen=True)
class _FakeResult:
    report_path: str
    expected_missing_dxfs: tuple[str, ...] = ()
    orphan_dxfs: tuple[str, ...] = ()
    missing_pdfs: tuple[str, ...] = ()
    nonlaser_parts: tuple[str, ...] = ()


class ReportReviewDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_warning_lines_skips_headers_and_none(self) -> None:
        report_text = (
            "Expected laser but missing DXF (likely deleted / missing):\n"
            "  8500-F55985-11.dxf\n"
            "\n"
            "Orphan DXFs (in folder but not referenced by BOM):\n"
            "  8500-f55900-11.dxf\n"
            "\n"
            "DXFs missing PDFs:\n"
            "  (none)\n"
            "\n"
            "Non-laser parts (no DXF; token-classified):\n"
            "  (none)\n"
        )
        self.assertEqual(
            ReportReviewDialog._warning_lines(report_text),
            [
                ("red", "8500-F55985-11.dxf"),
                ("yellow", "8500-f55900-11.dxf"),
            ],
        )

    def test_ack_button_requires_every_line_checked(self) -> None:
        """Regression for F59270 Pump House: a single blanket checkbox let a
        report with real warnings get acknowledged without reading them.
        Every red/yellow line now needs its own tick before the button
        enables, and each one is independent - checking one must not enable
        the others."""
        report_text = (
            "Expected laser but missing DXF (likely deleted / missing):\n"
            "  8500-F55985-11.dxf\n"
            "\n"
            "Orphan DXFs (in folder but not referenced by BOM):\n"
            "  8500-f55900-11.dxf\n"
        )
        report_path = Path(self.id().replace(".", "_") + "_report.txt").resolve()
        report_path.write_text(report_text, encoding="utf-8")
        self.addCleanup(report_path.unlink, missing_ok=True)

        result = _FakeResult(
            report_path=str(report_path),
            expected_missing_dxfs=("8500-F55985-11.dxf",),
            orphan_dxfs=("8500-f55900-11.dxf",),
        )
        dialog = ReportReviewDialog(result)
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(len(dialog.line_checkboxes), 2)
        self.assertFalse(dialog.btn_ack.isEnabled())

        dialog.chk_ack.setChecked(True)
        self.assertFalse(dialog.btn_ack.isEnabled(), "still missing per-line acks")

        dialog.line_checkboxes[0].setChecked(True)
        self.assertFalse(dialog.btn_ack.isEnabled(), "one of two lines is not enough")

        dialog.line_checkboxes[1].setChecked(True)
        self.assertTrue(dialog.btn_ack.isEnabled())

        dialog.line_checkboxes[0].setChecked(False)
        self.assertFalse(dialog.btn_ack.isEnabled(), "unchecking a line must disable it again")

    def test_no_warnings_means_no_line_checkboxes(self) -> None:
        report_text = (
            "Expected laser but missing DXF (likely deleted / missing):\n"
            "  (none)\n"
            "\n"
            "Orphan DXFs (in folder but not referenced by BOM):\n"
            "  (none)\n"
        )
        report_path = Path(self.id().replace(".", "_") + "_report.txt").resolve()
        report_path.write_text(report_text, encoding="utf-8")
        self.addCleanup(report_path.unlink, missing_ok=True)

        result = _FakeResult(report_path=str(report_path))
        dialog = ReportReviewDialog(result)
        self.addCleanup(dialog.deleteLater)

        self.assertEqual(dialog.line_checkboxes, [])
        dialog.chk_ack.setChecked(True)
        self.assertTrue(dialog.btn_ack.isEnabled())


if __name__ == "__main__":
    unittest.main()
