"""Full decision loop, hermetic (mock cognition + fail-closed engine, plus a
test-double engine for the flagship VIOLATION→revision arc)."""
import os

os.environ["GENESIS_MOCK"] = "1"

import pytest

from app.config import Settings
from app.models.enterprise import (
    Decision,
    DecisionStatus,
    PolicyFinding,
    PolicyState,
)
from seed.proposals import FLAGSHIP


class FlagshipArcEngine:
    """Test double standing in for the Bob-built engine: round 1 catches the
    vendor-concentration VIOLATION; the revised round is COMPLIANT."""

    version = "test-arc-v1"

    def __init__(self):
        self.calls = 0

    def evaluate(self, proposal):
        self.calls += 1
        concentration = PolicyState.VIOLATION if self.calls == 1 else PolicyState.COMPLIANT
        return [
            PolicyFinding(policy_id="budget-threshold", policy_version=self.version,
                          clause="Capex above $5M requires board tier", state=PolicyState.COMPLIANT,
                          observed={"amount_usd": proposal.amount_usd}, threshold={"max": 5_000_000}),
            PolicyFinding(policy_id="vendor-concentration", policy_version=self.version,
                          clause="No vendor may exceed 25% of trailing-12m spend",
                          state=concentration,
                          observed={"share": 0.31 if self.calls == 1 else 0.19},
                          threshold={"max_share": 0.25}),
        ]


@pytest.fixture()
def runtime(tmp_path):
    import app.workflows.runtime as rt_mod

    settings = Settings(data_dir=tmp_path, force_mock=True)
    rt = rt_mod.EnterpriseRuntime(settings)
    rt_mod._runtime = rt
    yield rt
    rt_mod._runtime = None


def _submit(rt) -> Decision:
    from app.workflows.run_decision import run_decision

    dec = Decision(proposal=FLAGSHIP)
    rt.working.put(dec)
    run_decision(dec.id)
    return rt.working.get(dec.id)


def test_pending_engine_never_clears_governance(runtime):
    from app.governance.engine import PendingPolicyEngine

    runtime.policy_engine = PendingPolicyEngine()  # the stand-in is this test's subject
    dec = _submit(runtime)
    assert dec.status == DecisionStatus.AWAITING_AUTHORIZATION
    assert dec.verdict.outcome == "ESCALATED"          # fail-closed: NEEDS_REVIEW everywhere
    assert dec.recommendation.strength <= 0.95
    assert all(f.state == PolicyState.NEEDS_REVIEW for f in dec.policy_findings)


def test_flagship_arc_violation_then_revision_then_authorized(runtime):
    from app.workflows.run_decision import run_authorization, run_decision

    runtime.policy_engine = FlagshipArcEngine()
    dec = _submit(runtime)
    assert dec.verdict.outcome == "BLOCKED"
    blocked_strength = dec.recommendation.strength
    assert blocked_strength <= 0.25                    # computed damping

    run_authorization(dec.id, "revise", "split the build-out across two vendors")
    dec = runtime.working.get(dec.id)
    assert dec.round == 2
    assert dec.verdict.outcome == "CLEAR"              # revised round passes
    assert dec.recommendation.strength > blocked_strength
    assert dec.status == DecisionStatus.AWAITING_AUTHORIZATION

    run_authorization(dec.id, "approved", "authorized with the vendor split")
    dec = runtime.working.get(dec.id)
    assert dec.status == DecisionStatus.AUTHORIZED
    assert dec.objective is not None and dec.objective.requirements


def test_approval_refused_while_blocked(runtime):
    class AlwaysViolates(FlagshipArcEngine):
        def evaluate(self, proposal):
            self.calls = 0                             # never advances to compliant
            return super().evaluate(proposal)

    from app.workflows.run_decision import run_authorization

    runtime.policy_engine = AlwaysViolates()
    dec = _submit(runtime)
    assert dec.verdict.outcome == "BLOCKED"
    run_authorization(dec.id, "approved", "just do it")
    dec = runtime.working.get(dec.id)
    # governance cannot be overridden by approval alone (locked §2.8)
    assert dec.status in (DecisionStatus.AWAITING_AUTHORIZATION,)
    assert dec.round == 2
    assert any(a.decision == "revise" and "VIOLATION" in a.note for a in dec.authorizations)


def test_action_delivery_closes_and_promotes(runtime):
    from app.workflows.run_decision import run_authorization

    runtime.policy_engine = FlagshipArcEngine()
    dec = _submit(runtime)
    run_authorization(dec.id, "revise", "split vendors")
    run_authorization(dec.id, "approved", "go")
    final = runtime.executive.attach_action(
        dec.id, "Provisioning change delivered by IBM Bob (session 4)",
        ["docs/bob-evidence/session-04/diff.patch"])
    assert final == "CLOSED"
    dec = runtime.working.get(dec.id)
    assert dec.action_record.delivered_by == "ibm-bob"
    events = {e["event"] for e in runtime.bus.tail(200)}
    assert {"decision.submitted", "policy.finding", "governance.verdict",
            "recommendation.created", "authorization.decided",
            "action.objective_issued", "action.delivered", "decision.closed"} <= events


def test_revise_amendments_change_the_proposal(runtime):
    from app.workflows.run_decision import run_authorization

    runtime.policy_engine = FlagshipArcEngine()
    dec = _submit(runtime)
    run_authorization(dec.id, "revise", "split across two vendors",
                      {"vendor": "NimbusRender", "ignored_field": "x"})
    dec = runtime.working.get(dec.id)
    assert dec.proposal.vendor == "NimbusRender"          # whitelisted field applied
    assert not hasattr(dec.proposal, "ignored_field")
    assert any("amended vendor → NimbusRender" in g for g in dec.revision_guidance)
    assert dec.round == 2


def test_latch_released_after_rejection(runtime):
    from app.memory.ephemeral import DECISION_LATCH, LATCH_TTL_S
    from app.workflows.run_decision import run_authorization

    dec = _submit(runtime)
    run_authorization(dec.id, "rejected", "not this quarter")
    assert runtime.working.get(dec.id).status == DecisionStatus.REJECTED
    assert runtime.ephemeral.acquire_latch(DECISION_LATCH, "probe", LATCH_TTL_S) is None
    runtime.ephemeral.release_latch(DECISION_LATCH)
