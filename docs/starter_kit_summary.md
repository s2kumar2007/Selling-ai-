# Starter kit summary

- `store.csv`: 100 products, 6 categories (apparel 45, footwear 28, accessories 10, electronics 7, bags 6, watches 4). 15 out of stock, 26 with stock <= 3.
- `policy.json`: max discount 0.25; min margin per category 0.22-0.35; 10 rounds.
- Margin is defined on selling price: margin = (unit_price - cost) / unit_price.
- Floor = ceil(max(cost / (1 - min_margin), price * (1 - max_discount))); ranges 75%-95% of list. Margin binds for 42 products, discount for 58.
- Messages: buyer sends request / counter / accept / walk_away; seller sends offer / accept / walk_away / message. Items are {sku, qty, unit_price}. The harness adds `round`.
- A deal is the seller's last offer (buyer accepts) or the buyer's last priced items (seller accepts).
- Truthfulness is regex-checked in `harness.check_text`: numbers >= 100 must be in-play amounts, percentages real, stock claims exact, no pressure words, no fee words.
- Score = value - 1.0*policy - 0.5*truth - 0.25*deadlock. Baseline example seller: 48.5 (deal rate 0.757, margin kept 0.673, 21 deadlocks, 0 violations).
- Rezolve TraceWare: POST /api/v1/traceware/verify, X-API-KEY header; decisions PASS / WARN / REGENERATE / BLOCK.
