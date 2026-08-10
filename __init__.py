"""inventor_to_radan - converts an Inventor BOM export into a RADAN-ready CSV.

The package marker exists so sibling repos can `import inventor_to_radan.x`
rather than manipulating sys.path, and so `config.py` stops colliding with the
same-named modules in other C:\Tools repos.

This only became possible once the main module was renamed from
`inventor_to_radan.py` to `bom_converter.py`. While it shared the repo's name,
`import inventor_to_radan` meant the *file* whenever this directory was on
sys.path (pytest, the .bat, running from inside the repo) and the *package*
otherwise - so adding this marker broke the test suite instead of helping.

Intra-repo imports stay flat (`import bom_reader`), which keeps
`bom_converter.py` runnable as the script the .bat invokes and exec-able by
inline_runner, which is how odd_job_intake and truck_nest_explorer use it.

When installed via pip (`pip install git+https://...`), this directory lands
in site-packages as `inventor_to_radan/`, off of sys.path by default - so the
same flat imports need this directory on sys.path too, not just the script-run
and inline_runner cases above.
"""

import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)
