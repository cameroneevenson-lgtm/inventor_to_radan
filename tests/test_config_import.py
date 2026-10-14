"""Standalone/frozen config must not require the private sibling package."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def isolated_import(tmp_path, code):
    env = os.environ.copy()
    env["INVENTOR_TO_RADAN_DATA_DIR"] = str(tmp_path / "data")
    env.pop("INVENTOR_TO_RADAN_BOM_ROOT", None)
    # -I -S removes PYTHONPATH, site-packages and the shared C:/Tools .pth.
    return subprocess.run(
        [sys.executable, "-I", "-S", "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); " + code, str(ROOT)],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )


def test_config_import_without_tools_parent_or_radan_package(tmp_path):
    result = isolated_import(tmp_path,
        "from pathlib import Path; "
        "assert all(Path(p).resolve() != Path(sys.argv[1]).parent for p in sys.path); "
        "import config; print(config.BOM_SEARCH_ROOT)")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == r"W:\LASER\For Battleshield Fabrication"


@pytest.mark.parametrize("exception", ["RuntimeError", "ImportError"])
def test_config_does_not_mask_site_loader_errors(tmp_path, exception):
    result = isolated_import(tmp_path,
        "import types; "
        "package=types.ModuleType('radan_tools'); package.__path__=[]; "
        "site=types.ModuleType('radan_tools.site_config'); "
        f"site.load_site_config=lambda: (_ for _ in ()).throw({exception}('bad site config')); "
        "sys.modules['radan_tools']=package; sys.modules['radan_tools.site_config']=site; "
        "import config")
    assert result.returncode != 0
    assert f"{exception}: bad site config" in result.stderr
