from datetime import UTC
from decimal import Decimal
from typing import Any

from futures_mvp.domain.enums import EventSource, ExecutionReportStatus, OrderStatus
from futures_mvp.domain.models import (
    NormalizedExecutionReport,
    OrderEvent,
    OrderEventCandidate,
    OrderState,
)
from futures_mvp.modules.oms_event_application.canonical import _datetime_value
from futures_mvp.modules.oms_event_application.ids import build_oms_order_event_id

_MAPPABLE_STATUSES = {
    ExecutionReportStatus.ACKED: OrderStatus.ACKED,
    ExecutionReportStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
    ExecutionReportStatus.FILLED: OrderStatus.FILLED,
    ExecutionReportStatus.REJECTED: OrderStatus.REJECTED_BY_EXCHANGE,
    ExecutionReportStatus.CANCELED: OrderStatus.CANCELED,
}

_CANDIDATE_STATUS_BY_EXECUTION_STATUS = {
    **_MAPPABLE_STATUSES,
    ExecutionReportStatus.SUBMITTED: OrderStatus.SUBMITTED,
    ExecutionReportStatus.ERROR: OrderStatus.UNKNOWN,
}


def build_application_candidate(
    normalized_report: NormalizedExecutionReport,
) -> OrderEventCandidate:
    return OrderEventCandidate(
        normalized_report_id=normalized_report.report_id,
        order_id=normalized_report.order_id,
        new_status=_CANDIDATE_STATUS_BY_EXECUTION_STATUS[normalized_report.execution_status],
        event_source=EventSource.EXECUTION_REPORT_NORMALIZER,
        external_event_id=normalized_report.report_id,
        occurred_at=normalized_report.report_ts,
        execution_status=normalized_report.execution_status,
        command_id=normalized_report.command_id,
        client_order_id=normalized_report.client_order_id,
        adapter_order_ref=normalized_report.adapter_order_ref,
        exchange_order_id=normalized_report.exchange_order_id,
        filled_qty=normalized_report.filled_qty,
        fill_price=normalized_report.fill_price,
        cumulative_filled_qty=normalized_report.cumulative_filled_qty,
        raw_payload={
            "normalized_report_id": normalized_report.report_id,
            "source_report_hash": normalized_report.source_report_hash,
        },
    )


def map_candidate_to_order_event(
    candidate: OrderEventCandidate,
    current_order_state: OrderState,
) -> OrderEvent:
    if candidate.execution_status is None:
        raise ValueError("execution_status is required")
    new_status = _MAPPABLE_STATUSES.get(candidate.execution_status)
    if new_status is None:
        raise ValueError(f"{candidate.execution_status.value} has no OMS event")
    event_id = build_oms_order_event_id(candidate)
    return OrderEvent(
        order_id=candidate.order_id,
        previous_status=current_order_state.status,
        new_status=new_status,
        event_source=EventSource.EXECUTION_REPORT_NORMALIZER,
        external_event_id=event_id,
        execution_status=candidate.execution_status,
        report_id=candidate.normalized_report_id,
        report_ts=candidate.occurred_at,
        filled_qty=candidate.filled_qty,
        fill_price=candidate.fill_price,
        cumulative_filled_qty=candidate.cumulative_filled_qty,
        raw_payload=_event_metadata(candidate, event_id),
        occurred_at=candidate.occurred_at,
    )


def candidate_no_event_reason(candidate: OrderEventCandidate) -> tuple[str, str] | None:
    if candidate.execution_status is ExecutionReportStatus.SUBMITTED:
        return ("NO_OP", "submitted_report_no_oms_event")
    if candidate.execution_status is ExecutionReportStatus.ERROR:
        return ("REJECTED_NO_EVENT", "error_report_no_oms_event")
    return None


def _event_metadata(candidate: OrderEventCandidate, event_id: str) -> dict[str, Any]:
    return {
        "adapter_order_ref": candidate.adapter_order_ref,
        "client_order_id": candidate.client_order_id,
        "command_id": candidate.command_id,
        "cumulative_filled_qty": _decimal_value(candidate.cumulative_filled_qty),
        "event_id": event_id,
        "exchange_order_id": candidate.exchange_order_id,
        "execution_status": candidate.execution_status.value
        if candidate.execution_status is not None
        else None,
        "fill_price": _decimal_value(candidate.fill_price),
        "filled_qty": _decimal_value(candidate.filled_qty),
        "normalized_report_id": candidate.normalized_report_id,
        "report_id": candidate.normalized_report_id,
        "report_ts": _datetime_value(candidate.occurred_at.astimezone(UTC))
        if candidate.occurred_at.tzinfo is not None
        else _datetime_value(candidate.occurred_at),
    }


def _decimal_value(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")
