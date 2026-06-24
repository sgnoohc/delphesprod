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

## Inspecting the output

```bash
source setup/env.sh
PYTHONPATH=src python3 - <<'PY'
import pyarrow.parquet as pq
t = pq.ParquetFile("samples/ww/flat/ww_seed1.parquet").read()
names = [f.name for f in t.schema]
for n in names:                       # first event = row 0
    print(f"{n} = {t.column(n)[0].as_py()}")
PY
```

First event (`event_idx = 0`) of `samples/ww/flat/ww_seed1.parquet`. The
`parton_*` block is the LHE hard process — incoming `u u~` (pdg ±2, status -1)
producing `W+ W-` (pdg ±24, status 1, mass 80.42 GeV); the `reco_*` block is the
Delphes detector response. Bulky particle-flow arrays are truncated here with
`…` (the snippet above prints them in full):

```
process            = ww
event_idx          = 0

# --- reco: jets (5) ---
reco_Jet_PT        = [85.476, 77.059, 43.990, 35.027, 22.502]
reco_Jet_Eta       = [-2.124, -3.572, -2.457, -3.655, -3.028]
reco_Jet_Phi       = [-1.752, 2.344, 0.238, 1.168, -1.308]
reco_Jet_Mass      = [13.228, 9.140, 6.468, 2.524, 2.778]
reco_Jet_BTag      = [0, 0, 0, 0, 0]
reco_Jet_TauTag    = [0, 0, 0, 0, 0]
reco_Jet_Flavor    = [21, 0, 3, 0, 0]

# --- reco: leptons / photons (none in this event) ---
reco_Electron_*    = []        (PT, Eta, Phi, Charge, IsolationVar)
reco_Muon_*        = []        (PT, Eta, Phi, Charge, IsolationVar)
reco_Photon_*      = []        (PT, Eta, Phi, IsolationVar)

# --- reco: missing ET ---
reco_MissingET_MET = [14.555]
reco_MissingET_Phi = [0.673]

# --- reco: particle-flow constituents (counts) ---
reco_EFlowTrack_*         = 42 tracks   e.g. PT[0:3]=[0.681, 3.603, 3.582], PID[0:3]=[211, 211, -211]
reco_EFlowPhoton_*        = 36 photons  e.g. ET[0:3]=[0.452, 0.828, 0.887]
reco_EFlowNeutralHadron_* = 70 hadrons  e.g. ET[0:3]=[0.776, 0.573, 2.359]

# --- parton: LHE hard process  u u~ -> W+ W- ---
parton_pdg         = [-2, 2, 24, -24]            # u~, u, W+, W-
parton_status      = [-1, -1, 1, 1]              # -1 = incoming, 1 = outgoing
parton_mother1     = [0, 0, 1, 1]
parton_mother2     = [0, 0, 2, 2]
parton_px          = [-0.0, 0.0, -57.043, 57.043]
parton_py          = [0.0, -0.0, -1.508, 1.508]
parton_pz          = [3.310, -3157.851, -1994.493, -1160.048]
parton_E           = [3.310, 3157.851, 1996.929, 1164.232]
parton_mass        = [0.0, 0.0, 80.419, 80.419]  # both W bosons on-shell
```

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
