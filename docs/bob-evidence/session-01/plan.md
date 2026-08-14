# Session 1 Plan — Policy Pack Schema + Loader

**Bob session:** 1  
**Target files:** `app/governance/packs.py`, `policy/studio-governance-v1.yaml`  
**Success gate:** `pytest tests/test_governance_engine.py` green; `app/governance/engine.py` untouched.

---

## Overview

The governance subsystem reserves a slot for the Bob-built `PackPolicyEngine`. Until it
exists, `get_engine()` in `engine.py` falls back to `PendingPolicyEngine` (fail-closed
NEEDS_REVIEW everywhere). This session fills that slot: a YAML-driven policy pack loader
that evaluates proposals against three deterministic rules, producing `PolicyFinding` objects
the rest of the system already consumes.

The flagship fixture (`seed/proposals.py:FLAGSHIP`) is a $2.8 M capex proposal for vendor
HelioCompute — it sits above the $2 M NEEDS_REVIEW threshold but below the $5 M VIOLATION
threshold, so the budget-threshold rule alone returns NEEDS_REVIEW. Vendor-concentration
in Session 1 is fail-closed (no spend baseline yet — that arrives in Session 2). Risk class
defaults to `standard` → COMPLIANT.

**No changes to `app/governance/engine.py` or `app/models/enterprise.py`.**

---

## Sub-Tasks

---

### Sub-Task 1 — Policy YAML pack

**Intent:** Author the canonical versioned policy file. This is the machine-readable contract
for all three rules; the loader (`packs.py`) references it by filename.

**Expected Outcomes:**
- `policy/studio-governance-v1.yaml` exists and is valid YAML.
- Contains three policy entries: `budget-threshold`, `vendor-concentration`,
  `risk-classification`, each with `id`, `clause`, `applies_to`, and a `rule` block.
- Budget thresholds: ≥$5 M → VIOLATION, ≥$2 M → NEEDS_REVIEW, below → COMPLIANT.
- Vendor concentration: `max_share: 0.25`, `window_days: 365`, `source: ledger`.
- Risk classes: `standard: COMPLIANT`, `elevated: NEEDS_REVIEW`, `restricted: VIOLATION`.

**Todo List:**
1. Create `policy/studio-governance-v1.yaml` with `version: "1"` at the top.
2. Add the `budget-threshold` policy block (applies_to: capex; rule type: amount_max).
3. Add the `vendor-concentration` policy block (applies_to: vendor,capex; rule type:
   vendor_concentration).
4. Add the `risk-classification` policy block (applies_to: "*"; rule type: risk_class).

**Relevant Context:**
- Pack schema from SESSION-PLAN.md: `id`, `clause`, `applies_to`, `rule`.
- Rule shapes: `amount_max`, `vendor_concentration`, `risk_class` — defined in SESSION-PLAN.md.
- The `version` field of the pack file is what `PackPolicyEngine.version` returns.

**Status:** [ ] pending

---

### Sub-Task 2 — `PackPolicyEngine` loader and rule evaluators (`app/governance/packs.py`)

**Intent:** Implement the Python module that `get_engine()` in `engine.py` imports when it
exists. The class must satisfy the `PolicyEngine` protocol — no modifications to `engine.py`
are needed or permitted.

**Expected Outcomes:**
- `app/governance/packs.py` exists and imports cleanly.
- `PackPolicyEngine(policy_dir, version)` constructor loads YAML packs from `policy_dir`.
  - `version="latest"` resolves the highest semver pack file present.
  - `version="1"` (or any explicit string) loads the pack whose YAML `version` field matches.
- `engine.version` property returns the resolved pack version string.
- `evaluate(proposal)` dispatches each policy through its rule evaluator and returns a
  `list[PolicyFinding]`.

**Rule evaluator behaviour (pure, deterministic, no network):**

| Rule type | Logic |
|---|---|
| `amount_max` | Check `proposal.amount_usd` against each threshold bracket; emit the matching `PolicyState`. |
| `vendor_concentration` | Call `get_vendor_share(vendor) -> float \| None`; if `None` → NEEDS_REVIEW (fail-closed); if above `max_share` → VIOLATION. |
| `risk_class` | Read `risk_class` from proposal evidence or default `"standard"`; map to `PolicyState`. |

