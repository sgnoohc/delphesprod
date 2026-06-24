"""Build a (proc, seed) work list for manifest-driven SLURM fan-out.

A spec is ``proc=N`` (seeds 1..N) or ``proc=a-b`` (seeds a..b). The manifest is
one ``proc seed`` per line, consumed by run_chain.sbatch via SLURM_ARRAY_TASK_ID.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple


def parse_spec(spec: str) -> List[Tuple[str, int]]:
    if "=" not in spec:
        raise ValueError(f"bad spec '{spec}'; expected proc=N or proc=a-b")
    proc, rng = spec.split("=", 1)
    proc = proc.strip()
    rng = rng.strip()
    if "-" in rng:
        a, b = rng.split("-", 1)
        lo, hi = int(a), int(b)
    else:
        lo, hi = 1, int(rng)
    if lo > hi:
        raise ValueError(f"bad range in '{spec}': {lo} > {hi}")
    return [(proc, s) for s in range(lo, hi + 1)]


def build(specs: List[str]) -> List[Tuple[str, int]]:
    rows: List[Tuple[str, int]] = []
    for spec in specs:
        rows.extend(parse_spec(spec))
    return rows


def write(rows: List[Tuple[str, int]], out: Path) -> int:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        for proc, seed in rows:
            fh.write(f"{proc} {seed}\n")
    return len(rows)
