"""delphesprod configuration.

Single source of truth for all site-specific paths. Parses ``config.toml`` (or
the committed ``config.example.toml`` fallback) and exposes:

* :func:`load` / :class:`Config` — structured access for the Python layer
  (cli, chain, submit, bootstrap, doctor, flatten);
* :func:`env_vars` / :func:`emit_env` — the ``DPROD_*`` export lines that
  ``setup/env.sh`` evals so the bash stage scripts get the same paths without
  duplicating any of them.

Runs on system python 3.9+ (uses the ``tomli`` backport when ``tomllib`` from
3.11 is unavailable).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:  # py3.11+
    import tomllib
except ModuleNotFoundError:  # py3.9 / 3.10 — backport is present on HPG system python
    import tomli as tomllib  # type: ignore


# ----------------------------------------------------------------------
# Project root + config file discovery
# ----------------------------------------------------------------------

def find_project_root(start: Path | None = None) -> Path:
    """Return the repo root (the dir containing ``pyproject.toml``).

    Honors ``$DELPHESPROD_HOME`` if set; otherwise walks up from this file.
    """
    env = os.environ.get("DELPHESPROD_HOME")
    if env:
        return Path(env).resolve()
    here = (start or Path(__file__)).resolve()
    for cand in [here, *here.parents]:
        if (cand / "pyproject.toml").is_file():
            return cand
    # Fallback: src/delphesprod/config.py -> repo root is two parents up.
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = find_project_root()


def config_path() -> Path:
    """Location of the active config file.

    ``$DELPHESPROD_CONFIG`` wins; then ``config.toml``; else the committed
    ``config.example.toml`` (so the tooling still runs before a user copies it).
    """
    env = os.environ.get("DELPHESPROD_CONFIG")
    if env:
        return Path(env)
    cfg = PROJECT_ROOT / "config.toml"
    if cfg.is_file():
        return cfg
    return PROJECT_ROOT / "config.example.toml"


def load_raw() -> Dict[str, Any]:
    with open(config_path(), "rb") as fh:
        return tomllib.load(fh)


# ----------------------------------------------------------------------
# Structured access
# ----------------------------------------------------------------------

class Config:
    """Thin typed view over the parsed TOML, with sensible defaults."""

    def __init__(self, raw: Dict[str, Any] | None = None, root: Path = PROJECT_ROOT):
        self.raw = raw if raw is not None else load_raw()
        self.root = root

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.raw.get(section, {}).get(key, default)

    # -- tools / toolchain -------------------------------------------------
    @property
    def mg5_home(self) -> str:
        return os.environ.get("DPROD_MG5_HOME") or self.get("tools", "mg5_home", "") or ""

    @property
    def mg5_bin(self) -> str:
        return f"{self.mg5_home}/bin/mg5_aMC" if self.mg5_home else ""

    @property
    def py8_interface(self) -> str:
        m = self.mg5_home
        return f"{m}/HEPTools/MG5aMC_PY8_interface/MG5aMC_PY8_interface" if m else ""

    @property
    def delphes_home(self) -> str:
        return f"{self.mg5_home}/Delphes" if self.mg5_home else ""

    @property
    def scram_arch(self) -> str:
        return self.get("toolchain", "scram_arch", "el9_amd64_gcc13")

    @property
    def cmssw(self) -> str:
        return self.get("toolchain", "cmssw", "CMSSW_16_0_0_pre4")

    # -- bootstrap ---------------------------------------------------------
    @property
    def bootstrap_prefix(self) -> str:
        return self.get("bootstrap", "prefix", str(self.root / "external"))

    @property
    def mg5_version(self) -> str:
        return self.get("bootstrap", "mg5_version", "3.5.0")

    # -- output paths ------------------------------------------------------
    @property
    def output_base(self) -> Path:
        return Path(os.environ.get("DPROD_OUTPUT_BASE")
                    or self.get("output", "base", "") or str(self.root / "samples"))

    @property
    def scratch(self) -> Path:
        return Path(os.environ.get("DPROD_SCRATCH")
                    or self.get("output", "scratch", "") or str(self.output_base))

    @property
    def flat_base(self) -> Path:
        return Path(os.environ.get("DPROD_FLAT_BASE")
                    or self.get("output", "flat_base", "") or str(self.output_base))

    # -- slurm -------------------------------------------------------------
    def slurm(self) -> Dict[str, Any]:
        s = dict(account="avery", qos="avery", partition="hpg-default",
                 time="08:00:00", mem="16G", cpus=4)
        s.update(self.raw.get("slurm", {}))
        return s


def load() -> Config:
    return Config()


# ----------------------------------------------------------------------
# Environment export (consumed by setup/env.sh)
# ----------------------------------------------------------------------

def env_vars() -> Dict[str, str]:
    """Build the ``DPROD_*`` variable map that the bash stages rely on.

    Existing ``DPROD_*`` values already in the environment win (this is how a
    SLURM job injects ``DPROD_SCRATCH=$SLURM_TMPDIR``).
    """
    cfg = Config()
    m = cfg.mg5_home
    beams = cfg.raw.get("beams", {})

    v: Dict[str, str] = {
        "DPROD_HOME": str(cfg.root),
        "DPROD_CARDS_DIR": str(cfg.root / "cards"),
        "DPROD_SCRIPTS_DIR": str(cfg.root / "scripts"),
        "DPROD_MG5_HOME": m,
        "DPROD_MG5_BIN": cfg.mg5_bin,
        "DPROD_PYTHIA8_HOME": f"{m}/HEPTools/pythia8" if m else "",
        "DPROD_PY8_INTERFACE": cfg.py8_interface,
        "DPROD_HEPMC_HOME": f"{m}/HEPTools/hepmc" if m else "",
        "DPROD_DELPHES_HOME": cfg.delphes_home,
        "DPROD_PYTHIA8DATA": (cfg.get("tools", "pythia8data", "") or
                              (f"{m}/HEPTools/pythia8/share/Pythia8/xmldoc" if m else "")),
        "DPROD_OUTPUT_BASE": str(cfg.output_base),
        "DPROD_SCRATCH": str(cfg.scratch),
        "DPROD_FLAT_BASE": str(cfg.flat_base),
        "DPROD_EBEAM1": str(beams.get("ebeam1", 6800)),
        "DPROD_EBEAM2": str(beams.get("ebeam2", 6800)),
        "DPROD_SCRAM_ARCH": cfg.scram_arch,
        "DPROD_CMSSW": cfg.cmssw,
    }
    for k in list(v):
        ov = os.environ.get(k)
        if ov:
            v[k] = ov
    return v


def emit_env() -> str:
    """Return ``export K="V"`` lines for ``eval`` in setup/env.sh."""
    lines = []
    for k, val in env_vars().items():
        esc = val.replace('"', r"\"")
        lines.append(f'export {k}="{esc}"')
    return "\n".join(lines)
