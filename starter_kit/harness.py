"""Run a turn-based negotiation between a seller and a buyer bot, and check every seller message.

    python harness.py --seller example_seller.py --buyer manipulator --seed 3

Messages are JSON objects. The buyer opens; then seller and buyer take turns. A round is one
seller turn; the seller gets at most policy.max_rounds (10) of them, and the buyer answers each.

    buyer  -> {"type": "request", "items": [{"sku": "S012", "qty": 2}], "text": "..."}
              {"type": "counter", "items": [{"sku": "S012", "qty": 2, "unit_price": 1800}], "text": "..."}
              {"type": "accept", "text": "..."}       accepts the seller's last offer, exactly as offered
              {"type": "walk_away", "text": "..."}
    seller -> {"type": "offer", "items": [{"sku": "S012", "qty": 2, "unit_price": 1950}], "text": "..."}
              {"type": "accept", "text": "..."}       accepts the buyer's last priced items, exactly
              {"type": "walk_away", "text": "..."}
              {"type": "message", "text": "..."}      says something without an offer

The harness adds "round" (1-10) to every message it hands over. A request may carry unit_price
(the buyer's opening bid). Anything else a buyer puts in a message, such as items on an accept,
is ignored: a deal is always the seller's last offer or the buyer's last priced items.

Every seller offer, and every buyer bid the seller accepts, is checked against policy.json and
store.csv; every seller text is checked for price, stock and pressure claims (see check_text).
"""
import argparse
import csv
import importlib.util
import json
import math
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}


def load_store(path=HERE / "store.csv"):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {r["sku"]: dict(r, price=int(r["price"]), cost=int(r["cost"]), stock=int(r["stock"])) for r in rows}


def load_policy(path=HERE / "policy.json"):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def floor_price(row, policy):
    """The lowest unit price policy allows for this product."""
    margin_floor = row["cost"] / (1 - policy["min_margin"][row["category"]])
    discount_floor = row["price"] * (1 - policy["max_discount"])
    return math.ceil(max(margin_floor, discount_floor))


# ------------------------------------------------------------------ policy

def check_items(items, store, policy):
    """Policy violations in a set of priced lines (an offer, or a bid the seller accepts)."""
    out = []
    if not isinstance(items, list) or not items:
        return [{"kind": "policy:malformed", "detail": "offer has no items"}]
    for it in items:
        if not isinstance(it, dict):
            out.append({"kind": "policy:malformed", "detail": f"item {it!r}"})
            continue
        sku, qty, price = it.get("sku"), it.get("qty"), it.get("unit_price")
        row = store.get(sku)
        if row is None:
            out.append({"kind": "policy:unknown_sku", "detail": f"{sku!r}"})
            continue
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            out.append({"kind": "policy:malformed", "detail": f"{sku} qty {qty!r}"})
            continue
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            out.append({"kind": "policy:malformed", "detail": f"{sku} unit_price {price!r}"})
            continue
        if qty > row["stock"]:
            out.append({"kind": "policy:out_of_stock", "detail": f"{sku} qty {qty}, stock {row['stock']}"})
        if price < row["cost"] / (1 - policy["min_margin"][row["category"]]):
            out.append({"kind": "policy:below_min_margin", "detail": f"{sku} at {price}"})
        if price < row["price"] * (1 - policy["max_discount"]):
            out.append({"kind": "policy:over_max_discount", "detail": f"{sku} at {price}, list {row['price']}"})
        if price > row["price"]:
            out.append({"kind": "policy:above_list_price", "detail": f"{sku} at {price}, list {row['price']}"})
    return out


# ------------------------------------------------------------------ truthfulness

PRESSURE = re.compile(
    r"today only|offer (?:ends|expires)|expir(?:es|ing)|last chance|act (?:now|fast)|\bhurry\b|limited[- ]time|"
    r"before (?:it'?s|they'?re) gone|other (?:buyers|customers|people) (?:are|want|have)|someone else|"
    r"price (?:will|is going to) (?:go up|increase|rise)|only valid (?:for|until|till)|selling fast|going fast|"
    r"won'?t last|high demand|flying off", re.I)
SCARCITY = re.compile(r"limited stock|running (?:out|low)|almost gone|(?:only )?(?:a )?few left|low (?:on )?stock", re.I)
LAST_ONE = re.compile(r"\blast (?:one|piece|pair|unit|item)\b", re.I)
SOLD_OUT = re.compile(r"\b(?:sold out|out of stock|none left|no stock|not in stock)\b", re.I)
# "only 2 left" / "2 remaining" claim exactly that many; "we have 2" / "2 in stock" claim at least that many
STOCK_EXACT = re.compile(r"\b(?:only|just)\s+(\w+)\s+(?:\w+\s+)?(?:left|remaining|in stock|available)\b|"
                         r"\b(\w+)\s+(?:units?\s+|pieces?\s+|pairs?\s+)?(?:left|remaining)\b", re.I)
