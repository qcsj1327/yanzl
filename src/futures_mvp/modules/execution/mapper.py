from collections.abc import Mapping

from futures_mvp.domain.enums import EventSource, OrderStatus
from futures_mvp.domain.models import OrderEvent
from futures_mvp.modules.execution.models import (
    DeliveryPhase,
    ExchangeReport,
    ExchangeReportType,
    ExecutionOperation,
    MappingContext,
    MappingError,
    MappingErrorReason,
    MappingResult,
    MappingResultStatus,
)

_RAW_FACT_KEYS = frozenset(
    {
        "report_type",
        "order_status",
        "status",
        "previous_status",
        "exchange_report_id",
        "operation",
        "delivery_phase",
        "occurred_at",
        "event_source",
        "fill_quantity",
        "fill_price",
        "trade_id",
        "fill_id",
        "quantity",
        "price",
        "exchange_trade_id",
    }
)

_FILL_FACT_KEYS = frozenset(
    {
        "fill_quantity",
        "fill_price",
        "trade_id",
        "fill_id",
        "quantity",
        "price",
        "exchange_trade_id",
    }
)

_SUBMIT_REPORT_TYPES = frozenset(
    {
        ExchangeReportType.ACK,
        ExchangeReportType.REJECTED,
    }
)

_CANCEL_REPORT_TYPES = frozenset(
    {
        ExchangeReportType.CANCELED,
        ExchangeReportType.CANCEL_REJECTED,
    }
)

_FILL_REPORT_TYPES = frozenset(
    {
        ExchangeReportType.PARTIAL_FILL,
        ExchangeReportType.FULL_FILL,
    }
)

_CONTEXT_REQUIRED_SAME_STATUS_TARGETS = frozenset(
    {
        OrderStatus.SUBMIT_TIMEOUT,
        OrderStatus.CANCEL_FAILED,
    }
)

_SAME_STATUS_ALLOWED_TARGETS = frozenset({OrderStatus.PARTIALLY_FILLED})


def map_exchange_report(report: ExchangeReport, context: MappingContext) -> MappingResult:
    raw_payload = report.raw_payload or {}

    report_type = _coerce_report_type(report.report_type)
    if report_type is None:
        return _mapping_error(
            _missing_reason(raw_payload, "report_type", MappingErrorReason.MISSING_REPORT_TYPE),
            "ExchangeReport.report_type is required.",
        )
    if isinstance(report_type, MappingErrorReason):
        return _mapping_error(report_type, "ExchangeReport.report_type is unsupported.")

    if report.exchange_report_id is None:
        return _mapping_error(
            _missing_reason(
                raw_payload,
                "exchange_report_id",
                MappingErrorReason.MISSING_EXCHANGE_REPORT_ID,
            ),
            "ExchangeReport.exchange_report_id is required.",
        )

    if report.occurred_at is None:
        return _mapping_error(
            _missing_reason(raw_payload, "occurred_at", MappingErrorReason.MISSING_OCCURRED_AT),
            "ExchangeReport.occurred_at is required.",
        )

    event_source = _coerce_event_source(report.event_source)
    if event_source is None:
        return _mapping_error(
            _missing_reason(raw_payload, "event_source", MappingErrorReason.MISSING_EVENT_SOURCE),
            "ExchangeReport.event_source is required.",
        )

    if report.order_id is None and report.client_order_id is None:
        return _mapping_error(
            _missing_order_identity_reason(raw_payload),
            "ExchangeReport requires order_id or client_order_id.",
        )

    if _is_duplicate(report.exchange_report_id, context):
        return MappingResult(status=MappingResultStatus.DUPLICATE_REPORT)

    if report_type is ExchangeReportType.UNKNOWN_REPORT:
        return _mapping_error(
            MappingErrorReason.UNKNOWN_REPORT_REQUIRES_OMS_UNKNOWN_ENTRY,
            "UNKNOWN_REPORT waits for a future OMS public UNKNOWN entry.",
        )

    operation = _resolve_operation(report, context)
    if isinstance(operation, MappingErrorReason):
        return _mapping_error(operation, "ExchangeReport.operation is invalid or missing.")

    delivery_phase = _resolve_delivery_phase(report)
    if isinstance(delivery_phase, MappingErrorReason):
        return _mapping_error(
            delivery_phase,
            "ExchangeReport.delivery_phase is invalid or missing.",
        )

    mismatch_reason = _operation_report_type_mismatch(report_type, operation)
    if mismatch_reason is not None:
        return _mapping_error(mismatch_reason, "operation does not match report_type semantics.")

    if report.order_id is None:
        return _insufficient_context(
            MappingErrorReason.MISSING_ORDER_IDENTITY,
            "client_order_id must be resolved to order_id before creating OrderEvent.",
        )

    if _raw_payload_has_forbidden_fill_facts(report_type, raw_payload):
        return _domain_field_unsupported(
            MappingErrorReason.RAW_PAYLOAD_ONLY_FACT_FORBIDDEN,
            "fill facts cannot be carried only by raw_payload.",
        )

    if report_type in _FILL_REPORT_TYPES and not context.allow_status_only_fill:
        return _domain_field_unsupported(
            MappingErrorReason.DOMAIN_FIELD_UNSUPPORTED,
            "fill facts require a future Domain/interface/schema migration.",
        )

    target_status = _target_status(report_type, operation, delivery_phase)
    if isinstance(target_status, MappingErrorReason):
        return _mapping_error(target_status, "ExchangeReport cannot be mapped to OrderStatus.")

    if (
        target_status in _CONTEXT_REQUIRED_SAME_STATUS_TARGETS
        and context.current_order_status is None
    ):
        return _insufficient_context(
            MappingErrorReason.MISSING_CURRENT_ORDER_STATUS,
            "current_order_status is required to avoid illegal same-status events.",
        )

    if (
        context.current_order_status == target_status
        and target_status not in _SAME_STATUS_ALLOWED_TARGETS
    ):
        return MappingResult(
            status=MappingResultStatus.IGNORED_REPORT,
            error=MappingError(
                reason=MappingErrorReason.ILLEGAL_SAME_STATUS_EVENT,
                message="mapper must not create illegal same-status OrderEvent.",
            ),
        )

    previous_status = context.expected_previous_status or context.current_order_status
    if previous_status is None:
        return _insufficient_context(
            MappingErrorReason.MISSING_EXPECTED_PREVIOUS_STATUS,
            "expected_previous_status or current_order_status is required.",
        )

    event = OrderEvent(
        order_id=report.order_id,
        previous_status=previous_status,
        new_status=target_status,
        event_source=event_source,
        external_event_id=report.exchange_report_id,
        raw_payload=dict(raw_payload),
        occurred_at=report.occurred_at,
    )
    return MappingResult(status=MappingResultStatus.MAPPED_ORDER_EVENT, order_event=event)


