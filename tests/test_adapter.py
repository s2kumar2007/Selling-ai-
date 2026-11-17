import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "starter_kit"))

import buyers as pb  # noqa: E402
import evaluate as ev  # noqa: E402
from harness import load_policy, load_store  # noqa: E402

from seller import Seller  # noqa: E402


def run_all(n=210, seed=0):
    store, policy = load_store(), load_policy()
    scen = pb.make_scenarios(store, policy, n, seed, pb.BUYERS)
    res, _, _ = ev.run(Seller, scen, pb.BUYERS, store, policy)
    return ev.summarise(res), res


def test_zero_violations_on_default_run():
    s, _ = run_all()
    assert s["policy"] == 0 and s["truth"] == 0


def test_beats_the_baseline_overall_and_zero_violations_per_bot():
    store, policy = load_store(), load_policy()
    scen = pb.make_scenarios(store, policy, 210, 0, pb.BUYERS)
    try:
        example_path = (ROOT / "starter_kit" / "example_seller.py").relative_to(Path.cwd()).as_posix()
    except ValueError:
        example_path = "starter_kit/example_seller.py"
    base = ev.summarise(ev.run(ev.load_class(example_path, "Seller"),
                               scen, pb.BUYERS, store, policy)[0])
    ours, res = run_all()
    assert ours["score"] > base["score"]
    for name in pb.BUYERS:
        rows = [r for r in res if r["buyer"] == name]
        t = ev.summarise(rows)
        assert t["policy"] == 0 and t["truth"] == 0, name


def test_zero_violations_across_seeds():
    for seed in (1, 2, 3):
        s, _ = run_all(120, seed)
        assert s["policy"] == 0 and s["truth"] == 0, seed
