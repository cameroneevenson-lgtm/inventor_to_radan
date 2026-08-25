"""`python -m inventor_to_radan <BOM>`.

The per-user Scripts directory pip installs `inventor-to-radan.exe` into is
usually not on PATH, and pip only warns about that rather than failing - so the
install looks fine and the command then comes back "not recognized". This entry
point needs no PATH entry at all.
"""
from __future__ import annotations

import sys

from inventor_to_radan.cli import main

if __name__ == "__main__":
    sys.exit(main())
