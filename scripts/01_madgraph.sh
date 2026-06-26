#!/bin/bash
# Stage 01: MadGraph -> LHE
#
# Usage: 01_madgraph.sh <proc> <nevents> [seed]
#
# Card paths come from the env (set by the Python layer via cards.resolve):
#   DPROD_CARD_PROCESS  required  the MG5 proc card
#   DPROD_CARD_RUNOPTS  optional  extra `set <var> <val>` launch lines
#   DPROD_CARD_MADSPIN  optional  MadSpin card (presence enables madspin=ON)
#
# Output: <output_base>/<proc>/lhe/<proc>_seed<seed>.lhe.gz
# Side effect: per-seed self-contained proc dir at
#   <output_base>/<proc>/mg5_work/proc_<proc>_seed<seed>/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../setup/env.sh"

usage() { echo "Usage: $0 <proc> <nevents> [seed]" >&2; }

PROC="${1:?$(usage; echo missing proc)}"
NEVT="${2:?$(usage; echo missing nevents)}"
SEED="${3:-1}"

PROC_CARD="${DPROD_CARD_PROCESS:?DPROD_CARD_PROCESS not set (run via the delphesprod CLI)}"
[ -f "$PROC_CARD" ] || { echo "no proc card at $PROC_CARD" >&2; exit 1; }
[ -n "${DPROD_MG5_BIN:-}" ] && [ -x "$DPROD_MG5_BIN" ] || {
  echo "MG5 not available (DPROD_MG5_BIN='$DPROD_MG5_BIN'); run: delphesprod bootstrap" >&2; exit 1; }

OUTDIR="$DPROD_OUTPUT_BASE/$PROC"
WORKDIR="$OUTDIR/mg5_work"
LHEDIR="$OUTDIR/lhe"
LOGDIR="$OUTDIR/logs"
mkdir -p "$WORKDIR" "$LHEDIR" "$LOGDIR"

PROCDIR_NAME="proc_${PROC}_seed${SEED}"
PROCDIR="$WORKDIR/$PROCDIR_NAME"
SCRIPT="$WORKDIR/mg5_input_${PROC}_seed${SEED}.dat"
LOG="$LOGDIR/01_mg5_seed${SEED}.log"
DST_LHE="$LHEDIR/${PROC}_seed${SEED}.lhe.gz"

# --- Gridpack fast path -------------------------------------------------------
# If the Python layer resolved a current gridpack (DPROD_GRIDPACK), generate this
# seed from it: unpack to node-local scratch and run `run.sh <nevt> <seed>`. No
# per-seed recompile, and nothing lands on /blue except the LHE. Falls through to
# the per-seed `output`+compile below when no gridpack is set (e.g. MadSpin).
if [ -n "${DPROD_GRIDPACK:-}" ] && [ -f "$DPROD_GRIDPACK" ]; then
  RUNROOT="$DPROD_SCRATCH/$PROC"
  mkdir -p "$RUNROOT"
  RUNAREA=$(mktemp -d -p "$RUNROOT" "gprun_seed${SEED}_XXXXXX")
  trap 'rm -rf "$RUNAREA"' EXIT
  echo "[01_madgraph] gridpack run ($PROC, nevents=$NEVT, seed=$SEED, log=$LOG)"
  tar xzf "$DPROD_GRIDPACK" -C "$RUNAREA"
  ( cd "$RUNAREA" && ./run.sh "$NEVT" "$SEED" ) > "$LOG" 2>&1 || {
    echo "[01_madgraph] gridpack run.sh failed; tail of log:" >&2
    tail -40 "$LOG" >&2
    exit 1
  }
  SRC_LHE="$RUNAREA/events.lhe.gz"
  [ -f "$SRC_LHE" ] || { echo "[01_madgraph] no LHE at $SRC_LHE" >&2; tail -40 "$LOG" >&2; exit 1; }
  cp "$SRC_LHE" "$DST_LHE"
  echo "[01_madgraph] wrote $DST_LHE (from gridpack)"
  exit 0
fi
# --- else: per-seed output + compile (fallback) -------------------------------