def _coerce_report_type(
    value: ExchangeReportType | str | None,
) -> ExchangeReportType | MappingErrorReason | None:
    if value is None:
        return None
    if isinstance(value, ExchangeReportType):
        return value
    try:
        return ExchangeReportType(value)
    except ValueError:
        return MappingErrorReason.UNSUPPORTED_REPORT_TYPE


def _coerce_operation(
    value: ExecutionOperation | str | None,
) -> ExecutionOperation | MappingErrorReason | None:
    if value is None:
        return None
    if isinstance(value, ExecutionOperation):
        return value
    try:
        return ExecutionOperation(value)
    except ValueError:
        return MappingErrorReason.UNSUPPORTED_OPERATION


def _coerce_delivery_phase(
    value: DeliveryPhase | str | None,
) -> DeliveryPhase | MappingErrorReason | None:
    if value is None:
        return None
    if isinstance(value, DeliveryPhase):
        return value
    try:
        return DeliveryPhase(value)
    except ValueError:
        return MappingErrorReason.UNSUPPORTED_DELIVERY_PHASE


def _coerce_event_source(value: EventSource | str | None) -> EventSource | None:
    if value is None:
        return None
    if isinstance(value, EventSource):
        return value
    try:
        return EventSource(value)
    except ValueError:
        return None


def _resolve_operation(
    report: ExchangeReport,
    context: MappingContext,
) -> ExecutionOperation | MappingErrorReason | None:
    report_operation = _coerce_operation(report.operation)
    if isinstance(report_operation, MappingErrorReason):
        return report_operation

    context_operation = _coerce_operation(context.operation)
    if isinstance(context_operation, MappingErrorReason):
        return context_operation

    operation = report_operation or context_operation
    report_type = _coerce_report_type(report.report_type)
    if report_type in {
        ExchangeReportType.TIMEOUT,
        ExchangeReportType.EXCHANGE_UNAVAILABLE,
    } and operation is None:
        return _missing_reason(
            report.raw_payload or {},
            "operation",
            MappingErrorReason.MISSING_OPERATION,
        )

    return operation


def _resolve_delivery_phase(report: ExchangeReport) -> DeliveryPhase | MappingErrorReason | None:
    delivery_phase = _coerce_delivery_phase(report.delivery_phase)
    if isinstance(delivery_phase, MappingErrorReason):
        return delivery_phase

    report_type = _coerce_report_type(report.report_type)
    if report_type is ExchangeReportType.EXCHANGE_UNAVAILABLE and delivery_phase is None:
        return _missing_reason(
            report.raw_payload or {},
            "delivery_phase",
            MappingErrorReason.MISSING_DELIVERY_PHASE,
        )
    return delivery_phase


