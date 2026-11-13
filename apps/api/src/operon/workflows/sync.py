"""Temporal workflow for integration syncs (ADR 0003).

The workflow is deliberately thin: all logic lives in `modules.integrations.sync.run_sync`, which
is tested directly. Temporal adds durability, retries with backoff, schedules and history.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from uuid import UUID

    from operon.modules.integrations.sync import SyncRuntime, run_sync
    from operon.workflows.maintenance import DETECT_ACTIVITY, DetectInput

NON_RETRYABLE = ["AuthError", "ConfigError", "ProtocolError"]


@dataclass
class SyncInput:
    organisation_id: str
    connection_id: str
    trigger: str


class SyncActivities:
    def __init__(self, runtime: SyncRuntime) -> None:
        self.rt = runtime

    @activity.defn(name="sync_connection")
    async def sync_connection(self, inp: SyncInput) -> dict[str, object]:
        info = activity.info()
        outcome = await run_sync(
            self.rt,
            organisation_id=UUID(inp.organisation_id),
            connection_id=UUID(inp.connection_id),
            trigger=inp.trigger,
            workflow_id=info.workflow_id,
        )
        if outcome.status == "failed":
            raise ApplicationError(
                outcome.error or "Sync failed",
                type="TransientError" if outcome.retryable else "ConfigError",
                non_retryable=not outcome.retryable,
            )
        return {"status": outcome.status, "stats": outcome.stats}


@workflow.defn(name="SyncConnection")
class SyncConnectionWorkflow:
    @workflow.run
    async def run(self, inp: SyncInput) -> dict[str, object]:
        result: dict[str, object] = await workflow.execute_activity(
            "sync_connection",
            inp,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=30),
                backoff_coefficient=2,
                maximum_interval=timedelta(minutes=10),
                maximum_attempts=4,
                non_retryable_error_types=NON_RETRYABLE,
            ),
        )
        if result.get("status") == "succeeded":
            # New data: re-run detection. Failure here doesn't fail the sync.
            try:
                await workflow.execute_activity(
                    DETECT_ACTIVITY,
                    DetectInput(inp.organisation_id, "sync"),
                    start_to_close_timeout=timedelta(minutes=15),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            except Exception:
                workflow.logger.warning("detection after sync failed")
        return result


def workflow_id(connection_id: str) -> str:
    return f"sync-{connection_id}"


def schedule_id(connection_id: str) -> str:
    return f"sync-schedule-{connection_id}"
