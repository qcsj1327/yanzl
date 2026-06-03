import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from futures_mvp.domain.enums import EventSource, OrderStatus
from futures_mvp.modules.execution import (
    DeliveryPhase,
    ExchangeReport,
    ExchangeReportType,
    ExecutionOperation,
    MappingContext,
    MappingErrorReason,
    MappingResultStatus,
    map_exchange_report,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def report(
    report_type: ExchangeReportType | str | None,
    *,
    exchange_report_id: str | None = "report-1",
    occurred_at: datetime | None = NOW,
    event_source: EventSource | str | None = EventSource.EXCHANGE,
    order_id: str | None = "order-1",
    client_order_id: str | None = None,
    operation: ExecutionOperation | str | None = None,
    delivery_phase: DeliveryPhase | str | None = None,
    raw_payload: dict[str, object] | None = None,
) -> ExchangeReport:
    return ExchangeReport(
        report_type=report_type,
        exchange_report_id=exchange_report_id,
        occurred_at=occurred_at,
        event_source=event_source,
        order_id=order_id,
        client_order_id=client_order_id,
        operation=operation,
        delivery_phase=delivery_phase,
        raw_payload=raw_payload,
    )


def context(
    *,
    current_order_status: OrderStatus | None = OrderStatus.SUBMITTING,
    expected_previous_status: OrderStatus | None = None,
    known_exchange_report_ids: set[str] | None = None,
    operation: ExecutionOperation | str | None = None,
    allow_status_only_fill: bool = True,
) -> MappingContext:
    return MappingContext(
        current_order_status=current_order_status,
        expected_previous_status=expected_previous_status,
        known_exchange_report_ids=known_exchange_report_ids,
        operation=operation,
        allow_status_only_fill=allow_status_only_fill,
    )


def test_enum_values_match_contract() -> None:
    assert {item.value for item in ExchangeReportType} == {
        "ACK",
        "REJECTED",
        "PARTIAL_FILL",
        "FULL_FILL",
        "CANCELED",
        "CANCEL_REJECTED",
        "EXPIRED",
        "TIMEOUT",
        "EXCHANGE_UNAVAILABLE",
        "UNKNOWN_REPORT",
    }
    assert "OUT_OF_ORDER_REPORT" not in {item.value for item in ExchangeReportType}
    assert "DUPLICATE_REPORT" not in {item.value for item in ExchangeReportType}

    assert {item.value for item in ExecutionOperation} == {"SUBMIT", "CANCEL"}
    assert {item.value for item in DeliveryPhase} == {"PRE_SEND", "POST_SEND_UNCERTAIN"}
    assert {item.value for item in MappingResultStatus} == {
        "MAPPED_ORDER_EVENT",
        "DUPLICATE_REPORT",
        "IGNORED_REPORT",
        "INSUFFICIENT_CONTEXT",
        "ENTER_UNKNOWN_CANDIDATE",
        "MAPPING_ERROR",
        "DOMAIN_FIELD_UNSUPPORTED",
    }
    assert {item.value for item in MappingErrorReason} == {
        "MISSING_REPORT_TYPE",
        "MISSING_EXCHANGE_REPORT_ID",
        "MISSING_OCCURRED_AT",
        "MISSING_EVENT_SOURCE",
        "MISSING_ORDER_IDENTITY",
        "MISSING_OPERATION",
        "MISSING_DELIVERY_PHASE",
        "UNSUPPORTED_REPORT_TYPE",
        "UNSUPPORTED_OPERATION",
        "UNSUPPORTED_DELIVERY_PHASE",
        "OPERATION_REPORT_TYPE_MISMATCH",
        "MISSING_CURRENT_ORDER_STATUS",
        "MISSING_EXPECTED_PREVIOUS_STATUS",
        "ILLEGAL_SAME_STATUS_EVENT",
        "DOMAIN_FIELD_UNSUPPORTED",
        "RAW_PAYLOAD_ONLY_FACT_FORBIDDEN",
        "UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY",
    }


def test_exchange_report_and_context_defaults_are_untrusted_boundary_dto() -> None:
    dto = ExchangeReport()
    mapping_context = MappingContext()

    assert dto.report_type is None
    assert dto.exchange_report_id is None
    assert dto.occurred_at is None
    assert dto.event_source is None
    assert dto.raw_payload is None
    assert mapping_context.current_order_status is None
    assert mapping_context.expected_previous_status is None
    assert mapping_context.known_exchange_report_ids is None
    assert mapping_context.operation is None
    assert mapping_context.allow_status_only_fill is True


@pytest.mark.parametrize(
    ("exchange_report", "reason"),
    [
        (report(None), MappingErrorReason.MISSING_REPORT_TYPE),
        (report("BOGUS"), MappingErrorReason.UNSUPPORTED_REPORT_TYPE),
        (
            report(ExchangeReportType.ACK, exchange_report_id=None),
            MappingErrorReason.MISSING_EXCHANGE_REPORT_ID,
        ),
        (
            report(ExchangeReportType.ACK, occurred_at=None),
            MappingErrorReason.MISSING_OCCURRED_AT,
        ),
        (
            report(ExchangeReportType.ACK, event_source=None),
            MappingErrorReason.MISSING_EVENT_SOURCE,
        ),
        (
            report(ExchangeReportType.ACK, order_id=None, client_order_id=None),
            MappingErrorReason.MISSING_ORDER_IDENTITY,
        ),
    ],
)
def test_base_required_fields_return_mapping_error(
    exchange_report: ExchangeReport,
    reason: MappingErrorReason,
) -> None:
    result = map_exchange_report(exchange_report, context())

    assert result.status is MappingResultStatus.MAPPING_ERROR
    assert result.error is not None
    assert result.error.reason is reason
    assert result.order_event is None


def test_client_order_id_without_order_id_is_insufficient_context() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.ACK, order_id=None, client_order_id="client-1"),
        context(),
    )

    assert result.status is MappingResultStatus.INSUFFICIENT_CONTEXT
    assert result.error is not None
    assert result.error.reason is MappingErrorReason.MISSING_ORDER_IDENTITY
    assert result.order_event is None


