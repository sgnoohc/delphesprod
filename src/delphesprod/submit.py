"""Build and launch SLURM array jobs for the production chain.

Two modes:
  * manifest  — one array task per line of a (proc seed) manifest, with a global
                concurrency cap (``--cap N`` -> ``--array=1-M%N``);
  * seed      — one process, an array of seeds (``--seeds 1-20``).

``--burst`` switches to the preemptible ``avery-b`` qos and submits WITHOUT
``--export=ALL`` (so preempted jobs requeue cleanly), passing only the explicit
variables the sbatch needs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

from delphesprod import manifest as manifest_mod
from delphesprod.config import Config


def _array_spec(n: int, cap: Optional[int]) -> str:
    return f"1-{n}%{cap}" if cap else f"1-{n}"


def build_sbatch_cmd(
    *,
    cfg: Config,
    nevt: int,
    mode: str,
    manifest: Optional[Path] = None,
    proc: Optional[str] = None,
    seeds: Optional[str] = None,
    cap: Optional[int] = None,
    burst: bool = False,
    cleanup: bool = False,
) -> List[str]:
    s = cfg.slurm()
    qos = "avery-b" if burst else s["qos"]
    logdir = cfg.root / "slurm" / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    sbatch_file = cfg.root / "slurm" / "run_chain.sbatch"

    # Variables the sbatch needs regardless of mode.
    exports = {
        "DELPHESPROD_HOME": str(cfg.root),
        "NEVT": str(nevt),
        "MODE": mode,
    }
    if cleanup:
        exports["CLEANUP"] = "1"

    if mode == "manifest":
        assert manifest is not None
        rows = sum(1 for line in Path(manifest).read_text().splitlines() if line.strip())
        array = _array_spec(rows, cap)
        exports["MANIFEST"] = str(Path(manifest).resolve())
        jobname = "dprod_manifest"
    elif mode == "seed":
        assert proc and seeds
        array = f"{seeds}%{cap}" if cap else seeds
        exports["PROC"] = proc
        jobname = f"dprod_{proc}"
    else:
        raise ValueError(f"unknown mode {mode}")

    export_str = ",".join(f"{k}={v}" for k, v in exports.items())
    if not burst:
        export_str = "ALL," + export_str

    cmd = [
        "sbatch",
        f"--array={array}",
        f"--account={s['account']}",
        f"--qos={qos}",
        f"--partition={s['partition']}",
        f"--time={s['time']}",
        f"--mem={s['mem']}",
        f"--cpus-per-task={s['cpus']}",
        f"--job-name={jobname}",
        f"--output={logdir}/%x-%A_%a.out",
        f"--error={logdir}/%x-%A_%a.err",
        f"--export={export_str}",
        str(sbatch_file),
    ]
    return cmd


def submit(cmd: List[str], dry_run: bool = False) -> int:
    print(" ".join(cmd))
    if dry_run:
        return 0
    r = subprocess.run(cmd)
    return r.returncode
