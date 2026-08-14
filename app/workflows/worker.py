"""Temporal worker for Enterprise Decision Intelligence.

Run:  .venv/bin/python -m app.workflows.worker
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from app.config import settings
from app.workflows.temporal_activities import ALL_ACTIVITIES
from app.workflows.temporal_workflows import EnterpriseDecisionWorkflow


async def main() -> None:
    from app.observability.tracing import setup_tracing

    setup_tracing(settings, "genesis-enterprise-worker")
    client = await Client.connect(settings.temporal_address)
    print(f"[worker] connected to Temporal at {settings.temporal_address} · "
          f"queue={settings.temporal_task_queue}")
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[EnterpriseDecisionWorkflow],
        activities=ALL_ACTIVITIES,
        activity_executor=ThreadPoolExecutor(max_workers=8),
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