@pytest.mark.parametrize(
    ("exchange_report", "reason"),
    [
        (
            report(ExchangeReportType.TIMEOUT),
            MappingErrorReason.MISSING_OPERATION,
        ),
        (
            report(ExchangeReportType.EXCHANGE_UNAVAILABLE, operation=ExecutionOperation.SUBMIT),
            MappingErrorReason.MISSING_DELIVERY_PHASE,
        ),
        (
            report(ExchangeReportType.TIMEOUT, operation="BOGUS"),
            MappingErrorReason.UNSUPPORTED_OPERATION,
        ),
        (
            report(
                ExchangeReportType.EXCHANGE_UNAVAILABLE,
                operation=ExecutionOperation.SUBMIT,
                delivery_phase="BOGUS",
            ),
            MappingErrorReason.UNSUPPORTED_DELIVERY_PHASE,
        ),
        (
            report(ExchangeReportType.ACK, operation=ExecutionOperation.CANCEL),
            MappingErrorReason.OPERATION_REPORT_TYPE_MISMATCH,
        ),
        (
            report(ExchangeReportType.CANCELED, operation=ExecutionOperation.SUBMIT),
            MappingErrorReason.OPERATION_REPORT_TYPE_MISMATCH,
        ),
    ],
)
def test_conditional_fields_and_operation_consistency(
    exchange_report: ExchangeReport,
    reason: MappingErrorReason,
) -> None:
    result = map_exchange_report(exchange_report, context())

    assert result.status is MappingResultStatus.MAPPING_ERROR
    assert result.error is not None
    assert result.error.reason is reason


@pytest.mark.parametrize(
    ("exchange_report", "expected_status", "previous_status"),
    [
        (report(ExchangeReportType.ACK), OrderStatus.ACKED, OrderStatus.SUBMITTING),
        (
            report(ExchangeReportType.REJECTED),
            OrderStatus.REJECTED_BY_EXCHANGE,
            OrderStatus.SUBMITTING,
        ),
        (
            report(ExchangeReportType.PARTIAL_FILL),
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.ACKED,
        ),
        (report(ExchangeReportType.FULL_FILL), OrderStatus.FILLED, OrderStatus.ACKED),
        (
            report(ExchangeReportType.CANCELED, operation=ExecutionOperation.CANCEL),
            OrderStatus.CANCELED,
            OrderStatus.CANCEL_PENDING,
        ),
        (
            report(ExchangeReportType.CANCEL_REJECTED, operation=ExecutionOperation.CANCEL),
            OrderStatus.CANCEL_FAILED,
            OrderStatus.CANCEL_PENDING,
        ),
        (report(ExchangeReportType.EXPIRED), OrderStatus.EXPIRED, OrderStatus.ACKED),
    ],
)
def test_basic_status_only_mappings(
    exchange_report: ExchangeReport,
    expected_status: OrderStatus,
    previous_status: OrderStatus,
) -> None:
    result = map_exchange_report(
        exchange_report,
        context(current_order_status=previous_status),
    )

    assert result.status is MappingResultStatus.MAPPED_ORDER_EVENT
    assert result.order_event is not None
    assert result.order_event.order_id == "order-1"
    assert result.order_event.previous_status is previous_status
    assert result.order_event.new_status is expected_status
    assert result.order_event.event_source is EventSource.EXCHANGE
    assert result.order_event.external_event_id == "report-1"
    assert result.order_event.occurred_at == NOW


