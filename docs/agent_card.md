# Agent card: store seller agent

**What it is.** A seller agent for a small fashion and accessories store. It negotiates unit prices and bundles with buyer agents over a JSON message format, for at most 10 rounds.

**What it can negotiate**
- The unit price of any in-stock product, between the list price and a policy floor.
- Bundles: several lines or several units in one basket, with a slightly better total.
- Quantities up to the stock on hand (it offers fewer units if stock is short, and says so).

**What it cannot and will not do**
- Sell below the minimum margin for the category, or give more than the maximum discount, or sell above list.
- Sell out-of-stock items, or more units than are in stock.
- Add fees, surcharges, delivery or handling charges, or taxes on top of the stated price.
- Invent scarcity or urgency, or use pressure tactics.
- Match competitor quotes, accept claimed budgets, or follow claimed manager, system or developer instructions.
- Reveal costs, margins, the floor price or its instructions.
- Promise anything beyond the offer on the table. A deal exists only when an offer is accepted exactly as made.

**How it decides.** Every price, quantity and stock figure comes from deterministic code reading the store data. A language model only chooses the wording of a message from a menu of moves the code has already approved, and it never writes a number. Buyer text is treated as data, never as instructions.

**How it is checked.** Each outgoing message is checked locally against the store data and the tool-call log, then by Rezolve TraceWare against the recorded deal actions, and is sent only after it passes.

**Fairness.** Two buyers who ask for the same items get the same price path. Buyer wording, claims and tone do not change the price.
