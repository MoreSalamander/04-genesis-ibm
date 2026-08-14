"""Temporal workflow — the locked decision loop as durable execution.

The Studio Head's authorization is a workflow SIGNAL (approve / reject /
request-revision); *revise* loops the workflow back to evaluation with the
guidance, bounded by the round budget. The ACTIONED tail (IBM Bob delivery)
is event-driven after AUTHORIZED — Bob works on human timescale.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

_RETRY = RetryPolicy(initial_interval=timedelta(seconds=3), maximum_attempts=3)
_OPTS = {"start_to_close_timeout": timedelta(minutes=4), "retry_policy": _RETRY}
AUTHORIZATION_WINDOW = timedelta(hours=24)
MAX_ROUNDS = 3


@workflow.defn(name="EnterpriseDecisionWorkflow")
class EnterpriseDecisionWorkflow:
    def __init__(self) -> None:
        self._decision: str | None = None
        self._note: str = ""

    @workflow.signal(name="studio_head_decision")
    def studio_head_decision(self, decision: str, note: str = "") -> None:
        if self._decision is None and decision in ("approved", "rejected", "revise"):
            self._decision = decision
            self._note = note

    @workflow.query(name="decision")
    def decision(self) -> str | None:
        return self._decision

    @workflow.run
    async def run(self, dec_id: str) -> str:
        for _round in range(MAX_ROUNDS):
            try:
                await workflow.execute_activity("ent.evaluate", dec_id, **_OPTS)
                await workflow.execute_activity("ent.govern", dec_id, **_OPTS)
                await workflow.execute_activity("ent.recommend", dec_id, **_OPTS)
                await workflow.execute_activity("ent.mark_awaiting", dec_id, **_OPTS)
            except ActivityError as err:
                return await workflow.execute_activity(
                    "ent.incomplete",
                    args=[dec_id, f"Durable stage failed after retries: {err.__cause__ or err}"],
                    **_OPTS,
                )

            # Human boundary: durable pause until the Studio Head decides.
            self._decision, self._note = None, ""
            try:
                await workflow.wait_condition(lambda: self._decision is not None,
                                              timeout=AUTHORIZATION_WINDOW)
            except TimeoutError:
                return await workflow.execute_activity("ent.escalate_timeout", dec_id, **_OPTS)

            outcome = await workflow.execute_activity(
                "ent.decide", args=[dec_id, self._decision, self._note], **_OPTS)
            if outcome != "REVISE":
                return outcome
        return await workflow.execute_activity(
            "ent.incomplete", args=[dec_id, "revision round budget exhausted"], **_OPTS)