@pytest.mark.parametrize(
    ("operation", "expected_status"),
    [
        (ExecutionOperation.SUBMIT, OrderStatus.SUBMIT_TIMEOUT),
        (ExecutionOperation.CANCEL, OrderStatus.CANCEL_FAILED),
    ],
)
def test_timeout_mapping(operation: ExecutionOperation, expected_status: OrderStatus) -> None:
    current_status = (
        OrderStatus.SUBMITTING
        if operation is ExecutionOperation.SUBMIT
        else OrderStatus.CANCEL_PENDING
    )
    result = map_exchange_report(
        report(ExchangeReportType.TIMEOUT, operation=operation),
        context(current_order_status=current_status),
    )

    assert result.status is MappingResultStatus.MAPPED_ORDER_EVENT
    assert result.order_event is not None
    assert result.order_event.new_status is expected_status


@pytest.mark.parametrize(
    ("operation", "delivery_phase", "expected_status"),
    [
        (ExecutionOperation.SUBMIT, DeliveryPhase.PRE_SEND, OrderStatus.SUBMIT_FAILED),
        (
            ExecutionOperation.SUBMIT,
            DeliveryPhase.POST_SEND_UNCERTAIN,
            OrderStatus.SUBMIT_TIMEOUT,
        ),
        (ExecutionOperation.CANCEL, DeliveryPhase.PRE_SEND, OrderStatus.CANCEL_FAILED),
        (
            ExecutionOperation.CANCEL,
            DeliveryPhase.POST_SEND_UNCERTAIN,
            OrderStatus.CANCEL_FAILED,
        ),
    ],
)
def test_exchange_unavailable_mapping(
    operation: ExecutionOperation,
    delivery_phase: DeliveryPhase,
    expected_status: OrderStatus,
) -> None:
    current_status = (
        OrderStatus.SUBMITTING
        if operation is ExecutionOperation.SUBMIT
        else OrderStatus.CANCEL_PENDING
    )

    result = map_exchange_report(
        report(
            ExchangeReportType.EXCHANGE_UNAVAILABLE,
            operation=operation,
            delivery_phase=delivery_phase,
        ),
        context(current_order_status=current_status),
    )

    assert result.status is MappingResultStatus.MAPPED_ORDER_EVENT
    assert result.order_event is not None
    assert result.order_event.new_status is expected_status


def test_operation_can_come_from_mapping_context_for_timeout() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.TIMEOUT),
        context(
            current_order_status=OrderStatus.CANCEL_PENDING,
            operation=ExecutionOperation.CANCEL,
        ),
    )

    assert result.status is MappingResultStatus.MAPPED_ORDER_EVENT
    assert result.order_event is not None
    assert result.order_event.new_status is OrderStatus.CANCEL_FAILED


def test_duplicate_report_does_not_generate_order_event() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.ACK, exchange_report_id="dup-1"),
        context(known_exchange_report_ids={"dup-1"}),
    )

    assert result.status is MappingResultStatus.DUPLICATE_REPORT
    assert result.order_event is None
    assert result.error is None


def test_missing_known_ids_does_not_claim_duplicate() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.ACK, exchange_report_id="dup-1"),
        context(known_exchange_report_ids=None),
    )

    assert result.status is MappingResultStatus.MAPPED_ORDER_EVENT


def test_out_of_order_is_normal_report_with_expected_previous_status_mismatch() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.ACK),
        context(
            current_order_status=OrderStatus.CANCEL_PENDING,
            expected_previous_status=OrderStatus.SUBMITTING,
        ),
    )

    assert result.status is MappingResultStatus.MAPPED_ORDER_EVENT
    assert result.order_event is not None
    assert result.order_event.previous_status is OrderStatus.SUBMITTING
    assert result.order_event.new_status is OrderStatus.ACKED


