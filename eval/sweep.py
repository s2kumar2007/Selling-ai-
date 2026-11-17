"""Parameter sweep against the starter-kit buyers. Prints score by config. Usage: python eval/sweep.py"""
import itertools
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "starter_kit"))
sys.path.insert(0, str(ROOT))

import buyers as pb  # noqa: E402  (starter kit buyers.py)
import evaluate as ev  # noqa: E402
from harness import load_policy, load_store  # noqa: E402

from seller_agent.agent import Seller  # noqa: E402
from seller_agent.config import Config  # noqa: E402


def score(cfg, seed=0, n=210):
    store, policy = load_store(), load_policy()
    scen = pb.make_scenarios(store, policy, n, seed, pb.BUYERS)
    cls = lambda s, p: Seller(s, p, cfg)  # noqa: E731
    res, _, _ = ev.run(cls, scen, pb.BUYERS, store, policy)
    return ev.summarise(res)


if __name__ == "__main__":
    base = Config()
    grid = {"beta": [0.5, 0.8, 1.2], "final_start": [6, 8, 9], "accept_gain": [1.0, 0.5, 0.3],
            "accept_gain_decay": [0.0, 0.05]}
    rows = []
    for vals in itertools.product(*grid.values()):
        cfg = replace(base, **dict(zip(grid, vals)))
        s = score(cfg)
        rows.append((s["score"], vals, s))
    rows.sort(key=lambda r: -r[0])
    print(list(grid))
    for sc, vals, s in rows[:10]:
        print(f"{sc:5.1f} {vals} deal={s['deal_rate']:.2f} margin={s['margin_kept']:.2f} dl={s['deadlocks']} pol={s['policy']} truth={s['truth']}")
