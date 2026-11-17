# Selling to Machines: seller agent

Techfest IIT Bombay 2026-27, AgentX (Rezolve AI), Challenge 2. A seller agent that negotiates price and bundles with AI buyer bots. **Code decides every number; the LLM never invents a price, stock count or policy.**

## Layout
- `seller.py` harness entry point (`Seller`)
- `seller_agent/` parser, kernel, floor, templates, tactician, llm_client (Groq), gate, traceware, agent
- `tools/` the five logged tool calls
- `llm_buyers/` our own LLM buyer personas (offline scripted stand-in when no key)
- `eval/` `run_eval.py`, `fairness.py`, `redteam.py`, `tune.py`, `sweep.py`, saved `baselines/`
- `demo/` trace panel; `scripts/` helpers; `docs/` abstract, architecture note, agent card, demo script
- `starter_kit/` the organisers' files, unmodified

## Setup
    cp .env.example .env            # add GROQ_API_KEY, REZOLVE_API_KEY, REZOLVE_MERCHANT_ID (never commit .env)
    cp config.example.json config.json   # set seller_model / buyer_model (different families), use_llm, traceware_enabled
    python3 -m pytest -q tests

## Run
    cd starter_kit && python3 evaluate.py --seller ../seller.py --log ../logs/transcripts.jsonl
    python3 eval/run_eval.py --buyers public          # kernel seller vs the starter bots
    python3 eval/run_eval.py --buyers llm             # persona buyers
    python3 eval/fairness.py                          # twin-buyer fairness
    python3 eval/redteam.py                           # needs GROQ_API_KEY: unprotected vs careful vs Option D
    python3 scripts/demo_run.py --persona injector    # writes demo/panel.html

## Baseline (kernel only, starter-kit buyers, 210 negotiations)
Score 51.4 (example seller 48.5), 0 policy and 0 truthfulness violations, deals in every feasible negotiation.
See `docs/starter_kit_summary.md` and `eval/baselines/`.
