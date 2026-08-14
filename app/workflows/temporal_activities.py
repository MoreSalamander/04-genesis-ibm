"""Temporal activities — each decision stage as a durable, retryable unit."""
from __future__ import annotations

from temporalio import activity


def _executive():
    from app.workflows.runtime import get_runtime

    return get_runtime().executive


@activity.defn(name="ent.evaluate")
def evaluate_activity(dec_id: str) -> str:
    return _executive().evaluate(dec_id)


@activity.defn(name="ent.govern")
def govern_activity(dec_id: str) -> str:
    return _executive().govern(dec_id)


@activity.defn(name="ent.recommend")
def recommend_activity(dec_id: str) -> str:
    return _executive().recommend(dec_id)


@activity.defn(name="ent.mark_awaiting")
def mark_awaiting_activity(dec_id: str) -> str:
    return _executive().mark_awaiting(dec_id)


@activity.defn(name="ent.decide")
def decide_activity(dec_id: str, decision: str, note: str) -> str:
    return _executive().decide(dec_id, decision, note)


@activity.defn(name="ent.incomplete")
def incomplete_activity(dec_id: str, reason: str) -> str:
    return _executive().incomplete(dec_id, reason)


@activity.defn(name="ent.escalate_timeout")
def escalate_timeout_activity(dec_id: str) -> str:
    from app.memory.ephemeral import DECISION_LATCH
    from app.workflows.runtime import get_runtime

    rt = get_runtime()
    dec = rt.working.get(dec_id)
    if dec is None:
        return "UNKNOWN"
    dec.escalated = True
    dec.touch()
    rt.working.put(dec)
    rt.bus.emit("authorization.decided", decision_id=dec.id, decision="escalated_timeout",
                note="authorization window elapsed without a Studio Head decision")
    rt.ephemeral.release_latch(DECISION_LATCH)
    return dec.status.value


ALL_ACTIVITIES = [evaluate_activity, govern_activity, recommend_activity,
                  mark_awaiting_activity, decide_activity, incomplete_activity,
                  escalate_timeout_activity]
