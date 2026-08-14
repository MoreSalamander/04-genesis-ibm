# IBM Bob session plan — the Bob-built subsystems (locked §2.5a)

Track requirement (verified): *"your project must be built using IBM Bob as part of the
development process … Projects that do not demonstrate usage of IBM Bob will not meet the
requirements for the IBM track."* These sessions are that demonstration. The Studio Head
drives Bob on their trial account; the builder guides; every session's plan, record and diff
is captured here.

## Evidence capture (every session)

1. Export/record the session: Bob's plan output, the conversation, BobShell command log
   (format verified empirically at session 1 — screenshots/screen-recording as fallback).
2. Save into `docs/bob-evidence/session-NN/` (`plan.md`, `record.*`, `diff.patch`).
3. Commit Bob's changes with `Built-with: IBM Bob (session NN)` in the message body.
4. 10–20 s of each session screen-recorded for the demo video's built-with-Bob segment.

## Session 1 — policy pack schema + loader (`app/governance/packs.py`, `policy/*.yaml`)

**Bob mode: plan → code.** Target contract (already depended on by `app/governance/engine.py`):

- `PackPolicyEngine(policy_dir, version)` implementing the `PolicyEngine` protocol:
  `version: str` property; `evaluate(proposal: DecisionProposal) -> list[PolicyFinding]`.
- Loads versioned YAML packs from `policy/` (e.g. `studio-governance-v1.yaml`). Pack schema
  (Bob may refine, keeping these semantics): a list of policies, each with `id`, `clause`
  (human-readable), `applies_to` (category filter), and a `rule` — one of:
  - `amount_max`: {field: amount_usd, max: <usd>, above: VIOLATION|NEEDS_REVIEW}
  - `vendor_concentration`: {max_share: <0..1>, window_days: N, source: ledger}
    — share of studio spend with this vendor; above the cap ⇒ VIOLATION
  - `risk_class`: {classes: {standard: COMPLIANT, elevated: NEEDS_REVIEW, restricted: VIOLATION}}
- Every finding must carry `observed` and `threshold` values and the pack `clause`.
- Deterministic, pure, no network. `pytest tests/test_governance_engine.py` green
  (tests already written — they currently exercise the contract via a test double).

## Session 2 — vendor-concentration data + evaluators hardening

**Bob mode: code + ask.** The concentration rule needs the spend baseline: Bob implements
`app/governance/spend_history.py` (deterministic seeded vendor-spend fixture mirroring the
studio's world: HelioCompute share engineered just above the cap so the flagship catches a
real VIOLATION) and wires it into the evaluator. Edge cases: zero-history vendors, EXEMPT
categories, versioned pack selection (`POLICY_VERSION=latest` resolves highest semver).

## Session 3 — console dossier panel (`frontend/components/PolicyFindings.tsx`)

**Bob mode: code.** The policy-findings panel of the governance chamber: one row per
finding — state chip (COMPLIANT emerald · VIOLATION signal-red · NEEDS_REVIEW amber ·
EXEMPT slate), the clause, observed-vs-threshold values, pack version footer. Props typed
against `lib/api.ts` `PolicyFinding`. Matches the existing chamber styles (`globals.css`).

## Session 4 (flagship demo beat) — the Software Action

**Bob mode: orchestration/advanced.** When the Studio Head authorizes the flagship decision,
the system issues the Authorized Software Objective (render-capacity provisioning change +
tests). Bob executes it on camera; the diff/test-run/session record becomes the decision's
`ActionRecord.evidence_refs`. This is Handoff §4's locked flow, demonstrated end to end.
