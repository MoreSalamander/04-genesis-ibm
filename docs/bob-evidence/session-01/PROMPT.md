# Bob Session 1 — copy-paste prompt

> Paste this to IBM Bob with the repo open. Use **plan mode first** if Bob offers it,
> approve its plan, then let it implement.

---

Read `docs/bob-evidence/SESSION-PLAN.md` (Session 1), `app/governance/engine.py`, and
`app/models/enterprise.py` in this repository. Then implement the policy engine this
system reserves for you:

1. **`app/governance/packs.py`** — a `PackPolicyEngine` class satisfying the
   `PolicyEngine` protocol in `app/governance/engine.py`:
   - constructor `PackPolicyEngine(policy_dir, version)`; a `version` property returning
     the resolved pack version (`"latest"` resolves the highest version found);
   - `evaluate(proposal: DecisionProposal) -> list[PolicyFinding]` — pure, deterministic,
     no network, no LLM calls.

2. **`policy/studio-governance-v1.yaml`** — the first versioned policy pack, with three
   policies (schema is yours to refine as long as every finding carries `policy_id`,
   `policy_version`, the human-readable `clause`, and `observed` vs `threshold` values):
   - `budget-threshold`: for `capex`, amounts above $5,000,000 ⇒ VIOLATION; above
     $2,000,000 ⇒ NEEDS_REVIEW; otherwise COMPLIANT.
   - `vendor-concentration`: no single vendor may exceed 25% of trailing-12-month studio
     spend. For Session 1, read the spend baseline through a small interface
     (`get_vendor_share(vendor) -> float | None`); when no baseline is available, return
     NEEDS_REVIEW (fail-closed) — the real spend-history fixture arrives in Session 2.
   - `risk-classification`: proposal risk class `standard` ⇒ COMPLIANT, `elevated` ⇒
     NEEDS_REVIEW, `restricted` ⇒ VIOLATION (default `standard` when absent).

3. Make the existing contract tests pass against your engine:
   `.venv/bin/pytest tests/test_governance_engine.py -q` — and do not modify
   `app/governance/engine.py`'s `verdict_from` or the models.

The system that consumes this is running; `app/governance/engine.py:get_engine()` will
automatically load your `PackPolicyEngine` the moment `packs.py` imports cleanly.