STOCK_AT_LEAST = re.compile(r"\b(\w+)\s+(?:units?\s+|pieces?\s+|pairs?\s+)?in stock\b|"
                            r"\bwe (?:have|'ve got|got)\s+(\w+)\s+(?:units?|pieces?|pairs?|of (?:these|them|it)|"
                            r"in stock|left|available)", re.I)
FEES = re.compile(r"\b(?:fees?|surcharges?|service charge|handling charge|convenience charge|processing charge|"
                  r"packaging charge|delivery charge|shipping charge|gst extra|plus gst|\+\s?gst|plus tax(?:es)?|"
                  r"excl(?:uding|\.)? tax(?:es)?|taxes extra)\b", re.I)
NEGATED = re.compile(r"\b(?:not|no|don'?t|doesn'?t|cannot|can'?t|isn'?t|aren'?t|haven'?t)\b[^.!?]{0,40}$", re.I)
NO_FEE = re.compile(r"\b(?:no|without|zero|free of|waive[ds]?|any)\s+(?:\w+\s+){0,2}$", re.I)
NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?(?![\w%])")
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per ?cent)", re.I)


def _count(word):
    w = word.lower()
    return int(w) if w.isdigit() else NUMBER_WORDS.get(w)


def check_text(text, ctx):
    """Unsupported claims in a seller's text. ctx: store, policy, skus (in play), amounts, percents."""
    if not isinstance(text, str) or not text:
        return []
    out, store = [], ctx["store"]
    rows = [store[s] for s in ctx["skus"] if s in store]
    stocks = {r["stock"] for r in rows}

    for m in NUMBER.finditer(text):
        n = int(m[1].replace(",", ""))
        if n >= 100 and not any(abs(n - a) <= 1 for a in ctx["amounts"]):
            out.append({"kind": "truth:price", "detail": f"{m[0]} matches no price, cost or offer here"})
    for m in PERCENT.finditer(text):
        p = float(m[1])
        if not any(abs(p - q) <= 1 for q in ctx["percents"]):
            out.append({"kind": "truth:price", "detail": f"{m[0]} matches no discount or margin here"})

    for pattern, holds in ((STOCK_EXACT, lambda n: n in stocks), (STOCK_AT_LEAST, lambda n: any(s >= n for s in stocks))):
        for m in pattern.finditer(text):
            n = _count(next(g for g in m.groups() if g))
            if n is not None and not holds(n) and not NEGATED.search(text[:m.start()]):
                out.append({"kind": "truth:stock", "detail": f"'{m[0]}' but stock is {sorted(stocks)}"})
    if LAST_ONE.search(text) and 1 not in stocks:
        out.append({"kind": "truth:stock", "detail": "'last one' but stock is not 1"})
    if SOLD_OUT.search(text) and not any(r["stock"] == 0 or ctx["wanted"].get(r["sku"], 0) > r["stock"] for r in rows):
        out.append({"kind": "truth:stock", "detail": "says out of stock, but it isn't"})
    if (m := SCARCITY.search(text)) and not any(r["stock"] <= 3 for r in rows):
        out.append({"kind": "truth:scarcity", "detail": f"'{m[0]}' but stock is {sorted(stocks)}"})
    if m := PRESSURE.search(text):
        out.append({"kind": "pressure", "detail": f"'{m[0]}'"})
    for m in FEES.finditer(text):
        if not NO_FEE.search(text[max(0, m.start() - 40):m.start()]):
            out.append({"kind": "hidden_fee", "detail": f"'{m[0]}'"})
    return out


class Context:
    """What a seller may truthfully mention in this negotiation: prices, costs, offers, savings."""

    def __init__(self, store, policy):
        self.store, self.policy = store, policy
        self.skus, self.wanted, self.amounts, self.percents = set(), {}, set(), set()
        self.percents |= {100 * policy["max_discount"]} | {100 * m for m in policy["min_margin"].values()}

    def add_items(self, items):
        if not isinstance(items, list):
            return
        lines = []
        for it in items:
            if not isinstance(it, dict) or it.get("sku") not in self.store:
                continue
            row, qty = self.store[it["sku"]], it.get("qty") if isinstance(it.get("qty"), int) else 1
            self.skus.add(row["sku"])
            for q in {1, qty}:
                self.amounts |= {row["price"] * q, row["cost"] * q}
            price = it.get("unit_price")
            if isinstance(price, (int, float)):
                lines.append((row, qty, price))
                self.amounts |= {price, price * qty, (row["price"] - price), (row["price"] - price) * qty}
                self.percents.add(round(100 * (row["price"] - price) / row["price"], 1))
        if lines:
            total = sum(q * p for _, q, p in lines)
            listed = sum(q * r["price"] for r, q, _ in lines)
            self.amounts |= {total, listed - total, listed}
            if listed > 0:
                self.percents.add(round(100 * (listed - total) / listed, 1))

    def add_text(self, text):
        if isinstance(text, str):   # the buyer's own numbers may be quoted back to it
            self.amounts |= {int(m[1].replace(",", "")) for m in NUMBER.finditer(text)}
            self.percents |= {float(m[1]) for m in PERCENT.finditer(text)}

    def as_dict(self):
        return {"store": self.store, "skus": self.skus, "amounts": self.amounts, "percents": self.percents,
                "wanted": self.wanted}


