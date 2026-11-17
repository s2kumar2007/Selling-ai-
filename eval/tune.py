"""Milestone 14: tune beta, opening discount, final-round start, accept thresholds and the last-round gamble.
Train = starter-kit bots, seeds 0-2. Held-out = persona buyers on seeds 20-22 (never used to pick parameters).
The floor and policy are never parameters. beta stays < 1 (Boulware)."""
from __future__ import annotations

import itertools
import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "starter_kit"))
sys.path.insert(0, str(ROOT))

import buyers as pb  # noqa: E402
import evaluate as ev  # noqa: E402
from harness import load_policy, load_store  # noqa: E402

from llm_buyers import BUYERS as LLM  # noqa: E402
from seller_agent.agent import Seller  # noqa: E402
from seller_agent.config import Config  # noqa: E402

TRAIN_SEEDS, HELD_SEEDS = (0, 1, 2), (20, 21, 22)


def score(cfg: Config, buyers, seeds, n=210):
    store, policy = load_store(), load_policy()
    out = []
    for sd in seeds:
        scen = pb.make_scenarios(store, policy, n, sd, buyers)
        res, _, _ = ev.run(lambda s, p: Seller(s, p, cfg), scen, buyers, store, policy)
        out.append(ev.summarise(res))
    return {"score": statistics.mean(o["score"] for o in out), "policy": sum(o["policy"] for o in out),
            "truth": sum(o["truth"] for o in out), "deadlocks": sum(o["deadlocks"] for o in out),
            "deal_rate": statistics.mean(o["deal_rate"] for o in out),
            "margin": statistics.mean(o["margin_kept"] for o in out)}


GRID = {"beta": [0.5, 0.8, 0.95], "open_discount": [0.0, 0.03], "final_start": [7, 8, 9],
        "accept_gain": [1.0, 0.6], "gamble_min_ratio": [0.7, 0.85, 1.0]}


def main() -> None:
    base = Config.load()
    rows = []
    for vals in itertools.product(*GRID.values()):
        cfg = replace(base, **dict(zip(GRID, vals)))
        rows.append((score(cfg, pb.BUYERS, TRAIN_SEEDS, 120), vals))
    rows.sort(key=lambda r: (-r[0]["policy"] * -1 if False else 0, -r[0]["score"]))
    ok = [r for r in rows if r[0]["policy"] == 0 and r[0]["truth"] == 0]
    best_cfg = dict(zip(GRID, ok[0][1]))
    print("top 5 on TRAIN (starter bots):")
    for t, v in ok[:5]:
        print(f"  {t['score']:5.1f} {dict(zip(GRID, v))} deals={t['deal_rate']:.3f} margin={t['margin']:.3f} dl={t['deadlocks']}")
    cur = score(base, LLM, HELD_SEEDS)
    best = score(replace(base, **best_cfg), LLM, HELD_SEEDS)
    print(f"\nHELD-OUT (persona buyers, seeds {HELD_SEEDS}):")
    print(f"  current defaults {cur['score']:.1f} (pol {cur['policy']}, truth {cur['truth']}, dl {cur['deadlocks']})")
    print(f"  tuned            {best['score']:.1f} (pol {best['policy']}, truth {best['truth']}, dl {best['deadlocks']})")
    Path(ROOT / "eval/out").mkdir(exist_ok=True)
    (ROOT / "eval/out/tune_result.json").write_text(json.dumps(
        {"best_on_train": best_cfg, "held_out_tuned": best, "held_out_current": cur}, indent=2))


if __name__ == "__main__":
    main()
