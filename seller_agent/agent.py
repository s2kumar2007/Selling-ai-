"""Seller: parser -> kernel (via logged tools) -> optional LLM tactician -> local pre-check -> TraceWare -> send.

Every number comes from the kernel. A message goes out only after the local check passes and, when TraceWare is
reachable, TraceWare returns PASS. After `max_regenerations` failures a safe template is sent.
"""
from __future__ import annotations

import time
from typing import Any, Mapping

from tools.toolbox import ToolBox

from .config import Config
from .gate import Verdict, local_check
from .kernel import Kernel, Move
from .llm_client import GroqClient
from .parser import parse_message
from .store import policy_from_dict, store_from_rows
from .tactician import Tactician
from .templates import render
from .traceware import TraceWareClient, build_observations

LAST_RESORT = "Thanks for your message. Let me confirm the details and come back to you."


class Seller:
    def __init__(self, store: Mapping[str, Mapping[str, Any]], policy: Mapping[str, Any],
                 config: Config | None = None, client: GroqClient | None = None,
                 traceware: TraceWareClient | None = None):
        self.store, self.policy = store_from_rows(store), policy_from_dict(policy)
        self.cfg = config or Config.load()
        self.kernel = Kernel(self.store, self.policy, self.cfg)
        self.tools = ToolBox(self.store, self.policy, self.kernel)
        self.client = client
        if self.client is None and self.cfg.use_llm:
            self.client = GroqClient(self.cfg)
        self.tactician = Tactician(self.client) if self.client and self.client.available else None
        self.traceware = traceware
        if self.traceware is None and self.cfg.traceware_enabled:
            self.traceware = TraceWareClient(self.cfg)
        self.traces: list[dict] = []
        self.negotiation_id = "neg"

    def start(self, negotiation_id: str) -> None:
        self.negotiation_id = negotiation_id
        self.kernel.reset()
        self.tools.reset()
        self.traces = []

    # ------------------------------------------------------------------ gate

    def _verify(self, text: str, move: Move, rnd: int, attempt: int) -> tuple[bool, Verdict, Any]:
        local = local_check(text, self.tools.log, rnd, move.name, move.facts)
        if not local.ok:
            return False, local, None
        if self.traceware is None:
            return True, local, None
        scope = self.cfg.traceware_scope
        if scope == "deal_only" and move.msg_type != "accept":
            return True, local, None
        trace_id = f"{self.negotiation_id}-r{rnd}-a{attempt}"
        obs = build_observations(trace_id, move.items, {s: p.name for s, p in self.store.items()}) \
            if move.msg_type == "accept" else []
        tw = self.traceware.verify(self.negotiation_id, f"buyer-{self.negotiation_id}", trace_id, text, obs)
        if not tw.available:          # outage or config error: never PASS on its own; local check already passed
            return True, local, tw
        return tw.passed, Verdict(tw.passed, [] if tw.passed else [tw.evidence()]), tw

    # ------------------------------------------------------------------ turn

    def respond(self, message: Mapping[str, Any]) -> dict[str, Any]:
        t0 = time.perf_counter()
        rnd = int(message.get("round", 1))
        parsed = parse_message(message)
        opts, default = self.tools.compute_offer(message)
        move_name, text, source = default, "", "template"
        evidence: str | None = None
        trace: dict[str, Any] = {"round": rnd, "buyer": parsed.safe_summary(), "claims": [vars(c) for c in parsed.claims],
                                 "attempts": []}

        # choose a move; a bid the kernel accepts is always accepted, the LLM only picks wording / safe alternatives
        use_llm = self.tactician is not None and default not in ("accept", "walk_away", "out_of_stock")
        move = opts[default]
        if move.msg_type == "accept":
            self.tools.accept_deal(move)
        sent_text, last_tw = "", None
        for attempt in range(self.cfg.max_regenerations + 1):
            if use_llm and attempt < self.cfg.max_regenerations:
                ch = self.tactician.choose(parsed.safe_summary(), opts, default, evidence)
                if ch:
                    move, text, source = opts[ch.move], ch.message, "llm"
                else:
                    move, text, source = opts[default], render(default, opts[default].facts), "template"
            else:
                move, text, source = opts[default], render(default, opts[default].facts), "template"
            ok, verdict, tw = self._verify(text, move, rnd, attempt)
            last_tw = tw
            trace["attempts"].append({"move": move.name, "text": text, "source": source, "local_ok": verdict.ok,
                                      "reasons": verdict.reasons,
                                      "traceware": None if tw is None else {
                                          "decision": tw.decision, "violations": tw.violations, "claims": tw.claims,
                                          "available": tw.available, "error": tw.error, "credits": tw.credits_charged,
                                          "latency_s": round(tw.latency_s, 3)}})
            if ok:
                sent_text = text
                break
            evidence = verdict.evidence()
            if not use_llm:
                break
        if not sent_text:
            move, sent_text = opts[default], LAST_RESORT
            if render(default, opts[default].facts) and local_check(
                    render(default, opts[default].facts), self.tools.log, rnd, default, opts[default].facts).ok:
                sent_text = render(default, opts[default].facts)
            trace["fallback"] = True
        move = self.kernel.commit(move)
        out: dict[str, Any] = {"type": move.msg_type, "text": sent_text}
        if move.msg_type == "offer":
            out["items"] = move.items
        trace.update({"sent": sent_text, "move": move.name, "msg_type": move.msg_type,
                      "latency_s": round(time.perf_counter() - t0, 4)})
        self.traces.append(trace)
        return out
