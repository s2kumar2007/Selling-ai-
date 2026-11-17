"""Template narration. Every number comes from the move's verified facts; no LLM, no invented claims.

Only amounts the harness counts as 'in play' are used: unit price, line total, basket total, saving, list price.
"""
from __future__ import annotations

from typing import Any, Mapping


def rs(n: int | float) -> str:
    return f"₹{int(round(n)):,}"


def describe(lines: list[Mapping[str, Any]]) -> str:
    return " and ".join(f"{l['qty']} x {l['name']}" for l in lines)


def _notes(facts: Mapping[str, Any]) -> str:
    out = []
    for u in facts.get("unsellable", []):
        if u["stock"] == 0:
            out.append(f"{u['name']} is out of stock.")
        elif u["supplied"] > 0:
            out.append(f"I can supply {u['supplied']} of {u['name']}.")
    return (" " + " ".join(out)) if out else ""


def render(move_name: str, facts: Mapping[str, Any]) -> str:
    lines = facts.get("lines", [])
    d, total = (describe(lines), facts.get("total", 0)) if lines else ("", 0)
    n = _notes(facts)
    if move_name == "out_of_stock":
        names = ", ".join(u["name"] for u in facts.get("unsellable", [])) or "that item"
        return f"Sorry, {names} is out of stock, so I can't offer it. Thank you for asking."
    if move_name == "walk_away":
        return "I'm sorry, my final offer is the lowest I can go, so I'll leave it there. Thank you for your time."
    if move_name == "accept":
        return f"Deal! {d} for {rs(total)} in total. Thank you."
    if move_name == "final_offer":
        return f"This is my final offer: {d} for {rs(total)} in total. It is the lowest I can go.{n}"
    if move_name == "hold":
        return f"I'm holding at {rs(total)} in total for {d}. That is already a good price.{n}"
    if move_name == "offer_bundle":
        return f"For the whole bundle I can do {d} for {rs(total)} in total, saving {rs(facts['saving'])} off list.{n}"
    # concede / opening offer
    if facts.get("saving", 0) == 0:
        return f"Happy to help. I can do {d} for {rs(total)} in total.{n}"
    return f"I can come down to {rs(total)} in total for {d}.{n}"
