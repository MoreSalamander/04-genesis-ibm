"""Decision Executive — owns the decision objective (locked §2.3) and drives the
locked loop (§2.6):

  proposal → computed criterion scores (+ Gemini rationales) → policy findings
  (Bob-built engine, rule-derived) → governance verdict (computed) →
  recommendation (strength computed) → human authorization signal →
  Authorized Software Objective → Bob delivery evidence → closure → promotion.

Stages are Temporal-activity-callable by decision id; state checkpoints to the
durable store between stages. The ACTIONED tail is event-driven (Bob delivery
arrives on human timescale via the action endpoint), so the workflow completes
at AUTHORIZED without holding the latch hostage.
"""
from __future__ import annotations

from app.agents.evaluation.scoring import recommendation_strength, score_all
from app.governance.engine import verdict_from
from app.memory.ephemeral import DECISION_LATCH
from app.models.enterprise import (
    ActionRecord,
    AuthorizationRecord,
    Decision,
    DecisionStatus,
    Promotion,
    Recommendation,
    SoftwareActionObjective,
)

MAX_ROUNDS = 3


class DecisionExecutive:
    def __init__(self, runtime):
        self.rt = runtime

    # -- helpers ------------------------------------------------------------
    def _get(self, dec_id: str) -> Decision:
        dec = self.rt.working.get(dec_id)
        if dec is None:
            raise RuntimeError(f"unknown decision {dec_id}")
        return dec

    def _save(self, dec: Decision) -> None:
        dec.touch()
        self.rt.working.put(dec)

    # -- stage: evaluate ----------------------------------------------------
    def evaluate(self, dec_id: str) -> str:
        dec = self._get(dec_id)
        if dec.round == 1 and not dec.scores:
            self.rt.bus.emit("decision.submitted", decision_id=dec.id,
                             title=dec.proposal.title, amount_usd=dec.proposal.amount_usd,
                             category=dec.proposal.category)
        dec.status = DecisionStatus.EVALUATING
        dec.scores = score_all(dec.proposal)          # numbers first, in code
        evidence_payload = [i.model_dump(mode="json") for i in dec.proposal.evidence]
        for score in dec.scores:                       # then Gemini's reasoning around them
            panel = self.rt.cognition.generate_json("criterion_evaluation", {
                "criterion": score.criterion,
                "proposal": {"title": dec.proposal.title, "amount_usd": dec.proposal.amount_usd,
                             "vendor": dec.proposal.vendor, "description": dec.proposal.description},
                "evidence": [e for e in evidence_payload if e["kind"] == score.criterion],
                "revision_guidance": dec.revision_guidance,
            })
            score.rationale = str(panel.get("rationale", ""))
            cited = list(panel.get("cited_evidence_ids", []))
            if cited:
                score.cited_evidence_ids = cited
        self.rt.bus.emit("decision.evaluated", decision_id=dec.id,
                         scores={s.criterion: s.score for s in dec.scores})
        dec.status = DecisionStatus.GOVERNANCE_REVIEW
        self._save(dec)
        return dec.status.value

    # -- stage: govern ------------------------------------------------------
    def govern(self, dec_id: str) -> str:
        dec = self._get(dec_id)
        engine = self.rt.policy_engine
        dec.policy_findings = engine.evaluate(dec.proposal)
        for finding in dec.policy_findings:
            self.rt.bus.emit("policy.finding", decision_id=dec.id, policy_id=finding.policy_id,
                             state=finding.state.value, clause=finding.clause,
                             observed=finding.observed, threshold=finding.threshold)
        dec.verdict = verdict_from(dec.policy_findings, engine.version)
        self.rt.bus.emit("governance.verdict", decision_id=dec.id,
                         outcome=dec.verdict.outcome, required_tier=dec.verdict.required_tier,
                         basis=dec.verdict.basis, policy_version=engine.version)
        self._save(dec)
        return dec.status.value

    # -- stage: recommend ---------------------------------------------------
    def recommend(self, dec_id: str) -> str:
        dec = self._get(dec_id)
        strength = recommendation_strength(dec.scores, dec.verdict)
        synthesis = self.rt.cognition.generate_json("recommendation", {
            "proposal": dec.proposal.model_dump(mode="json", exclude={"evidence"}),
            "scores": [s.model_dump(mode="json") for s in dec.scores],
            "findings": [f.model_dump(mode="json") for f in dec.policy_findings],
            "verdict": dec.verdict.model_dump(mode="json") if dec.verdict else None,
            "revision_guidance": dec.revision_guidance,
        })
        dec.recommendation = Recommendation(
            action=str(synthesis.get("action", "")).strip(),
            rationale=str(synthesis.get("rationale", "")).strip(),
            strength=strength,
            caveats=[str(c) for c in synthesis.get("caveats", [])][:6],
        )
        dec.status = DecisionStatus.RECOMMENDED
        self._save(dec)
        self.rt.bus.emit("recommendation.created", decision_id=dec.id,
                         action=dec.recommendation.action, strength=strength,
                         verdict=dec.verdict.outcome if dec.verdict else None)
        return dec.status.value

    def mark_awaiting(self, dec_id: str) -> str:
        dec = self._get(dec_id)
        dec.status = DecisionStatus.AWAITING_AUTHORIZATION
        self._save(dec)
        return dec.status.value

    # -- stage: decide (human signal) ---------------------------------------
    def decide(self, dec_id: str, decision: str, note: str = "") -> str:
        dec = self._get(dec_id)
        decision = decision.lower().strip()
        dec.authorizations.append(AuthorizationRecord(decision=decision, note=note))
        self.rt.bus.emit("authorization.decided", decision_id=dec.id, decision=decision,
                         note=note, round=dec.round,
                         required_tier=dec.verdict.required_tier if dec.verdict else None)
        if decision == "approved":
            if dec.verdict is not None and dec.verdict.outcome == "BLOCKED":
                # policy findings cannot be overridden by approval alone (locked §2.8)
                dec.authorizations.append(AuthorizationRecord(
                    decision="revise",
                    note="approval refused by governance: a VIOLATION stands — revise instead"))
                return self._revise(dec, "resolve the standing policy violation")
            dec.status = DecisionStatus.AUTHORIZED
            draft = self.rt.cognition.generate_json("objective_draft", {
                "proposal": dec.proposal.model_dump(mode="json", exclude={"evidence"}),
                "recommendation": dec.recommendation.model_dump(mode="json") if dec.recommendation else None,
                "note": note,
            })
            dec.objective = SoftwareActionObjective(
                objective=str(draft.get("objective", "")).strip(),
                business_purpose=str(draft.get("business_purpose", "")).strip(),
                requirements=[str(r) for r in draft.get("requirements", [])][:8],
                acceptance_criteria=[str(a) for a in draft.get("acceptance_criteria", [])][:6],
                risk_class=str(draft.get("risk_class", "standard")),
            )
            self.rt.bus.emit("action.objective_issued", decision_id=dec.id,
                             objective=dec.objective.objective,
                             requirements=dec.objective.requirements)
            self._save(dec)
            self.rt.episodic.record(dec)
            self.rt.ephemeral.release_latch(DECISION_LATCH)  # Bob delivers on human timescale
            return dec.status.value
        if decision == "revise" and dec.round < MAX_ROUNDS:
            return self._revise(dec, note)
        if decision == "revise":
            dec.authorizations.append(AuthorizationRecord(
                decision="rejected", note=f"revision budget exhausted ({MAX_ROUNDS} rounds)"))
        dec.status = DecisionStatus.REJECTED
        self._finalize(dec, closed_event=True)
        return dec.status.value

    def _revise(self, dec: Decision, guidance: str) -> str:
        if guidance:
            dec.revision_guidance.append(guidance)
        dec.round += 1
        dec.status = DecisionStatus.EVALUATING
        self._save(dec)
        return "REVISE"

    # -- action delivery (Bob evidence, event-driven tail) -------------------
    def attach_action(self, dec_id: str, summary: str, evidence_refs: list[str]) -> str:
        dec = self._get(dec_id)
        if dec.status != DecisionStatus.AUTHORIZED or dec.objective is None:
            raise ValueError(f"no authorized objective awaiting delivery (status {dec.status.value})")
        dec.action_record = ActionRecord(summary=summary, evidence_refs=evidence_refs)
        dec.status = DecisionStatus.ACTIONED
        self.rt.bus.emit("action.delivered", decision_id=dec.id, summary=summary,
                         evidence_refs=evidence_refs, delivered_by="ibm-bob")
        self._save(dec)
        return self.close(dec_id)

    def close(self, dec_id: str) -> str:
        dec = self._get(dec_id)
        urns = self.rt.datahub.promote(dec)
        dec.promotion = Promotion(datahub_urns=urns)
        if urns:
            self.rt.bus.emit("knowledge.promoted", decision_id=dec.id, datahub_urns=urns)
        dec.status = DecisionStatus.CLOSED
        self._finalize(dec, closed_event=True)
        return dec.status.value

    # -- failure ------------------------------------------------------------
    def incomplete(self, dec_id: str, reason: str) -> str:
        dec = self._get(dec_id)
        dec.status = DecisionStatus.INCOMPLETE
        dec.incomplete_reason = reason[:500]
        self.rt.bus.emit("decision.incomplete", decision_id=dec.id, reason=reason[:500])
        self._finalize(dec, closed_event=False)
        return dec.status.value

    def _finalize(self, dec: Decision, closed_event: bool) -> None:
        self._save(dec)
        self.rt.episodic.record(dec)
        if closed_event:
            self.rt.bus.emit("decision.closed", decision_id=dec.id, status=dec.status.value,
                             rounds=dec.round, findings=dec.finding_counts(),
                             strength=dec.recommendation.strength if dec.recommendation else None)
        self.rt.ephemeral.release_latch(DECISION_LATCH)
