"""Worker for syncs, detection and maintenance.

Run with `python -m operon.workers.integrations` (one or more replicas).
"""

import asyncio
import contextlib

from temporalio.client import Client
from temporalio.worker import Worker

from operon.core.config import get_settings
from operon.core.crypto import SecretBox
from operon.core.db import Database
from operon.core.logging import configure_logging, get_logger
from operon.modules.ai.service import ProviderRegistry
from operon.modules.integrations.sync import SyncRuntime, default_http_factory
from operon.modules.intelligence.engine import IntelligenceRuntime
from operon.modules.workflows.engine import WorkflowRuntime
from operon.workflows.maintenance import (
    MAINTENANCE_SCHEDULE_ID,
    MAINTENANCE_WORKFLOW_ID,
    IntelligenceActivities,
    MaintenanceWorkflow,
)
from operon.workflows.purchase_request import PurchaseRequestWorkflow, WorkflowActivities
from operon.workflows.sync import SyncActivities, SyncConnectionWorkflow


async def ensure_maintenance_schedule(client: Client, task_queue: str) -> None:
    from datetime import timedelta

    from temporalio.client import (
        Schedule,
        ScheduleActionStartWorkflow,
        ScheduleAlreadyRunningError,
        ScheduleIntervalSpec,
        ScheduleOverlapPolicy,
        SchedulePolicy,
        ScheduleSpec,
    )

    with contextlib.suppress(ScheduleAlreadyRunningError):
        await client.create_schedule(
            MAINTENANCE_SCHEDULE_ID,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    MaintenanceWorkflow.run, id=MAINTENANCE_WORKFLOW_ID, task_queue=task_queue
                ),
                spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=5))]),
                policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
            ),
        )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger("operon.worker")
    db = Database(settings)
    runtime = SyncRuntime(
        db=db,
        settings=settings,
        box=SecretBox(settings.secret_keys.get_secret_value()),
        http_factory=default_http_factory(settings),
    )
    intelligence = IntelligenceActivities(
        IntelligenceRuntime(db=db, providers=ProviderRegistry.from_settings(settings))
    )
    purchase = WorkflowActivities(WorkflowRuntime(sync=runtime))
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    await ensure_maintenance_schedule(client, settings.temporal_task_queue)
    activities = SyncActivities(runtime)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[SyncConnectionWorkflow, MaintenanceWorkflow, PurchaseRequestWorkflow],
        activities=[
            activities.sync_connection,
            intelligence.detect,
            intelligence.escalate,
            intelligence.run_agents,
            purchase.advance_execution,
        ],
    )
    log.info("worker_started", task_queue=settings.temporal_task_queue)
    try:
        await worker.run()
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
