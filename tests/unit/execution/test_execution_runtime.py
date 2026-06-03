import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from futures_mvp.domain.enums import Direction, EventSource, Offset, OrderStatus
from futures_mvp.domain.models import OrderRequest, OrderState
from futures_mvp.modules.execution import (
    ConfigurableMockFuturesExchange,
    DeliveryPhase,
    DeterministicReportIdGenerator,
    ExchangeReport,
    ExchangeReportType,
    ExecutionManagementSystem,
    ExecutionOperation,
    ExecutionReportHandler,
    InMemoryExecutionReportSink,
    MappingContext,
    MappingResult,
    MappingResultStatus,
    MockCancelResult,
    MockSubmitResult,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def order_state(status: OrderStatus = OrderStatus.SUBMITTING) -> OrderState:
    return OrderState(
        order_id="order-1",
        request=OrderRequest(
            client_order_id="client-1",
            account_id="account-1",
            instrument_id="IF2601",
            exchange="CFFEX",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            limit_price=Decimal("4000"),
            quantity=Decimal("1"),
        ),
        status=status,
    )


class FakeExchangeCommandPort:
    def __init__(self) -> None:
        self.submitted: list[OrderState] = []
        self.canceled: list[OrderState] = []

    def submit_limit_order(self, order: OrderState) -> None:
        self.submitted.append(order)

    def cancel_order(self, order: OrderState) -> None:
        self.canceled.append(order)


def fixed_clock() -> datetime:
    return NOW


def test_report_sink_append_list_and_drain_reports() -> None:
    sink = InMemoryExecutionReportSink()
    report = ExchangeReport(
        report_type=ExchangeReportType.ACK,
        exchange_report_id="report-1",
        occurred_at=NOW,
        event_source=EventSource.EXCHANGE,
        order_id="order-1",
    )

    sink.append(report)

    listed = sink.list_reports()
    assert listed == [report]
    listed.clear()
    assert sink.list_reports() == [report]
    assert sink.drain_reports() == [report]
    assert sink.list_reports() == []


def test_ems_depends_on_fake_exchange_command_port_for_submit_and_cancel() -> None:
    fake_exchange = FakeExchangeCommandPort()
    ems = ExecutionManagementSystem(fake_exchange)
    order = order_state()

    submit_result = ems.submit(order)
    cancel_result = ems.cancel(order)

    assert submit_result is None
    assert cancel_result is None
    assert fake_exchange.submitted == [order]
    assert fake_exchange.canceled == [order]


@pytest.mark.parametrize(
    ("mock_result", "report_type", "delivery_phase"),
    [
        (MockSubmitResult.ACK, ExchangeReportType.ACK, None),
        (MockSubmitResult.REJECTED, ExchangeReportType.REJECTED, None),
        (MockSubmitResult.TIMEOUT, ExchangeReportType.TIMEOUT, None),
        (
            MockSubmitResult.EXCHANGE_UNAVAILABLE_PRE_SEND,
            ExchangeReportType.EXCHANGE_UNAVAILABLE,
            DeliveryPhase.PRE_SEND,
        ),
        (
            MockSubmitResult.EXCHANGE_UNAVAILABLE_POST_SEND_UNCERTAIN,
            ExchangeReportType.EXCHANGE_UNAVAILABLE,
            DeliveryPhase.POST_SEND_UNCERTAIN,
        ),
    ],
)
def test_mock_exchange_submit_reports(
    mock_result: MockSubmitResult,
    report_type: ExchangeReportType,
    delivery_phase: DeliveryPhase | None,
) -> None:
    sink = InMemoryExecutionReportSink()
    exchange = ConfigurableMockFuturesExchange(
        sink,
        clock=fixed_clock,
        submit_results=[mock_result],
    )

    result = exchange.submit_limit_order(order_state())

    assert result is None
    [report] = sink.list_reports()
    assert report.report_type is report_type
    assert report.exchange_report_id == "exchange-report-1"
    assert report.occurred_at == NOW
    assert report.event_source is EventSource.EXCHANGE
    assert report.order_id == "order-1"
    assert report.client_order_id == "client-1"
    assert report.operation is ExecutionOperation.SUBMIT
    assert report.delivery_phase is delivery_phase
    assert report.raw_payload is None


@pytest.mark.parametrize(
    ("mock_result", "report_type", "delivery_phase"),
    [
        (MockCancelResult.CANCELED, ExchangeReportType.CANCELED, None),
        (MockCancelResult.CANCEL_REJECTED, ExchangeReportType.CANCEL_REJECTED, None),
        (MockCancelResult.TIMEOUT, ExchangeReportType.TIMEOUT, None),
        (
            MockCancelResult.EXCHANGE_UNAVAILABLE_PRE_SEND,
            ExchangeReportType.EXCHANGE_UNAVAILABLE,
            DeliveryPhase.PRE_SEND,
        ),
        (
            MockCancelResult.EXCHANGE_UNAVAILABLE_POST_SEND_UNCERTAIN,
            ExchangeReportType.EXCHANGE_UNAVAILABLE,
            DeliveryPhase.POST_SEND_UNCERTAIN,
        ),
    ],
)
def test_mock_exchange_cancel_reports(
    mock_result: MockCancelResult,
    report_type: ExchangeReportType,
    delivery_phase: DeliveryPhase | None,
) -> None:
    sink = InMemoryExecutionReportSink()
    exchange = ConfigurableMockFuturesExchange(
        sink,
        clock=fixed_clock,
        cancel_results=[mock_result],
    )

    result = exchange.cancel_order(order_state(OrderStatus.CANCEL_PENDING))

    assert result is None
    [report] = sink.list_reports()
    assert report.report_type is report_type
    assert report.exchange_report_id == "exchange-report-1"
    assert report.occurred_at == NOW
    assert report.event_source is EventSource.EXCHANGE
    assert report.order_id == "order-1"
    assert report.client_order_id == "client-1"
    assert report.operation is ExecutionOperation.CANCEL
    assert report.delivery_phase is delivery_phase
    assert report.raw_payload is None


def test_report_id_generation_is_deterministic_and_replayable() -> None:
    counter = DeterministicReportIdGenerator(prefix="test-report")
    assert counter() == "test-report-1"
    assert counter() == "test-report-2"

    sink = InMemoryExecutionReportSink()
    exchange = ConfigurableMockFuturesExchange(
        sink,
        id_generator=lambda: "duplicate-report",
        clock=fixed_clock,
    )

    exchange.submit_limit_order(order_state())
    exchange.submit_limit_order(order_state())

    reports = sink.list_reports()
    assert [report.exchange_report_id for report in reports] == [
        "duplicate-report",
        "duplicate-report",
    ]


def test_configurable_mock_exchange_can_be_used_as_ems_command_port() -> None:
    sink = InMemoryExecutionReportSink()
    exchange = ConfigurableMockFuturesExchange(sink, clock=fixed_clock)
    ems = ExecutionManagementSystem(exchange)

    ems.submit(order_state())

    assert len(sink.list_reports()) == 1


@pytest.mark.parametrize("status", list(MappingResultStatus))
def test_report_handler_returns_mapper_result_without_splitting(
    status: MappingResultStatus,
) -> None:
    expected = MappingResult(status=status)
    calls: list[tuple[ExchangeReport, MappingContext]] = []

    def mapper(report: ExchangeReport, context: MappingContext) -> MappingResult:
        calls.append((report, context))
        return expected

    handler = ExecutionReportHandler(mapper=mapper)
    exchange_report = ExchangeReport(report_type=ExchangeReportType.ACK)
    mapping_context = MappingContext()

    result = handler.handle(exchange_report, mapping_context)

    assert result is expected
    assert calls == [(exchange_report, mapping_context)]
    assert not hasattr(handler, "split")


def test_report_handler_keeps_unknown_report_as_mapper_result() -> None:
    handler = ExecutionReportHandler()
    result = handler.handle(
        ExchangeReport(
            report_type=ExchangeReportType.UNKNOWN_REPORT,
            exchange_report_id="unknown-1",
            occurred_at=NOW,
            event_source=EventSource.EXCHANGE,
            order_id="order-1",
        ),
        MappingContext(current_order_status=OrderStatus.ACKED),
    )

    assert result.status is MappingResultStatus.MAPPING_ERROR
    assert result.order_event is None


def test_runtime_layer_does_not_import_forbidden_boundaries() -> None:
    module_paths = [
        Path("src/futures_mvp/modules/execution/ems.py"),
        Path("src/futures_mvp/modules/execution/mock_exchange.py"),
        Path("src/futures_mvp/modules/execution/reports.py"),
    ]
    forbidden_modules = {
        "futures_mvp.modules.oms",
        "futures_mvp.modules.risk",
        "futures_mvp.db",
        "futures_mvp.interfaces.repositories",
        "sqlalchemy",
        "kafka",
        "redis",
        "celery",
        "fastapi",
        "requests",
        "httpx",
    }
    forbidden_names = {
        "OMSService",
        "RiskEngine",
        "Repository",
        "UnitOfWork",
        "Position",
        "Margin",
        "PnL",
        "Settlement",
        "CTP",
        "SimNow",
        "broker",
        "adapter",
        "Kafka",
        "Redis",
        "Celery",
        "FastAPI",
        "KMS",
        "cloud",
    }

    for path in module_paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_modules
                    assert alias.name.split(".")[-1] not in forbidden_names
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module not in forbidden_modules
                assert module.split(".")[-1] not in forbidden_names
                for alias in node.names:
                    assert alias.name not in forbidden_names
