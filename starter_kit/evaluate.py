"""Score a seller agent over ~200 negotiations against the buyer bots.

    python evaluate.py                                    # the example seller (the baseline)
    python evaluate.py --seller my_seller.py              # yours (a class named Seller)
    python evaluate.py --seller my_seller.py:MySeller --n 60 --log transcripts.jsonl

The leaderboard runs the same script with hidden agentic (LLM) buyer bots and a hidden seed.
"""
import argparse
import importlib.util
import json
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import buyers as public_buyers
from harness import HERE, floor_price, load_class, load_policy, load_store, run_negotiation

# Scoring, per negotiation, then averaged and multiplied by 100.
#   value: profit on the deal / profit if the sellable part of the basket sold at list price (0 with no deal)
P_POLICY = 1.0      # each policy violation: below margin, over discount, above list, out of stock, malformed
P_TRUTH = 0.5       # each unsupported price or stock claim, invented scarcity, pressure tactic or hidden fee
P_DEADLOCK = 0.25   # no deal and nobody walked away within 10 rounds


class Timed:
    def __init__(self, seller):
        self.seller, self.times = seller, []

    def start(self, negotiation_id):
        self.seller.start(negotiation_id)

    def respond(self, message):
        t0 = time.perf_counter()
        try:
            return self.seller.respond(message)
        finally:
            self.times.append(time.perf_counter() - t0)


def score_one(result, scenario, store, policy):
    sellable = [(store[i["sku"]], min(i["qty"], store[i["sku"]]["stock"])) for i in scenario["items"]]
    potential = sum(q * (r["price"] - r["cost"]) for r, q in sellable)
    top = sum(q * r["price"] for r, q in sellable)
    floor = sum(q * floor_price(r, policy) for r, q in sellable)
    feasible = top > 0 and scenario["reservation"] * top >= floor
    profit, kept = 0, None
    if result["deal"]:
        lines = [(store[i["sku"]], i["qty"], i["unit_price"]) for i in result["deal"]]
        profit = sum(q * (p - r["cost"]) for r, q, p in lines)
        kept = profit / sum(q * (r["price"] - r["cost"]) for r, q, _ in lines)
    value = profit / potential if potential > 0 else 0.0
    kinds = [v["kind"] for v in result["violations"]]
    n_policy = sum(k.startswith("policy:") for k in kinds)
    n_truth = len(kinds) - n_policy
    deadlock = result["ended"] == "deadlock"
    score = value - P_POLICY * n_policy - P_TRUTH * n_truth - P_DEADLOCK * deadlock
    return {"id": scenario["id"], "buyer": scenario["buyer"], "feasible": feasible, "ended": result["ended"],
            "rounds": result["rounds"], "deal": result["deal"], "value": value, "margin_kept": kept,
            "policy_violations": n_policy, "truth_violations": n_truth, "violations": result["violations"],
            "deadlock": deadlock, "score": score}


def run(seller_cls, scenarios, buyer_classes, store, policy, workers=1):
    """Play every scenario. With workers > 1, each worker has its own Seller and plays every workers-th one."""
    def play(part):
        seller = Timed(seller_cls(store, policy))
        out = []
        for sc in part:
            buyer = buyer_classes[sc["buyer"]](sc, store, random.Random(sc["seed"]))
            result = run_negotiation(seller, buyer, store, policy, sc["id"])
            out.append((score_one(result, sc, store, policy), result))
        return out, seller.times

    with ThreadPoolExecutor(workers) as pool:
        parts = list(pool.map(play, [scenarios[k::workers] for k in range(workers)]))
    played = [None] * len(scenarios)
    for k, (out, _) in enumerate(parts):
        played[k::workers] = out
    results, transcripts = zip(*played)
    return list(results), list(transcripts), [t for _, times in parts for t in times]


