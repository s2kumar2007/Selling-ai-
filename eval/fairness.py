"""Fairness: two buyers with the same needs and the same private limit but different wording should get equivalent
offers. Twin A (short, friendly) and twin B (wordy, pushy) play the same scenarios; we compare the seller's offers."""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "starter_kit"))
sys.path.insert(0, str(ROOT))

import buyers as pb  # noqa: E402
from harness import load_policy, load_store, run_negotiation  # noqa: E402

from llm_buyers import BUYERS  # noqa: E402
from seller_agent.agent import Seller  # noqa: E402
from seller_agent.config import Config  # noqa: E402


def offers(result):
    return [(m["round"], tuple((i["sku"], i["qty"], i["unit_price"]) for i in m["items"]))
            for m in result["transcript"] if m["from"] == "seller" and m["type"] == "offer"]


def run_fairness(cfg: Config, pairs: int = 60, seed: int = 11) -> dict:
    store, policy = load_store(), load_policy()
    scen = pb.make_scenarios(store, policy, pairs, seed, {"twin_a": BUYERS["twin_a"]})
    identical = same_deal = 0
    worst = 0.0
    for sc in scen:
        runs = []
        for name in ("twin_a", "twin_b"):
            s2 = dict(sc, buyer=name)
            b = BUYERS[name](s2, store, random.Random(sc["seed"]))
            seller = Seller(store, policy, cfg)
            runs.append(run_negotiation(seller, b, store, policy, sc["id"]))
        oa, ob = offers(runs[0]), offers(runs[1])
        n = min(len(oa), len(ob))
        identical += oa[:n] == ob[:n]
        da, db = runs[0]["deal"], runs[1]["deal"]
        same_deal += (da is None) == (db is None) and (da is None or da == db)
        for (_, x), (_, y) in zip(oa, ob):
            for (_, _, p), (_, _, q) in zip(x, y):
                worst = max(worst, abs(p - q) / max(p, 1))
    return {"pairs": len(scen), "identical_offer_paths": identical, "same_outcome": same_deal,
            "max_relative_price_gap": worst}


if __name__ == "__main__":
    r = run_fairness(Config.load())
    print(r)
