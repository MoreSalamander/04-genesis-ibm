# Bob Session 2 — copy-paste prompt

> Paste this to IBM Bob with the repo open. Plan mode first, approve, then implement.

---

Session 1 left the vendor-concentration rule fail-closed (`get_vendor_share` has no
baseline → always NEEDS_REVIEW). Session 2 gives it the real spend baseline. Read
`docs/bob-evidence/SESSION-PLAN.md` (Session 2), `app/governance/packs.py`, and
`policy/studio-governance-v1.yaml`, then:

1. **Implement `app/governance/spend_history.py`** — the studio's deterministic
   trailing-12-month vendor-spend baseline (a seeded, in-repo fixture; no network, no
   randomness at import time — hardcode or derive from a fixed seed):
   - 8–12 vendors with realistic annual spend across render compute, cloud, facilities,
     post, and marketing. Total trailing-12m spend around $38M.
   - **Engineered shares (these exact relationships are the acceptance bar):**
     - `HelioCompute` existing spend ≈ $8.9M — so that after adding a $2.8M proposal,
       `(8.9M + 2.8M) / (38M + 2.8M) ≈ 0.287` → **above the 0.25 cap → VIOLATION**.
     - `NimbusRender` existing spend ≈ $1.3M — after the same $2.8M,
       `(1.3M + 2.8M) / 40.8M ≈ 0.10` → comfortably **COMPLIANT**.
   - Public interface:
     `get_vendor_share(vendor: str, additional_spend_usd: float = 0.0) -> float | None`
     — returns the vendor's share of trailing spend INCLUDING the proposed amount
     (share-after math above); an unknown vendor has existing spend 0 (its share is just
     its own proposal against the enlarged total); return `None` ONLY if the baseline
     itself cannot be loaded.

2. **Wire it into the vendor-concentration evaluator** in `packs.py`:
   - pass the proposal's `amount_usd` as `additional_spend_usd`;
   - empty `vendor` field ⇒ **EXEMPT** (rule not applicable), with a clause saying so;
   - `None` baseline ⇒ keep the existing fail-closed NEEDS_REVIEW;
   - findings keep `observed` (vendor, share, existing/total spend) vs `threshold`.

3. **Add tests** to `tests/test_governance_engine.py` (new tests only; don't touch the
   existing ones): flagship $2.8M + HelioCompute ⇒ vendor-concentration **VIOLATION**
   (observed share > 0.25 and verdict BLOCKED via `verdict_from`); same proposal with
   vendor `NimbusRender` ⇒ **COMPLIANT**; vendor `""` ⇒ **EXEMPT**; unknown vendor
   `"Wildcat FX"` ⇒ COMPLIANT with share ≈ amount/(total+amount).

Acceptance: `.venv/bin/pytest tests/test_governance_engine.py -q` fully green, and the
FLAGSHIP proposal from `seed/proposals.py` now yields budget NEEDS_REVIEW +
vendor-concentration VIOLATION + risk COMPLIANT ⇒ verdict **BLOCKED**.
