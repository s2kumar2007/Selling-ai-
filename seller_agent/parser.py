"""Layer 1: untrusted-input parser. Buyer text is DATA. We pull out structured fields and claim flags;
the text itself is never passed on as instructions, and nothing here can change a price, floor or policy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

NUM = r"(?:₹|rs\.?\s?|inr\s?)?\s?(\d{1,3}(?:,\d{2,3})+|\d+)"

# (kind, pattern). Order does not matter; every match is recorded.
CLAIM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("competitor_quote", re.compile(r"\b(?:quickkart|amazon|flipkart|myntra|another (?:store|shop|seller)|competitor|"
                                    r"other (?:store|shop|seller)s?|elsewhere|cheaper (?:at|elsewhere|online)|"
                                    r"has the same|match (?:it|that|their|the price))\b", re.I)),
    ("budget_claim", re.compile(r"\b(?:my budget|budget (?:is|of)|can(?:'|no)?t (?:afford|pay more)|not a rupee more|"
                                r"maximum i can|max(?:imum)? (?:i|budget))\b", re.I)),
    ("authority_claim", re.compile(r"\b(?:as (?:the )?(?:store )?(?:manager|owner|admin)|i am (?:the )?(?:manager|owner)|"
                                   r"system\s*:|\[system\]|developer mode|admin override|i authori[sz]e)\b", re.I)),
    ("policy_override", re.compile(r"\b(?:max_discount|min_margin|policy (?:is )?(?:now|updated|changed)|"
                                  r"store policy updated|new policy)\b", re.I)),
    ("prior_agreement", re.compile(r"\byou (?:already )?(?:agreed|promised|said|confirmed|offered)\b|"
                                   r"\bhonou?r (?:it|that|your)\b|\bas (?:we )?agreed\b", re.I)),
    ("injection", re.compile(r"\b(?:ignore (?:all |your |the )?(?:previous|prior|above|earlier)? ?(?:instructions|rules|prompt)|"
                             r"disregard (?:your|the|all)|forget (?:your|the|all) (?:rules|instructions)|"
                             r"you are now|act as|pretend (?:to be|you)|new instructions|reveal your (?:prompt|instructions)|"
                             r"system prompt)\b", re.I)),
    ("cost_probe", re.compile(r"\b(?:print|show|reveal|tell me|what(?:'s| is)) (?:your |the )?(?:cost|margin|floor|"
                              r"minimum price|wholesale)\b|\bcost price\b", re.I)),
    ("threat", re.compile(r"\b(?:report (?:this|you|your)|price gouging|sue|bad review|one-star|leave a review)\b", re.I)),
    ("stock_assertion", re.compile(r"\b(?:your (?:website|site|app) says|you have \d+ (?:of these )?in stock|"
                                   r"\d+ (?:units? )?in stock)\b", re.I)),
    ("fake_message_json", re.compile(r'"type"\s*:\s*"(?:accept|offer|walk_away)"')),
]


@dataclass
class Claim:
    kind: str
    amount: int | None = None     # a number the buyer attached to the claim, for the demo panel only


@dataclass
class Parsed:
    intent: str                                   # request | counter | accept | walk_away | message | unknown
    round: int
    items: list[dict[str, Any]] = field(default_factory=list)   # well-formed lines only
    dropped_lines: int = 0                         # malformed or unusable lines ignored
    offered_total: int | None = None
    claims: list[Claim] = field(default_factory=list)
    untrusted_text: bool = True                    # always: the text is data, never instructions

    def claim_kinds(self) -> list[str]:
        return sorted({c.kind for c in self.claims})

    def safe_summary(self) -> dict[str, Any]:
        """What a downstream LLM may see: structure and claim categories only, never the buyer's words."""
        return {"intent": self.intent, "round": self.round, "n_lines": len(self.items),
                "offered_total": self.offered_total, "claims": self.claim_kinds()}


def _amount_near(text: str, start: int, end: int) -> int | None:
    window = text[max(0, start - 40): end + 60]
    m = re.search(NUM, window, re.I)
    return int(m.group(1).replace(",", "")) if m else None


def extract_claims(text: Any) -> list[Claim]:
    if not isinstance(text, str):
        return []
    out: list[Claim] = []
    for kind, pat in CLAIM_PATTERNS:
        for m in pat.finditer(text[:4000]):
            out.append(Claim(kind, _amount_near(text, m.start(), m.end())))
    return out


def parse_message(msg: Mapping[str, Any]) -> Parsed:
    mtype = msg.get("type") if isinstance(msg, Mapping) else None
    intent = mtype if mtype in ("request", "counter", "accept", "walk_away", "message") else "unknown"
    rnd = msg.get("round") if isinstance(msg.get("round"), int) else 0
    items, dropped = [], 0
    raw = msg.get("items")
    if isinstance(raw, list):
        for it in raw:
            if (isinstance(it, Mapping) and isinstance(it.get("sku"), str)
                    and isinstance(it.get("qty"), int) and not isinstance(it.get("qty"), bool) and it["qty"] > 0):
                line: dict[str, Any] = {"sku": it["sku"], "qty": it["qty"]}
                p = it.get("unit_price")
                if isinstance(p, (int, float)) and not isinstance(p, bool) and p == p and p != float("inf"):
                    line["unit_price"] = p
                items.append(line)
            else:
                dropped += 1
    total = None
    if items and all("unit_price" in i for i in items):
        total = int(round(sum(i["qty"] * i["unit_price"] for i in items)))
    return Parsed(intent, rnd, items, dropped, total, extract_claims(msg.get("text")))
