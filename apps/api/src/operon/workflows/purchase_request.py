"""Temporal workflow for purchase requests (ADR 0012).

Thin by design: every decision lives in `modules.workflows.engine.advance`, which is tested
directly. The workflow provides durability, timers (approval deadlines, retry backoff) and a
signal that wakes it when someone decides, cancels or retries.
"""

import contextlib
from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from datetime import UTC, datetime
    from uuid import UUID

    from operon.modules.workflows.engine import WorkflowRuntime, advance

ADVANCE_ACTIVITY = "advance_execution"


@dataclass
class ExecutionInput:
    organisation_id: str
    execution_id: str


@dataclass
class AdvanceResult:
    done: bool
    wait_seconds: float | None


class WorkflowActivities:
    def __init__(self, runtime: WorkflowRuntime) -> None:
        self.rt = runtime

    @activity.defn(name=ADVANCE_ACTIVITY)
    async def advance_execution(self, inp: ExecutionInput) -> AdvanceResult:
        step = await advance(self.rt, UUID(inp.organisation_id), UUID(inp.execution_id))
        wait = None
        if step.wake_at is not None:
            wait = max(1.0, (step.wake_at - datetime.now(UTC)).total_seconds())
        return AdvanceResult(step.done, wait)


@workflow.defn(name="PurchaseRequest")
class PurchaseRequestWorkflow:
    def __init__(self) -> None:
        self._woken = False

    @workflow.signal
    def wake(self) -> None:
        self._woken = True

    @workflow.run
    async def run(self, inp: ExecutionInput) -> str:
        while True:
            result: AdvanceResult = await workflow.execute_activity(
                ADVANCE_ACTIVITY,
                inp,
                result_type=AdvanceResult,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_interval=timedelta(minutes=5)),
            )
            if result.done:
                return "done"
            self._woken = False
            timeout = timedelta(seconds=result.wait_seconds) if result.wait_seconds else None
            # On timeout the deadline has passed; the next advance handles it.
            with contextlib.suppress(TimeoutError):
                await workflow.wait_condition(lambda: self._woken, timeout=timeout)


def workflow_id(execution_id: str) -> str:
    return f"purchase-request-{execution_id}"
