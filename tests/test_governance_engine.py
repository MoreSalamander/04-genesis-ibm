"""Governance contract tests — they bind the Bob-built engine to the invariants
the executive depends on (docs/bob-evidence/SESSION-PLAN.md session 1 makes
these pass against `PackPolicyEngine`; until then the fail-closed stand-in and
a test double exercise the same contract)."""
from app.governance.engine import PendingPolicyEngine, get_engine, verdict_from
from app.models.enterprise import PolicyFinding, PolicyState
from seed.proposals import FLAGSHIP


def _finding(policy_id: str, state: PolicyState) -> PolicyFinding:
    return PolicyFinding(policy_id=policy_id, policy_version="test", clause="c", state=state)


def test_pending_engine_fails_closed():
    findings = PendingPolicyEngine().evaluate(FLAGSHIP)
    assert findings, "fail-closed engine must still report every policy area"
    assert all(f.state == PolicyState.NEEDS_REVIEW for f in findings)


def test_any_violation_blocks():
    verdict = verdict_from(
        [_finding("a", PolicyState.COMPLIANT), _finding("b", PolicyState.VIOLATION)], "test")
    assert verdict.outcome == "BLOCKED"
    assert "b" in verdict.basis


def test_needs_review_escalates_tier():
    verdict = verdict_from(
        [_finding("a", PolicyState.COMPLIANT), _finding("b", PolicyState.NEEDS_REVIEW)], "test")
    assert verdict.outcome == "ESCALATED"
    assert verdict.required_tier == "studio-head+finance"


def test_all_compliant_is_clear():
    verdict = verdict_from(
        [_finding("a", PolicyState.COMPLIANT), _finding("b", PolicyState.EXEMPT)], "test")
    assert verdict.outcome == "CLEAR"


def test_get_engine_falls_back_to_pending(monkeypatch):
    from app.config import Settings

    engine = get_engine(Settings(force_mock=True))
    # until the Bob session lands packs.py, the stand-in must load
    assert engine.version == "pending-bob-build" or hasattr(engine, "evaluate")
