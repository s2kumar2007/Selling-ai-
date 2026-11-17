"""Deterministic pricing kernel. Plain Python: it alone decides every number, quantity and move.

Per negotiation it keeps the lines we can sell, our last prices (offers never go back up) and the
buyer's bid history (numbers only). Buyer text never reaches this module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from .config import Config
from .floor import floor_price, is_sellable, max_qty
from .store import Policy, Product

Items = list[dict[str, Any]]


@dataclass
class Move:
    name: str                   # hold | concede | offer_bundle | final_offer | accept | walk_away | out_of_stock
    msg_type: str               # offer | accept | walk_away | message
    items: Items = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class Opponent:
    """BOA-lite: the buyer's concession rate from bid numbers only. Never touches the floor."""
    ratios: list[float] = field(default_factory=list)   # bid_total / list_total per round

    def observe(self, ratio: float) -> None:
        self.ratios.append(ratio)

    def rate(self) -> float:
        if len(self.ratios) < 2:
            return 0.0
        return max(0.0, (self.ratios[-1] - self.ratios[0]) / (len(self.ratios) - 1))

    def estimate_max(self, rounds_left: int) -> float:
        return (self.ratios[-1] if self.ratios else 0.0) + self.rate() * max(0, rounds_left)


class Kernel:
    def __init__(self, store: Mapping[str, Product], policy: Policy, cfg: Config | None = None):
        self.store, self.policy, self.cfg = store, policy, cfg or Config()
        self.reset()

    def reset(self) -> None:
        self.lines: dict[str, int] = {}
        self.unsellable: list[dict[str, Any]] = []
        self.last: dict[str, int] = {}
        self.started = False
        self.opp = Opponent()

    # ------------------------------------------------------------ setup

    def _init_lines(self, items: Any) -> None:
        self.started = True
        wanted: dict[str, int] = {}
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and isinstance(it.get("sku"), str) and it["sku"] in self.store \
                        and isinstance(it.get("qty"), int) and not isinstance(it["qty"], bool) and it["qty"] > 0:
                    wanted[it["sku"]] = wanted.get(it["sku"], 0) + it["qty"]
        for sku, qty in wanted.items():
            p = self.store[sku]
            n = max_qty(p, self.policy, qty)
            if n > 0:
                self.lines[sku] = n
            self.unsellable.append({"sku": sku, "name": p.name, "stock": p.stock, "wanted": qty, "supplied": n}) \
                if n < qty else None

    # ------------------------------------------------------------ numbers

    def floor(self, sku: str) -> int:
        return floor_price(self.store[sku], self.policy)

    def open_price(self, sku: str) -> int:
        p = self.store[sku]
        return max(self.floor(sku), math.ceil(p.price * (1 - self.cfg.open_discount)))

    def curve(self, sku: str, rnd: int, speedup: float = 0.0) -> int:
        """offer(t) = open - (open - floor) * (t/H)^(1/beta), t = round-1, H = final_start-1; ceil to a rupee."""
        o, f = self.open_price(sku), self.floor(sku)
        horizon = max(1, self.cfg.final_start - 1)
        frac = min(1.0, max(0.0, (rnd - 1) / horizon) ** (1.0 / self.cfg.beta))
        frac = min(1.0, frac * (1.0 + speedup))
        return max(f, math.ceil(o - (o - f) * frac))

    def is_bundle(self) -> bool:
        return len(self.lines) > 1 or any(q > 1 for q in self.lines.values())

    def _prices(self, rnd: int, speedup: float = 0.0, final: bool = False) -> dict[str, int]:
        out = {}
        for sku in self.lines:
            want = self.floor(sku) if final else self.curve(sku, rnd, speedup)
            prev = self.last.get(sku)
            out[sku] = min(prev, want) if prev is not None else want     # never back up
            out[sku] = max(out[sku], self.floor(sku))                    # never below floor
        return out

    def _items(self, prices: Mapping[str, int]) -> Items:
        return [{"sku": s, "qty": q, "unit_price": prices[s]} for s, q in self.lines.items()]

    def _facts(self, items: Items) -> dict[str, Any]:
        lines = []
        for it in items:
            p = self.store[it["sku"]]
            lines.append({"sku": p.sku, "name": p.name, "qty": it["qty"], "unit_price": it["unit_price"],
                          "list_price": p.price, "line_total": it["qty"] * it["unit_price"],
                          "stock_zero": p.stock == 0})
        total = sum(l["line_total"] for l in lines)
        listed = sum(l["qty"] * l["list_price"] for l in lines)
        return {"lines": lines, "total": total, "list_total": listed, "saving": listed - total,
                "unsellable": list(self.unsellable)}

    # ------------------------------------------------------------ buyer bid

    def read_bid(self, msg: Mapping[str, Any]) -> dict[str, tuple[int, float]] | None:
        """The buyer's priced lines, only if every line is well formed. Unknown SKUs make it unusable."""
        items = msg.get("items")
        if msg.get("type") not in ("request", "counter") or not isinstance(items, list) or not items:
            return None
        bid: dict[str, tuple[int, float]] = {}
        for it in items:
            if not isinstance(it, dict):
                return None
            sku, qty, price = it.get("sku"), it.get("qty"), it.get("unit_price")
            if not isinstance(sku, str) or sku in bid or not isinstance(qty, int) or isinstance(qty, bool) \
                    or qty < 1 or not isinstance(price, (int, float)) or isinstance(price, bool) \
                    or not math.isfinite(price):
                return None
            bid[sku] = (qty, float(price))
        return bid

    def _observe(self, bid: Mapping[str, tuple[int, float]] | None) -> None:
        if not bid:
            return
        listed = sum(q * self.store[s].price for s, (q, _) in bid.items() if s in self.lines)
        paid = sum(q * pr for s, (q, pr) in bid.items() if s in self.lines)
        if listed > 0:
            self.opp.observe(paid / listed)

    def bid_acceptable(self, bid: Mapping[str, tuple[int, float]] | None, planned: Mapping[str, int],
                       rnd: int = 1) -> bool:
        """Every bid line is one we sell, within our quantity, inside [floor, list]; total is worth the plan."""
        if not bid:
            return False
        total = plan_total = floor_total = open_total = 0.0
        for sku, (qty, price) in bid.items():
            if sku not in self.lines or qty > self.lines[sku]:
                return False
            if price < self.floor(sku) or price > self.store[sku].price:
                return False
            total += qty * price
            plan_total += qty * planned[sku]
            floor_total += qty * self.floor(sku)
            open_total += qty * self.open_price(sku)
        if total >= plan_total * (1.0 - self.cfg.accept_slack) - 1e-9:
            return True
        gain = max(0.0, self.cfg.accept_gain - self.cfg.accept_gain_decay * (rnd - 1))
        return open_total > floor_total and total >= floor_total + gain * (open_total - floor_total) - 1e-9

    # ------------------------------------------------------------ decisions

    def options(self, msg: Mapping[str, Any]) -> tuple[dict[str, Move], str]:
        """Every move that is allowed this turn (with verified facts) and the kernel's own pick."""
        rnd = int(msg.get("round", 1))
        T = self.policy.max_rounds
        if not self.started:
            self._init_lines(msg.get("items"))
        if not self.lines:
            mv = Move("out_of_stock", "walk_away", [], {"lines": [], "total": 0, "list_total": 0, "saving": 0,
                                                       "unsellable": list(self.unsellable)})
            return {"out_of_stock": mv}, "out_of_stock"

        bid = self.read_bid(msg)
        self._observe(bid)
        final_phase = rnd >= self.cfg.final_start
        opts: dict[str, Move] = {}

        concede = self._prices(rnd)
        planned = self._prices(rnd, final=final_phase)
        if self.bid_acceptable(bid, planned, rnd):
            accepted = [{"sku": s, "qty": q, "unit_price": int(p) if float(p).is_integer() else p}
                        for s, (q, p) in bid.items()]
            opts["accept"] = Move("accept", "accept", accepted, self._facts(accepted))

        if final_phase:
            opts["final_offer"] = Move("final_offer", "offer", self._items(planned), self._facts(self._items(planned)))
        else:
            first = not self.last
            name = "offer" if first else "concede"
            opts["concede"] = Move(name if False else "concede", "offer", self._items(concede),
                                   self._facts(self._items(concede)))
            if self.last:
                hold = dict(self.last)
                opts["hold"] = Move("hold", "offer", self._items(hold), self._facts(self._items(hold)))
            if self.is_bundle() and rnd >= self.cfg.bundle_min_round:
                b = self._prices(rnd, speedup=self.cfg.bundle_bonus)
                opts["offer_bundle"] = Move("offer_bundle", "offer", self._items(b), self._facts(self._items(b)))

        # last round with no acceptable bid: gamble on a repeated final offer only if the buyer looks close
        if rnd >= T:
            floors = {s: self.floor(s) for s in self.lines}
            floor_ratio = sum(q * floors[s] for s, q in self.lines.items()) / \
                sum(q * self.store[s].price for s, q in self.lines.items())
            close = self.opp.estimate_max(0) >= self.cfg.gamble_min_ratio * floor_ratio
            opts["walk_away"] = Move("walk_away", "walk_away", [], self._facts(self._items(floors)))
            if "accept" in opts:
                return opts, "accept"
            if not close:
                opts.pop("final_offer", None)
                return opts, "walk_away"
            return opts, "final_offer"

        if "accept" in opts:
            return opts, "accept"
        if final_phase:
            return opts, "final_offer"
        return opts, "concede"

    def decide(self, msg: Mapping[str, Any]) -> Move:
        opts, default = self.options(msg)
        return self.commit(opts[default])

    def commit(self, move: Move) -> Move:
        """Record an offer as our new last prices. Called only with a validated move."""
        if move.msg_type == "offer":
            for it in move.items:
                self.last[it["sku"]] = it["unit_price"]
        return move
