from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from dialogs.report_review_dialog import ReportReviewDialog
from dialogs.tk_base import ensure_root


@dataclass(frozen=True)
class _FakeResult:
    report_path: str
    expected_missing_dxfs: tuple[str, ...] = ()
    orphan_dxfs: tuple[str, ...] = ()
    missing_pdfs: tuple[str, ...] = ()
    nonlaser_parts: tuple[str, ...] = ()


class ReportReviewDialogTests(unittest.TestCase):
    """These assert the review gate's rule, not its widgets: the dialog exposes
    checklist_labels / set_line_checked / set_acknowledged / ack_enabled so the
    rule survives a change of toolkit, which is exactly what happened when the
    app moved off Qt."""

    @classmethod
    def setUpClass(cls) -> None:
        ensure_root()

    def build(self, report_text: str, **result_kwargs) -> ReportReviewDialog:
        report_path = Path(self.id().replace(".", "_") + "_report.txt").resolve()
        report_path.write_text(report_text, encoding="utf-8")
        self.addCleanup(report_path.unlink, missing_ok=True)

        dialog = ReportReviewDialog(_FakeResult(report_path=str(report_path), **result_kwargs))
        self.addCleanup(dialog.close)
        return dialog

    def test_warning_lines_skips_headers_and_none(self) -> None:
        report_text = (
            "Expected laser but missing DXF:\n"
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

    def test_new_descriptions_need_a_tick(self) -> None:
        """A verification run cannot resolve these itself, so they are a yellow
        item somebody has to see - not a green confirmation."""
        report_text = (
            "New descriptions (laser, but no RADAN rule yet):\n"
            "  TITANIUM SPACE PANEL 9000\n"
        )
        self.assertEqual(
            ReportReviewDialog._warning_lines(report_text),
            [("yellow", "TITANIUM SPACE PANEL 9000")],
        )

    def test_nonlaser_parts_are_not_checkboxes(self) -> None:
        """Token-classified non-laser parts confirm a rule the operator already
        wrote; they are not decisions. A BOM with 18 of them must not put 18
        checkboxes in front of the real warnings."""
        report_text = (
            "Expected laser but missing DXF:\n"
            "  (none)\n"
            "\n"
            "Orphan DXFs (in folder but not referenced by BOM):\n"
            "  8500-f55900-11.dxf\n"
            "\n"
            "Non-laser parts (no DXF; token-classified):\n"
            "  STEEL-1.5x1.5x0.125\n"
            "  UNISTRUT-P1000\n"
        )
        self.assertEqual(
            ReportReviewDialog._warning_lines(report_text),
            [("yellow", "8500-f55900-11.dxf")],
        )

        dialog = self.build(
            report_text,
            orphan_dxfs=("8500-f55900-11.dxf",),
            nonlaser_parts=("STEEL-1.5x1.5x0.125", "UNISTRUT-P1000"),
        )

        self.assertEqual(dialog.checklist_labels(), ["8500-f55900-11.dxf"])

        dialog.set_acknowledged(True)
        dialog.set_line_checked(0, True)
        self.assertTrue(dialog.ack_enabled())

    def test_ack_button_requires_every_line_checked(self) -> None:
        """Regression for F59270 Pump House: a single blanket checkbox let a
        report with real warnings get acknowledged without reading them.
        Every red/yellow line now needs its own tick before the button
        enables, and each one is independent - checking one must not enable
        the others."""
        report_text = (
            "Expected laser but missing DXF:\n"
            "  8500-F55985-11.dxf\n"
            "\n"
            "Orphan DXFs (in folder but not referenced by BOM):\n"
            "  8500-f55900-11.dxf\n"
        )
        dialog = self.build(
            report_text,
            expected_missing_dxfs=("8500-F55985-11.dxf",),
            orphan_dxfs=("8500-f55900-11.dxf",),
        )

        self.assertEqual(len(dialog.checklist_labels()), 2)
        self.assertFalse(dialog.ack_enabled())

        dialog.set_acknowledged(True)
        self.assertFalse(dialog.ack_enabled(), "still missing per-line acks")

        dialog.set_line_checked(0, True)
        self.assertFalse(dialog.ack_enabled(), "one of two lines is not enough")

        dialog.set_line_checked(1, True)
        self.assertTrue(dialog.ack_enabled())

        dialog.set_line_checked(0, False)
        self.assertFalse(dialog.ack_enabled(), "unchecking a line must disable it again")

    def test_no_warnings_means_no_line_checkboxes(self) -> None:
        report_text = (
            "Expected laser but missing DXF:\n"
            "  (none)\n"
            "\n"
            "Orphan DXFs (in folder but not referenced by BOM):\n"
            "  (none)\n"
        )
        dialog = self.build(report_text)

        self.assertEqual(dialog.checklist_labels(), [])
        dialog.set_acknowledged(True)
        self.assertTrue(dialog.ack_enabled())


if __name__ == "__main__":
    unittest.main()
