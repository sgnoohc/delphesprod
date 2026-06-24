"""Config layer: project-root discovery, env var map, export formatting."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _env():
    e = dict(os.environ)
    e["PYTHONPATH"] = str(SRC) + os.pathsep + e.get("PYTHONPATH", "")
    return e


def test_find_project_root():
    sys.path.insert(0, str(SRC))
    from delphesprod.config import find_project_root
    assert find_project_root() == ROOT


def test_env_vars_keys():
    sys.path.insert(0, str(SRC))
    from delphesprod.config import env_vars
    v = env_vars()
    for k in ("DPROD_HOME", "DPROD_CARDS_DIR", "DPROD_SCRIPTS_DIR",
              "DPROD_OUTPUT_BASE", "DPROD_SCRATCH", "DPROD_FLAT_BASE",
              "DPROD_EBEAM1", "DPROD_SCRAM_ARCH", "DPROD_CMSSW"):
        assert k in v
    assert v["DPROD_EBEAM1"] == "6800"


def test_env_override_preserved():
    """An existing DPROD_* in the environment must win (SLURM_TMPDIR pattern)."""
    sys.path.insert(0, str(SRC))
    import importlib
    import delphesprod.config as c
    os.environ["DPROD_SCRATCH"] = "/tmp/override_scratch"
    try:
        importlib.reload(c)
        assert c.env_vars()["DPROD_SCRATCH"] == "/tmp/override_scratch"
    finally:
        del os.environ["DPROD_SCRATCH"]
        importlib.reload(c)


def test_emit_env_runs_as_subprocess():
    out = subprocess.run([sys.executable, "-m", "delphesprod", "env"],
                         env=_env(), capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert 'export DPROD_HOME=' in out.stdout