def test_missing_previous_status_context_returns_insufficient_context() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.ACK),
        context(current_order_status=None, expected_previous_status=None),
    )

    assert result.status is MappingResultStatus.INSUFFICIENT_CONTEXT
    assert result.error is not None
    assert result.error.reason is MappingErrorReason.MISSING_EXPECTED_PREVIOUS_STATUS
    assert result.order_event is None


@pytest.mark.parametrize(
    ("exchange_report", "current_status"),
    [
        (
            report(ExchangeReportType.ACK),
            OrderStatus.ACKED,
        ),
        (
            report(ExchangeReportType.CANCELED, operation=ExecutionOperation.CANCEL),
            OrderStatus.CANCELED,
        ),
        (
            report(ExchangeReportType.FULL_FILL),
            OrderStatus.FILLED,
        ),
        (
            report(ExchangeReportType.EXPIRED),
            OrderStatus.EXPIRED,
        ),
        (
            report(ExchangeReportType.REJECTED),
            OrderStatus.REJECTED_BY_EXCHANGE,
        ),
        (
            report(
                ExchangeReportType.EXCHANGE_UNAVAILABLE,
                operation=ExecutionOperation.SUBMIT,
                delivery_phase=DeliveryPhase.PRE_SEND,
            ),
            OrderStatus.SUBMIT_FAILED,
        ),
        (
            report(ExchangeReportType.TIMEOUT, operation=ExecutionOperation.SUBMIT),
            OrderStatus.SUBMIT_TIMEOUT,
        ),
        (
            report(ExchangeReportType.CANCEL_REJECTED, operation=ExecutionOperation.CANCEL),
            OrderStatus.CANCEL_FAILED,
        ),
        (
            report(
                ExchangeReportType.EXCHANGE_UNAVAILABLE,
                operation=ExecutionOperation.CANCEL,
                delivery_phase=DeliveryPhase.PRE_SEND,
            ),
            OrderStatus.CANCEL_FAILED,
        ),
    ],
)
def test_illegal_same_status_event_is_ignored(
    exchange_report: ExchangeReport,
    current_status: OrderStatus,
) -> None:
    result = map_exchange_report(
        exchange_report,
        context(current_order_status=current_status),
    )

    assert result.status is MappingResultStatus.IGNORED_REPORT
    assert result.error is not None
    assert result.error.reason is MappingErrorReason.ILLEGAL_SAME_STATUS_EVENT
    assert result.order_event is None


@pytest.mark.parametrize(
    ("exchange_report", "target_status", "different_current_status"),
    [
        (
            report(ExchangeReportType.ACK),
            OrderStatus.ACKED,
            None,
        ),
        (
            report(ExchangeReportType.CANCELED, operation=ExecutionOperation.CANCEL),
            OrderStatus.CANCELED,
            None,
        ),
        (
            report(ExchangeReportType.FULL_FILL),
            OrderStatus.FILLED,
            None,
        ),
        (
            report(ExchangeReportType.EXPIRED),
            OrderStatus.EXPIRED,
            None,
        ),
        (
            report(ExchangeReportType.REJECTED),
            OrderStatus.REJECTED_BY_EXCHANGE,
            None,
        ),
        (
            report(
                ExchangeReportType.EXCHANGE_UNAVAILABLE,
                operation=ExecutionOperation.SUBMIT,
                delivery_phase=DeliveryPhase.PRE_SEND,
            ),
            OrderStatus.SUBMIT_FAILED,
            None,
        ),
        (
            report(ExchangeReportType.TIMEOUT, operation=ExecutionOperation.SUBMIT),
            OrderStatus.SUBMIT_TIMEOUT,
            OrderStatus.SUBMITTING,
        ),
        (
            report(ExchangeReportType.CANCEL_REJECTED, operation=ExecutionOperation.CANCEL),
            OrderStatus.CANCEL_FAILED,
            OrderStatus.CANCEL_PENDING,
        ),
    ],
)
def test_expected_previous_status_same_status_event_is_ignored(
    exchange_report: ExchangeReport,
    target_status: OrderStatus,
    different_current_status: OrderStatus | None,
) -> None:
    result = map_exchange_report(
        exchange_report,
        context(
            current_order_status=different_current_status,
            expected_previous_status=target_status,
        ),
    )

    assert result.status is MappingResultStatus.IGNORED_REPORT
    assert result.error is not None
    assert result.error.reason is MappingErrorReason.ILLEGAL_SAME_STATUS_EVENT
    assert result.order_event is None


