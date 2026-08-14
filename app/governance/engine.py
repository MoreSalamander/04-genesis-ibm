"""Policy engine boundary — THE BOB-BUILT SUBSYSTEM (locked §2.5a).

This module defines the contract the rest of the system depends on. The real
implementation (pack loader + rule evaluators + policy/*.yaml packs) is built
in IBM Bob sessions on the Studio Head's account, to the written plan in
docs/bob-evidence/SESSION-PLAN.md, with evidence captured per session.

Until those sessions land, `PendingPolicyEngine` is the FAIL-CLOSED stand-in:
it judges nothing — every policy area returns NEEDS_REVIEW with an explicit
"policy engine pending" clause, so no decision can silently pass governance.
Honest pending state, never fabricated compliance.

Contract invariants (the executive and tests rely on these):
- evaluate() is pure: proposal in → findings out; no cognition, no network.
- Every finding carries the policy id, version, clause, observed vs threshold.
- Any VIOLATION ⇒ verdict BLOCKED. Any NEEDS_REVIEW ⇒ verdict ESCALATED
  (higher tier). All COMPLIANT/EXEMPT ⇒ CLEAR. (Computed in verdict_from().)
"""
from __future__ import annotations

from typing import Protocol

from app.models.enterprise import (
    DecisionProposal,
    GovernanceVerdict,
    PolicyFinding,
    PolicyState,
)


class PolicyEngine(Protocol):
    version: str

    def evaluate(self, proposal: DecisionProposal) -> list[PolicyFinding]: ...


class PendingPolicyEngine:
    """Fail-closed stand-in until the Bob-built engine lands."""

    version = "pending-bob-build"

    AREAS = ["budget-threshold", "vendor-concentration", "risk-classification"]

    def evaluate(self, proposal: DecisionProposal) -> list[PolicyFinding]:
        return [
            PolicyFinding(
                policy_id=area,
                policy_version=self.version,
                clause="Policy engine pending — this subsystem is built in IBM Bob "
                       "sessions (docs/bob-evidence/SESSION-PLAN.md); until then every "
                       "area requires human review.",
                state=PolicyState.NEEDS_REVIEW,
                detail="fail-closed default: no pack loaded, nothing auto-passes",
            )
            for area in self.AREAS
        ]


def verdict_from(findings: list[PolicyFinding], policy_version: str) -> GovernanceVerdict:
    """The governance verdict is a FUNCTION of findings — computed, auditable."""
    violation = [f for f in findings if f.state == PolicyState.VIOLATION]
    review = [f for f in findings if f.state == PolicyState.NEEDS_REVIEW]
    if violation:
        return GovernanceVerdict(
            outcome="BLOCKED",
            required_tier="studio-head",
            basis=f"{len(violation)} policy violation(s): "
                  + "; ".join(f.policy_id for f in violation),
            finding_ids=[f.id for f in findings],
            policy_version=policy_version,
        )
    if review:
        return GovernanceVerdict(
            outcome="ESCALATED",
            required_tier="studio-head+finance",
            basis=f"{len(review)} area(s) need review: " + "; ".join(f.policy_id for f in review),
            finding_ids=[f.id for f in findings],
            policy_version=policy_version,
        )
    return GovernanceVerdict(
        outcome="CLEAR",
        required_tier="studio-head",
        basis="all policies compliant or exempt",
        finding_ids=[f.id for f in findings],
        policy_version=policy_version,
    )


def get_engine(settings) -> PolicyEngine:
    """Loads the Bob-built engine when present; otherwise the fail-closed stand-in."""
    try:
        from app.governance.packs import PackPolicyEngine  # Bob-built module

        return PackPolicyEngine(settings.policy_dir, settings.policy_version)
    except ImportError:
        return PendingPolicyEngine()
