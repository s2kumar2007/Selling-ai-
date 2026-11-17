"""Layer 5, local half: a cheap deterministic pre-check of an outgoing message against store.csv and the tool log.
It enforces the invariants TraceWare's profile does not cover (price source, price >= floor, stock claims,
scarcity/pressure wording, competitor matching, journey claims only after a recorded accept_deal).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from tools.toolbox import ToolLog

NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?(?![\w%])")
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per ?cent)|\bpercent\b", re.I)
PRESSURE = re.compile(
    r"today only|offer (?:ends|expires)|expir(?:es|ing)|last chance|act (?:now|fast)|\bhurry\b|limited[- ]time|"
    r"before (?:it'?s|they'?re) gone|other (?:buyers|customers|people) (?:are|want|have)|someone else|"
    r"price (?:will|is going to) (?:go up|increase|rise)|only valid|selling fast|going fast|won'?t last|"
    r"high demand|flying off|don'?t miss|now or never|running out of time", re.I)
SCARCITY = re.compile(r"limited stock|running (?:out|low)|almost gone|(?:only )?(?:a )?few left|low (?:on )?stock|"
                      r"\blast (?:one|piece|pair|unit|item)\b|\bonly \w+ (?:left|remaining)\b", re.I)
FEES = re.compile(r"\b(?:fees?|surcharges?|service charge|handling charge|delivery charge|shipping charge|"
                  r"convenience charge|processing charge|gst extra|plus gst|plus tax(?:es)?|taxes extra)\b", re.I)
NO_FEE = re.compile(r"\b(?:no|without|zero|free of)\s+(?:\w+\s+){0,2}$", re.I)
COMPETITOR = re.compile(r"\b(?:price[- ]match|match(?:ing)? (?:their|that|the|your|competitor)|beat (?:their|that|the) price|"
                        r"competitor|quickkart|amazon|flipkart|other (?:store|shop|seller)s?)\b", re.I)
JOURNEY = re.compile(r"\b(?:deal (?:is )?confirmed|order (?:is )?(?:placed|confirmed|complete[d]?)|reserved|"
                     r"discount (?:has been )?applied|added to your (?:cart|order|basket)|i(?:'ve| have) added|"
                     r"payment (?:received|processed)|will be (?:shipped|delivered))\b", re.I)
SOLD_OUT = re.compile(r"\b(?:sold out|out of stock|none left|no stock|not in stock)\b", re.I)
STOCK_COUNT = re.compile(r"\b(\d+|\w+)\s+(?:units?\s+|pieces?\s+|pairs?\s+)?(?:left|remaining|in stock|available)\b|"
                         r"\bwe (?:have|'ve got|got)\s+(\w+)\b", re.I)


@dataclass
class Verdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)

    def evidence(self) -> str:
        return "; ".join(self.reasons)


def _allowed_amounts(log: ToolLog, rnd: int, extra: Mapping[str, Any] | None) -> tuple[set[int], dict[str, int]]:
    """Numbers a message may cite: unit prices, line totals, basket total, list prices, savings — from the log."""
    amounts: set[int] = set()
    floors: dict[str, int] = {}
    for c in log.for_round(rnd):
        if c.name == "compute_floor" and c.result.get("floor") is not None:
            floors[c.result["sku"]] = c.result["floor"]
        if c.name == "get_price" and c.result.get("list_price") is not None:
            amounts.add(c.result["list_price"])
    if extra:
        for ln in extra.get("lines", []):
            q = ln["qty"]
            amounts |= {ln["unit_price"], ln["line_total"], ln["list_price"], ln["list_price"] * q,
                        (ln["list_price"] - ln["unit_price"]) * q, ln["list_price"] - ln["unit_price"]}
        amounts |= {extra.get("total", 0), extra.get("list_total", 0), extra.get("saving", 0)}
    return amounts, floors


def local_check(text: str, log: ToolLog, rnd: int, move_name: str, facts: Mapping[str, Any],
                buyer_numbers: set[int] | None = None) -> Verdict:
    reasons: list[str] = []
    amounts, floors = _allowed_amounts(log, rnd, facts)
    amounts |= buyer_numbers or set()
    for m in NUMBER.finditer(text):
        n = int(m[1].replace(",", ""))
        if n >= 100 and not any(abs(n - a) <= 1 for a in amounts):
            reasons.append(f"price {m[0]} was not produced by compute_offer")
    if PERCENT.search(text):
        reasons.append("percentage claim not backed by a tool call")
    # quoted prices must be at or above the floor, and the quoted offer must be one the kernel produced
    for ln in facts.get("lines", []):
        fl = floors.get(ln["sku"])
        if fl is not None and move_name != "accept" and ln["unit_price"] < fl:
            reasons.append(f"{ln['sku']} quoted below floor")
    if move_name in ("concede", "hold", "offer_bundle", "final_offer"):
        quotes = [c for c in log.named("compute_offer", rnd)]
        ok_quote = any(any(q == [{"sku": l["sku"], "qty": l["qty"], "unit_price": l["unit_price"]}
                           for l in facts.get("lines", [])] for q in c.result["quotes"].values()) for c in quotes)
        if not ok_quote:
            reasons.append("offer did not come from compute_offer")
    # stock claims: only 'out of stock' for a product the stock tool reported empty; no counts, no scarcity
    stock = {c.result["sku"]: c.result["stock"] for c in log.named("check_stock", rnd)}
    if SOLD_OUT.search(text) and not any(s == 0 for s in stock.values()) and not facts.get("unsellable"):
        reasons.append("out-of-stock claim not backed by check_stock")
    for m in STOCK_COUNT.finditer(text):
        word = next(g for g in m.groups() if g)
        if word.isdigit() and int(word) not in stock.values():
            reasons.append(f"stock claim '{m[0]}' does not match check_stock")
    if SCARCITY.search(text) and not any(0 < s <= 3 for s in stock.values()):
        reasons.append("scarcity wording without stock backing")
    if m := PRESSURE.search(text):
        reasons.append(f"pressure wording '{m[0]}'")
    for m in FEES.finditer(text):
        if not NO_FEE.search(text[max(0, m.start() - 40):m.start()]):
            reasons.append(f"fee wording '{m[0]}'")
    if COMPETITOR.search(text):
        reasons.append("competitor / price-matching wording")
    if JOURNEY.search(text) and not log.named("accept_deal", rnd):
        reasons.append("deal/order claim without a recorded accept_deal")
    return Verdict(not reasons, reasons)
