from __future__ import annotations

import csv
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import inventor_to_radan

TEST_TMP_ROOT = PROJECT_DIR / "_tmp_tests"


class InventorToRadanTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp_dir = TEST_TMP_ROOT / uuid.uuid4().hex
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def patch_config_paths(self):
        return patch.multiple(
            inventor_to_radan,
            RULES_CSV=str(self.config_dir / "description_rules.csv"),
            FTQ_CSV=str(self.config_dir / "ftq_parts.csv"),
            NONLASER_TOKENS_CSV=str(self.config_dir / "nonlaser_tokens.csv"),
            EXPECTED_LASER_DESC_CSV=str(self.config_dir / "expected_laser_descriptions.csv"),
            LASER_MATERIALS_CSV=str(self.config_dir / "laser_materials.csv"),
        )

    def write_bom(self, rows: list[list[str]]) -> Path:
        bom_path = self.temp_dir / "kit-bom.csv"
        with bom_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Part Number", "Description", "Qty", "Material"])
            writer.writerows(rows)
        return bom_path

    def test_convert_bom_to_radan_csv_runs_without_ui_when_rules_exist(self) -> None:
        bom_path = self.write_bom([["ABC-001", "LASER PANEL", "2", "ALUMINUM"]])
        (self.temp_dir / "ABC-001.dxf").write_text("dxf", encoding="utf-8")
        (self.config_dir / "description_rules.csv").write_text(
            "Description,Material,Thickness,Strategy\n"
            "LASER PANEL,Aluminum 3003,0.125,Default\n",
            encoding="utf-8",
        )

        with self.patch_config_paths():
            result = inventor_to_radan.convert_bom_to_radan_csv(
                str(bom_path),
                allow_prompts=False,
                show_summary=False,
            )

        self.assertEqual(result.added_count, 1)
        self.assertEqual(Path(result.out_path), self.temp_dir / "kit-bom_Radan.csv")
        self.assertEqual(Path(result.report_path), self.temp_dir / "kit-bom_report.txt")
        self.assertEqual(
            (self.temp_dir / "kit-bom_Radan.csv").read_text(encoding="utf-8").strip(),
            f"{self.temp_dir / 'ABC-001.dxf'},2,Aluminum 3003,0.125,in,Default",
        )

    def test_convert_bom_to_radan_csv_reports_missing_rules_without_ui(self) -> None:
        bom_path = self.write_bom([["ABC-002", "NEW LASER PANEL", "1", "ALUMINUM"]])
        (self.temp_dir / "ABC-002.dxf").write_text("dxf", encoding="utf-8")

        with self.patch_config_paths():
            with self.assertRaises(inventor_to_radan.InventorToRadanNeedsUi) as raised:
                inventor_to_radan.convert_bom_to_radan_csv(
                    str(bom_path),
                    allow_prompts=False,
                    show_summary=False,
                )

        self.assertEqual(raised.exception.missing_rules, ["NEW LASER PANEL"])
        self.assertEqual(raised.exception.missing_dxf_items, [])


if __name__ == "__main__":
    unittest.main()
