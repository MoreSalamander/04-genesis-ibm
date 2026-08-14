"""Domain model for Enterprise Decision Intelligence (locked §2.2, §2.6).

The decision lineage is explicit and auditable:
Proposal → Evidence Package → Criterion Scores (computed) → Policy Findings
(rule-derived, Bob-built engine) → Governance Verdict (function of findings) →
Recommendation → Authorization (human signal) → Software Action (IBM Bob) →
Closure. Scores and compliance outcomes are computed in code — Gemini frames,
cites and narrates; it never emits an aggregate number or a compliance state.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class DecisionStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    EVALUATING = "EVALUATING"
    GOVERNANCE_REVIEW = "GOVERNANCE_REVIEW"
    RECOMMENDED = "RECOMMENDED"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"   # durable Temporal pause
    AUTHORIZED = "AUTHORIZED"
    ACTIONED = "ACTIONED"                               # Bob delivery evidence attached
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    INCOMPLETE = "INCOMPLETE"                           # substrate failure — never fabricated


class PolicyState(str, Enum):
    COMPLIANT = "COMPLIANT"
    VIOLATION = "VIOLATION"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    EXEMPT = "EXEMPT"


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=lambda: _id("evd"))
    kind: str                      # financial | operational | strategic | risk
    statement: str
    metric: str = ""               # normalizer key (app/agents/evaluation/scoring.py)
    value: Optional[float] = None
    unit: str = ""
    source: str = ""               # where this evidence came from (system, report, sibling API)
    at: datetime = Field(default_factory=_now)


class DecisionProposal(BaseModel):
    title: str
    description: str
    category: str                  # capex | vendor | distribution | staffing | other
    amount_usd: float = 0.0
    vendor: str = ""
    requested_by: str = "studio-operations"
    evidence: list[EvidenceItem] = Field(default_factory=list)


class CriterionScore(BaseModel):
    """One evaluation criterion. The score is COMPUTED from declared weights over
    evidence values; the rationale is Gemini's, with citations into the evidence."""

    id: str = Field(default_factory=lambda: _id("crt"))
    criterion: str                 # financial | operational | strategic | risk
    weight: float
    score: float                   # 0..1, computed in code
    basis: str = ""                # how the computation derived it
    rationale: str = ""            # Gemini narrative, cites evidence ids
    cited_evidence_ids: list[str] = Field(default_factory=list)


class PolicyFinding(BaseModel):
    """One policy judged against the proposal — rule-derived by the Bob-built engine."""

    id: str = Field(default_factory=lambda: _id("pol"))
    policy_id: str
    policy_version: str
    clause: str                    # the human-readable clause that triggered
    state: PolicyState
    observed: dict[str, Any] = Field(default_factory=dict)
    threshold: dict[str, Any] = Field(default_factory=dict)
    detail: str = ""


class GovernanceVerdict(BaseModel):
    """Computed from findings: any VIOLATION blocks; NEEDS_REVIEW escalates."""

    outcome: str                   # CLEAR | BLOCKED | ESCALATED
    required_tier: str             # studio-head | studio-head+finance | board
    basis: str = ""
    finding_ids: list[str] = Field(default_factory=list)
    policy_version: str = ""


class Recommendation(BaseModel):
    id: str = Field(default_factory=lambda: _id("rec"))
    action: str
    rationale: str
    strength: float                # computed: f(criterion scores, verdict) — never model-asserted
    caveats: list[str] = Field(default_factory=list)
    at: datetime = Field(default_factory=_now)


class AuthorizationRecord(BaseModel):
    decision: str                  # approved | rejected | revise
    note: str = ""
    by: str = "studio-head"
    at: datetime = Field(default_factory=_now)


class SoftwareActionObjective(BaseModel):
    """The Authorized Software Objective handed to IBM Bob (locked §2.5b)."""

    id: str = Field(default_factory=lambda: _id("aso"))
    objective: str
    business_purpose: str = ""
    requirements: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_class: str = "standard"
    issued_at: datetime = Field(default_factory=_now)


class ActionRecord(BaseModel):
    """Delivery evidence for the Software Action — executed by IBM Bob during
    development, demonstrably (session record, diff, tests)."""

    delivered_by: str = "ibm-bob"
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)   # docs/bob-evidence/ paths, commits
    at: datetime = Field(default_factory=_now)


class Promotion(BaseModel):
    datahub_urns: list[str] = Field(default_factory=list)
    at: datetime = Field(default_factory=_now)


class Decision(BaseModel):
    id: str = Field(default_factory=lambda: _id("dec"))
    proposal: DecisionProposal
    status: DecisionStatus = DecisionStatus.SUBMITTED
    round: int = 1                                     # increments on request-revision
    revision_guidance: list[str] = Field(default_factory=list)
    scores: list[CriterionScore] = Field(default_factory=list)
    policy_findings: list[PolicyFinding] = Field(default_factory=list)
    verdict: Optional[GovernanceVerdict] = None
    recommendation: Optional[Recommendation] = None
    authorizations: list[AuthorizationRecord] = Field(default_factory=list)
    objective: Optional[SoftwareActionObjective] = None
    action_record: Optional[ActionRecord] = None
    promotion: Optional[Promotion] = None
    escalated: bool = False
    incomplete_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    def touch(self) -> None:
        self.updated_at = _now()

    def finding_counts(self) -> dict[str, int]:
        counts = {state.value: 0 for state in PolicyState}
        for finding in self.policy_findings:
            counts[finding.state.value] += 1
        return counts
