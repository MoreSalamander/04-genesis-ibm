"""HTTP interface for the governance chamber (frontend/) and the eventual
Genesis OS Enterprise Decision Contract adapter. The standalone owns this API;
the federation consumes it — never the reverse.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.models.enterprise import Decision, DecisionProposal, DecisionStatus
from app.workflows.run_decision import (
    dispatch_authorization,
    dispatch_decision,
    run_authorization,
    run_decision,
)
from app.workflows.runtime import get_runtime

router = APIRouter(prefix="/api")

VALID_DECISIONS = {"approved", "rejected", "revise"}


class ProposalRequest(BaseModel):
    proposal: DecisionProposal


class AuthorizationRequest(BaseModel):
    decision: str
    note: str = Field(default="", max_length=500)


class ActionDeliveryRequest(BaseModel):
    summary: str = Field(min_length=5, max_length=500)
    evidence_refs: list[str] = Field(default_factory=list)


def _summary(dec: Decision) -> dict:
    return {
        "id": dec.id,
        "title": dec.proposal.title,
        "category": dec.proposal.category,
        "amount_usd": dec.proposal.amount_usd,
        "vendor": dec.proposal.vendor,
        "status": dec.status.value,
        "round": dec.round,
        "verdict": dec.verdict.outcome if dec.verdict else None,
        "findings": dec.finding_counts(),
        "strength": dec.recommendation.strength if dec.recommendation else None,
        "escalated": dec.escalated,
        "created_at": dec.created_at,
        "updated_at": dec.updated_at,
    }


@router.get("/status")
def status() -> dict:
    runtime = get_runtime()
    return {
        "system": "Genesis OS — Enterprise Decision Intelligence",
        "banner": runtime.settings.banner(),
        "gemini_live": runtime.settings.gemini_live,
        "confluent_live": runtime.settings.confluent_live,
        "policy_engine": runtime.policy_engine.version,
        "decisions": len(runtime.working.all()),
    }


@router.post("/decisions", status_code=202)
def submit_decision(body: ProposalRequest, background: BackgroundTasks) -> dict:
    from app.memory.ephemeral import DECISION_LATCH, LATCH_TTL_S

    runtime = get_runtime()
    # Latch FIRST — a blocked attempt must never persist a phantom decision.
    dec = Decision(proposal=body.proposal)
    holder = runtime.ephemeral.acquire_latch(DECISION_LATCH, dec.id, LATCH_TTL_S)
    if holder is not None:
        raise HTTPException(
            409, f"a decision is already in governance ({holder}) — one at a time"
        )
    runtime.working.put(dec)
    execution = dispatch_decision(dec.id)
    if execution == "local":
        background.add_task(run_decision, dec.id)
    return {"id": dec.id, "status": dec.status.value, "execution": execution}


@router.get("/decisions")
def list_decisions() -> list[dict]:
    return [_summary(d) for d in get_runtime().working.all()]


@router.get("/decisions/{dec_id}")
def get_decision(dec_id: str) -> dict:
    dec = get_runtime().working.get(dec_id)
    if dec is None:
        raise HTTPException(404, "decision not found")
    return dec.model_dump(mode="json")


@router.post("/decisions/{dec_id}/authorization", status_code=202)
def authorize(dec_id: str, body: AuthorizationRequest, background: BackgroundTasks) -> dict:
    runtime = get_runtime()
    dec = runtime.working.get(dec_id)
    if dec is None:
        raise HTTPException(404, "decision not found")
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(400, f"decision must be one of {sorted(VALID_DECISIONS)}")
    if dec.status not in (DecisionStatus.RECOMMENDED, DecisionStatus.AWAITING_AUTHORIZATION):
        raise HTTPException(400, f"no recommendation awaiting authorization (status {dec.status.value})")
    execution = dispatch_authorization(dec.id, body.decision, body.note)
    if execution == "local":
        background.add_task(run_authorization, dec.id, body.decision, body.note)
    return {"id": dec.id, "decision": body.decision, "status": "processing", "execution": execution}


@router.post("/decisions/{dec_id}/action", status_code=200)
def deliver_action(dec_id: str, body: ActionDeliveryRequest) -> dict:
    """Attach IBM Bob's delivery evidence to the authorized objective (locked §2.5b)."""
    runtime = get_runtime()
    try:
        final = runtime.executive.attach_action(dec_id, body.summary, body.evidence_refs)
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    return {"id": dec_id, "status": final}


@router.get("/events")
def events(limit: int = 150) -> list[dict]:
    return get_runtime().bus.tail(limit)


@router.get("/memory/episodic")
def episodic(limit: int = 50) -> list[dict]:
    return get_runtime().episodic.list(limit)
