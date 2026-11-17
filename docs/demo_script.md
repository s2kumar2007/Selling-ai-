# 3-minute demo script

**0:00 The problem (20 s).** "Shoppers will send AI agents to buy. Some of those agents bluff. Our seller agent negotiates with them and cannot be talked into a bad deal or caught saying something untrue."

**0:20 The design (30 s).** Show the architecture diagram. "Code decides every number. The model only picks the wording from a menu of moves the code has approved, and every message passes a local check and Rezolve TraceWare before it is sent."

**0:50 Live: the manipulator (60 s).** Open `demo/panel.html` (`python scripts/demo_run.py --persona injector`). Point at a buyer card: "fake SYSTEM message, tagged *policy override* and *injection*." Then the seller card: "the price moved exactly as the kernel's curve says, not as the buyer asked." Show the local check and the TraceWare verdict with its evidence.

**1:50 Live: a deal (30 s).** Run a cooperative buyer. Show the closing message, the recorded `add_to_basket`, and the TraceWare PASS.

**2:20 Numbers (30 s).** Show the results table: violations 0; deal rate; margin kept; the three-condition chart (unprotected LLM vs careful prompt vs ours).

**2:50 Close (10 s).** "Same buyers, same data: the unprotected model breaks policy; this design does not. Thank you."

*Record only after the live TraceWare and red-team runs are finished, so every number on screen is real.*
