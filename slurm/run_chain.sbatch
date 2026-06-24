#!/bin/bash
#SBATCH --job-name=dprod
#SBATCH --time=08:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#
# Single, parameterized array template for the delphesprod chain. Normally
# launched by `delphesprod submit`, which fills in account/qos/partition/array
# and the --export variables. Header values above are fallbacks only.
#
# Required env (set via --export by `delphesprod submit`):
#   DELPHESPROD_HOME   repo root
#   NEVT               events per (proc, seed)
#   MODE               "manifest" | "seed"
#   MANIFEST           (manifest mode) path to the proc-seed list
#   PROC               (seed mode) process name
#   CLEANUP            optional; "1" to drop intermediates after flatten

set -euo pipefail

# Burst jobs are submitted without --export=ALL so they requeue cleanly; that
# can leave a minimal PATH, so guarantee the basics.
export PATH="/usr/bin:/bin${PATH:+:$PATH}"

: "${DELPHESPROD_HOME:?set via --export}"
: "${NEVT:?set via --export}"
: "${MODE:?set via --export}"
: "${SLURM_ARRAY_TASK_ID:?must run as an array job}"

# Bulky HepMC/Delphes intermediates -> node-local NVMe (auto-cleaned, off /blue).
if [ -n "${SLURM_TMPDIR:-}" ]; then
  export DPROD_SCRATCH="$SLURM_TMPDIR"
fi

if [ "$MODE" = "manifest" ]; then
  : "${MANIFEST:?manifest mode needs MANIFEST}"
  LINE=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$MANIFEST")
  [ -n "$LINE" ] || { echo "no manifest line $SLURM_ARRAY_TASK_ID in $MANIFEST" >&2; exit 1; }
  read -r PROC SEED <<< "$LINE"
else
  : "${PROC:?seed mode needs PROC}"
  SEED="${SLURM_ARRAY_TASK_ID}"
fi
echo "[run_chain] proc=$PROC seed=$SEED nevents=$NEVT scratch=${DPROD_SCRATCH:-<config>}"

ARGS=("$PROC" "$NEVT" "$SEED")
[ -n "${CLEANUP:-}" ] && ARGS+=(--cleanup)

# Invoke via the module path so this works whether or not the console script is
# on PATH (the editable install puts the package under src/).
export PYTHONPATH="$DELPHESPROD_HOME/src${PYTHONPATH:+:$PYTHONPATH}"
cd "$DELPHESPROD_HOME"
exec python3 -m delphesprod run "${ARGS[@]}"