def _operation_report_type_mismatch(
    report_type: ExchangeReportType,
    operation: ExecutionOperation | None,
) -> MappingErrorReason | None:
    if operation is None:
        return None
    if report_type in _SUBMIT_REPORT_TYPES and operation is not ExecutionOperation.SUBMIT:
        return MappingErrorReason.OPERATION_REPORT_TYPE_MISMATCH
    if report_type in _CANCEL_REPORT_TYPES and operation is not ExecutionOperation.CANCEL:
        return MappingErrorReason.OPERATION_REPORT_TYPE_MISMATCH
    return None


def _target_status(
    report_type: ExchangeReportType,
    operation: ExecutionOperation | None,
    delivery_phase: DeliveryPhase | None,
) -> OrderStatus | MappingErrorReason:
    if report_type is ExchangeReportType.ACK:
        return OrderStatus.ACKED
    if report_type is ExchangeReportType.REJECTED:
        return OrderStatus.REJECTED_BY_EXCHANGE
    if report_type is ExchangeReportType.PARTIAL_FILL:
        return OrderStatus.PARTIALLY_FILLED
    if report_type is ExchangeReportType.FULL_FILL:
        return OrderStatus.FILLED
    if report_type is ExchangeReportType.CANCELED:
        return OrderStatus.CANCELED
    if report_type is ExchangeReportType.CANCEL_REJECTED:
        return OrderStatus.CANCEL_FAILED
    if report_type is ExchangeReportType.EXPIRED:
        return OrderStatus.EXPIRED
    if report_type is ExchangeReportType.TIMEOUT:
        return _timeout_status(operation)
    if report_type is ExchangeReportType.EXCHANGE_UNAVAILABLE:
        return _exchange_unavailable_status(operation, delivery_phase)
    return MappingErrorReason.UNSUPPORTED_REPORT_TYPE


def _timeout_status(operation: ExecutionOperation | None) -> OrderStatus | MappingErrorReason:
    if operation is ExecutionOperation.SUBMIT:
        return OrderStatus.SUBMIT_TIMEOUT
    if operation is ExecutionOperation.CANCEL:
        return OrderStatus.CANCEL_FAILED
    return MappingErrorReason.MISSING_OPERATION


def _exchange_unavailable_status(
    operation: ExecutionOperation | None,
    delivery_phase: DeliveryPhase | None,
) -> OrderStatus | MappingErrorReason:
    if operation is None:
        return MappingErrorReason.MISSING_OPERATION
    if delivery_phase is None:
        return MappingErrorReason.MISSING_DELIVERY_PHASE
    if operation is ExecutionOperation.SUBMIT and delivery_phase is DeliveryPhase.PRE_SEND:
        return OrderStatus.SUBMIT_FAILED
    if (
        operation is ExecutionOperation.SUBMIT
        and delivery_phase is DeliveryPhase.POST_SEND_UNCERTAIN
    ):
        return OrderStatus.SUBMIT_TIMEOUT
    if operation is ExecutionOperation.CANCEL:
        return OrderStatus.CANCEL_FAILED
    return MappingErrorReason.UNSUPPORTED_OPERATION


def _is_duplicate(exchange_report_id: str, context: MappingContext) -> bool:
    known_ids = context.known_exchange_report_ids
    return known_ids is not None and exchange_report_id in known_ids


def _missing_reason(
    raw_payload: Mapping[str, object],
    key: str,
    fallback: MappingErrorReason,
) -> MappingErrorReason:
    if key in raw_payload:
        return MappingErrorReason.RAW_PAYLOAD_ONLY_FACT_FORBIDDEN
    return fallback


def _missing_order_identity_reason(raw_payload: Mapping[str, object]) -> MappingErrorReason:
    if "order_id" in raw_payload or "client_order_id" in raw_payload:
        return MappingErrorReason.RAW_PAYLOAD_ONLY_FACT_FORBIDDEN
    return MappingErrorReason.MISSING_ORDER_IDENTITY


def _raw_payload_has_forbidden_fill_facts(
    report_type: ExchangeReportType,
    raw_payload: Mapping[str, object],
) -> bool:
    return report_type in _FILL_REPORT_TYPES and bool(_FILL_FACT_KEYS.intersection(raw_payload))


def _mapping_error(reason: MappingErrorReason, message: str) -> MappingResult:
    return MappingResult(
        status=MappingResultStatus.MAPPING_ERROR,
        error=MappingError(reason=reason, message=message),
    )


def _insufficient_context(reason: MappingErrorReason, message: str) -> MappingResult:
    return MappingResult(
        status=MappingResultStatus.INSUFFICIENT_CONTEXT,
        error=MappingError(reason=reason, message=message),
    )


def _domain_field_unsupported(reason: MappingErrorReason, message: str) -> MappingResult:
    return MappingResult(
        status=MappingResultStatus.DOMAIN_FIELD_UNSUPPORTED,
        error=MappingError(reason=reason, message=message),
    )
