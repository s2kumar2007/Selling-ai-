# Rezolve Labs capabilities

| Capability | Status | How it is used |
|---|---|---|
| TraceWare commerce claim verification | Integrated (`seller_agent/traceware.py`), unit-tested against a fake transport; live calls run once the Labs key and merchant ID are in `.env` | Final truthfulness gate on every outgoing message; deal turns carry an `add_to_basket` observation recorded after `accept_deal` |
| TraceWare configured checks (`GET /traceware/checks`) | Read from the docs | Confirms enabled checks: `cart_contents`, `order_completed` |
| Managed knowledge retrieval | Documents generated (`docs/kb/`), upload pending the endpoint details | Policy text, product descriptions, FAQ, agent card. No prices or stock |
| Agent builder / managed runtime | Evaluated, not adopted | The kernel must stay in our own code; revisit only if it can call our kernel as tools |
