"""Store and policy loading. Plain data, no behaviour beyond validation."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE = ROOT / "starter_kit" / "store.csv"
DEFAULT_POLICY = ROOT / "starter_kit" / "policy.json"


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    category: str
    brand: str
    price: int   # list price, rupees
    cost: int    # rupees
    stock: int


@dataclass(frozen=True)
class Policy:
    max_discount: float
    min_margin: Mapping[str, float]
    max_rounds: int = 10


def product_from_row(row: Mapping[str, Any]) -> Product:
    return Product(sku=str(row["sku"]), name=str(row["name"]), category=str(row["category"]),
                   brand=str(row.get("brand", "")), price=int(row["price"]), cost=int(row["cost"]),
                   stock=int(row["stock"]))


def policy_from_dict(d: Mapping[str, Any]) -> Policy:
    return Policy(max_discount=float(d["max_discount"]),
                  min_margin={k: float(v) for k, v in d["min_margin"].items()},
                  max_rounds=int(d.get("max_rounds", 10)))


def store_from_rows(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Product]:
    """Build the store from the {sku: row} dict the harness passes to Seller.__init__."""
    return {sku: product_from_row(r) for sku, r in rows.items()}


def load_store(path: Path | str = DEFAULT_STORE) -> dict[str, Product]:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["sku"]: product_from_row(r) for r in csv.DictReader(fh)}


def load_policy(path: Path | str = DEFAULT_POLICY) -> Policy:
    with open(path, encoding="utf-8") as fh:
        return policy_from_dict(json.load(fh))
