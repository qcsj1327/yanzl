import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from futures_mvp.domain.enums import (
    Direction,
    EventApplicationStatus,
    EventSource,
    Offset,
    OrderStatus,
    OrderType,
)
from futures_mvp.domain.models import (
    OrderEvent,
    OrderEventApplicationResult,
    OrderRequest,
    OrderState,
    RiskResult,
)
from futures_mvp.modules.execution import (
    ApplicationExecutionOrchestrator,
    ExchangeReport,
    ExchangeReportType,
    ExecutionOperation,
    ExecutionOrchestrationStatus,
    MappingContext,
    MappingError,
    MappingErrorReason,
    MappingResult,
    MappingResultStatus,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def order_state(
    status: OrderStatus = OrderStatus.RISK_ACCEPTED,
    *,
    order_id: str = "order-1",
    client_order_id: str = "client-1",
) -> OrderState:
    return OrderState(
        order_id=order_id,
        request=OrderRequest(
            client_order_id=client_order_id,
            account_id="account-1",
            instrument_id="IF2601",
            exchange="CFFEX",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("4000"),
            quantity=Decimal("1"),
        ),
        status=status,
    )


def app_result(
    status: EventApplicationStatus,
    order: OrderState,
    *,
    reason: str | None = None,
) -> OrderEventApplicationResult:
    return OrderEventApplicationResult(status=status, order=order, reason=reason)


def order_event(
    *,
    order: OrderState,
    previous_status: OrderStatus,
    new_status: OrderStatus,
    external_event_id: str = "report-1",
) -> OrderEvent:
    return OrderEvent(
        order_id=order.order_id,
        previous_status=previous_status,
        new_status=new_status,
        event_source=EventSource.EXCHANGE,
        external_event_id=external_event_id,
        raw_payload={"diagnostic": True},
        occurred_at=NOW,
    )


def report(
    *,
    order: OrderState,
    operation: ExecutionOperation,
    report_id: str = "report-1",
    report_type: ExchangeReportType = ExchangeReportType.ACK,
) -> ExchangeReport:
    return ExchangeReport(
        report_type=report_type,
        exchange_report_id=report_id,
        occurred_at=NOW,
        event_source=EventSource.EXCHANGE,
        order_id=order.order_id,
        client_order_id=order.request.client_order_id,
        operation=operation,
    )


class FakeOMS:
    def __init__(
        self,
        *,
        pre_result: OrderEventApplicationResult,
        application_results: list[OrderEventApplicationResult] | None = None,
    ) -> None:
        self.pre_result = pre_result
        self.application_results = list(application_results or [])
        self.applied_events: list[OrderEvent] = []

    def create_order(self, request: OrderRequest, *, client_order_id: str) -> OrderState:
        raise NotImplementedError

    def apply_risk_result(
        self,
        order_id: str,
        risk_result: RiskResult,
        *,
        external_event_id: str,
        occurred_at: datetime | None = None,
    ) -> OrderEventApplicationResult:
        _ = order_id, risk_result, external_event_id, occurred_at
        raise NotImplementedError

    def apply_order_event(self, event: OrderEvent) -> OrderEventApplicationResult:
        self.applied_events.append(event)
        if len(self.applied_events) == 1:
            return self.pre_result
        if self.application_results:
            return self.application_results.pop(0)
        return app_result(
            EventApplicationStatus.APPLIED,
            order_state(event.new_status, order_id=event.order_id),
        )

    def recover_order(self, order_id: str) -> OrderEventApplicationResult:
        _ = order_id
        raise NotImplementedError

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None:
        _ = client_order_id
        raise NotImplementedError


class FakeEMS:
    def __init__(self) -> None:
        self.submitted: list[OrderState] = []
        self.canceled: list[OrderState] = []

    def submit(self, order: OrderState) -> None:
        self.submitted.append(order)

    def cancel(self, order: OrderState) -> None:
        self.canceled.append(order)


class FakeReportSink:
    def __init__(self, reports: list[ExchangeReport] | None = None) -> None:
        self.reports = list(reports or [])
        self.drained = False

    def append(self, report: ExchangeReport) -> None:
        self.reports.append(report)

    def list_reports(self) -> list[ExchangeReport]:
        return list(self.reports)

    def drain_reports(self) -> list[ExchangeReport]:
        self.drained = True
        reports = list(self.reports)
        self.reports.clear()
        return reports


class FakeReportHandler:
    def __init__(self, results: list[MappingResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[ExchangeReport, MappingContext]] = []

    def handle(self, report: ExchangeReport, context: MappingContext) -> MappingResult:
        self.calls.append((report, context))
        return self.results.pop(0)


def orchestrator(
    *,
    oms: FakeOMS,
    ems: FakeEMS,
    sink: FakeReportSink,
    handler: FakeReportHandler,
) -> ApplicationExecutionOrchestrator:
    return ApplicationExecutionOrchestrator(
        oms=oms,
        ems=ems,
        report_sink=sink,
        report_handler=handler,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )


def test_submit_pre_event_applied_calls_ems_submit() -> None:
    order = order_state()
    submitting = order.model_copy(update={"status": OrderStatus.SUBMITTING})
    oms = FakeOMS(pre_result=app_result(EventApplicationStatus.APPLIED, submitting))
    ems = FakeEMS()
    sink = FakeReportSink()
    handler = FakeReportHandler([])

    result = orchestrator(oms=oms, ems=ems, sink=sink, handler=handler).submit_and_process(
        order,
        external_event_id="submit-pre-1",
    )

    assert result.status is ExecutionOrchestrationStatus.NO_REPORTS
    assert result.command_executed is True
    assert ems.submitted == [submitting]
    assert oms.applied_events[0].previous_status is OrderStatus.RISK_ACCEPTED
    assert oms.applied_events[0].new_status is OrderStatus.SUBMITTING


def test_submit_pre_event_rejected_does_not_call_ems_submit() -> None:
    order = order_state()
    oms = FakeOMS(
        pre_result=app_result(
            EventApplicationStatus.MISMATCH_REJECTED,
            order,
            reason="invalid_transition_rejected",
        )
    )
    ems = FakeEMS()

    result = orchestrator(
        oms=oms,
        ems=ems,
        sink=FakeReportSink(),
        handler=FakeReportHandler([]),
    ).submit_and_process(order, external_event_id="submit-pre-1")

    assert result.status is ExecutionOrchestrationStatus.PRE_EVENT_REJECTED
    assert result.command_executed is False
    assert ems.submitted == []


def test_cancel_pre_event_applied_calls_ems_cancel() -> None:
    order = order_state(OrderStatus.ACKED)
    cancel_pending = order.model_copy(update={"status": OrderStatus.CANCEL_PENDING})
    oms = FakeOMS(pre_result=app_result(EventApplicationStatus.APPLIED, cancel_pending))
    ems = FakeEMS()

    result = orchestrator(
        oms=oms,
        ems=ems,
        sink=FakeReportSink(),
        handler=FakeReportHandler([]),
    ).cancel_and_process(order, external_event_id="cancel-pre-1")

    assert result.status is ExecutionOrchestrationStatus.NO_REPORTS
    assert result.command_executed is True
    assert ems.canceled == [cancel_pending]
    assert oms.applied_events[0].previous_status is OrderStatus.ACKED
    assert oms.applied_events[0].new_status is OrderStatus.CANCEL_PENDING


def test_cancel_pre_event_rejected_does_not_call_ems_cancel() -> None:
    order = order_state(OrderStatus.FILLED)
    oms = FakeOMS(
        pre_result=app_result(
            EventApplicationStatus.IGNORED_TERMINAL,
            order,
            reason="terminal_order_event_noop",
        )
    )
    ems = FakeEMS()

    result = orchestrator(
        oms=oms,
        ems=ems,
        sink=FakeReportSink(),
        handler=FakeReportHandler([]),
    ).cancel_and_process(order, external_event_id="cancel-pre-1")

    assert result.status is ExecutionOrchestrationStatus.PRE_EVENT_REJECTED
    assert result.command_executed is False
    assert ems.canceled == []


def test_report_filtering_only_handles_current_order_and_operation_without_draining() -> None:
    order = order_state()
    submitting = order.model_copy(update={"status": OrderStatus.SUBMITTING})
    matched = report(order=submitting, operation=ExecutionOperation.SUBMIT, report_id="matched")
    wrong_operation = report(
        order=submitting,
        operation=ExecutionOperation.CANCEL,
        report_id="wrong-operation",
    )
    wrong_order = report(
        order=order_state(order_id="order-2", client_order_id="client-2"),
        operation=ExecutionOperation.SUBMIT,
        report_id="wrong-order",
    )
    handler = FakeReportHandler([MappingResult(status=MappingResultStatus.DUPLICATE_REPORT)])
    sink = FakeReportSink([matched, wrong_operation, wrong_order])

    result = orchestrator(
        oms=FakeOMS(pre_result=app_result(EventApplicationStatus.APPLIED, submitting)),
        ems=FakeEMS(),
        sink=sink,
        handler=handler,
    ).submit_and_process(order, external_event_id="submit-pre-1")

    assert result.status is ExecutionOrchestrationStatus.MAPPING_PASSTHROUGH
    assert [call[0] for call in handler.calls] == [matched]
    assert sink.list_reports() == [matched, wrong_operation, wrong_order]
    assert sink.drained is False


def test_report_filtering_accepts_string_operation() -> None:
    order = order_state()
    submitting = order.model_copy(update={"status": OrderStatus.SUBMITTING})
    matched = ExchangeReport(
        report_type=ExchangeReportType.ACK,
        exchange_report_id="report-1",
        occurred_at=NOW,
        event_source=EventSource.EXCHANGE,
        order_id=submitting.order_id,
        operation=ExecutionOperation.SUBMIT.value,
    )
    handler = FakeReportHandler([MappingResult(status=MappingResultStatus.DUPLICATE_REPORT)])

    result = orchestrator(
        oms=FakeOMS(pre_result=app_result(EventApplicationStatus.APPLIED, submitting)),
        ems=FakeEMS(),
        sink=FakeReportSink([matched]),
        handler=handler,
    ).submit_and_process(order, external_event_id="submit-pre-1")

    assert result.status is ExecutionOrchestrationStatus.MAPPING_PASSTHROUGH
    assert [call[0] for call in handler.calls] == [matched]


def test_mapped_order_event_calls_oms_apply_order_event() -> None:
    order = order_state()
    submitting = order.model_copy(update={"status": OrderStatus.SUBMITTING})
    acked = order.model_copy(update={"status": OrderStatus.ACKED})
    mapped_event = order_event(
        order=submitting,
        previous_status=OrderStatus.SUBMITTING,
        new_status=OrderStatus.ACKED,
    )
    oms = FakeOMS(
        pre_result=app_result(EventApplicationStatus.APPLIED, submitting),
        application_results=[app_result(EventApplicationStatus.APPLIED, acked)],
    )

    result = orchestrator(
        oms=oms,
        ems=FakeEMS(),
        sink=FakeReportSink([report(order=submitting, operation=ExecutionOperation.SUBMIT)]),
        handler=FakeReportHandler(
            [
                MappingResult(
                    status=MappingResultStatus.MAPPED_ORDER_EVENT,
                    order_event=mapped_event,
                )
            ]
        ),
    ).submit_and_process(order, external_event_id="submit-pre-1")

    assert result.status is ExecutionOrchestrationStatus.REPORTS_PROCESSED
    assert len(oms.applied_events) == 2
    assert oms.applied_events[1] == mapped_event
    assert result.oms_application_results == [
        app_result(EventApplicationStatus.APPLIED, acked)
    ]
    assert result.final_order == acked


@pytest.mark.parametrize(
    "mapping_status",
    [
        MappingResultStatus.DUPLICATE_REPORT,
        MappingResultStatus.IGNORED_REPORT,
        MappingResultStatus.INSUFFICIENT_CONTEXT,
        MappingResultStatus.ENTER_UNKNOWN_CANDIDATE,
        MappingResultStatus.MAPPING_ERROR,
        MappingResultStatus.DOMAIN_FIELD_UNSUPPORTED,
    ],
)
def test_non_mapped_results_do_not_call_oms_apply_order_event(
    mapping_status: MappingResultStatus,
) -> None:
    order = order_state()
    submitting = order.model_copy(update={"status": OrderStatus.SUBMITTING})
    oms = FakeOMS(pre_result=app_result(EventApplicationStatus.APPLIED, submitting))

    result = orchestrator(
        oms=oms,
        ems=FakeEMS(),
        sink=FakeReportSink([report(order=submitting, operation=ExecutionOperation.SUBMIT)]),
        handler=FakeReportHandler(
            [
                MappingResult(
                    status=mapping_status,
                    error=MappingError(
                        MappingErrorReason.UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY,
                        "passthrough",
                    )
                    if mapping_status is MappingResultStatus.MAPPING_ERROR
                    else None,
                )
            ]
        ),
    ).submit_and_process(order, external_event_id="submit-pre-1")

    assert result.status is ExecutionOrchestrationStatus.MAPPING_PASSTHROUGH
    assert len(oms.applied_events) == 1
    assert result.oms_application_results == []


def test_oms_application_rejected_is_typed_result() -> None:
    order = order_state()
    submitting = order.model_copy(update={"status": OrderStatus.SUBMITTING})
    mapped_event = order_event(
        order=submitting,
        previous_status=OrderStatus.SUBMITTING,
        new_status=OrderStatus.ACKED,
    )
    rejected = app_result(
        EventApplicationStatus.MISMATCH_REJECTED,
        submitting,
        reason="invalid_transition_rejected",
    )

    result = orchestrator(
        oms=FakeOMS(
            pre_result=app_result(EventApplicationStatus.APPLIED, submitting),
            application_results=[rejected],
        ),
        ems=FakeEMS(),
        sink=FakeReportSink([report(order=submitting, operation=ExecutionOperation.SUBMIT)]),
        handler=FakeReportHandler(
            [
                MappingResult(
                    status=MappingResultStatus.MAPPED_ORDER_EVENT,
                    order_event=mapped_event,
                )
            ]
        ),
    ).submit_and_process(order, external_event_id="submit-pre-1")

    assert result.status is ExecutionOrchestrationStatus.OMS_APPLICATION_REJECTED
    assert result.oms_application_results == [rejected]
    assert result.reason == "oms_application_rejected"


def test_no_reports_returns_no_reports_status() -> None:
    order = order_state()
    submitting = order.model_copy(update={"status": OrderStatus.SUBMITTING})

    result = orchestrator(
        oms=FakeOMS(pre_result=app_result(EventApplicationStatus.APPLIED, submitting)),
        ems=FakeEMS(),
        sink=FakeReportSink(),
        handler=FakeReportHandler([]),
    ).submit_and_process(order, external_event_id="submit-pre-1")

    assert result.status is ExecutionOrchestrationStatus.NO_REPORTS
    assert result.mapping_results == []
    assert result.oms_application_results == []
    assert result.final_order == submitting


def test_mapping_context_uses_latest_oms_order_status_and_operation() -> None:
    order = order_state()
    submitting = order.model_copy(update={"status": OrderStatus.SUBMITTING})
    submitted = order.model_copy(update={"status": OrderStatus.SUBMITTED})
    acked = order.model_copy(update={"status": OrderStatus.ACKED})
    handler = FakeReportHandler(
        [
            MappingResult(
                status=MappingResultStatus.MAPPED_ORDER_EVENT,
                order_event=order_event(
                    order=submitting,
                    previous_status=OrderStatus.SUBMITTING,
                    new_status=OrderStatus.SUBMITTED,
                    external_event_id="report-1",
                ),
            ),
            MappingResult(status=MappingResultStatus.DUPLICATE_REPORT),
        ]
    )

    orchestrator(
        oms=FakeOMS(
            pre_result=app_result(EventApplicationStatus.APPLIED, submitting),
            application_results=[app_result(EventApplicationStatus.APPLIED, submitted)],
        ),
        ems=FakeEMS(),
        sink=FakeReportSink(
            [
                report(order=submitting, operation=ExecutionOperation.SUBMIT, report_id="report-1"),
                report(order=acked, operation=ExecutionOperation.SUBMIT, report_id="report-2"),
            ]
        ),
        handler=handler,
    ).submit_and_process(
        order,
        external_event_id="submit-pre-1",
        known_exchange_report_ids={"known-report"},
        allow_status_only_fill=False,
    )

    first_context = handler.calls[0][1]
    second_context = handler.calls[1][1]
    assert first_context.current_order_status is OrderStatus.SUBMITTING
    assert first_context.expected_previous_status is OrderStatus.SUBMITTING
    assert first_context.known_exchange_report_ids == {"known-report"}
    assert first_context.operation is ExecutionOperation.SUBMIT
    assert first_context.allow_status_only_fill is False
    assert second_context.current_order_status is OrderStatus.SUBMITTED
    assert second_context.expected_previous_status is OrderStatus.SUBMITTED


def test_orchestrator_does_not_import_forbidden_boundaries() -> None:
    path = Path("src/futures_mvp/modules/execution/orchestrator.py")
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    forbidden_fragments = {
        "futures_mvp.db",
        "futures_mvp.interfaces.repositories",
        "futures_mvp.modules.risk",
        "futures_mvp.modules.oms.service",
        "futures_mvp.modules.position",
        "futures_mvp.modules.margin",
        "futures_mvp.modules.pnl",
        "futures_mvp.modules.settlement",
        "broker",
        "ctp",
        "simnow",
        "fastapi",
        "celery",
        "kafka",
        "redis",
        "kms",
    }
    assert all(
        not any(fragment in imported.lower() for fragment in forbidden_fragments)
        for imported in imports
    )
