from __future__ import annotations

import os
import sys

PKG_DIR = os.path.dirname(os.path.abspath(__file__))

def _resolve_seed_dir() -> str:
    """Where the packaged default CSVs are read from to fill a fresh DATA_DIR.

    A PyInstaller build unpacks its data files under `sys._MEIPASS`, and
    whether they land at the root or in a package-named subdirectory depends
    on the `--add-data` destination the build used, which in turn depends on
    whether the package or `bom_converter.py` was frozen. Both are accepted
    because guessing wrong is silent and expensive: seeding finds nothing, the
    operator opens the tool to an empty catalog, and starts re-teaching rules
    the shop already has.
    """
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        nested = os.path.join(bundle, "inventor_to_radan")
        if os.path.exists(os.path.join(nested, "description_rules.csv")):
            return nested
        return bundle
    return PKG_DIR


def _user_data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "inventor_to_radan")


def _is_writable(path: str) -> bool:
    """Can we actually create files here? Asked, not assumed.

    A share can be mounted read-only, and the answer decides whether the exe
    keeps its tables beside itself or falls back to a per-user copy.
    """
    probe = os.path.join(path, ".itr_write_probe")
    try:
        os.makedirs(path, exist_ok=True)
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("")
        os.remove(probe)
        return True
    except OSError:
        return False


def _resolve_data_dir() -> str:
    """Where the four rule CSVs are read from and written back to.

    Three deployments, three answers:

    A checkout is its own data dir - the shop's tables are version controlled
    and shared by pulling and committing them, so writes have to land in the
    clone.

    A frozen exe keeps them beside itself. That is what makes a copy of the
    dist folder on a share work as one shared installation: everyone running
    it reads and writes the same four CSVs, instead of each PC quietly growing
    a private catalog under LOCALAPPDATA that nobody else ever sees. If the
    share is read-only the per-user copy is the fallback, because the tool
    still has to be able to learn a rule.

    A pip install has nowhere safe to write - site-packages is replaced on the
    next upgrade - so it gets the per-user directory too.

    INVENTOR_TO_RADAN_DATA_DIR overrides all three.
    """
    override = os.environ.get("INVENTOR_TO_RADAN_DATA_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    if getattr(sys, "frozen", False):
        beside_exe = os.path.dirname(os.path.abspath(sys.executable))
        if _is_writable(beside_exe):
            return beside_exe
        return _user_data_dir()
    if os.path.exists(os.path.join(PKG_DIR, ".git")):
        return PKG_DIR
    return _user_data_dir()


DATA_DIR = _resolve_data_dir()

# Defaults shipped inside the package/checkout/bundle, used to fill a fresh DATA_DIR.
SEED_DIR = _resolve_seed_dir()

RULES_CSV = os.path.join(DATA_DIR, "description_rules.csv")
FTQ_CSV = os.path.join(DATA_DIR, "ftq_parts.csv")

NONLASER_TOKENS_CSV = os.path.join(DATA_DIR, "nonlaser_tokens.csv")
STOCK_CUT_PARTS_CSV = os.path.join(DATA_DIR, "stock_cut_parts.csv")

CONFIG_CSV_NAMES = (
    "description_rules.csv",
    "ftq_parts.csv",
    "nonlaser_tokens.csv",
    "stock_cut_parts.csv",
)

RADAN_OUTPUT_SUFFIX = "_Radan.csv"
REPORT_SUFFIX = "_report.txt"
SUPPORTED_BOM_EXTENSIONS = {".csv", ".xlsx"}

RADAN_COL_ORDER = ["FILE", "QTY", "MATERIAL", "THICKNESS", "UNIT", "STRATEGY"]
