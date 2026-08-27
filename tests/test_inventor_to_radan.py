from __future__ import annotations

import csv
import importlib.util
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import bom_converter
import bom_finder
import config
import inline_runner
import rule_store

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
            STOCK_CUT_PARTS_CSV=str(self.config_dir / "stock_cut_parts.csv"),
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

    def test_stock_cut_families_are_not_expected_missing_dxfs(self) -> None:
        """Tie-downs are cut to length off a stock strip, so no per-length DXF
        is ever drawn - but they carry an ordinary sheet description, which is
        what put all eight of them in the red missing-DXF section. One
        family row has to cover every length, including ones nobody has cut
        yet."""
        bom_path = self.write_bom([
            ["TIE DOWN-18", "PLATE, AL ALY, .25\" THK, 5052 H32", "2"],
            ["TIE DOWN-28.75", "PLATE, AL ALY, .25\" THK, 5052 H32", "1"],
            ["ABC-005", "PLATE, AL ALY, .25\" THK, 5052 H32", "1"],
        ])
        (self.config_dir / "description_rules.csv").write_text(
            "Description,Material,Thickness,Strategy\n"
            "\"PLATE, AL ALY, .25\"\" THK, 5052 H32\",Aluminum 5052,0.25,Air\n",
            encoding="utf-8",
        )
        (self.config_dir / "stock_cut_parts.csv").write_text(
            "PartFamily\nTIE DOWN\n",
            encoding="utf-8",
        )

        with self.patch_config_paths():
            result = bom_converter.convert_bom_to_radan_csv(
                str(bom_path),
                allow_prompts=False,
                show_summary=False,
            )

        # The real laser part beside them still gets flagged.
        self.assertEqual(result.expected_missing_dxfs, ("ABC-005.dxf",))
        self.assertEqual(result.stock_cut_parts, ("TIE DOWN-18", "TIE DOWN-28.75"))
        report = Path(result.report_path).read_text(encoding="utf-8")
        self.assertIn("Cut to length from stock (no DXF expected):\n  TIE DOWN-18\n", report)

    def test_interactive_expected_laser_choice_creates_complete_rule(self) -> None:
        bom_path = self.write_bom([["ABC-004", "NEW MISSING LASER PANEL", "1"]])

        class AcceptExpectedDialog:
            def __init__(self, items):
                self.expected_descriptions = [item["desc"] for item in items]

            def exec(self):
                return bom_converter.ACCEPTED

        class AcceptRuleDialog:
            def __init__(self, descriptions, ftq_descriptions):
                self.descriptions = descriptions

            def exec(self):
                for description in self.descriptions:
                    bom_converter.append_rule(description, "Aluminum 5052", "0.125", "Air")
                return bom_converter.ACCEPTED

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
            bom_converter._missing("openpyxl", "openpyxl", ImportError("boom"))
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


