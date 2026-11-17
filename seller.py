"""Harness entry point: `python evaluate.py --seller /path/to/seller.py` loads `Seller` from here."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seller_agent.agent import Seller  # noqa: E402,F401
