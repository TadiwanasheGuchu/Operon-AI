"""Temporal workflows for intelligence: detection after syncs, and the maintenance schedule.

Like the sync workflow, these are thin wrappers: the logic lives in `intelligence.engine` and
`incidents.service`, which are tested directly.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from uuid import UUID

    from operon.modules.incidents.service import escalate_overdue
    from operon.modules.intelligence.engine import IntelligenceRuntime, run_detection

DETECT_ACTIVITY = "run_detection"
ESCALATE_ACTIVITY = "escalate_incidents"
MAINTENANCE_SCHEDULE_ID = "operon-maintenance"
MAINTENANCE_WORKFLOW_ID = "operon-maintenance-run"


@dataclass
class DetectInput:
    organisation_id: str
    trigger: str


class IntelligenceActivities:
    def __init__(self, runtime: IntelligenceRuntime) -> None:
        self.rt = runtime

    @activity.defn(name=DETECT_ACTIVITY)
    async def detect(self, inp: DetectInput) -> dict[str, object]:
        run = await run_detection(self.rt, UUID(inp.organisation_id), inp.trigger)
        return {"status": run.status, "stats": run.stats}

    @activity.defn(name=ESCALATE_ACTIVITY)
    async def escalate(self) -> int:
        return await escalate_overdue(self.rt.db)


@workflow.defn(name="Maintenance")
class MaintenanceWorkflow:
    """Runs every few minutes from a schedule: incident escalation."""

    @workflow.run
    async def run(self) -> int:
        escalated: int = await workflow.execute_activity(
            ESCALATE_ACTIVITY,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        return escalated