class SeedingConfigCsvsTests(unittest.TestCase):
    """A pip install cannot keep its rule tables in site-packages - the next
    upgrade replaces that directory - so it reads and writes a per-user
    DATA_DIR seeded from the packaged defaults. Without seeding the operator
    would open the tool to four header-only files instead of the catalog.
    """

    def setUp(self) -> None:
        self._temp_context = tempfile.TemporaryDirectory(prefix="inventor_to_radan_seed_")
        self.temp_dir = Path(self._temp_context.name)
        self.seed_dir = self.temp_dir / "packaged"
        self.data_dir = self.temp_dir / "userdata"
        self.seed_dir.mkdir()
        (self.seed_dir / "description_rules.csv").write_text(
            "Description,Material,Thickness,Strategy\nLASER PANEL,Aluminum 3003,0.125,Default\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._temp_context.cleanup()

    def seeded_data_dir(self):
        return patch.multiple(
            bom_converter,
            DATA_DIR=str(self.data_dir),
            SEED_DIR=str(self.seed_dir),
        )

    def test_a_fresh_data_dir_gets_the_packaged_rules(self) -> None:
        with self.seeded_data_dir():
            bom_converter.ensure_config_csvs()
        seeded = (self.data_dir / "description_rules.csv").read_text(encoding="utf-8")
        self.assertIn("LASER PANEL", seeded)

    def test_seeding_never_overwrites_rules_already_there(self) -> None:
        """The operator's own learned rules outrank the shipped defaults."""
        self.data_dir.mkdir()
        (self.data_dir / "description_rules.csv").write_text(
            "Description,Material,Thickness,Strategy\nTHEIR OWN PANEL,Stainless Steel,0.25,AIR\n",
            encoding="utf-8",
        )
        with self.seeded_data_dir():
            bom_converter.ensure_config_csvs()
        kept = (self.data_dir / "description_rules.csv").read_text(encoding="utf-8")
        self.assertIn("THEIR OWN PANEL", kept)
        self.assertNotIn("LASER PANEL", kept)

    def test_a_checkout_seeds_from_itself_and_is_left_alone(self) -> None:
        """DATA_DIR is SEED_DIR in a clone, where the tables are shared by
        committing them. Copying a file onto itself would truncate it."""
        rules = self.seed_dir / "description_rules.csv"
        before = rules.read_text(encoding="utf-8")
        rule_store.seed_csv(str(rules), str(rules))
        self.assertEqual(rules.read_text(encoding="utf-8"), before)


class VerificationOnlyTests(unittest.TestCase):
    """The frozen exe handed to designers checks a BOM and reports on it. The
    RADAN import CSV is the laser programmer's artifact, so a verification run
    must not leave one behind in the job folder.
    """

    def setUp(self) -> None:
        self._temp_context = tempfile.TemporaryDirectory(prefix="inventor_to_radan_verify_")
        self.temp_dir = Path(self._temp_context.name)
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir()
        (self.config_dir / "description_rules.csv").write_text(
            "Description,Material,Thickness,Strategy\nLASER PANEL,Aluminum 3003,0.125,Default\n",
            encoding="utf-8",
        )
        bom = self.temp_dir / "kit-bom.csv"
        with bom.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Part Number", "Description", "Qty"])
            writer.writerow(["ABC-001", "LASER PANEL", "2"])
        (self.temp_dir / "ABC-001.dxf").write_text("dxf", encoding="utf-8")
        self.bom_path = bom

    def tearDown(self) -> None:
        self._temp_context.cleanup()

    def patch_config_paths(self):
        return patch.multiple(
            bom_converter,
            RULES_CSV=str(self.config_dir / "description_rules.csv"),
            FTQ_CSV=str(self.config_dir / "ftq_parts.csv"),
            NONLASER_TOKENS_CSV=str(self.config_dir / "nonlaser_tokens.csv"),
            STOCK_CUT_PARTS_CSV=str(self.config_dir / "stock_cut_parts.csv"),
        )

    def convert(self, **kwargs):
        with self.patch_config_paths():
            return bom_converter.convert_bom_to_radan_csv(
                str(self.bom_path), allow_prompts=False, show_summary=False, **kwargs
            )

    def test_verification_writes_the_report_but_no_csv(self) -> None:
        result = self.convert(write_csv=False)
        self.assertTrue(Path(result.report_path).exists())
        self.assertFalse((self.temp_dir / "kit-bom_Radan.csv").exists())

    def test_verification_still_counts_the_rows_that_would_export(self) -> None:
        """The report is only useful if the checks still ran."""
        result = self.convert(write_csv=False)
        self.assertEqual(result.added_count, 1)
        self.assertIsNone(result.out_path)

    def test_the_report_does_not_name_a_csv_that_was_never_written(self) -> None:
        result = self.convert(write_csv=False)
        report = Path(result.report_path).read_text(encoding="utf-8")
        self.assertIn("not written (verification only)", report)
        self.assertNotIn("kit-bom_Radan.csv", report)

    def test_the_default_still_writes_the_csv(self) -> None:
        """Verification is opt-in; the laser programmer's path is unchanged."""
        result = self.convert()
        self.assertTrue((self.temp_dir / "kit-bom_Radan.csv").exists())
        self.assertEqual(result.out_path, str(self.temp_dir / "kit-bom_Radan.csv"))


class BomShortlistTests(unittest.TestCase):
    """The picker offers the last few BOMs off the share, because the answer is
    nearly always one of them and navigating there by hand is the slow part.
    """

    def setUp(self) -> None:
        self._temp_context = tempfile.TemporaryDirectory(prefix="inventor_to_radan_find_")
        self.root = Path(self._temp_context.name)

    def tearDown(self) -> None:
        self._temp_context.cleanup()

    def make(self, relative: str, age_days: float = 0.0) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
        stamp = time.time() - age_days * 86400
        os.utime(path, (stamp, stamp))
        return path

    def find(self, **kwargs):
        return [p for p, _ in bom_finder.find_recent_boms(str(self.root), **kwargs)]

    def test_newest_first(self) -> None:
        self.make("job/old-BOM.xlsx", age_days=30)
        self.make("job/new-BOM.xlsx", age_days=1)
        self.make("job/middle-BOM.xlsx", age_days=10)
        self.assertEqual(
            [Path(p).name for p in self.find()],
            ["new-BOM.xlsx", "middle-BOM.xlsx", "old-BOM.xlsx"],
        )

    def test_the_tools_own_output_is_not_offered_back_as_input(self) -> None:
        """*_Radan.csv lands beside the BOM it came from. Listing it is how
        somebody converts a converted file."""
        self.make("job/F59822-BOM.xlsx")
        self.make("job/F59822-BOM_Radan.csv")
        self.assertEqual([Path(p).name for p in self.find()], ["F59822-BOM.xlsx"])

    def test_excel_lock_files_are_skipped(self) -> None:
        self.make("job/kit-BOM.xlsx")
        self.make("job/~$kit-BOM.xlsx")
        self.assertEqual([Path(p).name for p in self.find()], ["kit-BOM.xlsx"])

    def test_depth_is_bounded(self) -> None:
        """The share is deep and mostly not BOMs; an unbounded walk is the
        difference between a second and a minute."""
        self.make("a/BOM.xlsx")
        self.make("a/b/c/d/deep-BOM.xlsx")
        names = [Path(p).name for p in self.find(max_depth=1)]
        self.assertIn("BOM.xlsx", names)
        self.assertNotIn("deep-BOM.xlsx", names)

    def test_limit_is_honoured(self) -> None:
        for i in range(8):
            self.make(f"job/bom{i}-BOM.xlsx", age_days=i)
        self.assertEqual(len(self.find(limit=3)), 3)

    def test_an_unmapped_drive_returns_nothing_rather_than_raising(self) -> None:
        """W: is not always mapped. The picker still has to open."""
        self.assertEqual(bom_finder.find_recent_boms(r"Z:\nope\not\here"), [])
        self.assertEqual(bom_finder.find_recent_boms(""), [])

    def test_the_apps_own_rule_tables_are_not_offered_as_boms(self) -> None:
        """The four tables sit beside the exe, so an exe on the share puts them
        inside the search root. They are .csv files and emphatically not BOMs.

        Driven off config.CONFIG_CSV_NAMES, the same tuple the app seeds from,
        so a fifth table cannot be added without this exclusion following it.
        """
        import config

        for name in config.CONFIG_CSV_NAMES:
            self.make(f"dist/{name}")
        self.make("dist/F59822-BOM.xlsx")

        names = [Path(p).name for p in self.find(exclude_names=config.CONFIG_CSV_NAMES)]
        self.assertEqual(names, ["F59822-BOM.xlsx"])

    def test_exclusion_ignores_case(self) -> None:
        self.make("job/DESCRIPTION_RULES.CSV")
        self.make("job/real-BOM.xlsx")
        names = [Path(p).name for p in self.find(exclude_names=("description_rules.csv",))]
        self.assertEqual(names, ["real-BOM.xlsx"])

    def test_only_the_last_30_days_count_as_recent(self) -> None:
        """The share holds ~800 spreadsheets under the fabrication root. Without
        a window the shortlist is a museum, not a list of current work."""
        self.make("job/this-week-BOM.xlsx", age_days=3)
        self.make("job/last-year-BOM.xlsx", age_days=400)
        self.make("job/just-inside-BOM.xlsx", age_days=29)
        self.make("job/just-outside-BOM.xlsx", age_days=31)

        names = sorted(Path(p).name for p in self.find(max_age_days=30))
        self.assertEqual(names, ["just-inside-BOM.xlsx", "this-week-BOM.xlsx"])

    def test_no_age_window_keeps_everything(self) -> None:
        self.make("job/ancient-BOM.xlsx", age_days=900)
        self.assertEqual([Path(p).name for p in self.find()], ["ancient-BOM.xlsx"])

    def test_kit_boms_are_reached_at_depth_three(self) -> None:
        """A kit BOM is not at job level. Under the fabrication root a pack sits
        one below the job and PUMP PACK nests one deeper again - the depth that
        made the canonical kit BOMs invisible."""
        self.make("F59979/F59979-BOM.xlsx")
        self.make("F59270/EXTERIOR PACK/F59270-EXTERIOR PACK-BOM.xlsx")
        self.make("F59808/PUMP PACK/PUMP HOUSE/F59808-Pump House-BOM.xlsx")

        found = sorted(Path(p).name for p in self.find(max_depth=3))
        self.assertEqual(
            found,
            [
                "F59270-EXTERIOR PACK-BOM.xlsx",
                "F59808-Pump House-BOM.xlsx",
                "F59979-BOM.xlsx",
            ],
        )

    def test_hits_are_reported_as_they_are_found(self) -> None:
        """The picker fills its list during the ~20 s walk rather than after
        it. Rows appearing is what shows the thing is alive; a folder counter
        climbing into the thousands only reads as alarming."""
        self.make("a/one-BOM.xlsx")
        self.make("b/two-BOM.xlsx")
        streamed: list[str] = []
        returned = self.find(on_hit=lambda path, mtime: streamed.append(path))

        self.assertEqual(len(streamed), 2, "on_hit was not called for every match")
        self.assertEqual(sorted(streamed), sorted(returned),
                         "streamed rows and the final list must agree")

    def test_the_walk_stops_at_its_time_budget(self) -> None:
        """The full share walk is ~25 s. Folders are visited newest-first, so
        cutting it short drops the oldest end of the search."""
        for i in range(40):
            self.make(f"job{i:02d}/bom{i:02d}-BOM.xlsx", age_days=i)

        started = time.monotonic()
        bom_finder.find_recent_boms(str(self.root), time_budget=0.0)
        self.assertLess(time.monotonic() - started, 2.0, "budget of 0 should return at once")

    def test_the_walk_stops_once_the_list_is_full(self) -> None:
        """Not just trimmed at the end - stopped. on_hit firing for every file
        on the share would mean it walked the whole thing and threw the rest
        away, which is the 20 s this is meant to avoid."""
        for i in range(30):
            self.make(f"job{i:02d}/bom{i:02d}-BOM.xlsx", age_days=i)

        streamed: list[str] = []
        found = bom_finder.find_recent_boms(
            str(self.root), limit=10, on_hit=lambda p, m: streamed.append(p)
        )
        self.assertEqual(len(found), 10)
        self.assertEqual(len(streamed), 10, "walked past the limit instead of stopping")

    def test_no_budget_walks_everything(self) -> None:
        for i in range(5):
            self.make(f"job{i}/bom{i}-BOM.xlsx", age_days=i)
        self.assertEqual(len(self.find()), 5)

    def test_only_spreadsheets(self) -> None:
        self.make("job/real-BOM.xlsx")
        self.make("job/notes.txt")
        self.make("job/drawing.dxf")
        self.assertEqual([Path(p).name for p in self.find()], ["real-BOM.xlsx"])


class UpstreamPromptTests(unittest.TestCase):
    """The verify exe goes to people upstream of RADAN. Material, thickness and
    strategy are the laser programmer's vocabulary; asking a designer for them
    gets guesses written into the shop's rule table. So a verification run asks
    only the laser/not-laser question and reports what it could not resolve.
    """

    def setUp(self) -> None:
        self._temp_context = tempfile.TemporaryDirectory(prefix="inventor_to_radan_up_")
        self.temp_dir = Path(self._temp_context.name)
        self.config_dir = self.temp_dir / "config"
        self.config_dir.mkdir()
        self.rules_csv = self.config_dir / "description_rules.csv"
        self.rules_csv.write_text(
            "Description,Material,Thickness,Strategy\nKNOWN PANEL,Aluminum 3003,0.125,Default\n",
            encoding="utf-8",
        )
        bom = self.temp_dir / "kit-bom.csv"
        with bom.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Part Number", "Description", "Qty"])
            writer.writerow(["ABC-001", "KNOWN PANEL", "2"])
            writer.writerow(["NEW-001", "BRAND NEW MATERIAL", "3"])
        (self.temp_dir / "ABC-001.dxf").write_text("dxf", encoding="utf-8")
        (self.temp_dir / "NEW-001.dxf").write_text("dxf", encoding="utf-8")
        self.bom_path = bom

    def tearDown(self) -> None:
        self._temp_context.cleanup()

    def patch_config_paths(self):
        return patch.multiple(
            bom_converter,
            RULES_CSV=str(self.rules_csv),
            FTQ_CSV=str(self.config_dir / "ftq_parts.csv"),
            NONLASER_TOKENS_CSV=str(self.config_dir / "nonlaser_tokens.csv"),
            STOCK_CUT_PARTS_CSV=str(self.config_dir / "stock_cut_parts.csv"),
        )

    def convert(self, **kwargs):
        with self.patch_config_paths():
            return bom_converter.convert_bom_to_radan_csv(
                str(self.bom_path), allow_prompts=True, show_summary=False, **kwargs
            )

    def test_a_new_description_is_reported_not_prompted_for(self) -> None:
        def explode(*args, **kwargs):
            raise AssertionError("a designer must never be asked for a RADAN rule")

        with patch.object(bom_converter, "RadanRuleDialog", explode):
            result = self.convert(write_csv=False, collect_radan_rules=False)

        self.assertEqual(result.unresolved_descriptions, ("BRAND NEW MATERIAL",))
        report = Path(result.report_path).read_text(encoding="utf-8")
        self.assertIn("New descriptions (laser, but no RADAN rule yet):", report)
        self.assertIn("BRAND NEW MATERIAL", report)

    def test_the_rule_table_is_left_exactly_as_it_was(self) -> None:
        """A rule with blank fields is worse than no rule: column A of
        description_rules.csv is what marks a description as known laser."""
        before = self.rules_csv.read_text(encoding="utf-8")
        with patch.object(bom_converter, "RadanRuleDialog", None):
            self.convert(write_csv=False, collect_radan_rules=False)
        self.assertEqual(self.rules_csv.read_text(encoding="utf-8"), before)

    def test_known_descriptions_still_count_toward_the_export(self) -> None:
        with patch.object(bom_converter, "RadanRuleDialog", None):
            result = self.convert(write_csv=False, collect_radan_rules=False)
        self.assertEqual(result.added_count, 1)

    def test_no_section_when_everything_is_already_known(self) -> None:
        """An empty '(none)' section every run is noise the operator learns to
        skip past."""
        self.rules_csv.write_text(
            "Description,Material,Thickness,Strategy\n"
            "KNOWN PANEL,Aluminum 3003,0.125,Default\n"
            "BRAND NEW MATERIAL,Stainless Steel,0.25,AIR\n",
            encoding="utf-8",
        )
        result = self.convert(write_csv=False, collect_radan_rules=False)
        self.assertEqual(result.unresolved_descriptions, ())
        report = Path(result.report_path).read_text(encoding="utf-8")
        self.assertNotIn("New descriptions", report)

    def test_answering_yes_it_is_laser_still_lands_in_the_red_section(self) -> None:
        """The whole point of the tool. Normally that answer writes a rule, and
        the description shows up as expected-laser because it is then in the
        table; a verification run writes nothing, so the answer has to be
        carried through directly or it vanishes from the section it belongs in.
        """
        bom = self.temp_dir / "nodxf-bom.csv"
        with bom.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Part Number", "Description", "Qty"])
            writer.writerow(["MISSING-1", "UNSEEN MATERIAL", "1"])

        class SayItIsLaser:
            def __init__(self, items):
                self.expected_descriptions = [item["desc"] for item in items]

            def exec(self):
                return bom_converter.ACCEPTED

        with (
            self.patch_config_paths(),
            patch.object(bom_converter, "MissingDxfDialog", SayItIsLaser),
        ):
            result = bom_converter.convert_bom_to_radan_csv(
                str(bom), allow_prompts=True, show_summary=False,
                write_csv=False, collect_radan_rules=False,
            )

        self.assertEqual(result.expected_missing_dxfs, ("MISSING-1.dxf",))
        report = Path(result.report_path).read_text(encoding="utf-8")
        self.assertIn("MISSING-1.dxf", report)
        # and it is still flagged as needing a rule from somebody who has one
        self.assertIn("UNSEEN MATERIAL", result.unresolved_descriptions)

    def test_the_laser_programmers_path_still_demands_a_full_rule(self) -> None:
        """Default is unchanged: TNE and the clone launcher still get the
        NeedsUi contract rather than a silently incomplete table."""
        with self.assertRaises(bom_converter.InventorToRadanNeedsUi) as caught:
            with self.patch_config_paths():
                bom_converter.convert_bom_to_radan_csv(
                    str(self.bom_path), allow_prompts=False, show_summary=False
                )
        self.assertIn("BRAND NEW MATERIAL", caught.exception.missing_rules)


class FrozenDataFolderTests(unittest.TestCase):
    """The exe keeps its tables in a `data` folder beside itself. Builds before
    that kept them loose beside the exe, and on a deployed copy those loose
    files are not a stale snapshot - they are the live tables, holding every
    classification made since it went out.
    """

    def setUp(self) -> None:
        self._temp_context = tempfile.TemporaryDirectory(prefix="inventor_to_radan_mig_")
        self.exe_dir = Path(self._temp_context.name)
        self.data_dir = self.exe_dir / config.FROZEN_DATA_SUBDIR

    def tearDown(self) -> None:
        self._temp_context.cleanup()

    def write_loose(self, text: str = "Description,Material,Thickness,Strategy\nKEEP ME,Al,0.1,Air\n"):
        for name in config.CONFIG_CSV_NAMES:
            (self.exe_dir / name).write_text(text, encoding="utf-8")

    def test_loose_tables_are_moved_not_abandoned(self) -> None:
        self.write_loose()
        config._migrate_loose_tables(str(self.data_dir))

        self.assertTrue(self.data_dir.is_dir())
        for name in config.CONFIG_CSV_NAMES:
            self.assertIn("KEEP ME", (self.data_dir / name).read_text(encoding="utf-8"))
            self.assertFalse((self.exe_dir / name).exists(), f"{name} left behind to go stale")

    def test_an_existing_data_folder_is_never_overwritten(self) -> None:
        """Second run, or a copy already on the new layout: the live folder wins."""
        self.data_dir.mkdir()
        (self.data_dir / "description_rules.csv").write_text("CURRENT", encoding="utf-8")
        self.write_loose()

        config._migrate_loose_tables(str(self.data_dir))
        self.assertEqual(
            (self.data_dir / "description_rules.csv").read_text(encoding="utf-8"), "CURRENT"
        )

    def test_a_fresh_install_migrates_nothing(self) -> None:
        config._migrate_loose_tables(str(self.data_dir))
        self.assertFalse(self.data_dir.exists(), "created a folder with nothing to put in it")

    def test_only_runs_for_the_frozen_layout(self) -> None:
        """A clone's DATA_DIR is the checkout itself; nothing should move."""
        self.write_loose()
        config._migrate_loose_tables(str(self.exe_dir))
        for name in config.CONFIG_CSV_NAMES:
            self.assertTrue((self.exe_dir / name).exists())


class TableBackupTests(unittest.TestCase):
    """The data folder is the only record of what a deployed exe has learned. Deleting
    it used to be a silent rollback to the build-time snapshot, so a copy of
    the last known-good tables is kept beside it.
    """

    def setUp(self) -> None:
        self._temp_context = tempfile.TemporaryDirectory(prefix="inventor_to_radan_bak_")
        root = Path(self._temp_context.name)
        self.data_dir = root / "data"
        self.backup_dir = root / "data.backup"
        self.bundle = root / "bundle"
        self.bundle.mkdir()
        self.data_dir.mkdir()
        for name in config.CONFIG_CSV_NAMES:
            (self.bundle / name).write_text("SNAPSHOT\n", encoding="utf-8")
            (self.data_dir / name).write_text("LEARNED SINCE DEPLOYMENT\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._temp_context.cleanup()

    def back_up(self):
        rule_store.back_up_tables(
            str(self.data_dir), str(self.backup_dir), config.CONFIG_CSV_NAMES
        )

    def restore(self):
        """What ensure_config_csvs does: backup first, snapshot only after."""
        for name in config.CONFIG_CSV_NAMES:
            target = str(self.data_dir / name)
            rule_store.seed_csv(str(self.backup_dir / name), target)
            rule_store.seed_csv(str(self.bundle / name), target)

    def test_the_backup_survives_deleting_the_folder_it_protects(self) -> None:
        """The property that matters. Inside `data`, the backup would be
        deleted along with what it protects, and the next launch would reseed
        from the snapshot and back *that* up - destroying the only good copy on
        the second launch rather than the first."""
        self.back_up()
        shutil.rmtree(self.data_dir)

        self.assertTrue(self.backup_dir.is_dir(), "backup went with the data folder")
        for name in config.CONFIG_CSV_NAMES:
            self.assertEqual(
                (self.backup_dir / name).read_text(encoding="utf-8"),
                "LEARNED SINCE DEPLOYMENT\n",
            )

    def test_deleting_the_data_folder_costs_nothing_after_a_backup(self) -> None:
        self.back_up()
        shutil.rmtree(self.data_dir)
        self.data_dir.mkdir()
        self.restore()
        for name in config.CONFIG_CSV_NAMES:
            self.assertEqual(
                (self.data_dir / name).read_text(encoding="utf-8"),
                "LEARNED SINCE DEPLOYMENT\n",
                f"{name} fell back to the build-time snapshot",
            )

    def test_the_snapshot_is_used_only_when_there_is_no_backup(self) -> None:
        shutil.rmtree(self.data_dir)
        self.data_dir.mkdir()
        self.restore()
        for name in config.CONFIG_CSV_NAMES:
            self.assertEqual((self.data_dir / name).read_text(encoding="utf-8"), "SNAPSHOT\n")

    def test_a_truncated_table_never_overwrites_a_good_backup(self) -> None:
        """Backing up an empty file would launder the corruption into the only
        copy that could have fixed it."""
        self.back_up()
        (self.data_dir / "description_rules.csv").write_text("", encoding="utf-8")
        self.back_up()
        self.assertEqual(
            (self.backup_dir / "description_rules.csv").read_text(encoding="utf-8"),
            "LEARNED SINCE DEPLOYMENT\n",
        )

    def test_a_truncated_table_is_repaired_from_the_backup(self) -> None:
        self.back_up()
        (self.data_dir / "description_rules.csv").write_text("", encoding="utf-8")
        self.restore()
        self.assertEqual(
            (self.data_dir / "description_rules.csv").read_text(encoding="utf-8"),
            "LEARNED SINCE DEPLOYMENT\n",
        )

    def test_backup_is_disabled_for_a_checkout(self) -> None:
        """A clone's tables are version controlled - git is the backup, and a
        stray folder beside the repo would just be litter."""
        rule_store.back_up_tables(str(self.data_dir), "", config.CONFIG_CSV_NAMES)
        self.assertFalse(self.backup_dir.exists())


if __name__ == "__main__":
    unittest.main()
