# Reproduce from a fresh HiPerGator login — 100 events of `p p > w+ w-`

Everything below is literal copy-paste. The only thing you edit is the two
variables in step 0. No `pip install` is needed: the chain runs on the system
`/usr/bin/python3` via `PYTHONPATH=src python3 -m delphesprod`.

Prerequisites: a HiPerGator account, CVMFS mounted (default on login/compute
nodes), and GitHub access to the repo (your SSH key registered with GitHub, or
use the HTTPS URL in step 1).

```bash
# ── 0. Pick YOUR writable locations ──────────────────────────────────────────
WORK=/blue/avery/$USER      # <-- a /blue dir you can write to (has space + CVMFS)
ACCOUNT=avery               # <-- your SLURM allocation (only matters for `submit`)
mkdir -p "$WORK" && cd "$WORK"

# ── 1. Clone the repo ────────────────────────────────────────────────────────
git clone git@github.com:sgnoohc/delphesprod.git
#   (no SSH key on GitHub? use: git clone https://github.com/sgnoohc/delphesprod.git)
cd delphesprod

# ── 2. Site config: copy the template, point paths at YOUR dirs ───────────────
cp config.example.toml config.toml
sed -i \
  -e "s|^prefix .*|prefix      = \"$WORK/delphesprod-tools\"|" \
  -e "s|^base .*|base      = \"$WORK/delphesprod/samples\"|" \
  -e "s|^account .*|account   = \"$ACCOUNT\"|" \
  config.toml
#   ([tools].mg5_home stays empty — step 3 fills it in automatically.)

# ── 3. One-time build of MG5 + Pythia8 + Delphes (~20-30 min, needs network) ──
#   Downloads MG5 v3.5.0 from launchpad, builds Pythia8/Delphes against CVMFS
#   CMSSW ROOT, and writes [tools].mg5_home back into config.toml.
PYTHONPATH=src python3 -m delphesprod bootstrap

# ── 4. Load the environment and sanity-check ─────────────────────────────────
source setup/env.sh
PYTHONPATH=src python3 -m delphesprod doctor      # expect: "all required checks passed"

# ── 5. Define the process: p p > w+ w- ───────────────────────────────────────
PYTHONPATH=src python3 -m delphesprod init ww
cat > cards/ww/process.mg5 <<'EOF'
import model sm
define p = g u c d s u~ c~ d~ s~
generate p p > w+ w-
EOF

# ── 6. Generate 100 events (MadGraph5 -> Pythia8 -> Delphes -> parquet) ───────
#   Args: <process> <nevents> <seed>
PYTHONPATH=src python3 -m delphesprod run ww 100 1
```

Result — one parquet row per event (100 rows, 45 columns: `reco_*` + `parton_*`):

```
$WORK/delphesprod/samples/ww/flat/ww_seed1.parquet
```

(plus `lhe/`, `hepmc/`, `delphes/`, and per-stage `logs/` under `samples/ww/`).

## Notes
- **Already bootstrapped?** Skip steps 0–4. From an existing checkout the whole
  thing is just steps 5–6 (and step 5's `init` only once).
- **Console-script form (matches the README):** run `python3 -m pip install --user -e .`
  once, then you can drop the `PYTHONPATH=src python3 -m` prefix and just type
  `delphesprod run ww 100 1`.
- **`seed`** (trailing `1`) is the MadGraph random seed — bump it for independent
  statistically-uncorrelated samples (e.g. `run ww 100 2`).
- **Pre-staged MG5 tarball:** if launchpad is flaky, drop a `MG5_aMC_v3.5.0.tar.gz`
  somewhere and set `[bootstrap].url = "file:///path/to/MG5_aMC_v3.5.0.tar.gz"`
  in `config.toml` before step 3.
