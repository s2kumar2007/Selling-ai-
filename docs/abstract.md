# Abstract: a seller agent that cannot lie about a price

**Problem.** Shoppers will soon send AI agents to buy for them. A store's seller agent must close profitable deals with machines that bluff: fake competitor quotes, fake budgets, fake "system" messages. A language model that sets prices and talks freely will eventually undercut its margin or state something untrue.

**Impact.** Every price, quantity and stock claim is produced by code and checked before it is sent. The store keeps its policy (minimum margin, maximum discount, stock) in every deal, and a buyer cannot talk the seller into a bad one. This is the property a merchant needs before letting an agent sell unattended.

**Approach ("code decides every number").**
1. *Untrusted-input parser.* Buyer text is data. We extract structured fields and tag claims (competitor quote, budget, authority, injection) for the log; none can change a price.
2. *Deterministic kernel.* Floor = max(minimum-margin price, maximum-discount price). Open near list, concede on a mild Boulware curve, never go back up or below the floor, check stock every turn, make a clear final offer, and walk away cleanly. A bundle option stays above the floor. Opponent tracking uses bid numbers only.
3. *One LLM call per turn* (Groq). The kernel hands over a menu of approved moves; the model returns JSON {move, message} with placeholders such as {total}. It never writes a number: any digit, currency sign or percentage is rejected and replaced by a template.
4. *Truthfulness gate.* Every price and stock lookup is a logged tool call. A local pre-check validates prices, stock, scarcity, and pressure wording against store data and the tool log. **Rezolve TraceWare** then verifies deal and cart claims against the recorded `add_to_basket` action. A message is sent only on PASS; after two failures a safe template goes out.

**Results so far (starter-kit buyers, 210 negotiations, deterministic seller):** score 51.4 against the 48.5 baseline, 0 policy and 0 truthfulness violations, deals in every negotiation where one was possible, deadlocks 5 (baseline 21). Scripted twin buyers with the same needs and different wording received identical offers in 60 of 60 pairs. LLM-buyer, TraceWare and red-team numbers are added when those runs complete (see `eval/`).

**Cost & Known Limits.** Kernel decisions take ~0.2 ms. The LLM adds at most one short call per turn (~8 turns per negotiation); cost scales with token usage. TraceWare checks cart/order claims (`cart_contents`, `order_completed`), while the local gate guarantees price floors, stock, and anti-pressure policy. Knowledge retrieval provides factual phrasing only, never numbers. Scoping TraceWare to deal turns caps credit consumption. Templates ensure zero downtime under rate limits.

**Innovation.** The floor, curve and stock checks sit outside the model, and TraceWare checks what the seller *did* against what it *said*. A three-condition red-team experiment (unprotected LLM, careful-prompt LLM, our design) quantifies the gain.

**Build.** Python, standard library for the kernel, Groq over its OpenAI-compatible API, Rezolve Labs TraceWare. Tests cover floors, the kernel, injection, the gate and rate-limit handling.