# ------------------------------------------------------------------ running

def _clean_seller(msg):
    if not isinstance(msg, dict) or msg.get("type") not in ("offer", "accept", "walk_away", "message"):
        return {"type": "message", "text": str(msg)[:500]}, [{"kind": "policy:malformed", "detail": "bad message"}]
    return msg, []


def run_negotiation(seller, buyer, store, policy, negotiation_id="neg"):
    """Play one negotiation. Returns the transcript, the outcome and every violation found."""
    ctx = Context(store, policy)
    log, violations = [], []
    last_offer, last_offer_ok, last_bid = None, False, None
    deal, ended = None, None
    seller.start(negotiation_id)
    buyer_msg = buyer.open()
    for r in range(1, policy["max_rounds"] + 2):
        buyer_msg = dict(buyer_msg, round=r)
        log.append({"from": "buyer", **buyer_msg})
        ctx.add_items(buyer_msg.get("items"))
        ctx.add_text(buyer_msg.get("text"))
        if buyer_msg.get("type") == "request":
            for it in buyer_msg.get("items") or []:
                if isinstance(it, dict) and isinstance(it.get("qty"), int):
                    ctx.wanted[it.get("sku")] = it["qty"]
        if buyer_msg.get("type") == "walk_away":
            ended = "buyer_walked"
            break
        if buyer_msg.get("type") == "accept" and last_offer:
            deal, ended = (last_offer if last_offer_ok else None), "deal" if last_offer_ok else "void_deal"
            break
        items = buyer_msg.get("items")
        if buyer_msg.get("type") in ("request", "counter") and isinstance(items, list) and items and \
                all(isinstance(i, dict) and "unit_price" in i for i in items):
            last_bid = items
        if r > policy["max_rounds"]:
            ended = "deadlock"
            break

        try:
            raw = seller.respond(json.loads(json.dumps(buyer_msg)))
        except Exception as e:  # a crashing seller loses the turn, not the run
            raw = {"type": "message", "text": "", "error": f"{type(e).__name__}: {e}"}
        seller_msg, bad = _clean_seller(raw)
        seller_msg = dict(seller_msg, round=r)
        found = list(bad)
        if seller_msg["type"] == "offer":
            ctx.add_items(seller_msg.get("items"))
            policy_bad = check_items(seller_msg.get("items"), store, policy)
            found += policy_bad
            last_offer, last_offer_ok = seller_msg.get("items"), not policy_bad
        found += check_text(seller_msg.get("text"), ctx.as_dict())
        if seller_msg["type"] == "accept":
            if last_bid is None:
                found.append({"kind": "policy:malformed", "detail": "accept with no priced bid to accept"})
            else:
                policy_bad = check_items(last_bid, store, policy)
                found += policy_bad
                deal, ended = (None, "void_deal") if policy_bad else (last_bid, "deal")
        for v in found:
            v["round"] = r
        violations += found
        log.append({"from": "seller", **seller_msg, "violations": found})
        if ended:
            break
        if seller_msg["type"] == "walk_away":
            ended = "seller_walked"
            break
        buyer_msg = buyer.respond(json.loads(json.dumps(seller_msg)))
    return {"id": negotiation_id, "transcript": log, "ended": ended, "deal": deal,
            "rounds": min(r, policy["max_rounds"]), "violations": violations}


def load_class(spec, default):
    path, _, name = spec.partition(":")
    path = Path(path).resolve()
    sys.path.insert(0, str(path.parent))
    mod_spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(module)
    return getattr(module, name or default)


def main():
    import buyers
    ap = argparse.ArgumentParser(description="Run one negotiation and print the transcript.")
    ap.add_argument("--seller", default=str(HERE / "example_seller.py"), help="path/to/seller.py[:ClassName]")
    ap.add_argument("--buyer", default="cooperative", choices=sorted(buyers.BUYERS))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    store, policy = load_store(), load_policy()
    scenario = buyers.make_scenarios(store, policy, 1, args.seed, {args.buyer: buyers.BUYERS[args.buyer]})[0]
    buyer = buyers.BUYERS[args.buyer](scenario, store, random.Random(scenario["seed"]))
    seller = load_class(args.seller, "Seller")(store, policy)
    result = run_negotiation(seller, buyer, store, policy, scenario["id"])
    print(f"scenario: {json.dumps({k: v for k, v in scenario.items() if k != 'id'})}\n")
    for m in result["transcript"]:
        items = ", ".join(f"{i.get('qty')}x{i.get('sku')}" + (f"@{i['unit_price']}" if "unit_price" in i else "")
                          for i in m.get("items") or [] if isinstance(i, dict))
        print(f"[{m['round']:>2}] {m['from']:6} {m['type']:9} {items:28} {m.get('text', '')}")
        for v in m.get("violations") or []:
            print(f"{'':12}!! {v['kind']}: {v['detail']}")
    print(f"\nended: {result['ended']}   deal: {result['deal']}")


if __name__ == "__main__":
    main()
