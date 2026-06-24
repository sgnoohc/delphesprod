#!/bin/bash
# Stage 03: HepMC -> Delphes fast simulation -> ROOT
#
# Usage: 03_delphes.sh <proc> [seed]
# Card:  DPROD_CARD_DELPHES  (resolved delphes.tcl; set by the Python layer)
#
# Reads:  <scratch>/<proc>/hepmc/<proc>_seed<seed>.hepmc.gz
# Writes: <scratch>/<proc>/delphes/<proc>_seed<seed>.root

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../setup/env.sh"

PROC="${1:?usage: $0 <proc> [seed]}"
SEED="${2:-1}"

DELPHES_CARD="${DPROD_CARD_DELPHES:?DPROD_CARD_DELPHES not set (run via the delphesprod CLI)}"
HEPMC_GZ="$DPROD_SCRATCH/$PROC/hepmc/${PROC}_seed${SEED}.hepmc.gz"
[ -f "$HEPMC_GZ" ]     || { echo "no HepMC at $HEPMC_GZ" >&2; exit 1; }
[ -f "$DELPHES_CARD" ] || { echo "no Delphes card at $DELPHES_CARD" >&2; exit 1; }

DLPDIR="$DPROD_SCRATCH/$PROC/delphes"
LOGDIR="$DPROD_OUTPUT_BASE/$PROC/logs"
mkdir -p "$DLPDIR" "$LOGDIR"
ROOT_OUT="$DLPDIR/${PROC}_seed${SEED}.root"
LOG="$LOGDIR/03_delphes_seed${SEED}.log"

DELPHES_BIN=$(delphes_bin) || {
  echo "no Delphes binary under '$DPROD_DELPHES_HOME'; run: delphesprod bootstrap" >&2; exit 1; }

rm -f "$ROOT_OUT"   # Delphes refuses to overwrite

WORK=$(mktemp -d -p "$DLPDIR" delphes_XXXXXX)
trap "rm -rf $WORK" EXIT
HEPMC_PLAIN="$WORK/events.hepmc"
zcat "$HEPMC_GZ" > "$HEPMC_PLAIN"

echo "[03_delphes] running $(basename "$DELPHES_BIN") ($PROC, seed=$SEED, log=$LOG)"
"$DELPHES_BIN" "$DELPHES_CARD" "$ROOT_OUT" "$HEPMC_PLAIN" > "$LOG" 2>&1 || {
  echo "[03_delphes] Delphes failed; tail of log:" >&2
  tail -40 "$LOG" >&2
  exit 1
}

[ -s "$ROOT_OUT" ] || { echo "[03_delphes] ROOT output empty: $ROOT_OUT" >&2; exit 1; }
echo "[03_delphes] wrote $ROOT_OUT"
