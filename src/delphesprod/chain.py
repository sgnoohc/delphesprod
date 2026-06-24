"""Run the full 01->02->03->04 chain for one (proc, seed) pair.

The generation stages (01-03) are bash subprocesses that source setup/env.sh
(and thus the CVMFS CMSSW ROOT). Stage 04 (flatten) is called in-process so it
stays on system python, OUTSIDE the CMSSW environment.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Iterable, Set

from delphesprod import cards, flatten
from delphesprod.config import Config


def _scripts_dir(cfg: Config) -> Path:
    return Path(os.environ.get("DPROD_SCRIPTS_DIR") or (cfg.root / "scripts"))


def run_chain(proc: str, nevents: int, seed: int = 1,
              skip: Iterable[str] = (), cleanup: bool = False,
              cfg: Config | None = None) -> Path:
    """Run the chain; return the parquet path. Raises on any stage failure."""
    cfg = cfg or Config()
    skip_set: Set[str] = {s.strip() for s in skip if s.strip()}
    bundle = cards.resolve(proc)

    env = os.environ.copy()
    env.update(bundle.env())
    scripts = _scripts_dir(cfg)

    t0 = time.time()
    print(f"=== delphesprod chain: proc={proc} nevents={nevents} seed={seed} "
          f"skip=[{','.join(sorted(skip_set))}] ===")

    def stage(num: str, script: str, *args: str) -> None:
        if num in skip_set:
            print(f"[chain] skip {num}")
            return
        subprocess.run([str(scripts / script), *args], env=env, check=True)

    stage("01", "01_madgraph.sh", proc, str(nevents), str(seed))
    stage("02", "02_shower.sh", proc, str(seed))
    stage("03", "03_delphes.sh", proc, str(seed))

    out = cfg.flat_base / proc / "flat" / f"{proc}_seed{seed}.parquet"
    if "04" in skip_set:
        print("[chain] skip 04")
    else:
        out = flatten.flatten(proc, str(seed), cfg)

    if cleanup:
        _cleanup(proc, seed, cfg)

    print(f"=== done in {int(time.time() - t0)} s ===")
    return out


def _cleanup(proc: str, seed: int, cfg: Config) -> None:
    """Drop bulky intermediates once the parquet exists. Guarded on parquet."""
    flat = cfg.flat_base / proc / "flat" / f"{proc}_seed{seed}.parquet"
    if not (flat.exists() and flat.stat().st_size > 0):
        print(f"[cleanup] SKIPPED — no parquet at {flat}; leaving intermediates for debug")
        return
    hepmc = cfg.scratch / proc / "hepmc" / f"{proc}_seed{seed}.hepmc.gz"
    droot = cfg.scratch / proc / "delphes" / f"{proc}_seed{seed}.root"
    procd = cfg.output_base / proc / "mg5_work" / f"proc_{proc}_seed{seed}"
    for p in (hepmc, droot):
        p.unlink(missing_ok=True)
    if procd.is_dir():
        import shutil
        shutil.rmtree(procd, ignore_errors=True)
    print(f"[cleanup] removed hepmc/delphes/procdir for seed {seed} (kept {flat})")
