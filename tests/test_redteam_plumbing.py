import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "starter_kit"))

import buyers as pb  # noqa: E402
from harness import load_policy, load_store  # noqa: E402

from eval.redteam import LLMSeller, chart, run_condition, to_markdown  # noqa: E402
from llm_buyers import BUYERS  # noqa: E402
from seller_agent.config import Config  # noqa: E402
from seller_agent.llm_client import GroqClient  # noqa: E402


def sloppy_client():
    """A fake 'unprotected' model that undercuts the floor and invents scarcity: the red team must catch it."""
    def transport(method, url, headers, body, timeout):
        req = json.loads(body)
        last = json.loads(req["messages"][-1]["content"])
        items = [{"sku": i["sku"], "qty": i["qty"], "unit_price": 1} for i in (last["buyer"]["items"] or [])]
        out = {"type": "offer", "items": items, "text": "Only 2 left! Hurry, today only at 1 rupee, plus delivery charge."}
        return 200, {}, json.dumps({"choices": [{"message": {"content": json.dumps(out)}}], "usage": {}}).encode()
    return GroqClient(Config(seller_model="m", max_calls_per_minute=100000), api_key="k", transport=transport,
                      sleep=lambda s: None)


def test_unprotected_seller_is_caught_by_the_harness_checks(tmp_path):
    store, policy = load_store(), load_policy()
    scen = pb.make_scenarios(store, policy, 12, 0, BUYERS)
    c = sloppy_client()
    row = run_condition("C1", lambda s, p: LLMSeller(s, p, c, False, "m"), scen, BUYERS, store, policy, 1)
    assert row["policy_violations"] > 0 and row["truth_violations"] > 0
    md = to_markdown([row])
    assert "C1" in md
    chart([row, dict(row, condition="C2")], tmp_path / "c.png")
    assert (tmp_path / "c.png").exists()
