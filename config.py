from __future__ import annotations

import os

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

RULES_CSV = os.path.join(TOOLS_DIR, "description_rules.csv")
FTQ_CSV = os.path.join(TOOLS_DIR, "ftq_parts.csv")

NONLASER_TOKENS_CSV = os.path.join(TOOLS_DIR, "nonlaser_tokens.csv")

RADAN_OUTPUT_SUFFIX = "_Radan.csv"
REPORT_SUFFIX = "_report.txt"
SUPPORTED_BOM_EXTENSIONS = {".csv", ".xlsx"}

RADAN_COL_ORDER = ["FILE", "QTY", "MATERIAL", "THICKNESS", "UNIT", "STRATEGY"]
