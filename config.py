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


def _resolve_data_dir() -> str:
    """Where the four rule CSVs are read from and written back to.

    A checkout is its own data dir: the shop's rule tables are version
    controlled and shared by pulling and committing them, so writes have to
    land in the clone. A pip install has nowhere safe to write - site-packages
    is replaced on the next upgrade - so it gets a per-user directory seeded
    from the packaged defaults on first run, and diverges from the shop's
    tables from then on. Point INVENTOR_TO_RADAN_DATA_DIR at a share to keep a
    pip-installed machine on the same tables as everyone else.
    """
    override = os.environ.get("INVENTOR_TO_RADAN_DATA_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    if os.path.exists(os.path.join(PKG_DIR, ".git")):
        return PKG_DIR
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "inventor_to_radan")


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
