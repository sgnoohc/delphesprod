"""`delphesprod doctor` — verify every dependency layer in one command."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from delphesprod.config import Config, config_path


def _ok(msg: str) -> bool:
    print(f"  OK    {msg}")
    return True


def _miss(msg: str, hint: str = "") -> bool:
    print(f"  MISS  {msg}" + (f"\n        -> {hint}" if hint else ""))
    return False


def _warn(msg: str) -> None:
    print(f"  WARN  {msg}")


def doctor(cfg: Config | None = None) -> int:
    cfg = cfg or Config()
    ok = True

    print(f"config: {config_path()}")

    # --- Layer 0: CVMFS + CMSSW toolchain --------------------------------
    print("[toolchain]")
    cvmfs = Path("/cvmfs/cms.cern.ch")
    ok &= _ok(f"CVMFS present: {cvmfs}") if cvmfs.is_dir() \
        else _miss(f"CVMFS missing: {cvmfs}", "is /cvmfs/cms.cern.ch mounted on this node?")
    cmssw_src = cvmfs / cfg.scram_arch / "cms" / "cmssw" / cfg.cmssw / "src"
    ok &= _ok(f"CMSSW resolves: {cfg.cmssw} ({cfg.scram_arch})") if cmssw_src.is_dir() \
        else _miss(f"CMSSW not found: {cmssw_src}", "check [toolchain].cmssw / scram_arch")

    # --- Layer 1: ROOT (only meaningful once env.sh is sourced) ----------
    print("[root]")
    rootsys = os.environ.get("ROOTSYS", "")
    if not rootsys:
        _warn("ROOTSYS unset — source setup/env.sh first to validate ROOT at runtime")
    elif "/cvmfs/cms.cern.ch/" in rootsys:
        _ok(f"ROOT from CVMFS CMSSW: {rootsys}")
    else:
        _warn(f"ROOTSYS not under CVMFS CMSSW: {rootsys} "
              "(the root/6.38.00 module is deliberately NOT used; Delphes needs its ABI-matched ROOT)")

    # --- Layer 3: MG5 / Delphes binary tree ------------------------------
    print("[tools]")
    if not cfg.mg5_home:
        ok &= _miss("mg5_home is empty", "run: delphesprod bootstrap")
    else:
        for label, p in [
            ("mg5_aMC", Path(cfg.mg5_bin)),
            ("PY8 interface", Path(cfg.py8_interface)),
            ("DelphesHepMC2", Path(cfg.delphes_home) / "DelphesHepMC2"),
        ]:
            ok &= _ok(f"{label}: {p}") if p.exists() \
                else _miss(f"{label} missing: {p}", "run: delphesprod bootstrap")

    # --- Layer 2: python libs for flatten --------------------------------
    print("[python]")
    for m in ("uproot", "awkward", "pyarrow", "numpy"):
        try:
            mod = __import__(m)
            _ok(f"{m} {getattr(mod, '__version__', '?')}")
        except Exception:
            ok &= _miss(f"python module '{m}' not importable",
                        "pip install -r requirements.txt (or use HPG system python3)")

    # --- cards -----------------------------------------------------------
    print("[cards]")
    from delphesprod import cards
    procs = cards.list_processes()
    _ok(f"{len(procs)} process(es): {', '.join(procs) if procs else '(none yet)'}")

    print("\n" + ("doctor: all required checks passed" if ok
                  else "doctor: FAILURES above — fix before running"))
    return 0 if ok else 1
