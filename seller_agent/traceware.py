"""Rezolve Labs TraceWare client: final truthfulness gate. REST: POST /traceware/verify (X-API-KEY).

A reply is released only on decision PASS. Outages (timeout, 502/503/504, network) return `available=False`;
auth/merchant errors (400/401/403) are surfaced as errors and are never treated as PASS.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .config import Config
from .llm_client import ROOT, Transport, load_env, urllib_transport

BASE_URL = "https://api.rezolvelabs.com/api/v1"


@dataclass
class TWResult:
    decision: str | None = None           # PASS | WARN | REGENERATE | BLOCK | None when unavailable
    message: str = ""
    violations: list[Any] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    duplicate: bool = False
    available: bool = True
    error: str | None = None              # set for outages and for config/auth errors
    config_error: bool = False
    credits_charged: float = 0.0
    latency_s: float = 0.0
    trace_id: str = ""

    @property
    def passed(self) -> bool:
        return self.available and self.decision == "PASS"

    def evidence(self) -> str:
        if self.error:
            return self.error
        bits = [self.message] + [json.dumps(v) if not isinstance(v, str) else v for v in self.violations]
        return f"TraceWare {self.decision}: " + "; ".join(b for b in bits if b)


def build_observations(trace_id: str, deal_items: list[Mapping[str, Any]], names: Mapping[str, str]) -> list[dict]:
    """One add_to_basket SPAN per agreed line, recorded only after accept_deal."""
    obs = []
    for i, it in enumerate(deal_items):
        obs.append({
            "id": f"{trace_id}-ev{i}", "type": "SPAN", "name": "add_to_basket",
            "metadata": {"attributes": {
                "func.arg.product_id": it["sku"], "func.arg.name": names.get(it["sku"], it["sku"]),
                "func.arg.quantity": str(it["qty"]), "func.arg.price": f"{float(it['unit_price']):.1f}",
                "func.result": json.dumps({"success": True})}}})
    return obs


class TraceWareClient:
    def __init__(self, cfg: Config, api_key: str | None = None, merchant_id: str | None = None,
                 transport: Transport = urllib_transport, base_url: str = BASE_URL):
        load_env()
        self.cfg, self.transport, self.base_url = cfg, transport, base_url
        self.api_key = api_key or os.environ.get("REZOLVE_API_KEY")
        self.merchant_id = merchant_id or os.environ.get("REZOLVE_MERCHANT_ID")
        self.calls = 0
        self.credits = 0.0
        self.outages = 0

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.merchant_id)

    def verify(self, session_id: str, user_id: str, trace_id: str, output: str,
               observations: list[dict] | None = None) -> TWResult:
        if not self.configured:
            return TWResult(available=False, error="TraceWare not configured (REZOLVE_API_KEY / REZOLVE_MERCHANT_ID)",
                            config_error=True, trace_id=trace_id)
        body = {"id": trace_id, "sessionId": session_id, "userId": user_id,
                "metadata": {"merchant_id": self.merchant_id}, "output": output,
                "observations": observations or []}
        t0 = time.perf_counter()
        try:
            status, headers, raw = self.transport(
                "POST", f"{self.base_url}/traceware/verify",
                {"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json.dumps(body).encode(), self.cfg.traceware_timeout_s)
        except Exception as e:  # timeout / network: the reply was NOT verified
            self.outages += 1
            return TWResult(available=False, error=f"TraceWare unreachable: {type(e).__name__}",
                            latency_s=time.perf_counter() - t0, trace_id=trace_id)
        dt = time.perf_counter() - t0
        h = {k.lower(): v for k, v in headers.items()}
        self.calls += 1
        charged = float(h.get("x-credits-charged", 0) or 0)
        self.credits += charged
        if status in (502, 503, 504):
            self.outages += 1
            return TWResult(available=False, error=f"TraceWare outage (HTTP {status}); reply not verified",
                            latency_s=dt, trace_id=trace_id)
        if status != 200:
            return TWResult(available=False, error=f"TraceWare error HTTP {status}: fix key/merchant setup",
                            config_error=status in (400, 401, 403, 404, 409, 422), latency_s=dt, trace_id=trace_id)
        try:
            data = json.loads(raw)
            res = data["result"]
        except (ValueError, KeyError, TypeError):
            return TWResult(available=False, error="TraceWare returned an unreadable answer", latency_s=dt,
                            trace_id=trace_id)
        return TWResult(decision=res.get("decision"), message=res.get("message", ""),
                        violations=list(res.get("violations") or []), claims=data.get("claims") or {},
                        state=data.get("state") or {}, duplicate=bool(data.get("duplicate")),
                        credits_charged=charged, latency_s=dt, trace_id=res.get("trace_id", trace_id))
