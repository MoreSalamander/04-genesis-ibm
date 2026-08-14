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


# ---------------------------------------------------------------------------
# PackPolicyEngine resilience tests (session-1 amendment)
# ---------------------------------------------------------------------------

def test_pack_engine_missing_dir_fails_closed(tmp_path):
    """A missing policy directory must NOT raise — engine degrades to NEEDS_REVIEW."""
    from app.governance.packs import PackPolicyEngine

    engine = PackPolicyEngine(tmp_path / "nonexistent", "latest")
    assert engine.version == "missing"
    findings = engine.evaluate(FLAGSHIP)
    assert findings, "degraded engine must still emit a finding"
    assert all(f.state == PolicyState.NEEDS_REVIEW for f in findings)
    assert findings[0].policy_id == "pack-integrity"


def test_pack_engine_unknown_rule_type_fails_closed(tmp_path):
    """An unknown rule type in a loaded pack must produce NEEDS_REVIEW, not be skipped."""
    import yaml
    from app.governance.packs import PackPolicyEngine

    pack = {
        "version": "99",
        "policies": [
            {
                "id": "test-unknown-rule",
                "clause": "A test policy with an unrecognised rule type.",
                "applies_to": "*",
                "rule": {"type": "future_rule_not_yet_implemented"},
            }
        ],
    }
    pack_file = tmp_path / "studio-governance-v99.yaml"
    pack_file.write_text(yaml.safe_dump(pack))

    engine = PackPolicyEngine(tmp_path, "latest")
    findings = engine.evaluate(FLAGSHIP)
    assert findings, "unknown rule type must still produce a finding"
    assert findings[0].state == PolicyState.NEEDS_REVIEW
    assert findings[0].policy_id == "test-unknown-rule"


# ---------------------------------------------------------------------------
# Session 2 — vendor-concentration with real spend baseline
# ---------------------------------------------------------------------------

def _pack_engine():
    """Return a PackPolicyEngine loaded from the real policy directory."""
    from pathlib import Path
    from app.governance.packs import PackPolicyEngine
    return PackPolicyEngine(Path("./policy"), "latest")


def test_helio_vendor_concentration_violation():
    """FLAGSHIP (HelioCompute $2.8M) must produce a vendor-concentration VIOLATION
    and a BLOCKED verdict once the spend baseline is wired in."""
    from app.governance.engine import verdict_from
    engine = _pack_engine()
    findings = engine.evaluate(FLAGSHIP)
    vc = next(f for f in findings if f.policy_id == "vendor-concentration")
    assert vc.state == PolicyState.VIOLATION, (
        f"Expected VIOLATION, got {vc.state}; share={vc.observed.get('share')}"
    )
    assert vc.observed["share"] > 0.25
    verdict = verdict_from(findings, engine.version)
    assert verdict.outcome == "BLOCKED"


def test_nimbus_vendor_concentration_compliant():
    """Same $2.8M proposal with NimbusRender vendor must be COMPLIANT."""
    from app.models.enterprise import DecisionProposal
    proposal = FLAGSHIP.model_copy(update={"vendor": "NimbusRender"})
    engine = _pack_engine()
    findings = engine.evaluate(proposal)
    vc = next(f for f in findings if f.policy_id == "vendor-concentration")
    assert vc.state == PolicyState.COMPLIANT, (
        f"Expected COMPLIANT, got {vc.state}; share={vc.observed.get('share')}"
    )
    assert vc.observed["share"] < 0.25


def test_empty_vendor_concentration_exempt():
    """A proposal with no vendor must be EXEMPT for the concentration rule."""
    proposal = FLAGSHIP.model_copy(update={"vendor": ""})
    engine = _pack_engine()
    findings = engine.evaluate(proposal)
    vc = next(f for f in findings if f.policy_id == "vendor-concentration")
    assert vc.state == PolicyState.EXEMPT


def test_unknown_vendor_concentration_compliant():
    """An unknown vendor ('Wildcat FX') has $0 existing spend;
    share ≈ amount/(total+amount) — well below the cap → COMPLIANT."""
    from app.governance.spend_history import total_baseline_usd
    proposal = FLAGSHIP.model_copy(update={"vendor": "Wildcat FX"})
    engine = _pack_engine()
    findings = engine.evaluate(proposal)
    vc = next(f for f in findings if f.policy_id == "vendor-concentration")
    assert vc.state == PolicyState.COMPLIANT
    expected_share = FLAGSHIP.amount_usd / (total_baseline_usd() + FLAGSHIP.amount_usd)
    assert abs(vc.observed["share"] - expected_share) < 1e-6
