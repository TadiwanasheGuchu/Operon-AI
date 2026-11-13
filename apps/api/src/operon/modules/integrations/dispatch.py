"""How sync requests reach a worker.

- TemporalDispatcher (production): durable workflows; one per connection at a time; schedules.
- InlineDispatcher (development/test only, refused in production by settings validation): runs
  the same `run_sync` in-process, so the full path is exercised without a Temporal server.
"""

from datetime import timedelta
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from operon.core.logging import get_logger
from operon.modules.integrations.sync import SyncRuntime, run_sync

if TYPE_CHECKING:
    from temporalio.client import Client

log = get_logger(__name__)


class SyncDispatcher(Protocol):
    async def request_sync(
        self, organisation_id: UUID, connection_id: UUID, trigger: str
    ) -> None: ...
    async def ensure_schedule(
        self, organisation_id: UUID, connection_id: UUID, minutes: int, paused: bool
    ) -> None: ...
    async def remove_schedule(self, connection_id: UUID) -> None: ...


class InlineDispatcher:
    def __init__(self, runtime: SyncRuntime) -> None:
        self.rt = runtime

    async def request_sync(self, organisation_id: UUID, connection_id: UUID, trigger: str) -> None:
        outcome = await run_sync(
            self.rt, organisation_id=organisation_id, connection_id=connection_id, trigger=trigger
        )
        if outcome.status == "succeeded":
            await self.rt.data_changed(organisation_id, "sync")

    async def ensure_schedule(
        self, organisation_id: UUID, connection_id: UUID, minutes: int, paused: bool
    ) -> None:
        log.info("inline_dispatcher_no_schedules", connection_id=str(connection_id))

    async def remove_schedule(self, connection_id: UUID) -> None:
        return None


class TemporalDispatcher:
    def __init__(self, runtime: SyncRuntime) -> None:
        self.rt = runtime
        self._client: Client | None = None

    async def _c(self) -> "Client":
        from temporalio.client import Client

        if self._client is None:
            self._client = await Client.connect(
                self.rt.settings.temporal_address, namespace=self.rt.settings.temporal_namespace
            )
        return self._client

    async def request_sync(self, organisation_id: UUID, connection_id: UUID, trigger: str) -> None:
        from temporalio.common import WorkflowIDConflictPolicy

        from operon.workflows.sync import SyncConnectionWorkflow, SyncInput, workflow_id

        client = await self._c()
        await client.start_workflow(
            SyncConnectionWorkflow.run,
            SyncInput(str(organisation_id), str(connection_id), trigger),
            id=workflow_id(str(connection_id)),
            task_queue=self.rt.settings.temporal_task_queue,
            # A sync already running for this connection absorbs the request.
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        )

    async def ensure_schedule(
        self, organisation_id: UUID, connection_id: UUID, minutes: int, paused: bool
    ) -> None:
        from temporalio.client import (
            Schedule,
            ScheduleActionStartWorkflow,
            ScheduleAlreadyRunningError,
            ScheduleIntervalSpec,
            ScheduleOverlapPolicy,
            SchedulePolicy,
            ScheduleSpec,
            ScheduleState,
        )

        from operon.workflows.sync import (
            SyncConnectionWorkflow,
            SyncInput,
            schedule_id,
            workflow_id,
        )

        client = await self._c()
        schedule = Schedule(
            action=ScheduleActionStartWorkflow(
                SyncConnectionWorkflow.run,
                SyncInput(str(organisation_id), str(connection_id), "schedule"),
                id=workflow_id(str(connection_id)),
                task_queue=self.rt.settings.temporal_task_queue,
            ),
            spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=timedelta(minutes=minutes))]),
            policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
            state=ScheduleState(paused=paused),
        )
        sid = schedule_id(str(connection_id))
        try:
            await client.create_schedule(sid, schedule)
        except ScheduleAlreadyRunningError:
            from temporalio.client import ScheduleUpdate

            await client.get_schedule_handle(sid).update(
                lambda _: ScheduleUpdate(schedule=schedule)
            )

    async def remove_schedule(self, connection_id: UUID) -> None:
        from operon.workflows.sync import schedule_id

        client = await self._c()
        try:
            await client.get_schedule_handle(schedule_id(str(connection_id))).delete()
        except Exception:
            log.info("schedule_absent", connection_id=str(connection_id))


def create_dispatcher(runtime: SyncRuntime) -> SyncDispatcher:
    if runtime.settings.workflow_backend == "temporal":
        return TemporalDispatcher(runtime)
    return InlineDispatcher(runtime)
