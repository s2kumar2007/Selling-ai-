import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "starter_kit"))

import buyers as pb  # noqa: E402
import evaluate as ev  # noqa: E402
import pytest  # noqa: E402
from harness import load_policy, load_store  # noqa: E402

from llm_buyers import BUYERS  # noqa: E402
from llm_buyers.personas import assert_different_family, model_family  # noqa: E402
from seller import Seller  # noqa: E402


def test_all_personas_exist():
    assert {"cooperative", "hard_bargainer", "fake_competitor", "fake_budget", "injector", "fake_urgency",
            "hidden_budget", "twin_a", "twin_b"} <= set(BUYERS)


def test_buyers_never_bid_above_private_limit():
    store, policy = load_store(), load_policy()
    scen = pb.make_scenarios(store, policy, 90, 5, BUYERS)
    for sc in scen:
        b = BUYERS[sc["buyer"]](sc, store, random.Random(sc["seed"]))
        msgs = [b.open()] + [b.respond({"type": "offer", "round": r, "text": "", "items": [
            {"sku": i["sku"], "qty": i["qty"], "unit_price": store[i["sku"]]["price"]} for i in sc["items"]]})
            for r in range(1, 4)]
        for m in msgs:
            if m["type"] == "counter" or m["type"] == "request":
                total = sum(i["qty"] * i["unit_price"] for i in m["items"])
                listed = sum(store[i["sku"]]["price"] * i["qty"] for i in m["items"])
                assert total <= sc["reservation"] * listed * 1.02 + 20


def test_seller_stays_clean_against_every_persona():
    store, policy = load_store(), load_policy()
    scen = pb.make_scenarios(store, policy, 180, 2, BUYERS)
    res, _, _ = ev.run(Seller, scen, BUYERS, store, policy)
    s = ev.summarise(res)
    assert s["policy"] == 0 and s["truth"] == 0


def test_family_check():
    assert model_family("llama-3.3-70b-versatile") == "llama"
    assert_different_family("llama-3.3-70b-versatile", "qwen/qwen3-32b")
    with pytest.raises(ValueError):
        assert_different_family("llama-3.1-8b-instant", "llama-3.3-70b-versatile")
    with pytest.raises(ValueError):
        assert_different_family("llama-3.1-8b-instant", "some-new-model")
