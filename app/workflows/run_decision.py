"""Decision dispatch: Temporal durable execution by default, surfaced in-process
fallback so a clean clone (no Docker, no keys) still runs the entire loop."""
from __future__ import annotations

from app.config import settings
from app.workflows.runtime import get_runtime


def run_decision(dec_id: str) -> None:
    executive = get_runtime().executive
    try:
        executive.evaluate(dec_id)
        executive.govern(dec_id)
        executive.recommend(dec_id)
        executive.mark_awaiting(dec_id)
    except Exception as err:
        executive.incomplete(dec_id, f"in-process stage failed: {err}")


def run_authorization(dec_id: str, decision: str, note: str) -> None:
    executive = get_runtime().executive
    try:
        outcome = executive.decide(dec_id, decision, note)
        if outcome == "REVISE":
            run_decision(dec_id)
    except Exception as err:
        executive.incomplete(dec_id, f"authorization handling failed: {err}")


def _workflow_id(dec_id: str) -> str:
    return f"ent-wf-{dec_id}"


def dispatch_decision(dec_id: str) -> str:
    """Returns 'temporal' when the durable workflow started, else 'local'."""
    if settings.force_mock:
        return "local"
    try:
        import asyncio

        from temporalio.client import Client

        async def go():
            client = await Client.connect(settings.temporal_address)
            await client.start_workflow(
                "EnterpriseDecisionWorkflow", dec_id,
                id=_workflow_id(dec_id), task_queue=settings.temporal_task_queue,
            )

        asyncio.run(go())
        return "temporal"
    except Exception as err:
        print(f"[workflow] Temporal dispatch failed ({err}) — DEGRADED: in-process execution")
        return "local"


def dispatch_authorization(dec_id: str, decision: str, note: str) -> str:
    """Signals the durable workflow's human boundary; 'local' on fallback."""
    if settings.force_mock:
        return "local"
    try:
        import asyncio

        from temporalio.client import Client

        async def go():
            client = await Client.connect(settings.temporal_address)
            handle = client.get_workflow_handle(_workflow_id(dec_id))
            await handle.signal("studio_head_decision", args=[decision, note])

        asyncio.run(go())
        return "temporal"
    except Exception as err:
        print(f"[workflow] Temporal signal failed ({err}) — DEGRADED: in-process execution")
        return "local"
