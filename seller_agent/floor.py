"""Floor price: the lowest unit price policy allows. Mirrors starter_kit/harness.floor_price exactly."""
from __future__ import annotations

import math

from .store import Policy, Product


def margin_floor(p: Product, policy: Policy) -> float:
    """Lowest price meeting the minimum margin; margin = (price - cost) / price."""
    return p.cost / (1 - policy.min_margin[p.category])


def discount_floor(p: Product, policy: Policy) -> float:
    return p.price * (1 - policy.max_discount)


def floor_price(p: Product, policy: Policy) -> int:
    """max(margin floor, discount floor), rounded up to a whole rupee (same float maths as the harness)."""
    return math.ceil(max(margin_floor(p, policy), discount_floor(p, policy)))


def binding_constraint(p: Product, policy: Policy) -> str:
    return "margin" if margin_floor(p, policy) > discount_floor(p, policy) else "discount"


def is_sellable(p: Product, policy: Policy) -> bool:
    """In stock, and a compliant price exists at or below list. A floor above list means never sellable."""
    return p.stock > 0 and floor_price(p, policy) <= p.price


def max_qty(p: Product, policy: Policy, wanted: int) -> int:
    """How many units we may offer: never more than stock, zero if the product cannot be sold."""
    if wanted < 1 or not is_sellable(p, policy):
        return 0
    return min(wanted, p.stock)
