from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from futures_mvp.domain.enums import EventApplicationStatus, EventSource, OrderStatus
from futures_mvp.domain.models import (
    OrderEvent,
    OrderEventApplicationResult,
    OrderState,
)
from futures_mvp.interfaces.engines import EMS, OMS, ExecutionReportSink
from futures_mvp.modules.execution.models import (
    ExchangeReport,
    ExecutionOperation,
    MappingContext,
    MappingResult,
    MappingResultStatus,
)
from futures_mvp.modules.execution.reports import ExecutionReportHandler


class ExecutionOrchestrationStatus(StrEnum):
    COMMAND_EXECUTED = "COMMAND_EXECUTED"
    PRE_EVENT_REJECTED = "PRE_EVENT_REJECTED"
    REPORTS_PROCESSED = "REPORTS_PROCESSED"
    NO_REPORTS = "NO_REPORTS"
    MAPPING_PASSTHROUGH = "MAPPING_PASSTHROUGH"
    OMS_APPLICATION_REJECTED = "OMS_APPLICATION_REJECTED"
    LEGACY_DEFERRED = "LEGACY_DEFERRED"


@dataclass(frozen=True)
class ExecutionOrchestrationResult:
    status: ExecutionOrchestrationStatus
    pre_event_result: OrderEventApplicationResult
    command_executed: bool
    mapping_results: list[MappingResult] = field(default_factory=list)
    oms_application_results: list[OrderEventApplicationResult] = field(default_factory=list)
    final_order: OrderState | None = None
    reason: str | None = None


class ApplicationExecutionOrchestrator:
    def __init__(
        self,
        *,
        oms: OMS,
        ems: EMS,
        report_sink: ExecutionReportSink,
        report_handler: ExecutionReportHandler,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._oms = oms
        self._ems = ems
        self._report_sink = report_sink
        self._report_handler = report_handler
        self._clock = clock or (lambda: datetime.now(UTC))

    def submit_and_process(
        self,
        order: OrderState,
        *,
        external_event_id: str,
        known_exchange_report_ids: set[str] | None = None,
        allow_status_only_fill: bool = True,
    ) -> ExecutionOrchestrationResult:
        del external_event_id, known_exchange_report_ids, allow_status_only_fill
        return self._legacy_deferred(order)

    def cancel_and_process(
        self,
        order: OrderState,
        *,
        external_event_id: str,
        known_exchange_report_ids: set[str] | None = None,
        allow_status_only_fill: bool = True,
    ) -> ExecutionOrchestrationResult:
        del external_event_id, known_exchange_report_ids, allow_status_only_fill
        return self._legacy_deferred(order)

    def _process_reports(
        self,
        pre_result: OrderEventApplicationResult,
        *,
        operation: ExecutionOperation,
        known_exchange_report_ids: set[str] | None,
        allow_status_only_fill: bool,
    ) -> ExecutionOrchestrationResult:
        matching_reports = [
            report
            for report in self._report_sink.list_reports()
            if self._matches_report(report, pre_result.order, operation)
        ]
        if not matching_reports:
            return ExecutionOrchestrationResult(
                status=ExecutionOrchestrationStatus.NO_REPORTS,
                pre_event_result=pre_result,
                command_executed=True,
                final_order=pre_result.order,
                reason="no_matching_reports",
            )

        mapping_results: list[MappingResult] = []
        oms_application_results: list[OrderEventApplicationResult] = []
        current_order = pre_result.order
        saw_passthrough = False
        saw_oms_rejection = False

        for report in matching_reports:
            mapping_result = self._report_handler.handle(
                report,
                MappingContext(
                    current_order_status=current_order.status,
                    expected_previous_status=current_order.status,
                    known_exchange_report_ids=known_exchange_report_ids,
                    operation=operation,
                    allow_status_only_fill=allow_status_only_fill,
                ),
            )
            mapping_results.append(mapping_result)
            if mapping_result.status is not MappingResultStatus.MAPPED_ORDER_EVENT:
                saw_passthrough = True
                continue

            if mapping_result.order_event is None:
                saw_passthrough = True
                continue

            saw_passthrough = True

        if saw_oms_rejection:
            status = ExecutionOrchestrationStatus.OMS_APPLICATION_REJECTED
            reason = "oms_application_rejected"
        elif saw_passthrough:
            status = ExecutionOrchestrationStatus.MAPPING_PASSTHROUGH
            reason = "mapping_passthrough"
        else:
            status = ExecutionOrchestrationStatus.REPORTS_PROCESSED
            reason = None

        return ExecutionOrchestrationResult(
            status=status,
            pre_event_result=pre_result,
            command_executed=True,
            mapping_results=mapping_results,
            oms_application_results=oms_application_results,
            final_order=current_order,
            reason=reason,
        )

    def _pre_event(
        self,
        order: OrderState,
        *,
        previous_status: OrderStatus,
        new_status: OrderStatus,
        operation: ExecutionOperation,
        external_event_id: str,
    ) -> OrderEvent:
        return OrderEvent(
            order_id=order.order_id,
            previous_status=previous_status,
            new_status=new_status,
            event_source=EventSource.OMS,
            external_event_id=external_event_id,
            raw_payload={
                "reason": "application_execution_orchestrator_pre_event",
                "operation": operation.value,
            },
            occurred_at=self._clock(),
        )

    @staticmethod
    def _pre_event_rejected(
        pre_result: OrderEventApplicationResult,
    ) -> ExecutionOrchestrationResult:
        return ExecutionOrchestrationResult(
            status=ExecutionOrchestrationStatus.PRE_EVENT_REJECTED,
            pre_event_result=pre_result,
            command_executed=False,
            final_order=pre_result.order,
            reason=pre_result.reason or "pre_event_rejected",
        )

    @staticmethod
    def _legacy_deferred(
        order: OrderState,
    ) -> ExecutionOrchestrationResult:
        return ExecutionOrchestrationResult(
            status=ExecutionOrchestrationStatus.LEGACY_DEFERRED,
            pre_event_result=OrderEventApplicationResult(
                status=EventApplicationStatus.MISMATCH_REJECTED,
                order=order,
                reason=(
                    "legacy execution orchestrator is deferred; use "
                    "ExecutionReportNormalizer and OMSEventApplicationService"
                ),
            ),
            command_executed=False,
            final_order=order,
            reason="legacy_execution_orchestrator_deferred",
        )

    @staticmethod
    def _matches_report(
        report: ExchangeReport,
        order: OrderState,
        operation: ExecutionOperation,
    ) -> bool:
        order_matches = (
            report.order_id == order.order_id
            or report.client_order_id == order.request.client_order_id
        )
        return order_matches and _operation_matches(report.operation, operation)


def _operation_matches(
    report_operation: ExecutionOperation | str | None,
    expected: ExecutionOperation,
) -> bool:
    if report_operation is None:
        return False
    try:
        return ExecutionOperation(report_operation) is expected
    except ValueError:
        return False
