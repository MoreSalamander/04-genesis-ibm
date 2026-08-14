"""Criterion scores and recommendation strength are computed in code (locked §2.2)."""
from app.agents.evaluation.scoring import (
    normalize,
    recommendation_strength,
    score_all,
    score_criterion,
)
from app.models.enterprise import EvidenceItem, GovernanceVerdict
from seed.proposals import FLAGSHIP


def test_normalizers_are_direction_aware():
    good_payback = EvidenceItem(kind="financial", statement="", metric="payback_months", value=12)
    bad_payback = EvidenceItem(kind="financial", statement="", metric="payback_months", value=36)
    assert normalize(good_payback) == 1.0
    assert normalize(bad_payback) == 0.0


def test_unknown_metric_contributes_nothing():
    item = EvidenceItem(kind="financial", statement="", metric="vibes", value=99)
    assert normalize(item) is None
    score = score_criterion("financial", [item])
    assert score.score == 0.5 and "neutral prior" in score.basis


def test_flagship_scores_are_deterministic_and_based():
    scores = {s.criterion: s for s in score_all(FLAGSHIP)}
    assert set(scores) == {"financial", "operational", "strategic", "risk"}
    for score in scores.values():
        assert 0.0 <= score.score <= 1.0
        assert score.basis
    assert scores["operational"].score > 0.7      # engineered: capacity is the binding constraint


def test_strength_damped_by_verdict():
    scores = score_all(FLAGSHIP)
    clear = GovernanceVerdict(outcome="CLEAR", required_tier="studio-head")
    blocked = GovernanceVerdict(outcome="BLOCKED", required_tier="studio-head")
    escalated = GovernanceVerdict(outcome="ESCALATED", required_tier="studio-head+finance")
    s_clear = recommendation_strength(scores, clear)
    s_escalated = recommendation_strength(scores, escalated)
    s_blocked = recommendation_strength(scores, blocked)
    assert s_blocked <= 0.25
    assert s_escalated < s_clear