def test_same_status_guard_requires_current_order_status() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.TIMEOUT, operation=ExecutionOperation.SUBMIT),
        context(current_order_status=None, expected_previous_status=OrderStatus.SUBMITTING),
    )

    assert result.status is MappingResultStatus.INSUFFICIENT_CONTEXT
    assert result.error is not None
    assert result.error.reason is MappingErrorReason.MISSING_CURRENT_ORDER_STATUS


def test_partially_filled_same_status_remains_mappable() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.PARTIAL_FILL),
        context(current_order_status=OrderStatus.PARTIALLY_FILLED),
    )

    assert result.status is MappingResultStatus.MAPPED_ORDER_EVENT
    assert result.order_event is not None
    assert result.order_event.previous_status is OrderStatus.PARTIALLY_FILLED
    assert result.order_event.new_status is OrderStatus.PARTIALLY_FILLED


def test_expected_previous_partially_filled_same_status_remains_mappable() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.PARTIAL_FILL),
        context(
            current_order_status=OrderStatus.ACKED,
            expected_previous_status=OrderStatus.PARTIALLY_FILLED,
        ),
    )

    assert result.status is MappingResultStatus.MAPPED_ORDER_EVENT
    assert result.order_event is not None
    assert result.order_event.previous_status is OrderStatus.PARTIALLY_FILLED
    assert result.order_event.new_status is OrderStatus.PARTIALLY_FILLED


@pytest.mark.parametrize(
    "exchange_report",
    [
        report(ExchangeReportType.PARTIAL_FILL),
        report(ExchangeReportType.FULL_FILL),
    ],
)
def test_fill_status_only_can_be_disabled(exchange_report: ExchangeReport) -> None:
    result = map_exchange_report(
        exchange_report,
        context(current_order_status=OrderStatus.ACKED, allow_status_only_fill=False),
    )

    assert result.status is MappingResultStatus.DOMAIN_FIELD_UNSUPPORTED
    assert result.error is not None
    assert result.error.reason is MappingErrorReason.DOMAIN_FIELD_UNSUPPORTED
    assert result.order_event is None


@pytest.mark.parametrize(
    ("exchange_report", "mapping_context"),
    [
        (
            report(
                ExchangeReportType.TIMEOUT,
                operation=None,
                raw_payload={"operation": "SUBMIT"},
            ),
            context(),
        ),
        (
            report(
                ExchangeReportType.ACK,
                exchange_report_id=None,
                raw_payload={"exchange_report_id": "report-raw"},
            ),
            context(),
        ),
        (
            report(
                ExchangeReportType.ACK,
                order_id=None,
                raw_payload={"order_id": "order-raw"},
            ),
            context(),
        ),
        (
            report(
                ExchangeReportType.PARTIAL_FILL,
                raw_payload={"fill_price": "10.1"},
            ),
            context(current_order_status=OrderStatus.ACKED),
        ),
    ],
)
def test_raw_payload_cannot_supply_source_of_truth(
    exchange_report: ExchangeReport,
    mapping_context: MappingContext,
) -> None:
    result = map_exchange_report(exchange_report, mapping_context)

    assert result.status in {
        MappingResultStatus.MAPPING_ERROR,
        MappingResultStatus.DOMAIN_FIELD_UNSUPPORTED,
    }
    assert result.error is not None
    assert result.error.reason is MappingErrorReason.RAW_PAYLOAD_ONLY_FACT_FORBIDDEN
    assert result.order_event is None


def test_unknown_report_waits_for_future_oms_unknown_entry() -> None:
    result = map_exchange_report(
        report(ExchangeReportType.UNKNOWN_REPORT),
        context(),
    )

    assert result.status is MappingResultStatus.MAPPING_ERROR
    assert result.error is not None
    assert result.error.reason is MappingErrorReason.UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY
    assert result.order_event is None


def test_mapper_does_not_import_forbidden_runtime_boundaries() -> None:
    module_root = Path("src/futures_mvp/modules/execution")
    forbidden_modules = {
        "futures_mvp.modules.oms",
        "futures_mvp.modules.risk",
        "futures_mvp.db",
        "futures_mvp.interfaces.repositories",
        "sqlalchemy",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "redis",
        "subprocess",
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
    }

    for path in module_root.rglob("*.py"):
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
