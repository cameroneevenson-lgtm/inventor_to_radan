from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path

from radan_tools.sibling_import import SiblingModules


INLINE_IMPORT_NAMES = {
    "bom_reader",
    "config",
    "dialogs",
    "report_review_rules",
    "report_writer",
    "rule_store",
}
INLINE_MODULE_NAME = "_inventor_to_radan_inline_tool"


def module_path_for_entry(entry_path: Path | str) -> Path:
    entry = Path(str(entry_path))
    if entry.suffix.casefold() == ".py":
        return entry
    return entry.parent / "bom_converter.py"


@contextmanager
def inline_import_context(module_dir: Path):
    with SiblingModules(module_dir).active():
        yield


def run_inline(
    entry_path: Path | str,
    spreadsheet_path: Path | str,
    *,
    allow_prompts: bool = False,
    show_summary: bool = False,
) -> object:
    entry = Path(str(entry_path))
    spreadsheet = Path(str(spreadsheet_path))
    if not entry.exists():
        raise FileNotFoundError(str(entry))
    if not spreadsheet.exists():
        raise FileNotFoundError(str(spreadsheet))

    module_path = module_path_for_entry(entry)
    if not module_path.exists():
        raise FileNotFoundError(f"Could not find inline Inventor-to-RADAN module: {module_path}")

    spec = importlib.util.spec_from_file_location(INLINE_MODULE_NAME, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load inline Inventor-to-RADAN module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    previous_module = sys.modules.get(INLINE_MODULE_NAME)
    with inline_import_context(module_path.parent):
        sys.modules[INLINE_MODULE_NAME] = module
        try:
            spec.loader.exec_module(module)
            converter = getattr(module, "convert_bom_to_radan_csv", None)
            if not callable(converter):
                raise RuntimeError(
                    f"{module_path} does not expose convert_bom_to_radan_csv(). "
                    "Use the external launcher for this version."
                )
            return converter(str(spreadsheet), allow_prompts=allow_prompts, show_summary=show_summary)
        finally:
            if previous_module is not None:
                sys.modules[INLINE_MODULE_NAME] = previous_module
            else:
                sys.modules.pop(INLINE_MODULE_NAME, None)
