from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import bom_converter
import inline_runner

class InventorToRadanTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_context = tempfile.TemporaryDirectory(prefix="inventor_to_radan_")
        self.temp_dir = Path(self._temp_context.name)
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir()

    def tearDown(self) -> None:
        self._temp_context.cleanup()

    def patch_config_paths(self):
        return patch.multiple(
            bom_converter,
            RULES_CSV=str(self.config_dir / "description_rules.csv"),
            FTQ_CSV=str(self.config_dir / "ftq_parts.csv"),
            NONLASER_TOKENS_CSV=str(self.config_dir / "nonlaser_tokens.csv"),
        )

    def write_bom(self, rows: list[list[str]]) -> Path:
        bom_path = self.temp_dir / "kit-bom.csv"
        with bom_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Part Number", "Description", "Qty"])
            writer.writerows(rows)
        return bom_path

    def test_convert_bom_to_radan_csv_runs_without_ui_when_rules_exist(self) -> None:
        bom_path = self.write_bom([["ABC-001", "LASER PANEL", "2"]])
        (self.temp_dir / "ABC-001.dxf").write_text("dxf", encoding="utf-8")
        (self.config_dir / "description_rules.csv").write_text(
            "Description,Material,Thickness,Strategy\n"
            "LASER PANEL,Aluminum 3003,0.125,Default\n",
            encoding="utf-8",
        )

        with self.patch_config_paths():
            result = bom_converter.convert_bom_to_radan_csv(
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
        bom_path = self.write_bom([["ABC-002", "NEW LASER PANEL", "1"]])
        (self.temp_dir / "ABC-002.dxf").write_text("dxf", encoding="utf-8")

        with self.patch_config_paths():
            with self.assertRaises(bom_converter.InventorToRadanNeedsUi) as raised:
                bom_converter.convert_bom_to_radan_csv(
                    str(bom_path),
                    allow_prompts=False,
                    show_summary=False,
                )

        self.assertEqual(raised.exception.missing_rules, ["NEW LASER PANEL"])
        self.assertEqual(raised.exception.missing_dxf_items, [])

    def test_expected_missing_dxf_uses_description_rules_column_a(self) -> None:
        bom_path = self.write_bom([["ABC-003", "KNOWN LASER PANEL", "1"]])
        (self.config_dir / "description_rules.csv").write_text(
            "Description,Material,Thickness,Strategy\n"
            "KNOWN LASER PANEL,Aluminum 5052,0.125,Air\n",
            encoding="utf-8",
        )

        with self.patch_config_paths():
            result = bom_converter.convert_bom_to_radan_csv(
                str(bom_path),
                allow_prompts=False,
                show_summary=False,
            )

        self.assertEqual(result.expected_missing_dxfs, ("ABC-003.dxf",))
        self.assertFalse((self.config_dir / "expected_laser_descriptions.csv").exists())
        self.assertFalse((self.config_dir / "laser_materials.csv").exists())

    def test_interactive_expected_laser_choice_creates_complete_rule(self) -> None:
        bom_path = self.write_bom([["ABC-004", "NEW MISSING LASER PANEL", "1"]])

        class AcceptExpectedDialog:
            def __init__(self, items):
                self.expected_descriptions = [item["desc"] for item in items]

            def exec(self):
                return bom_converter.QDialog.Accepted

        class AcceptRuleDialog:
            def __init__(self, descriptions, ftq_descriptions):
                self.descriptions = descriptions

            def exec(self):
                for description in self.descriptions:
                    bom_converter.append_rule(description, "Aluminum 5052", "0.125", "Air")
                return bom_converter.QDialog.Accepted

        with (
            self.patch_config_paths(),
            patch.object(bom_converter, "MissingDxfDialog", AcceptExpectedDialog),
            patch.object(bom_converter, "RadanRuleDialog", AcceptRuleDialog),
        ):
            result = bom_converter.convert_bom_to_radan_csv(
                str(bom_path),
                allow_prompts=True,
                show_summary=False,
            )

        self.assertEqual(result.expected_missing_dxfs, ("ABC-004.dxf",))
        with (self.config_dir / "description_rules.csv").open(newline="", encoding="utf-8") as handle:
            rules = list(csv.DictReader(handle))
        self.assertEqual(
            rules,
            [{
                "Description": "NEW MISSING LASER PANEL",
                "Material": "Aluminum 5052",
                "Thickness": "0.125",
                "Strategy": "Air",
            }],
        )

    def test_inline_runner_loads_sibling_modules_with_foreign_dialogs_loaded(self) -> None:
        saved_path = list(sys.path)
        saved_modules = {
            name: sys.modules[name]
            for name in list(sys.modules)
            if name in inline_runner.INLINE_IMPORT_NAMES or name.startswith("dialogs.")
        }
        try:
            for name in saved_modules:
                sys.modules.pop(name, None)

            foreign_root = self.temp_dir / "foreign"
            foreign_dialogs = foreign_root / "dialogs"
            foreign_dialogs.mkdir(parents=True)
            (foreign_dialogs / "__init__.py").write_text("ORIGIN = 'foreign'\n", encoding="utf-8")
            sys.path.insert(0, str(foreign_root))
            foreign_module = __import__("dialogs")
            self.assertEqual(foreign_module.ORIGIN, "foreign")

            tool_dir = self.temp_dir / "tool"
            tool_dialogs = tool_dir / "dialogs"
            tool_dialogs.mkdir(parents=True)
            spreadsheet = self.temp_dir / "bom.csv"
            spreadsheet.write_text("Part Number,Description,Qty\n", encoding="utf-8")
            (tool_dir / "bom_reader.py").write_text("ADDED_COUNT = 7\n", encoding="utf-8")
            (tool_dialogs / "__init__.py").write_text("", encoding="utf-8")
            (tool_dialogs / "missing_dxf_dialog.py").write_text("VALUE = 'inventor'\n", encoding="utf-8")
            entry = tool_dir / "bom_converter.py"
            entry.write_text(
                "import bom_reader\n"
                "from dialogs.missing_dxf_dialog import VALUE\n"
                "from types import SimpleNamespace\n"
                "def convert_bom_to_radan_csv(path, *, allow_prompts, show_summary):\n"
                "    if allow_prompts or show_summary:\n"
                "        raise AssertionError('inline mode should not prompt')\n"
                "    return SimpleNamespace(added_count=bom_reader.ADDED_COUNT, dialog_value=VALUE, bom_path=path)\n",
                encoding="utf-8",
            )

            result = inline_runner.run_inline(entry, spreadsheet, allow_prompts=False, show_summary=False)

            self.assertEqual(result.added_count, 7)
            self.assertEqual(result.dialog_value, "inventor")
            self.assertEqual(result.bom_path, str(spreadsheet))
            self.assertIs(sys.modules.get("dialogs"), foreign_module)
            self.assertNotIn("dialogs.missing_dxf_dialog", sys.modules)
        finally:
            sys.path[:] = saved_path
            for name in [name for name in sys.modules if name in inline_runner.INLINE_IMPORT_NAMES or name.startswith("dialogs.")]:
                sys.modules.pop(name, None)
            sys.modules.update(saved_modules)

    def test_inventor_module_loads_from_spec_without_project_on_sys_path(self) -> None:
        saved_path = list(sys.path)
        saved_modules = {
            name: sys.modules[name]
            for name in list(sys.modules)
            if name in inline_runner.INLINE_IMPORT_NAMES or name.startswith("dialogs.")
        }
        module_name = "_inventor_to_radan_spec_probe"
        saved_probe = sys.modules.get(module_name)

        def is_project_path(path_text: str) -> bool:
            try:
                candidate = Path(path_text or ".").resolve()
            except OSError:
                return False
            return candidate == PROJECT_DIR.resolve()

        try:
            sys.path[:] = [path for path in sys.path if not is_project_path(path)]
            for name in saved_modules:
                sys.modules.pop(name, None)
            sys.modules.pop(module_name, None)

            spec = importlib.util.spec_from_file_location(module_name, PROJECT_DIR / "bom_converter.py")
            self.assertIsNotNone(spec)
            assert spec is not None
            self.assertIsNotNone(spec.loader)
            assert spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            self.assertTrue(callable(getattr(module, "convert_bom_to_radan_csv", None)))
        finally:
            sys.path[:] = saved_path
            for name in [name for name in sys.modules if name in inline_runner.INLINE_IMPORT_NAMES or name.startswith("dialogs.")]:
                sys.modules.pop(name, None)
            sys.modules.update(saved_modules)
            if saved_probe is not None:
                sys.modules[module_name] = saved_probe
            else:
                sys.modules.pop(module_name, None)


class MissingDependencyTests(unittest.TestCase):
    """This module is a library as well as a drag-and-drop CLI.

    A missing package used to be reported with print + sys.exit(1) at import
    time. SystemExit does not inherit from Exception, so it went straight
    through odd_job_intake's `except Exception` around the conversion and took
    that process down before it could say anything about which BOM failed.
    """

    def test_a_missing_package_raises_for_a_library_caller(self) -> None:
        with self.assertRaises(bom_converter.MissingDependencyError) as caught:
            bom_converter._missing("pandas", "pandas", ImportError("boom"))
        message = str(caught.exception)
        self.assertIn("pandas is not installed", message)
        # Still tells them how to fix it.
        self.assertIn("pip install pandas", message)

    def test_it_is_catchable_as_an_ordinary_exception(self) -> None:
        """The property that was missing. `except Exception` must see it."""
        try:
            bom_converter._missing("PySide6", "pyside6", ImportError("boom"))
        except Exception as exc:
            self.assertIsInstance(exc, ImportError)
        else:
            self.fail("nothing was raised")

    def test_run_directly_it_still_exits_with_the_install_line(self) -> None:
        """Someone dragging a BOM onto the script wants the one-line fix and a
        non-zero exit, not a traceback."""
        with patch.object(bom_converter, "__name__", "__main__"):
            with self.assertRaises(SystemExit) as caught:
                bom_converter._missing("pandas", "pandas", ImportError("boom"))
        self.assertEqual(caught.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
