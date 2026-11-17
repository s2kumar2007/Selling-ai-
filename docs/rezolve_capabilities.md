# Rezolve Labs capabilities

| Capability | Status | How it is used |
|---|---|---|
| TraceWare commerce claim verification | Integrated (`seller_agent/traceware.py`), unit-tested against a fake transport; live calls run once the Labs key and merchant ID are in `.env` | Verifies deal and cart claims against recorded actions (`add_to_basket` after `accept_deal`). The local gate covers prices, stock, scarcity, and pressure wording |
| TraceWare configured checks (`GET /traceware/checks`) | Read from the docs | Confirms enabled checks: `cart_contents`, `order_completed` |
| Managed knowledge retrieval | Documents generated (`docs/kb/`), upload pending endpoint details | Informational only (warranty, policy explanations, FAQ, agent card). Never supplies prices or stock |
| Agent builder / managed runtime | Evaluated, not adopted | The deterministic kernel must stay in verified code; revisit only if it can invoke our kernel as external tools |

## Known limits

- **TraceWare scope**: Active checks are restricted to `cart_contents` and `order_completed`. TraceWare validates what the seller claimed it put in the cart or ordered against observations; it does not evaluate list prices, margin floors, inventory stock counts, or conversational pressure tactics. Those are guaranteed locally by `seller_agent/gate.py`.
- **Credit and latency budget**: TraceWare network calls consume API credits and add round-trip latency. In high-frequency negotiations, scoping TraceWare calls to deal-closing turns (`traceware_scope: "deal_only"`) preserves credits while maintaining zero unverified closing claims.
- **Retrieval bounds**: Knowledge documents contain zero numeric pricing, discount caps, or stock figures. Retrieved context is restricted to conversational wording and factual product details.
- **Agent builder decoupling**: Standalone LLM agent builders cannot replace the local kernel without risking unconstrained price concessions or policy hallucinations under adversarial prompting.
