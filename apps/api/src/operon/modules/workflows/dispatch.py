"""How executions get driven forward.

- TemporalWorkflowDispatcher (production): one durable `PurchaseRequest` workflow per execution
  holds the timers (approval deadlines, retry backoff) and is woken by a signal on decisions.
- InlineWorkflowDispatcher (development/test only): calls `advance` in-process; deadlines and
  retries are picked up by the maintenance sweep.
Both run the same `engine.advance`.
"""

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from operon.modules.workflows.engine import WorkflowRuntime, advance

if TYPE_CHECKING:
    from temporalio.client import Client


class WorkflowDispatcher(Protocol):
    async def start(self, organisation_id: UUID, execution_id: UUID) -> None: ...
    async def wake(self, organisation_id: UUID, execution_id: UUID) -> None: ...


class InlineWorkflowDispatcher:
    def __init__(self, runtime: WorkflowRuntime) -> None:
        self.rt = runtime

    async def start(self, organisation_id: UUID, execution_id: UUID) -> None:
        await advance(self.rt, organisation_id, execution_id)

    async def wake(self, organisation_id: UUID, execution_id: UUID) -> None:
        await advance(self.rt, organisation_id, execution_id)


class TemporalWorkflowDispatcher:
    def __init__(self, runtime: WorkflowRuntime) -> None:
        self.rt = runtime
        self._client: Client | None = None

    async def _c(self) -> "Client":
        from temporalio.client import Client

        if self._client is None:
            settings = self.rt.sync.settings
            self._client = await Client.connect(
                settings.temporal_address, namespace=settings.temporal_namespace
            )
        return self._client

    async def start(self, organisation_id: UUID, execution_id: UUID) -> None:
        from temporalio.common import WorkflowIDConflictPolicy

        from operon.workflows.purchase_request import (
            ExecutionInput,
            PurchaseRequestWorkflow,
            workflow_id,
        )

        client = await self._c()
        await client.start_workflow(
            PurchaseRequestWorkflow.run,
            ExecutionInput(str(organisation_id), str(execution_id)),
            id=workflow_id(str(execution_id)),
            task_queue=self.rt.sync.settings.temporal_task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )

    async def wake(self, organisation_id: UUID, execution_id: UUID) -> None:
        from temporalio.service import RPCError

        from operon.workflows.purchase_request import PurchaseRequestWorkflow, workflow_id

        client = await self._c()
        handle = client.get_workflow_handle(workflow_id(str(execution_id)))
        try:
            await handle.signal(PurchaseRequestWorkflow.wake)
        except RPCError:
            # The workflow already finished (e.g. a retry after failure): start a new run.
            await self.start(organisation_id, execution_id)


def create_workflow_dispatcher(runtime: WorkflowRuntime) -> WorkflowDispatcher:
    if runtime.sync.settings.workflow_backend == "temporal":
        return TemporalWorkflowDispatcher(runtime)
    return InlineWorkflowDispatcher(runtime)
