#!/usr/bin/env python3
"""Stage 04: pair Delphes ROOT + LHE into a single parquet row per event.

Port of sandy/workflow/flatten/04_flatten.py — identical output schema. Uses
pure-python uproot (no ROOT), so it stays OUT of the CMSSW environment and runs
on system python.

Reads:
    <output_base>/<proc>/lhe/<proc>_seed<seed>.lhe.gz
    <scratch>/<proc>/delphes/<proc>_seed<seed>.root
Writes:
    <flat_base>/<proc>/flat/<proc>_seed<seed>.parquet
"""

from __future__ import annotations

import argparse
import gzip
import sys
from pathlib import Path
from typing import Dict, Iterator

import awkward as ak
import numpy as np
import pyarrow.parquet as pq
import uproot

from delphesprod.config import Config


# ----------------------------------------------------------------------
# LHE parsing
# ----------------------------------------------------------------------

def iter_lhe_events(lhe_path: Path) -> Iterator[dict]:
    """Yield one dict per <event> block in an LHE file (.lhe or .lhe.gz)."""
    opener = gzip.open if lhe_path.suffix == ".gz" else open
    with opener(lhe_path, "rt") as f:
        in_event = False
        header_seen = False
        buf: list[str] = []
        for line in f:
            stripped = line.strip()
            if stripped == "<event>":
                in_event = True
                header_seen = False
                buf = []
                continue
            if stripped == "</event>":
                in_event = False
                yield _parse_event_block(buf)
                continue
            if not in_event:
                continue
            if not header_seen and stripped and not stripped.startswith("#"):
                header_seen = True
                continue  # skip the per-event header line
            if stripped.startswith("<") or stripped.startswith("#"):
                continue
            if stripped:
                buf.append(stripped)


def _parse_event_block(particle_lines: list[str]) -> dict:
    pdg, status, m1, m2 = [], [], [], []
    px, py, pz, E, mass = [], [], [], [], []
    for line in particle_lines:
        parts = line.split()
        if len(parts) < 13:
            continue
        # Per LHE spec: ipdg istup mo1 mo2 col1 col2 px py pz E mass tau spin
        pdg.append(int(parts[0]))
        status.append(int(parts[1]))
        m1.append(int(parts[2]))
        m2.append(int(parts[3]))
        px.append(float(parts[6]))
        py.append(float(parts[7]))
        pz.append(float(parts[8]))
        E.append(float(parts[9]))
        mass.append(float(parts[10]))
    return dict(pdg=pdg, status=status, mother1=m1, mother2=m2,
                px=px, py=py, pz=pz, E=E, mass=mass)


# ----------------------------------------------------------------------
# Delphes ROOT reading
# ----------------------------------------------------------------------

RECO_BRANCHES = {
    "Jet":       ["PT", "Eta", "Phi", "Mass", "BTag", "TauTag", "Flavor"],
    "Electron":  ["PT", "Eta", "Phi", "Charge", "IsolationVar"],
    "Muon":      ["PT", "Eta", "Phi", "Charge", "IsolationVar"],
    "Photon":    ["PT", "Eta", "Phi", "IsolationVar"],
    "MissingET": ["MET", "Phi"],
    # particle-flow (energy-flow) constituents — the low-level inputs.
    "EFlowTrack":         ["PT", "Eta", "Phi", "Charge", "PID"],
    "EFlowPhoton":        ["ET", "Eta", "Phi"],
    "EFlowNeutralHadron": ["ET", "Eta", "Phi"],
    # Full tracking collection (all charged tracks). Same kinematics as
    # EFlowTrack plus impact-parameter info: D0/DZ are the transverse and
    # longitudinal impact parameters (mm) and ErrorD0/ErrorDZ their
    # resolutions, filled by the TrackSmearing module in the Delphes card.
    "Track":              ["PT", "Eta", "Phi", "Charge", "PID",
                           "D0", "DZ", "ErrorD0", "ErrorDZ"],
}


def read_delphes(root_path: Path) -> Dict[str, ak.Array]:
    """Map flat branch name -> awkward array (one entry per event)."""
    with uproot.open(root_path) as fh:
        tree = fh["Delphes"]
        out: Dict[str, ak.Array] = {}
        for coll, fields in RECO_BRANCHES.items():
            for f in fields:
                branch = f"{coll}.{f}"
                if branch not in tree:
                    continue
                out[f"reco_{coll}_{f}"] = tree[branch].array(library="ak")
        return out


# ----------------------------------------------------------------------
# Entry points
# ----------------------------------------------------------------------

def flatten(proc: str, seed: str, cfg: Config | None = None) -> Path:
    """Run the pairing for one (proc, seed); return the parquet path."""
    cfg = cfg or Config()
    lhe = cfg.output_base / proc / "lhe"     / f"{proc}_seed{seed}.lhe.gz"
    rt  = cfg.scratch     / proc / "delphes" / f"{proc}_seed{seed}.root"
    outdir = cfg.flat_base / proc / "flat"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{proc}_seed{seed}.parquet"

    for p in (lhe, rt):
        if not p.exists():
            raise FileNotFoundError(f"missing input: {p}")

    print(f"[04_flatten] reading Delphes  {rt}")
    reco = read_delphes(rt)
    n_reco = len(next(iter(reco.values())))

    print(f"[04_flatten] reading LHE      {lhe}")
    parton_events = list(iter_lhe_events(lhe))
    n_part = len(parton_events)

    if n_reco != n_part:
        print(f"[04_flatten] WARN: reco events ({n_reco}) != parton events ({n_part}); "
              f"pairing first {min(n_reco, n_part)}", file=sys.stderr)
    n = min(n_reco, n_part)

    parton_cols = {
        "parton_pdg":     [ev["pdg"]     for ev in parton_events[:n]],
        "parton_status":  [ev["status"]  for ev in parton_events[:n]],
        "parton_mother1": [ev["mother1"] for ev in parton_events[:n]],
        "parton_mother2": [ev["mother2"] for ev in parton_events[:n]],
        "parton_px":      [ev["px"]      for ev in parton_events[:n]],
        "parton_py":      [ev["py"]      for ev in parton_events[:n]],
        "parton_pz":      [ev["pz"]      for ev in parton_events[:n]],
        "parton_E":       [ev["E"]       for ev in parton_events[:n]],
        "parton_mass":    [ev["mass"]    for ev in parton_events[:n]],
    }

    table_data: Dict[str, ak.Array] = {
        "process":   ak.Array([proc] * n),
        "event_idx": ak.Array(np.arange(n, dtype=np.int64)),
    }
    for k, v in reco.items():
        table_data[k] = v[:n]
    for k, v in parton_cols.items():
        table_data[k] = ak.Array(v)

    print(f"[04_flatten] writing parquet  {out}  ({n} events)")
    ak.to_parquet(ak.Array(table_data), str(out))

    md = pq.read_metadata(str(out))
    print(f"[04_flatten] parquet rows={md.num_rows}, cols={md.num_columns}, "
          f"size={out.stat().st_size/1e6:.2f} MB")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("proc", help="process name (matches cards/<proc>/)")
    ap.add_argument("seed", nargs="?", default="1")
    args = ap.parse_args(argv)
    try:
        flatten(args.proc, args.seed)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
