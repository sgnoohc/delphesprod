"""`delphesprod bootstrap` — install the MG5/Pythia8/Delphes tree from scratch.

This is the mandatory first-run step (the package ships no shared default
``mg5_home``). It:

1. downloads the pinned MG5_aMC release into ``[bootstrap].prefix``;
2. runs ``install pythia8`` / ``install mg5amc_py8_interface`` / ``install Delphes``
   WITH the CVMFS CMSSW environment active, so the freshly-built Delphes is
   ABI-matched to the same ROOT the package sources at runtime;
3. writes the resulting ``mg5_home`` back into ``config.toml``.

Note: this downloads ~hundreds of MB and compiles for ~20-30 min — it needs
network access and the CVMFS CMSSW toolchain. It is the one step that cannot be
exercised in a unit test.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from delphesprod.config import Config, PROJECT_ROOT


def _mg5_url(cfg: Config) -> str:
    # A site can pre-stage the tarball and point [bootstrap].url at it (a local
    # path or file:// URL); this is the robust HPG pattern since launchpad's
    # download URL scheme is unstable. Otherwise fall back to launchpad.
    override = cfg.get("bootstrap", "url", "")
    if override:
        return override
    ver = cfg.mg5_version                       # e.g. "3.5.0"
    major, minor = ver.split(".")[:2]
    series = f"{major}.{minor}.x"               # "3.5.x"
    return (f"https://launchpad.net/mg5amcnlo/3.0/{series}/+download/"
            f"MG5_aMC_v{ver}.tar.gz")


def _fetch(url: str, dest: Path) -> None:
    """Fetch the MG5 tarball to ``dest`` — http(s), file://, or a local path."""
    if url.startswith(("http://", "https://", "ftp://")):
        urllib.request.urlretrieve(url, dest)
        return
    src = url[len("file://"):] if url.startswith("file://") else url
    src_path = Path(src)
    if not src_path.is_file():
        raise FileNotFoundError(f"local MG5 tarball not found: {src_path}")
    shutil.copy(src_path, dest)


def _mg5_dirname(cfg: Config) -> str:
    # MG5 extracts to a dir with underscores: MG5_aMC_v3_5_0
    return "MG5_aMC_v" + cfg.mg5_version.replace(".", "_")


def _download_and_extract(cfg: Config, prefix: Path) -> Path:
    url = _mg5_url(cfg)
    tarball = prefix / f"MG5_aMC_v{cfg.mg5_version}.tar.gz"
    print(f"[bootstrap] fetching MG5 tarball from {url}")
    _fetch(url, tarball)
    print(f"[bootstrap] extracting {tarball.name}")
    with tarfile.open(tarball) as tf:
        tf.extractall(prefix)
    tarball.unlink(missing_ok=True)
    mg5_home = prefix / _mg5_dirname(cfg)
    if not mg5_home.is_dir():
        # Fall back to whatever top-level MG5_aMC* dir the tar produced.
        cands = sorted(prefix.glob("MG5_aMC_v*"))
        if not cands:
            raise RuntimeError(f"extraction produced no MG5_aMC_v* dir under {prefix}")
        mg5_home = cands[-1]
    return mg5_home


def _cmssw_preamble(cfg: Config) -> str:
    """Bash that activates the CVMFS CMSSW ROOT toolchain (mirrors setup/env.sh)."""
    src = f"/cvmfs/cms.cern.ch/{cfg.scram_arch}/cms/cmssw/{cfg.cmssw}/src"
    return (
        "set -e\n"
        f"export SCRAM_ARCH={cfg.scram_arch}\n"
        "source /cvmfs/cms.cern.ch/cmsset_default.sh\n"
        f"cd {src}\n"
        'eval "$(scramv1 runtime -sh)"\n'
        "cd - >/dev/null\n"
    )


def _run_installs(cfg: Config, mg5_home: Path) -> None:
    mg5_bin = mg5_home / "bin" / "mg5_aMC"
    install_script = mg5_home / "dprod_install.dat"
    install_script.write_text(
        "install pythia8\n"
        "install mg5amc_py8_interface\n"
        "install Delphes\n"
    )
    bash = _cmssw_preamble(cfg) + f'"{mg5_bin}" "{install_script}"\n'
    # NOTE: these `install` steps fetch the LATEST HEPTools (e.g. Pythia 8.316),
    # not the versions contemporaneous with mg5_version. The stage scripts are
    # written to be robust to that. Delphes logs a harmless compile error for
    # DelphesCMSFWLite (needs CMS FWLite libs absent here); the binary we use,
    # DelphesHepMC2, builds fine before it.
    print("[bootstrap] running MG5 install pythia8 / py8 interface / Delphes "
          "(this takes ~20-30 min) ...")
    subprocess.run(["bash", "-c", bash], check=True)
    install_script.unlink(missing_ok=True)


def _write_mg5_home(mg5_home: Path) -> None:
    """Set [tools].mg5_home in config.toml (create from example if needed)."""
    cfg_path = PROJECT_ROOT / "config.toml"
    if not cfg_path.is_file():
        shutil.copy(PROJECT_ROOT / "config.example.toml", cfg_path)
    text = cfg_path.read_text()
    line = f'mg5_home    = "{mg5_home}"'
    new, n = re.subn(r'^\s*mg5_home\s*=.*$', line, text, count=1, flags=re.MULTILINE)
    if n == 0:
        new = text + f"\n[tools]\n{line}\n"
    cfg_path.write_text(new)
    print(f"[bootstrap] wrote mg5_home to {cfg_path}")


def bootstrap(cfg: Config | None = None) -> int:
    cfg = cfg or Config()
    prefix = Path(cfg.bootstrap_prefix)
    prefix.mkdir(parents=True, exist_ok=True)

    mg5_home = prefix / _mg5_dirname(cfg)
    if (mg5_home / "bin" / "mg5_aMC").exists():
        print(f"[bootstrap] reusing existing MG5 at {mg5_home}")
    else:
        mg5_home = _download_and_extract(cfg, prefix)

    _run_installs(cfg, mg5_home)
    _write_mg5_home(mg5_home)

    print("[bootstrap] done. Verify with:  source setup/env.sh && delphesprod doctor")
    return 0
