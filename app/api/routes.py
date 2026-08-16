"""HTTP interface for the governance chamber (frontend/) and the eventual
Genesis OS Enterprise Decision Contract adapter. The standalone owns this API;
the federation consumes it — never the reverse.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.models.enterprise import Decision, DecisionProposal, DecisionStatus, PolicyState
from app.workflows.run_decision import (
    dispatch_authorization,
    dispatch_decision,
    run_authorization,
    run_decision,
)
from app.workflows.runtime import get_runtime
from app import runtime_proof

router = APIRouter(prefix="/api")

VALID_DECISIONS = {"approved", "rejected", "revise"}


class ProposalRequest(BaseModel):
    proposal: DecisionProposal


class AuthorizationRequest(BaseModel):
    decision: str
    note: str = Field(default="", max_length=500)
    amendments: dict = Field(default_factory=dict)  # whitelisted proposal fields, applied on revise


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
        "runtime_proof": _runtime_proof(runtime.settings, runtime.policy_engine.version),
    }


def _runtime_proof(settings, policy_version: str) -> dict:
    """Substrate states for the console's runtime-proof footer.

    These are configuration-derived starting points; app.runtime_proof
    overrides any of them the moment the substrate is actually exercised, so a
    chip only reads LIVE on evidence.
    """
    return runtime_proof.snapshot({
        "gemini": (("LIVE", f"credential present — narration via {settings.gemini_model}")
                   if settings.gemini_live
                   else ("MOCK", "no GOOGLE_API_KEY — deterministic mock narration")),
        "confluent": (("LIVE", "Confluent credentials present — decisions land on the ledger topic")
                      if settings.confluent_live
                      else ("MOCK", "no Confluent credentials — local append-only ledger file")),
        "policy": ("LIVE", f"policy pack {policy_version} evaluated in code (built with IBM Bob)"),
        # An unset address means Temporal is not part of this deployment, not
        # that it broke — dialling it would report DEGRADED and read as a fault.
        "temporal": (("IDLE", f"configured at {settings.temporal_address} — "
                              "no workflow dispatched yet this session")
                     if settings.temporal_address
                     else ("MOCK", "no TEMPORAL_ADDRESS — in-process execution for this deployment")),
        "datahub": ("IDLE", f"configured at {settings.datahub_gms_url} — nothing promoted yet"),
    })


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


@router.get("/decisions/{dec_id}/vendor-alternates")
def vendor_alternates(dec_id: str, limit: int = 3) -> list[dict]:
    """Vendors this proposal could be amended to without breaching concentration.

    Each candidate is judged by running the *real* policy engine over an amended
    copy of the proposal, so a suggestion here can never contradict a verdict
    the chamber would later issue. Evaluation is pure and in-process — no
    network, no cognition — so this stays cheap enough to call on render.
    """
    from app.governance.spend_history import _BASELINE, get_vendor_share, total_baseline_usd

    runtime = get_runtime()
    dec = runtime.working.get(dec_id)
    if dec is None:
        raise HTTPException(404, "decision not found")

    current = (dec.proposal.vendor or "").strip()
    amount = dec.proposal.amount_usd
    out: list[dict] = []
    for vendor in _BASELINE:
        if vendor == current:
            continue
        amended = dec.proposal.model_copy(update={"vendor": vendor})
        concentration = [f for f in runtime.policy_engine.evaluate(amended)
                         if "vendor" in f.policy_id]
        # Only offer a vendor whose concentration finding actually comes back
        # COMPLIANT; anything else (violation, review, missing rule) is withheld.
        if not concentration or any(f.state != PolicyState.COMPLIANT for f in concentration):
            continue
        share = get_vendor_share(vendor, additional_spend_usd=amount)
        if share is None:
            continue
        out.append({
            "vendor": vendor,
            "share": round(share, 6),
            "cap": concentration[0].threshold.get("max_share"),
            "existing_spend_usd": _BASELINE.get(vendor, 0.0),
            "total_baseline_usd": total_baseline_usd() + amount,
            "policy_version": concentration[0].policy_version,
        })

    # Most headroom under the cap first. The baseline carries no machine-readable
    # vendor category, so the chamber ranks by the only thing the rule actually
    # measures — concentration — rather than guessing at procurement fit.
    out.sort(key=lambda row: row["share"])
    return out[:max(0, limit)]


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
    execution = dispatch_authorization(dec.id, body.decision, body.note, body.amendments)
    if execution == "local":
        background.add_task(run_authorization, dec.id, body.decision, body.note, body.amendments)
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
