"""Criterion scoring — COMPUTED IN CODE (locked §2.2 rule 1).

Each evidence item may carry a known metric; normalizers map raw values onto
0..1 (direction-aware). A criterion's score is the mean of its items' normalized
values; the recommendation strength is the weighted sum, damped by the
governance verdict. Gemini writes the rationale around these numbers — it never
produces them.
"""
from __future__ import annotations

from app.models.enterprise import (
    CriterionScore,
    DecisionProposal,
    EvidenceItem,
    GovernanceVerdict,
)

# metric → (lo, hi) mapped to (0, 1); reversed ranges score lower-is-better
NORMALIZERS: dict[str, tuple[float, float]] = {
    "projected_utilization":    (0.50, 1.00),
    "payback_months":           (36.0, 12.0),
    "queue_saturation_pct":     (60.0, 100.0),
    "overflow_incidents_90d":   (0.0, 12.0),
    "slate_vfx_titles":         (0.0, 8.0),
    "vendor_delivery_slip_days": (45.0, 0.0),
    "integration_lead_weeks":   (16.0, 4.0),
    "capex_share_of_annual":    (0.20, 0.02),
}

CRITERIA_WEIGHTS: dict[str, float] = {
    "financial": 0.35,
    "operational": 0.30,
    "strategic": 0.20,
    "risk": 0.15,          # scored as "assurance": higher = lower risk exposure
}


def normalize(item: EvidenceItem) -> float | None:
    bounds = NORMALIZERS.get(item.metric)
    if bounds is None or item.value is None:
        return None
    lo, hi = bounds
    if lo == hi:
        return None
    t = (item.value - lo) / (hi - lo)
    return max(0.0, min(1.0, t))


def score_criterion(criterion: str, items: list[EvidenceItem]) -> CriterionScore:
    weight = CRITERIA_WEIGHTS.get(criterion, 0.0)
    scored: list[tuple[str, float]] = []
    for item in items:
        normalized = normalize(item)
        if normalized is not None:
            scored.append((f"{item.metric}={item.value}→{normalized:.2f}", normalized))
    if scored:
        value = sum(v for _, v in scored) / len(scored)
        basis = f"mean of {len(scored)} normalized metric(s): " + ", ".join(k for k, _ in scored)
    else:
        value = 0.5
        basis = "no quantitative evidence for this criterion — neutral prior 0.5"
    return CriterionScore(
        criterion=criterion, weight=weight, score=round(value, 3), basis=basis,
        cited_evidence_ids=[i.id for i in items],
    )


def score_all(proposal: DecisionProposal) -> list[CriterionScore]:
    by_kind: dict[str, list[EvidenceItem]] = {c: [] for c in CRITERIA_WEIGHTS}
    for item in proposal.evidence:
        by_kind.setdefault(item.kind, []).append(item)
    return [score_criterion(criterion, by_kind.get(criterion, []))
            for criterion in CRITERIA_WEIGHTS]


def recommendation_strength(scores: list[CriterionScore], verdict: GovernanceVerdict | None) -> float:
    """strength = Σ weight×score, damped by the verdict — computed, never asserted."""
    total = sum(s.weight * s.score for s in scores)
    norm = sum(s.weight for s in scores) or 1.0
    strength = total / norm
    if verdict is not None:
        if verdict.outcome == "BLOCKED":
            strength = min(strength, 0.25)
        elif verdict.outcome == "ESCALATED":
            strength *= 0.85
    return round(max(0.05, min(0.95, strength)), 2)
