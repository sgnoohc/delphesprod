"""Card-bundle resolution + discovery."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from delphesprod import cards  # noqa: E402


def test_list_includes_example():
    assert "ttbar_semilep" in cards.list_processes()
    # reserved dirs are not processes
    assert "_template" not in cards.list_processes()
    assert "defaults" not in cards.list_processes()


def test_resolve_falls_back_to_defaults():
    b = cards.resolve("ttbar_semilep")
    assert b.process.name == "process.mg5"
    assert b.process.parent.name == "ttbar_semilep"
    # ttbar_semilep ships no per-process shower/detector card -> shared defaults
    assert b.pythia8 == ROOT / "cards" / "defaults" / "pythia8.cmnd"
    assert b.delphes == ROOT / "cards" / "defaults" / "delphes_CMS.tcl"
    assert b.run_opts is None
    assert b.madspin is None


def test_resolve_missing_raises():
    try:
        cards.resolve("does_not_exist")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")


def test_bundle_env_keys():
    e = cards.resolve("ttbar_semilep").env()
    assert e["DPROD_CARD_PROCESS"].endswith("ttbar_semilep/process.mg5")
    assert e["DPROD_CARD_RUNOPTS"] == ""
    assert e["DPROD_CARD_MADSPIN"] == ""


def test_template_sidecars_inactive():
    """The .example suffix keeps template sidecars from auto-activating."""
    tmpl = ROOT / "cards" / "_template"
    assert (tmpl / "process.mg5").is_file()
    assert not (tmpl / "madspin.dat").exists()
    assert (tmpl / "madspin.dat.example").is_file()
