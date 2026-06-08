from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from futures_mvp.domain.enums import ExecutionReportStatus, OrderStatus
from futures_mvp.domain.models import OrderEvent, OrderEventCandidate


def _decimal_value(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _datetime_value(value: datetime) -> str:
    if value.tzinfo is not None and value.utcoffset() is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.isoformat()


def _execution_status_value(value: ExecutionReportStatus | None) -> str | None:
    if value is None:
        return None
    return value.value


def canonical_event_id_payload(candidate: OrderEventCandidate) -> dict[str, Any]:
    return {
        "cumulative_filled_qty": _decimal_value(candidate.cumulative_filled_qty),
        "execution_status": _execution_status_value(candidate.execution_status),
        "order_id": candidate.order_id,
        "report_id": candidate.normalized_report_id,
        "report_ts": _datetime_value(candidate.occurred_at),
    }


def canonical_order_event_payload(event: OrderEvent) -> dict[str, Any] | None:
    if (
        event.execution_status is None
        or event.report_id is None
        or event.report_ts is None
        or event.cumulative_filled_qty is None
    ):
        return None
    return {
        "cumulative_filled_qty": _decimal_value(event.cumulative_filled_qty),
        "event_id": event.external_event_id,
        "execution_status": event.execution_status.value,
        "fill_price": _decimal_value(event.fill_price),
        "filled_qty": _decimal_value(event.filled_qty),
        "new_status": event.new_status.value,
        "order_id": event.order_id,
        "previous_status": _order_status_value(event.previous_status),
        "report_id": event.report_id,
        "report_ts": _datetime_value(event.report_ts),
    }


def _order_status_value(value: OrderStatus | None) -> str | None:
    if value is None:
        return None
    return value.value
