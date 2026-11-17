import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "starter_kit"))

import harness  # noqa: E402  (organisers' reference implementation)

from seller_agent.floor import binding_constraint, floor_price, is_sellable, max_qty  # noqa: E402
from seller_agent.store import (Policy, Product, load_policy, load_store, policy_from_dict,  # noqa: E402
                                store_from_rows)

POLICY = Policy(max_discount=0.25, min_margin={"apparel": 0.3, "accessories": 0.35})


def P(price, cost, stock=5, category="apparel"):
    return Product("X1", "x", category, "b", price, cost, stock)


def test_matches_harness_for_every_product():
    store, policy = load_store(), load_policy()
    h_store, h_policy = harness.load_store(ROOT / "starter_kit" / "store.csv"), harness.load_policy(
        ROOT / "starter_kit" / "policy.json")
    assert len(store) == 100
    for sku, p in store.items():
        assert floor_price(p, policy) == harness.floor_price(h_store[sku], h_policy), sku


def test_floor_never_fails_harness_policy_check():
    store, policy = load_store(), load_policy()
    h_store, h_policy = harness.load_store(ROOT / "starter_kit" / "store.csv"), harness.load_policy(
        ROOT / "starter_kit" / "policy.json")
    for sku, p in store.items():
        items = [{"sku": sku, "qty": 1, "unit_price": floor_price(p, policy)}]
        bad = [v for v in harness.check_items(items, h_store, h_policy) if v["kind"] != "policy:out_of_stock"]
        assert bad == [], (sku, bad)


def test_margin_binds_when_cost_is_high():
    p = P(price=1000, cost=800)             # margin floor 1142.86 > discount floor 750
    assert binding_constraint(p, POLICY) == "margin"
    assert floor_price(p, POLICY) == 1143
    assert not is_sellable(p, POLICY)       # floor above list: no compliant price exists


def test_discount_binds_when_cost_is_low():
    p = P(price=1000, cost=100)             # margin floor 142.9 < discount floor 750
    assert binding_constraint(p, POLICY) == "discount"
    assert floor_price(p, POLICY) == 750


def test_conflict_takes_the_higher_floor():
    p = P(price=1000, cost=560)             # margin floor 800 > discount floor 750
    assert floor_price(p, POLICY) == 800
    assert binding_constraint(p, POLICY) == "margin"


def test_floor_rounds_up_never_down():
    p = P(price=1001, cost=100)             # 750.75 -> 751
    assert floor_price(p, POLICY) == 751


def test_zero_stock_is_not_sellable():
    p = P(price=1000, cost=100, stock=0)
    assert not is_sellable(p, POLICY)
    assert max_qty(p, POLICY, 3) == 0


def test_max_qty_capped_by_stock():
    p = P(price=1000, cost=100, stock=2)
    assert max_qty(p, POLICY, 5) == 2
    assert max_qty(p, POLICY, 1) == 1
    assert max_qty(p, POLICY, 0) == 0


def test_store_from_rows_accepts_harness_dict():
    rows = harness.load_store(ROOT / "starter_kit" / "store.csv")
    store = store_from_rows(rows)
    assert store["S001"].stock == 1 and store["S001"].price == 2299
    assert policy_from_dict({"max_discount": 0.25, "min_margin": {"a": 0.1}}).max_rounds == 10


def test_unsellable_products_in_catalogue():
    store, policy = load_store(), load_policy()
    assert sum(1 for p in store.values() if p.stock == 0) == 15
    assert all(floor_price(p, policy) <= p.price for p in store.values())
