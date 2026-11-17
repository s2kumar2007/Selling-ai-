"""Play one negotiation and write demo/panel.html (claims, local check, TraceWare verdict + evidence per message).

  python scripts/demo_run.py --persona injector --seed 3
"""
from __future__ import annotations

import argparse
import json
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", default="injector", choices=sorted(BUYERS))
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "demo" / "panel.html"))
    a = ap.parse_args()
    store, policy, cfg = load_store(), load_policy(), Config.load()
    sc = pb.make_scenarios(store, policy, 1, a.seed, {a.persona: BUYERS[a.persona]})[0]
    seller = Seller(store, policy, cfg)
    res = run_negotiation(seller, BUYERS[a.persona](sc, store, random.Random(sc["seed"])), store, policy, sc["id"])
    deal = res["deal"]
    data = {"persona": a.persona, "seed": a.seed, "ended": res["ended"], "deal": deal,
            "deal_total": sum(i["qty"] * i["unit_price"] for i in deal) if deal else 0,
            "violations": res["violations"], "transcript": res["transcript"], "trace": seller.traces,
            "traceware_configured": seller.traceware is not None,
            "blocked": sum(1 for t in seller.traces if len(t["attempts"]) > 1 or t.get("fallback"))}
    html = (ROOT / "demo" / "panel_template.html").read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    Path(a.out).write_text(html, encoding="utf-8")
    print("wrote", a.out, "| ended:", res["ended"], "| harness violations:", len(res["violations"]))


if __name__ == "__main__":
    main()
