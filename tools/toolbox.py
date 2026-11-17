"""Logged tool layer. Every price/stock lookup and every deal goes through one of these five calls, and each
call is recorded. The local pre-check and the TraceWare gate both read this log as their ground truth."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from seller_agent.floor import floor_price
from seller_agent.kernel import Kernel, Move
from seller_agent.store import Policy, Product


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    result: dict[str, Any]
    round: int
    ts: float = field(default_factory=time.time)


@dataclass
class ToolLog:
    calls: list[ToolCall] = field(default_factory=list)

    def add(self, call: ToolCall) -> None:
        self.calls.append(call)

    def for_round(self, rnd: int) -> list[ToolCall]:
        return [c for c in self.calls if c.round == rnd]

    def named(self, name: str, rnd: int | None = None) -> list[ToolCall]:
        return [c for c in self.calls if c.name == name and (rnd is None or c.round == rnd)]

    def deals(self) -> list[ToolCall]:
        return self.named("accept_deal")


class ToolBox:
    def __init__(self, store: Mapping[str, Product], policy: Policy, kernel: Kernel):
        self.store, self.policy, self.kernel = store, policy, kernel
        self.log = ToolLog()
        self.round = 0

    def reset(self) -> None:
        self.log = ToolLog()
        self.round = 0

    def _rec(self, name: str, args: dict, result: dict) -> dict:
        self.log.add(ToolCall(name, args, result, self.round))
        return result

    def get_price(self, sku: str) -> dict:
        p = self.store.get(sku)
        return self._rec("get_price", {"sku": sku}, {"sku": sku, "list_price": p.price if p else None})

    def check_stock(self, sku: str, qty: int = 1) -> dict:
        p = self.store.get(sku)
        stock = p.stock if p else 0
        return self._rec("check_stock", {"sku": sku, "qty": qty},
                         {"sku": sku, "stock": stock, "available": stock >= qty > 0})

    def compute_floor(self, sku: str) -> dict:
        p = self.store.get(sku)
        return self._rec("compute_floor", {"sku": sku}, {"sku": sku, "floor": floor_price(p, self.policy) if p else None})

    def compute_offer(self, msg: Mapping[str, Any]) -> tuple[dict[str, Move], str]:
        """Kernel decision for this turn; the verified quotes it returns are what messages may cite."""
        self.round = int(msg.get("round", self.round or 1))
        opts, default = self.kernel.options(msg)
        for mv in opts.values():
            for it in mv.items:
                self.get_price(it["sku"])
                self.check_stock(it["sku"], it["qty"])
                self.compute_floor(it["sku"])
        quotes = {n: [{"sku": i["sku"], "qty": i["qty"], "unit_price": i["unit_price"]} for i in m.items]
                  for n, m in opts.items()}
        self._rec("compute_offer", {"round": self.round}, {"default": default, "quotes": quotes,
                                                            "unsellable": [dict(u) for u in self.kernel.unsellable]})
        return opts, default

    def accept_deal(self, move: Move) -> dict:
        items = [{"sku": i["sku"], "qty": i["qty"], "unit_price": i["unit_price"]} for i in move.items]
        return self._rec("accept_deal", {"items": items}, {"accepted": True, "items": items,
                                                            "total": sum(i["qty"] * i["unit_price"] for i in items)})
