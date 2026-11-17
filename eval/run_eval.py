"""Milestone 12: 200+ negotiations; policy violations (must be 0), deal rate, margin kept, deadlocks, claim
mismatches, cost and latency. Writes a JSON summary and (optionally) full transcripts.

  python eval/run_eval.py --buyers public            # the starter-kit bots
  python eval/run_eval.py --buyers llm               # our persona buyers (scripted stand-in without a Groq key)
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "starter_kit"))
sys.path.insert(0, str(ROOT))

import buyers as pb  # noqa: E402
import evaluate as ev  # noqa: E402
from harness import load_policy, load_store  # noqa: E402

from llm_buyers import BUYERS as LLM_BUYERS  # noqa: E402
from seller_agent.agent import Seller  # noqa: E402
from seller_agent.config import Config  # noqa: E402


def make_factory(cfg: Config, sink: list):
    lock = threading.Lock()

    def factory(store, policy):
        s = Seller(store, policy, cfg)
        with lock:
            sink.append(s)
        return s

    return factory


def collect(cfg: Config, sellers: list, n: int) -> dict:
    calls = sum(s.client.usage.calls for s in sellers if s.client)
    ptok = sum(s.client.usage.prompt_tokens for s in sellers if s.client)
    ctok = sum(s.client.usage.completion_tokens for s in sellers if s.client)
    tw_calls = sum(s.traceware.calls for s in sellers if s.traceware)
    tw_credits = sum(s.traceware.credits for s in sellers if s.traceware)
    tw_out = sum(s.traceware.outages for s in sellers if s.traceware)
    fallbacks = sum(1 for s in sellers for t in s.traces if t.get("fallback"))
    return {"llm_calls": calls, "prompt_tokens": ptok, "completion_tokens": ctok,
            "llm_calls_per_negotiation": calls / n if n else 0, "traceware_calls": tw_calls,
            "traceware_credits": tw_credits, "traceware_credits_per_negotiation": tw_credits / n if n else 0,
            "traceware_outages": tw_out, "gate_fallbacks": fallbacks}


def run_eval(cfg: Config, buyers_mode: str, n: int, seed: int, workers: int, log: str | None = None) -> dict:
    store, policy = load_store(), load_policy()
    buyer_classes = pb.BUYERS if buyers_mode == "public" else LLM_BUYERS
    scen = pb.make_scenarios(store, policy, n, seed, buyer_classes)
    sink: list[Seller] = []
    results, transcripts, times = ev.run(make_factory(cfg, sink), scen, buyer_classes, store, policy, workers)
    s = ev.summarise(results)
    ms = sorted(times)
    by = {}
    for name in buyer_classes:
        rows = [r for r in results if r["buyer"] == name]
        if rows:
            t = ev.summarise(rows)
            by[name] = {k: t[k] for k in ("n", "deal_rate", "feasible_deal_rate", "margin_kept", "value", "policy",
                                           "truth", "deadlocks", "score")}
    out = {"seller": "seller.py", "buyers": buyers_mode, "seed": seed, "summary": s, "by_buyer": by,
           "latency_ms_mean": 1000 * statistics.mean(ms) if ms else 0.0,
           "latency_ms_p95": 1000 * ms[int(.95 * (len(ms) - 1))] if ms else 0.0,
           "claim_mismatches": s["truth"], "usage": collect(cfg, sink, len(scen)),
           "config": {k: v for k, v in vars(cfg).items() if k != "extra"}}
    if log:
        with open(log, "w", encoding="utf-8") as fh:
            for r, t in zip(results, transcripts):
                fh.write(json.dumps({**r, "transcript": t["transcript"]}, ensure_ascii=False) + "\n")
    return out


def show(o: dict) -> None:
    s, u = o["summary"], o["usage"]
    print(f"buyers {o['buyers']}  seed {o['seed']}  negotiations {s['n']} ({s['feasible']} feasible)")
    print(f"policy violations {s['policy']}   truth violations (claim mismatches) {s['truth']}   kinds {s['kinds']}")
    print(f"deal rate {s['deal_rate']:.3f}  (where possible {s['feasible_deal_rate']:.3f})  margin kept {s['margin_kept']:.3f}  "
          f"value {s['value']:.3f}")
    print(f"deadlocks {s['deadlocks']}  seller walked {s['seller_walked']}  buyer walked {s['buyer_walked']}  rounds {s['rounds']:.1f}")
    print(f"latency {o['latency_ms_mean']:.2f} ms/turn (p95 {o['latency_ms_p95']:.2f})   SCORE {s['score']:.1f}")
    print(f"LLM calls/negotiation {u['llm_calls_per_negotiation']:.2f}  tokens {u['prompt_tokens']}+{u['completion_tokens']}  "
          f"TraceWare calls {u['traceware_calls']} credits {u['traceware_credits']}  outages {u['traceware_outages']}  "
          f"gate fallbacks {u['gate_fallbacks']}")
    print("by buyer:")
    for k, v in o["by_buyer"].items():
        print(f"  {k:16} n={v['n']:3} deals={v['deal_rate']:.2f} margin={v['margin_kept']:.2f} pol={v['policy']} "
              f"truth={v['truth']} dl={v['deadlocks']} score={v['score']:.1f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--buyers", choices=["public", "llm"], default="public")
    ap.add_argument("--n", type=int, default=210)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", help="write the JSON summary here")
    ap.add_argument("--log", help="write full transcripts (jsonl) here")
    ap.add_argument("--config", help="config json path")
    a = ap.parse_args()
    o = run_eval(Config.load(a.config), a.buyers, a.n, a.seed, a.workers, a.log)
    show(o)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(o, indent=2, default=str), encoding="utf-8")
