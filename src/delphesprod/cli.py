"""delphesprod command-line interface."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from delphesprod import cards
from delphesprod.config import Config, PROJECT_ROOT, emit_env


def _scripts_dir(cfg: Config) -> Path:
    return Path(os.environ.get("DPROD_SCRIPTS_DIR") or (cfg.root / "scripts"))


# ----------------------------------------------------------------------
# subcommand handlers
# ----------------------------------------------------------------------

def cmd_env(args) -> int:
    print(emit_env())
    return 0


def cmd_init(args) -> int:
    cfg = Config()
    dst = cfg.root / "cards" / args.name
    if dst.exists():
        print(f"refusing to overwrite existing {dst}", file=sys.stderr)
        return 1
    shutil.copytree(cfg.root / "cards" / "_template", dst)
    print(f"created {dst} — edit {dst/'process.mg5'} then: delphesprod run {args.name} <nevt> <seed>")
    return 0


def cmd_list(args) -> int:
    procs = cards.list_processes()
    if not procs:
        print("(no processes yet — create one with: delphesprod init <name>)")
        return 0
    for name in procs:
        print(cards.describe(name))
    return 0


def cmd_doctor(args) -> int:
    from delphesprod.doctor import doctor
    return doctor()


def cmd_bootstrap(args) -> int:
    from delphesprod.bootstrap import bootstrap
    return bootstrap()


def cmd_run(args) -> int:
    from delphesprod.chain import run_chain
    skip = args.skip.split(",") if args.skip else []
    try:
        run_chain(args.proc, args.nevents, args.seed,
                  skip=skip, cleanup=args.cleanup)
    except subprocess.CalledProcessError as e:
        print(f"stage failed (exit {e.returncode})", file=sys.stderr)
        return e.returncode or 1
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


def _run_stage(script: str, proc: str, *extra: str) -> int:
    """Resolve cards, export DPROD_CARD_*, exec one bash stage."""
    cfg = Config()
    bundle = cards.resolve(proc)
    env = os.environ.copy()
    env.update(bundle.env())
    cmd = [str(_scripts_dir(cfg) / script), proc, *extra]
    return subprocess.run(cmd, env=env).returncode


def cmd_madgraph(args) -> int:
    return _run_stage("01_madgraph.sh", args.proc, str(args.nevents), str(args.seed))


def cmd_shower(args) -> int:
    return _run_stage("02_shower.sh", args.proc, str(args.seed))


def cmd_delphes(args) -> int:
    return _run_stage("03_delphes.sh", args.proc, str(args.seed))


def cmd_flatten(args) -> int:
    from delphesprod.flatten import main as flatten_main
    return flatten_main([args.proc, str(args.seed)])


def cmd_manifest(args) -> int:
    from delphesprod import manifest
    rows = manifest.build(args.specs)
    n = manifest.write(rows, Path(args.out))
    print(f"wrote {n} (proc, seed) rows to {args.out}")
    return 0


def cmd_submit(args) -> int:
    from delphesprod import submit
    cfg = Config()
    if args.manifest:
        cmd = submit.build_sbatch_cmd(
            cfg=cfg, nevt=args.nevt, mode="manifest",
            manifest=Path(args.manifest), cap=args.cap,
            burst=args.burst, cleanup=args.cleanup)
    elif args.proc and args.seeds:
        cmd = submit.build_sbatch_cmd(
            cfg=cfg, nevt=args.nevt, mode="seed",
            proc=args.proc, seeds=args.seeds, cap=args.cap,
            burst=args.burst, cleanup=args.cleanup)
    else:
        print("submit needs either --manifest, or --proc and --seeds", file=sys.stderr)
        return 1
    return submit.submit(cmd, dry_run=args.dry_run)


# ----------------------------------------------------------------------
# parser
# ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="delphesprod",
                                description="MG5 -> Pythia8 -> Delphes -> parquet production chain")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("env", help="print DPROD_* export lines (used by setup/env.sh)").set_defaults(func=cmd_env)

    sp = sub.add_parser("init", help="scaffold a new process from the template")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_init)

    sub.add_parser("list", help="list discovered processes").set_defaults(func=cmd_list)
    sub.add_parser("doctor", help="verify environment + dependencies").set_defaults(func=cmd_doctor)
    sub.add_parser("bootstrap", help="download + build MG5/Pythia8/Delphes").set_defaults(func=cmd_bootstrap)

    sp = sub.add_parser("run", help="run the full chain for one (proc, seed)")
    sp.add_argument("proc")
    sp.add_argument("nevents", type=int)
    sp.add_argument("seed", nargs="?", type=int, default=1)
    sp.add_argument("--skip", default="", help="comma list of stages to skip (01,02,03,04)")
    sp.add_argument("--cleanup", action="store_true", help="drop intermediates after flatten")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("madgraph", help="stage 01 only")
    sp.add_argument("proc"); sp.add_argument("nevents", type=int)
    sp.add_argument("seed", nargs="?", type=int, default=1)
    sp.set_defaults(func=cmd_madgraph)

    sp = sub.add_parser("shower", help="stage 02 only")
    sp.add_argument("proc"); sp.add_argument("seed", nargs="?", type=int, default=1)
    sp.set_defaults(func=cmd_shower)

    sp = sub.add_parser("delphes", help="stage 03 only")
    sp.add_argument("proc"); sp.add_argument("seed", nargs="?", type=int, default=1)
    sp.set_defaults(func=cmd_delphes)

    sp = sub.add_parser("flatten", help="stage 04 only (ROOT+LHE -> parquet)")
    sp.add_argument("proc"); sp.add_argument("seed", nargs="?", type=int, default=1)
    sp.set_defaults(func=cmd_flatten)

    sp = sub.add_parser("manifest", help="build a (proc, seed) work list")
    sp.add_argument("specs", nargs="+", help="proc=N or proc=a-b")
    sp.add_argument("-o", "--out", default="manifest.txt")
    sp.set_defaults(func=cmd_manifest)

    sp = sub.add_parser("submit", help="submit a SLURM array")
    sp.add_argument("--manifest", help="manifest file (manifest mode)")
    sp.add_argument("--proc", help="process name (seed mode)")
    sp.add_argument("--seeds", help="seed range, e.g. 1-20 (seed mode)")
    sp.add_argument("--nevt", type=int, required=True, help="events per (proc, seed)")
    sp.add_argument("--cap", type=int, help="max concurrent array tasks (%%N)")
    sp.add_argument("--burst", action="store_true", help="use avery-b preemptible qos")
    sp.add_argument("--cleanup", action="store_true")
    sp.add_argument("--dry-run", action="store_true", help="print the sbatch cmd, don't submit")
    sp.set_defaults(func=cmd_submit)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