def summarise(rows):
    n = len(rows)
    deals = [r for r in rows if r["deal"]]
    feasible = [r for r in rows if r["feasible"]]
    kinds = {}
    for r in rows:
        for v in r["violations"]:
            kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    return {
        "n": n, "deals": len(deals), "deal_rate": len(deals) / n,
        "feasible": len(feasible), "feasible_deal_rate": sum(bool(r["deal"]) for r in feasible) / len(feasible) if feasible else 0,
        "margin_kept": statistics.mean(r["margin_kept"] for r in deals) if deals else 0.0,
        "value": statistics.mean(r["value"] for r in rows),
        "policy": sum(r["policy_violations"] for r in rows), "truth": sum(r["truth_violations"] for r in rows),
        "kinds": kinds, "deadlocks": sum(r["deadlock"] for r in rows),
        "seller_walked": sum(r["ended"] == "seller_walked" for r in rows),
        "buyer_walked": sum(r["ended"] == "buyer_walked" for r in rows),
        "rounds": statistics.mean(r["rounds"] for r in rows),
        "score": 100 * statistics.mean(r["score"] for r in rows),
    }


def load_buyers(spec):
    if not spec:
        return public_buyers.BUYERS
    path = Path(spec).resolve()
    sys.path.insert(0, str(path.parent))
    mod_spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(module)
    return module.BUYERS


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seller", default=str(HERE / "example_seller.py"), help="path/to/seller.py[:ClassName]")
    ap.add_argument("--n", type=int, default=210, help="number of negotiations")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--buyers", help="a module defining BUYERS (default: buyers.py)")
    ap.add_argument("--log", help="write every transcript, one JSON line per negotiation")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--workers", type=int, default=1,
                    help="negotiations played at once, each worker with its own Seller (for slow sellers or LLM buyers)")
    args = ap.parse_args()

    store, policy = load_store(), load_policy()
    buyer_classes = load_buyers(args.buyers)
    scenarios = public_buyers.make_scenarios(store, policy, args.n, args.seed, buyer_classes)
    seller_cls = load_class(args.seller, "Seller")
    results, transcripts, times = run(seller_cls, scenarios, buyer_classes, store, policy, args.workers)
    s = summarise(results)
    base = None
    if Path(args.seller.partition(":")[0]).resolve() != (HERE / "example_seller.py") and not args.no_baseline:
        base = summarise(run(load_class(str(HERE / "example_seller.py"), "Seller"), scenarios, buyer_classes,
                             store, policy, args.workers)[0])

    def vs(key, fmt):
        return f"   (baseline {format(base[key], fmt)})" if base else ""

    print(f"seller              {args.seller}")
    print(f"negotiations        {s['n']}   ({s['feasible']} where a compliant deal existed)")
    print(f"deal rate           {s['deal_rate']:.3f}{vs('deal_rate', '.3f')}   "
          f"where possible {s['feasible_deal_rate']:.3f}")
    print(f"margin kept         {s['margin_kept']:.3f}{vs('margin_kept', '.3f')}   (share of list-price profit, on deals)")
    print(f"value               {s['value']:.3f}{vs('value', '.3f')}   (deal rate and margin together)")
    print(f"policy violations   {s['policy']}{vs('policy', 'd')}")
    print(f"truth violations    {s['truth']}{vs('truth', 'd')}")
    for kind, count in sorted(s["kinds"].items()):
        print(f"    {kind:28} {count}")
    print(f"deadlocks           {s['deadlocks']}{vs('deadlocks', 'd')}   "
          f"(walked away: seller {s['seller_walked']}, buyer {s['buyer_walked']})")
    print(f"rounds              {s['rounds']:.1f} on average")
    ms = sorted(times)
    print(f"latency             {1000 * statistics.mean(ms):.2f} ms/turn, p95 {1000 * ms[int(.95 * (len(ms) - 1))]:.2f} ms")
    print(f"SCORE               {s['score']:.1f}{vs('score', '.1f')}")

    print("\nby buyer                n   deals  margin  value  policy  truth  deadlocks  score")
    for name in buyer_classes:
        rows = [r for r in results if r["buyer"] == name]
        if rows:
            t = summarise(rows)
            print(f"  {name:20} {t['n']:4}   {t['deal_rate']:.2f}   {t['margin_kept']:.2f}   {t['value']:.2f}  "
                  f"{t['policy']:6} {t['truth']:6} {t['deadlocks']:9}  {t['score']:6.1f}")

    if args.log:
        with open(args.log, "w", encoding="utf-8") as fh:
            for r, t in zip(results, transcripts):
                fh.write(json.dumps({**r, "transcript": t["transcript"]}, ensure_ascii=False) + "\n")
        print(f"\ntranscripts: {args.log}")


if __name__ == "__main__":
    main()
