from futures_mvp.domain.enums import ExecutionReportStatus, OrderStatus
from futures_mvp.domain.models import NormalizedExecutionReport, OrderEventCandidate

_STATUS_BY_REPORT_TYPE = {
    "submitted": ExecutionReportStatus.SUBMITTED,
    "accepted": ExecutionReportStatus.ACKED,
    "acked": ExecutionReportStatus.ACKED,
    "partial_fill": ExecutionReportStatus.PARTIALLY_FILLED,
    "partially_filled": ExecutionReportStatus.PARTIALLY_FILLED,
    "full_fill": ExecutionReportStatus.FILLED,
    "filled": ExecutionReportStatus.FILLED,
    "rejected": ExecutionReportStatus.REJECTED,
    "canceled": ExecutionReportStatus.CANCELED,
    "cancelled": ExecutionReportStatus.CANCELED,
    "unknown": ExecutionReportStatus.ERROR,
    "error": ExecutionReportStatus.ERROR,
}

_ORDER_STATUS_BY_EXECUTION_STATUS = {
    ExecutionReportStatus.ACKED: OrderStatus.ACKED,
    ExecutionReportStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
    ExecutionReportStatus.FILLED: OrderStatus.FILLED,
    ExecutionReportStatus.REJECTED: OrderStatus.REJECTED_BY_EXCHANGE,
    ExecutionReportStatus.CANCELED: OrderStatus.CANCELED,
}


def map_report_type_to_execution_status(report_type: str) -> ExecutionReportStatus:
    return _STATUS_BY_REPORT_TYPE.get(report_type.lower(), ExecutionReportStatus.ERROR)


def build_order_event_candidate(
    normalized_report: NormalizedExecutionReport,
) -> OrderEventCandidate | None:
    new_status = _ORDER_STATUS_BY_EXECUTION_STATUS.get(normalized_report.execution_status)
    if new_status is None:
        return None
    return OrderEventCandidate(
        normalized_report_id=normalized_report.report_id,
        order_id=normalized_report.order_id,
        new_status=new_status,
        external_event_id=normalized_report.report_id,
        occurred_at=normalized_report.report_ts,
        raw_payload={
            "normalized_report_id": normalized_report.report_id,
            "source_report_hash": normalized_report.source_report_hash,
        },
    )
