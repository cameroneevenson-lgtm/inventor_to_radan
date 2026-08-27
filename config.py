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


# The exe's tables live in a subfolder rather than loose beside it: the folder
# people copy to a share should look like a program, not a pile of CSVs.
FROZEN_DATA_SUBDIR = "data"


def _migrate_loose_tables(data_dir: str) -> None:
    """Move tables written by an older exe into the new `data` folder.

    Builds before this change kept the four CSVs loose beside the exe, and on
    a deployed copy those are not a stale snapshot - they are the live tables,
    holding every classification made since it went out. Seeding a fresh
    `data` folder from the bundle instead would silently abandon them.
    """
    if os.path.basename(data_dir) != FROZEN_DATA_SUBDIR or os.path.isdir(data_dir):
        return
    legacy_dir = os.path.dirname(data_dir)
    legacy = [n for n in CONFIG_CSV_NAMES if os.path.exists(os.path.join(legacy_dir, n))]
    if not legacy:
        return
    try:
        os.makedirs(data_dir, exist_ok=True)
        for name in legacy:
            os.replace(os.path.join(legacy_dir, name), os.path.join(data_dir, name))
    except OSError:
        # Read-only or a locked file: leave the originals alone. Seeding will
        # fill the new folder from the bundle, which is wrong but not lossy.
        pass


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

    A frozen exe keeps them in a `data` folder beside itself. That is what
    makes a copy on a share work as one shared installation: everyone running
    it reads and writes the same four CSVs, instead of each PC quietly growing
    a private catalog under LOCALAPPDATA that nobody else ever sees. If the
    location is read-only the per-user copy is the fallback, because the tool
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
            return os.path.join(beside_exe, FROZEN_DATA_SUBDIR)
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

# After CONFIG_CSV_NAMES: the migration needs to know which files to move.
_migrate_loose_tables(DATA_DIR)

# Where the picker looks for recently-touched BOMs to offer as a shortlist.
# Empty string disables the shortlist; the Select BOM... button is unaffected.
BOM_SEARCH_ROOT = os.environ.get(
    "INVENTOR_TO_RADAN_BOM_ROOT", r"W:\LASER\For Battleshield Fabrication"
)

# Depth 3, because a kit BOM is not at job level. Measured under that root:
#   depth 1  P59979\P59979-BOM.xlsx                        (whole-job BOM)
#   depth 2  F59270\EXTERIOR PACK\F59270-EXTERIOR PACK-BOM.xlsx
#   depth 3  F59808\PUMP PACK\PUMP HOUSE\F59808-Pump House-BOM.xlsx
# Rooting at W:\LASER with depth 2 reached only the first of those, which is
# why the canonical kit BOMs - the packs, and everything under PUMP PACK -
# never appeared. Depth 4 exists but held nothing recent and doubles the walk.
BOM_SEARCH_DEPTH = 3

# Only the last 30 days count as "recent". The share holds ~800 spreadsheets
# under this root; without a window the list is a museum.
BOM_MAX_AGE_DAYS = 30

# A cap, not the governing rule - the age window is. Sized so it rarely binds.
BOM_SHORTLIST_LIMIT = 40

RADAN_OUTPUT_SUFFIX = "_Radan.csv"
REPORT_SUFFIX = "_report.txt"
SUPPORTED_BOM_EXTENSIONS = {".csv", ".xlsx"}

RADAN_COL_ORDER = ["FILE", "QTY", "MATERIAL", "THICKNESS", "UNIT", "STRATEGY"]
