#!/bin/bash
# Stage 00 (one-time per process): build a relocatable MadGraph gridpack.
#
# A gridpack compiles the (seed-independent) process ONCE into a small, portable
# tarball; thereafter each seed runs `run.sh <nevents> <seed>` with no recompile
# (see the gridpack fast-path in 01_madgraph.sh). This replaces the per-seed
# `output`+compile, which rebuilt the identical ~30 MB process for every seed.
#
# Usage: 00_gridpack.sh <proc> [warmup_nevents]
# Reads (set by the Python layer / env.sh):
#   DPROD_CARD_PROCESS  required  the MG5 proc card
#   DPROD_CARD_RUNOPTS  optional  extra `set <var> <val>` lines (baked in here)
#   DPROD_EBEAM1/2                beam energies (baked in here)
# Writes:
#   <output_base>/<proc>/gridpack/<proc>.tar.gz   (the .sha is written by the
#                                                  Python layer after success)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../setup/env.sh"

PROC="${1:?usage: $0 <proc> [warmup_nevents]}"
WARMUP="${2:-2000}"

PROC_CARD="${DPROD_CARD_PROCESS:?DPROD_CARD_PROCESS not set (run via the delphesprod CLI)}"
[ -f "$PROC_CARD" ] || { echo "no proc card at $PROC_CARD" >&2; exit 1; }
[ -n "${DPROD_MG5_BIN:-}" ] && [ -x "$DPROD_MG5_BIN" ] || {
  echo "MG5 not available (DPROD_MG5_BIN='${DPROD_MG5_BIN:-}'); run: delphesprod bootstrap" >&2; exit 1; }

EBEAM1="${DPROD_EBEAM1:-6800}"
EBEAM2="${DPROD_EBEAM2:-6800}"

RUNOPTS_LINES=""
[ -n "${DPROD_CARD_RUNOPTS:-}" ] && [ -f "$DPROD_CARD_RUNOPTS" ] && \
  RUNOPTS_LINES="$(cat "$DPROD_CARD_RUNOPTS")"

GPDIR="$DPROD_OUTPUT_BASE/$PROC/gridpack"
LOGDIR="$DPROD_OUTPUT_BASE/$PROC/logs"
mkdir -p "$GPDIR" "$LOGDIR"
GPTAR="$GPDIR/${PROC}.tar.gz"
LOG="$LOGDIR/00_gridpack.log"

# Build in a throwaway dir: MG5 `output` compiles a ~30 MB proc dir, but only
# the small gridpack tarball is kept.
BUILD=$(mktemp -d -p "$GPDIR" build_XXXXXX)
trap 'rm -rf "$BUILD"' EXIT

SCRIPT="$BUILD/build.dat"
cat > "$SCRIPT" <<EOF
$(cat "$PROC_CARD")
output gp_${PROC} -nojpeg
launch gp_${PROC}
set gridpack True
set nevents $WARMUP
set iseed 1
set ebeam1 $EBEAM1
set ebeam2 $EBEAM2
$RUNOPTS_LINES
0
EOF

cd "$BUILD"
echo "[00_gridpack] building gridpack for '$PROC' (warmup nevents=$WARMUP, log=$LOG)"
"$DPROD_MG5_BIN" "$SCRIPT" > "$LOG" 2>&1 || {
  echo "[00_gridpack] MG5 gridpack build failed; tail of log:" >&2
  tail -40 "$LOG" >&2
  exit 1
}

SRC="$BUILD/gp_${PROC}/run_01_gridpack.tar.gz"
[ -f "$SRC" ] || {
  echo "[00_gridpack] no gridpack tarball at $SRC" >&2
  tail -40 "$LOG" >&2
  exit 1
}
mv -f "$SRC" "$GPTAR"
echo "[00_gridpack] wrote $GPTAR ($(du -h "$GPTAR" | cut -f1))"
