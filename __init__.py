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
"""
