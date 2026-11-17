"""All tunable parameters in one place. Override with config.json at the repo root."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    # --- pricing kernel
    beta: float = 0.8               # Boulware if < 1: concede little early, more late
    open_discount: float = 0.0      # opening offer = list * (1 - open_discount)
    final_start: int = 8            # from this round on, the offer is the final one (at floor)
    accept_slack: float = 0.0       # accept a bid worth >= planned_total * (1 - slack)
    accept_gain: float = 1.0        # also accept a bid capturing >= this share of the open-to-floor gap (1.0 = off)
    accept_gain_decay: float = 0.0  # gain threshold falls by this much per round
    bundle_bonus: float = 0.15      # extra concession speed for multi-line / multi-unit baskets
    bundle_min_round: int = 3
    gamble_min_ratio: float = 0.85  # last round: repeat the final offer only if est. buyer max >= this * floor total
    # --- LLM (Groq)
    seller_model: str = ""          # chosen by the user from the list of available models
    buyer_model: str = ""           # must be a different family from the seller
    temperature: float = 0.2
    max_tokens: int = 200
    timeout_s: float = 20.0
    max_retries: int = 4
    backoff_base_s: float = 1.0
    max_calls_per_minute: int = 25
    use_llm: bool = False
    # --- gate / Rezolve
    traceware_enabled: bool = False
    traceware_scope: str = "all"   # all | deal_only (deal_only: only closing messages go to TraceWare)
    traceware_timeout_s: float = 8.0
    max_regenerations: int = 2
    extra: dict = field(default_factory=dict)

    @staticmethod
    def load(path: Path | str | None = None) -> "Config":
        p = Path(path) if path else ROOT / "config.json"
        cfg = Config()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            known = {f.name for f in fields(Config)}
            for k, v in data.items():
                if k in known:
                    setattr(cfg, k, v)
        return cfg
