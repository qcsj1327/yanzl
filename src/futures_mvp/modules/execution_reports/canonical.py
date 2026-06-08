from datetime import UTC, datetime
from typing import Any

from futures_mvp.domain.models import (
    NormalizedExecutionReport,
    RawExecutionReport,
    stable_json_sha256,
)


def _decimal_value(value: object) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f") if hasattr(value, "normalize") else str(value)


def _datetime_value(value: datetime) -> str:
    if value.tzinfo is not None and value.utcoffset() is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.isoformat()


def canonical_raw_execution_report_payload(raw: RawExecutionReport) -> dict[str, Any]:
    return {
        "adapter_name": raw.adapter_name,
        "adapter_order_ref": raw.adapter_order_ref,
        "client_order_id": raw.client_order_id,
        "command_id": raw.command_id,
        "cumulative_filled_qty": _decimal_value(raw.cumulative_filled_qty),
        "exchange_order_id": raw.exchange_order_id,
        "execution_target": raw.execution_target.value,
        "fill_price": _decimal_value(raw.fill_price),
        "filled_qty": _decimal_value(raw.filled_qty),
        "order_id": raw.order_id,
        "raw_report_id": raw.raw_report_id,
        "remaining_qty": _decimal_value(raw.remaining_qty),
        "report_ts": _datetime_value(raw.report_ts),
        "report_type": raw.report_type,
    }


def build_source_report_hash(raw: RawExecutionReport) -> str:
    return stable_json_sha256(canonical_raw_execution_report_payload(raw))


def canonical_normalized_execution_report_payload(
    report: NormalizedExecutionReport,
) -> dict[str, Any]:
    return {
        "adapter_name": report.adapter_name,
        "adapter_order_ref": report.adapter_order_ref,
        "client_order_id": report.client_order_id,
        "command_id": report.command_id,
        "cumulative_filled_qty": _decimal_value(report.cumulative_filled_qty),
        "exchange_order_id": report.exchange_order_id,
        "execution_status": report.execution_status.value,
        "execution_target": report.execution_target.value,
        "fill_price": _decimal_value(report.fill_price),
        "filled_qty": _decimal_value(report.filled_qty),
        "order_id": report.order_id,
        "raw_report_id": report.raw_report_id,
        "reason": report.reason,
        "remaining_qty": _decimal_value(report.remaining_qty),
        "report_id": report.report_id,
        "report_ts": _datetime_value(report.report_ts),
        "source_report_hash": report.source_report_hash,
    }
