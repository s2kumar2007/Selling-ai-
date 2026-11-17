"""A simple, honest seller to start from. evaluate.py also uses it as the baseline.

It opens at list price, gives up a quarter of what is left above its floor each round, accepts
any bid at or above its floor, and never walks away, so a buyer that never leaves deadlocks it.
It never reads the buyer's text: immune to the manipulator's words, but not to its numbers.

    class Seller:
        def __init__(self, store, policy)   store: {sku: row from store.csv}, policy: policy.json
        def start(self, negotiation_id)      a new negotiation begins
        def respond(self, message) -> dict   the buyer's message in, your message out
"""
import math


class Seller:
    def __init__(self, store, policy):
        self.store, self.policy = store, policy

    def floor(self, sku):
        row = self.store[sku]
        margin = self.policy["min_margin"][row["category"]]
        return math.ceil(max(row["cost"] / (1 - margin), row["price"] * (1 - self.policy["max_discount"])))

    def start(self, negotiation_id):
        self.lines = None        # sku -> qty we will sell
        self.prices = None       # sku -> our current unit price

    def respond(self, message):
        if self.lines is None:
            wanted = {i.get("sku"): i.get("qty") for i in message.get("items") or [] if isinstance(i, dict)}
            self.lines = {sku: min(qty, self.store[sku]["stock"]) for sku, qty in wanted.items()
                          if sku in self.store and isinstance(qty, int) and qty > 0 and self.store[sku]["stock"] > 0}
            if not self.lines:
                return {"type": "walk_away", "text": "Sorry, we don't have that in stock."}
            self.prices = {sku: self.store[sku]["price"] for sku in self.lines}
        elif message.get("type") == "counter":
            for sku, price in self.prices.items():
                self.prices[sku] = max(self.floor(sku), math.ceil(price - (price - self.floor(sku)) / 4))

        if message.get("type") in ("request", "counter") and self.acceptable(message.get("items")):
            return {"type": "accept", "text": "Deal, thank you!"}
        items = [{"sku": sku, "qty": qty, "unit_price": self.prices[sku]} for sku, qty in self.lines.items()]
        total = sum(i["qty"] * i["unit_price"] for i in items)
        names = " and ".join(f"{i['qty']} x {self.store[i['sku']]['name']}" for i in items)
        return {"type": "offer", "items": items, "text": f"I can do {names} for ₹{total:,}."}

    def acceptable(self, bid):
        """A bid we can take: only our lines, in our quantities, each at or above its floor."""
        if not isinstance(bid, list) or not bid:
            return False
        for line in bid:
            sku = line.get("sku") if isinstance(line, dict) else None
            if sku not in self.lines or line.get("qty") != self.lines[sku]:
                return False
            price = line.get("unit_price")
            if not isinstance(price, (int, float)) or not self.floor(sku) <= price <= self.store[sku]["price"]:
                return False
        return len(bid) == len(self.lines)
