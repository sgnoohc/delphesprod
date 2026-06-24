"""Card-bundle discovery and resolution.

One process == one directory under ``cards/``. Only ``process.mg5`` is required;
the optional sidecars fall back to the shared ``cards/defaults/`` where one
exists. Resolution order for every file:

    cards/<proc>/<file>  ->  cards/defaults/<default>  ->  None (optional) / error (required)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from delphesprod.config import PROJECT_ROOT


def cards_dir() -> Path:
    return Path(os.environ.get("DPROD_CARDS_DIR") or (PROJECT_ROOT / "cards"))


# Reserved directory names that are not processes.
_RESERVED = {"_template", "defaults"}


@dataclass
class CardBundle:
    """Resolved set of card paths for one process."""

    name: str
    process: Path                    # required — the MG5 proc card
    run_opts: Optional[Path]         # optional — MG5 launch overrides
    madspin: Optional[Path]          # optional — MadSpin card
    pythia8: Path                    # resolved (process or default)
    delphes: Path                    # resolved (process or default)

    def env(self) -> dict:
        """The DPROD_CARD_* env vars the bash stages read."""
        e = {
            "DPROD_CARD_PROCESS": str(self.process),
            "DPROD_CARD_PYTHIA": str(self.pythia8),
            "DPROD_CARD_DELPHES": str(self.delphes),
            "DPROD_CARD_RUNOPTS": str(self.run_opts) if self.run_opts else "",
            "DPROD_CARD_MADSPIN": str(self.madspin) if self.madspin else "",
        }
        return e


def _resolve(proc_dir: Path, name: str, default: Optional[Path]) -> Optional[Path]:
    local = proc_dir / name
    if local.is_file():
        return local
    if default is not None and default.is_file():
        return default
    return None


def resolve(name: str) -> CardBundle:
    """Resolve the card bundle for ``name`` or raise ``FileNotFoundError``."""
    cd = cards_dir()
    proc_dir = cd / name
    defaults = cd / "defaults"

    process = proc_dir / "process.mg5"
    if not process.is_file():
        raise FileNotFoundError(
            f"no process card at {process}\n"
            f"  create one with:  delphesprod init {name}"
        )

    pythia = _resolve(proc_dir, "pythia8.cmnd", defaults / "pythia8.cmnd")
    if pythia is None:
        raise FileNotFoundError(
            f"no pythia8.cmnd for '{name}' and no default at {defaults/'pythia8.cmnd'}")
    delphes = _resolve(proc_dir, "delphes.tcl", defaults / "delphes_CMS.tcl")
    if delphes is None:
        raise FileNotFoundError(
            f"no delphes.tcl for '{name}' and no default at {defaults/'delphes_CMS.tcl'}")

    return CardBundle(
        name=name,
        process=process,
        run_opts=_resolve(proc_dir, "run.opts", None),
        madspin=_resolve(proc_dir, "madspin.dat", None),
        pythia8=pythia,
        delphes=delphes,
    )


def list_processes() -> List[str]:
    """Every directory under cards/ that holds a process.mg5 (sorted)."""
    cd = cards_dir()
    if not cd.is_dir():
        return []
    out = []
    for p in sorted(cd.iterdir()):
        if p.is_dir() and p.name not in _RESERVED and (p / "process.mg5").is_file():
            out.append(p.name)
    return out


def describe(name: str) -> str:
    """One-line summary of which optional cards a process carries."""
    b = resolve(name)
    flags = []
    if b.run_opts:
        flags.append("run.opts")
    if b.madspin:
        flags.append("madspin")
    if b.pythia8.parent.name == name:
        flags.append("pythia8*")
    if b.delphes.parent.name == name:
        flags.append("delphes*")
    extras = (" [" + ", ".join(flags) + "]") if flags else ""
    return f"{name}{extras}"
