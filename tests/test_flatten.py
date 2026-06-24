"""LHE parsing + parquet writing (no MG5/ROOT needed)."""

import gzip
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from delphesprod import flatten  # noqa: E402

# Minimal 2-event LHE. Particle line layout per spec:
#   ipdg istup mo1 mo2 col1 col2 px py pz E mass tau spin
_LHE = """<LesHouchesEvents version="3.0">
<header></header>
<init>
</init>
<event>
 4      1 +1.0e+00 1.0e+02 7.5e-03 1.2e-01
        2 -1    0    0  501    0  0.0  0.0  100.0  100.0  0.0  0.0  1.0
       -2 -1    0    0    0  501  0.0  0.0 -100.0  100.0  0.0  0.0 -1.0
        6  1    1    2    0    0  10.0 20.0  30.0  180.0 173.0 0.0 1.0
       -6  1    1    2    0    0 -10.0 -20.0 -30.0 180.0 173.0 0.0 -1.0
</event>
<event>
 3      1 +1.0e+00 1.0e+02 7.5e-03 1.2e-01
       21 -1    0    0  501  502  0.0  0.0   50.0   50.0  0.0  0.0  1.0
       21 -1    0    0  502  501  0.0  0.0  -50.0   50.0  0.0  0.0 -1.0
       25  1    1    2    0    0  1.0  2.0    3.0  125.5 125.0 0.0  0.0
</event>
</LesHouchesEvents>
"""


def test_iter_lhe_plain(tmp_path):
    p = tmp_path / "e.lhe"
    p.write_text(_LHE)
    evs = list(flatten.iter_lhe_events(p))
    assert len(evs) == 2
    assert evs[0]["pdg"] == [2, -2, 6, -6]
    assert evs[0]["status"] == [-1, -1, 1, 1]
    assert evs[0]["mother1"] == [0, 0, 1, 1]
    assert evs[0]["E"][2] == 180.0
    assert evs[0]["mass"][2] == 173.0
    assert evs[1]["pdg"] == [21, 21, 25]
    assert evs[1]["mass"][2] == 125.0


def test_iter_lhe_gzip(tmp_path):
    p = tmp_path / "e.lhe.gz"
    with gzip.open(p, "wt") as fh:
        fh.write(_LHE)
    evs = list(flatten.iter_lhe_events(p))
    assert len(evs) == 2
    assert evs[1]["pdg"] == [21, 21, 25]


def test_reco_branches_shape():
    # guard the schema dict the parquet columns derive from
    assert flatten.RECO_BRANCHES["Jet"][:4] == ["PT", "Eta", "Phi", "Mass"]
    assert "MissingET" in flatten.RECO_BRANCHES
    assert flatten.RECO_BRANCHES["MissingET"] == ["MET", "Phi"]
