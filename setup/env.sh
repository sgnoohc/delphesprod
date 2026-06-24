#!/bin/bash
# delphesprod runtime environment. Source before running any stage.
#
#   source setup/env.sh
#
# This is fully self-contained — it depends on NOTHING in any personal home
# directory (it replaces the old ~/setuproot.sh). It:
#   1. loads all DPROD_* paths from config.toml (via the CLI / config.py),
#   2. sets up ROOT from CVMFS CMSSW (the build Delphes is ABI-matched to),
#   3. exports the proven Pythia8/HepMC/Delphes runtime pins.

_DPROD_SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_DPROD_ROOT="$(cd "$_DPROD_SETUP_DIR/.." && pwd)"

# Resolve config via the installed CLI, falling back to running from the source
# tree (so this works before `pip install -e .`). Uses system python, which has
# the tomli backport — does NOT require the CMSSW environment to be set up yet.
_dprod_cli() {
  if command -v delphesprod >/dev/null 2>&1; then
    delphesprod "$@"
  else
    PYTHONPATH="$_DPROD_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m delphesprod "$@"
  fi
}

# 1. Load DPROD_* paths (mg5 binaries, output dirs, beams, toolchain pins).
eval "$(_dprod_cli env)"

# 2. ROOT runtime from CVMFS CMSSW (ABI-matched to the bootstrapped Delphes).
#    Deliberately NOT `module load root` — see reference_hpg_root note. Skipped
#    if a ROOT environment is already active (ROOTSYS set).
if [ -z "${ROOTSYS:-}" ]; then
  export SCRAM_ARCH="${DPROD_SCRAM_ARCH:-el9_amd64_gcc13}"
  _DPROD_CMSSW="${DPROD_CMSSW:-CMSSW_16_0_0_pre4}"
  _DPROD_CMSSW_SRC="/cvmfs/cms.cern.ch/$SCRAM_ARCH/cms/cmssw/$_DPROD_CMSSW/src"
  if [ -d "$_DPROD_CMSSW_SRC" ]; then
    source /cvmfs/cms.cern.ch/cmsset_default.sh
    pushd "$_DPROD_CMSSW_SRC" >/dev/null
    eval "$(scramv1 runtime -sh)"
    popd >/dev/null
  else
    echo "[env] WARN: CMSSW src not found at $_DPROD_CMSSW_SRC" >&2
    echo "[env]       (is CVMFS mounted? is [toolchain].cmssw correct?)" >&2
  fi
fi

# 3. Runtime pins for our own Pythia8/HepMC/Delphes binaries.
#    PYTHIA8DATA must match libpythia8 (8.306), not CMSSW's newer xmldoc.
if [ -n "${DPROD_PYTHIA8DATA:-}" ]; then
  export PYTHIA8DATA="$DPROD_PYTHIA8DATA"
fi
if [ -n "${DPROD_MG5_HOME:-}" ]; then
  export LD_LIBRARY_PATH="$DPROD_PYTHIA8_HOME/lib:$DPROD_HEPMC_HOME/lib:$DPROD_DELPHES_HOME:${LD_LIBRARY_PATH:-}"
fi

# Convenience: pick the right Delphes binary for HepMC v2 (Pythia8 plugin output).
delphes_bin() {
  if [ -x "$DPROD_DELPHES_HOME/DelphesHepMC2" ]; then
    echo "$DPROD_DELPHES_HOME/DelphesHepMC2"
  elif [ -x "$DPROD_DELPHES_HOME/DelphesHepMC3" ]; then
    echo "$DPROD_DELPHES_HOME/DelphesHepMC3"
  else
    return 1
  fi
}
