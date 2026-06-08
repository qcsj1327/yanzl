from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from futures_mvp.domain.enums import (
    ExecutionReportNormalizeResultStatus,
    ExecutionReportStatus,
    ExecutionTarget,
)
from futures_mvp.domain.errors import DecimalRequiredError
from futures_mvp.domain.models import (
    ExecutionReportNormalizeResult,
    NormalizedExecutionReport,
    RawExecutionReport,
)
from futures_mvp.modules.execution_reports import (
    build_normalized_report_id,
    build_source_report_hash,
    canonical_raw_execution_report_payload,
)

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


def _raw(**updates: object) -> RawExecutionReport:
    values = {
        "raw_report_id": "raw-1",
        "adapter_name": "mock",
        "execution_target": ExecutionTarget.MOCK,
        "command_id": "command-1",
        "order_id": "order-1",
        "client_order_id": "client-1",
        "adapter_order_ref": "adapter-order-1",
        "exchange_order_id": "exchange-order-1",
        "exchange_trade_id": None,
        "fill_id": None,
        "report_type": "partial_fill",
        "filled_qty": Decimal("1"),
        "fill_price": Decimal("500"),
        "cumulative_filled_qty": Decimal("1"),
        "remaining_qty": Decimal("1"),
        "fee_amount": None,
        "fee_currency": None,
        "fee_source": None,
        "report_ts": NOW,
        "received_at": NOW + timedelta(seconds=1),
        "raw_payload": {"diagnostic": "only"},
    }
    values.update(updates)
    return RawExecutionReport(**values)


def _normalized(**updates: object) -> NormalizedExecutionReport:
    raw = _raw()
    source_hash = build_source_report_hash(raw)
    values = {
        "report_id": build_normalized_report_id(raw, source_hash),
        "raw_report_id": raw.raw_report_id,
        "adapter_name": raw.adapter_name,
        "execution_target": raw.execution_target,
        "command_id": raw.command_id,
        "order_id": raw.order_id,
        "client_order_id": raw.client_order_id,
        "adapter_order_ref": raw.adapter_order_ref,
        "exchange_order_id": raw.exchange_order_id,
        "exchange_trade_id": raw.exchange_trade_id,
        "fill_id": raw.fill_id,
        "execution_status": ExecutionReportStatus.PARTIALLY_FILLED,
        "filled_qty": raw.filled_qty,
        "fill_price": raw.fill_price,
        "cumulative_filled_qty": raw.cumulative_filled_qty,
        "remaining_qty": raw.remaining_qty,
        "fee_amount": raw.fee_amount,
        "fee_currency": raw.fee_currency,
        "fee_source": raw.fee_source,
        "report_ts": raw.report_ts,
        "normalized_at": NOW + timedelta(seconds=2),
        "reason": None,
        "source_report_hash": source_hash,
        "raw_payload": raw.raw_payload,
    }
    values.update(updates)
    return NormalizedExecutionReport(**values)


def test_raw_execution_report_decimal_validation_and_no_float() -> None:
    raw = _raw()

    assert raw.filled_qty == Decimal("1")

    with pytest.raises(DecimalRequiredError):
        _raw(filled_qty=1.0)
    with pytest.raises(ValidationError):
        _raw(filled_qty=Decimal("-1"))
    with pytest.raises(ValidationError):
        _raw(report_type="filled", fill_price=None)
    with pytest.raises(ValidationError):
        _raw(report_ts="2026-06-08T09:00:00Z")


def test_normalized_execution_report_validation() -> None:
    report = _normalized()

    assert report.execution_status is ExecutionReportStatus.PARTIALLY_FILLED
    assert "trade" not in NormalizedExecutionReport.model_fields

    with pytest.raises(DecimalRequiredError):
        _normalized(fill_price=1.0)
    with pytest.raises(ValidationError):
        _normalized(
            execution_status=ExecutionReportStatus.FILLED,
            fill_price=None,
        )


def test_execution_report_stage_l3_typed_trade_inputs_and_fee_semantics() -> None:
    raw = _raw(
        exchange_trade_id="exchange-trade-1",
        fill_id="fill-1",
        fee_amount=Decimal("0"),
        fee_currency="CNY",
        fee_source="EXCHANGE_REPORT",
    )
    normalized = _normalized(
        exchange_trade_id=raw.exchange_trade_id,
        fill_id=raw.fill_id,
        fee_amount=raw.fee_amount,
        fee_currency=raw.fee_currency,
        fee_source=raw.fee_source,
    )

    assert raw.exchange_trade_id == "exchange-trade-1"
    assert normalized.fill_id == "fill-1"
    assert normalized.fee_amount == Decimal("0")

    with pytest.raises(ValidationError):
        _raw(fee_amount=Decimal("1"), fee_currency="CNY", fee_source=None)
    with pytest.raises(ValidationError):
        _normalized(fee_amount=Decimal("1"), fee_currency=None, fee_source="EXCHANGE_REPORT")


def test_source_report_hash_is_deterministic_and_excludes_diagnostics() -> None:
    raw = _raw()
    same = _raw(
        raw_payload={"diagnostic": "changed"},
        received_at=NOW + timedelta(minutes=10),
    )
    changed = _raw(cumulative_filled_qty=Decimal("2"))

    assert canonical_raw_execution_report_payload(raw) == canonical_raw_execution_report_payload(
        same
    )
    assert build_source_report_hash(raw) == build_source_report_hash(same)
    assert build_source_report_hash(raw) != build_source_report_hash(changed)


def test_normalized_report_id_is_deterministic_from_source_hash_and_lineage() -> None:
    raw = _raw()
    source_hash = build_source_report_hash(raw)

    assert build_normalized_report_id(raw, source_hash) == build_normalized_report_id(
        raw,
        source_hash,
    )
    assert build_normalized_report_id(raw, source_hash).startswith("er_")
    assert build_normalized_report_id(raw, source_hash) != build_normalized_report_id(
        raw,
        "different",
    )


def test_normalize_result_requires_report_for_success_statuses() -> None:
    with pytest.raises(ValidationError):
        ExecutionReportNormalizeResult(status=ExecutionReportNormalizeResultStatus.NORMALIZED)
    with pytest.raises(ValidationError):
        ExecutionReportNormalizeResult(status=ExecutionReportNormalizeResultStatus.DUPLICATE)