EBEAM1="${DPROD_EBEAM1:-6800}"
EBEAM2="${DPROD_EBEAM2:-6800}"

RUNOPTS_LINES=""
[ -n "${DPROD_CARD_RUNOPTS:-}" ] && [ -f "$DPROD_CARD_RUNOPTS" ] && \
  RUNOPTS_LINES="$(cat "$DPROD_CARD_RUNOPTS")"

USE_MADSPIN=""
if [ -n "${DPROD_CARD_MADSPIN:-}" ] && [ -f "$DPROD_CARD_MADSPIN" ]; then
  USE_MADSPIN="madspin=ON"
fi

# Each seed gets its own fully self-contained proc dir. MG5 bakes absolute paths
# into the proc dir at `output` time, so shared/copied proc dirs cause silent
# cross-task writes when several seeds run in parallel — every seed must compile
# its own.
if [ -d "$PROCDIR" ]; then
  echo "[01_madgraph] reusing existing $PROCDIR_NAME"
  cat > "$SCRIPT" <<EOF
launch $PROCDIR_NAME --name=run
$USE_MADSPIN
0
set nevents $NEVT
set iseed $SEED
set ebeam1 $EBEAM1
set ebeam2 $EBEAM2
$RUNOPTS_LINES
0
EOF
else
  cat > "$SCRIPT" <<EOF
$(cat "$PROC_CARD")
output $PROCDIR_NAME -nojpeg
launch $PROCDIR_NAME --name=run
$USE_MADSPIN
0
set nevents $NEVT
set iseed $SEED
set ebeam1 $EBEAM1
set ebeam2 $EBEAM2
$RUNOPTS_LINES
0
EOF
fi

# If a MadSpin card is provided, install it into the proc dir AFTER `output`
# has created the Cards/ directory.
if [ -n "$USE_MADSPIN" ]; then
  if [ ! -d "$PROCDIR" ]; then
    PRE_OUTPUT_SCRIPT="$WORKDIR/mg5_compile_${PROC}_seed${SEED}.dat"
    cat > "$PRE_OUTPUT_SCRIPT" <<EOF
$(cat "$PROC_CARD")
output $PROCDIR_NAME -nojpeg
quit
EOF
    cd "$WORKDIR"
    "$DPROD_MG5_BIN" "$PRE_OUTPUT_SCRIPT" > "$LOGDIR/01_mg5_compile_seed${SEED}.log" 2>&1
  fi
  cp "$DPROD_CARD_MADSPIN" "$PROCDIR/Cards/madspin_card.dat"
  echo "[01_madgraph] installed MadSpin card $(basename "$DPROD_CARD_MADSPIN")"
  cat > "$SCRIPT" <<EOF
launch $PROCDIR_NAME --name=run
$USE_MADSPIN
0
set nevents $NEVT
set iseed $SEED
set ebeam1 $EBEAM1
set ebeam2 $EBEAM2
$RUNOPTS_LINES
0
EOF
fi

cd "$WORKDIR"
echo "[01_madgraph] running MG5 ($PROC, nevents=$NEVT, seed=$SEED, log=$LOG)"
"$DPROD_MG5_BIN" "$SCRIPT" > "$LOG" 2>&1 || {
  echo "[01_madgraph] MG5 failed; tail of log:" >&2
  tail -40 "$LOG" >&2
  exit 1
}

# Prefer the MadSpin-decayed LHE if present; otherwise the parton-level one.
SRC_LHE_DECAYED="$PROCDIR/Events/run_decayed_1/unweighted_events.lhe.gz"
SRC_LHE="$PROCDIR/Events/run/unweighted_events.lhe.gz"
if [ -f "$SRC_LHE_DECAYED" ]; then
  SRC_LHE="$SRC_LHE_DECAYED"
fi
DST_LHE="$LHEDIR/${PROC}_seed${SEED}.lhe.gz"
[ -f "$SRC_LHE" ] || { echo "[01_madgraph] no LHE at $SRC_LHE" >&2; tail -40 "$LOG" >&2; exit 1; }
cp "$SRC_LHE" "$DST_LHE"
echo "[01_madgraph] wrote $DST_LHE"