- `applies_to` field: if set to `"*"` the policy always applies; otherwise it applies only when
  `proposal.category` is in the `applies_to` list. Policies that do not apply produce no finding.
- Every finding populates `observed` and `threshold` dicts for auditability.
- `get_vendor_share` stub (Session 1): always returns `None` → always NEEDS_REVIEW for
  vendor-concentration. Session 2 replaces this with real spend data.

**Todo List:**
1. Create `app/governance/packs.py` with imports and `PackPolicyEngine` class scaffold.
2. Implement pack discovery: scan `policy_dir` for `*-v*.yaml` files; parse version numbers;
   resolve `"latest"` to the highest version.
3. Implement the YAML loader: parse the selected file into a list of policy dicts.
4. Implement `applies_to` filtering helper.
5. Implement `_eval_amount_max(rule, proposal) -> PolicyFinding | None`.
6. Implement `_eval_vendor_concentration(rule, proposal) -> PolicyFinding | None` with
   `get_vendor_share` stub returning `None`.
7. Implement `_eval_risk_class(rule, proposal) -> PolicyFinding | None`.
8. Implement `evaluate()` — iterate policies, apply filter, dispatch to evaluator, collect findings.
9. Confirm `engine.get_engine(settings)` returns a `PackPolicyEngine` instance (not `PendingPolicyEngine`).

**Relevant Context:**
- `PolicyEngine` Protocol: `app/governance/engine.py` lines 31–34.
- `PolicyFinding` model: `app/models/enterprise.py` lines 82–92 — fields: `id` (auto), `policy_id`,
  `policy_version`, `clause`, `state: PolicyState`, `observed: dict`, `threshold: dict`, `detail`.
- `PolicyState` enum: `app/models/enterprise.py` lines 41–45.
- `DecisionProposal`: `app/models/enterprise.py` lines 59–66 — `category`, `amount_usd`, `vendor`.
- `get_engine` loader: `app/governance/engine.py` lines 89–96 — does `from app.governance.packs import PackPolicyEngine`.
- `Settings.policy_dir` = `Path("./policy")`, `Settings.policy_version` = `"latest"`.

**Status:** [ ] pending

---

### Sub-Task 3 — Verify tests pass

**Intent:** Confirm the contract tests all go green without touching `engine.py` or models.

**Expected Outcomes:**
- `pytest tests/test_governance_engine.py -q` reports 5 passed, 0 failed.
- `test_get_engine_falls_back_to_pending` passes (engine has `.evaluate`).
- `test_pending_engine_fails_closed` still passes (unchanged `PendingPolicyEngine`).

**Todo List:**
1. Run `pytest tests/test_governance_engine.py -q`.
2. If any test fails, diagnose and fix in `packs.py` or the YAML — not in `engine.py`.

**Relevant Context:**
- Tests: `tests/test_governance_engine.py` — all five tests, the last uses `Settings(force_mock=True)`
  which triggers `get_engine` fallback check.
- The test double `_finding()` helper constructs minimal `PolicyFinding` objects; the evaluator
  must produce structurally equivalent findings (same fields, correct `state`).

**Status:** [ ] pending

---

## Evidence Artefacts to Capture

After implementation:
- Save Bob's plan output as `docs/bob-evidence/session-01/plan.md` (this file).
- Save the conversation record as `docs/bob-evidence/session-01/record.md` (or screenshot).
- Generate the diff: `git diff HEAD > docs/bob-evidence/session-01/diff.patch`.
- Commit with message body containing `Built-with: IBM Bob (session 01)`.

---

## What is NOT in Scope (Session 1)

- `app/governance/spend_history.py` — Session 2.
- Real vendor-concentration baseline — Session 2 (Session 1 stub always returns `None`).
- `POLICY_VERSION=latest` semver resolution edge cases beyond "pick highest number" — Session 2.
- Frontend `PolicyFindings.tsx` — Session 3.
- Software Action execution — Session 4.
