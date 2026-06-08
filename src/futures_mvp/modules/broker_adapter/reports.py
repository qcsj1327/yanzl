from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from futures_mvp.domain.enums import ExecutionTarget
from futures_mvp.domain.models import RawExecutionReport, stable_json_sha256


class _Quarantine(Protocol):
    def append(self, evidence: object, *, reason: str) -> object: ...


class BrokerCallbackTranslationStatus(StrEnum):
    TRANSLATED = "TRANSLATED"
    QUARANTINED_UNRESOLVED_LINEAGE = "QUARANTINED_UNRESOLVED_LINEAGE"


@dataclass(frozen=True)
class BrokerCallbackEvidence:
    adapter_name: str
    execution_target: ExecutionTarget
    command_id: str | None
    order_id: str | None
    client_order_id: str | None
    adapter_order_ref: str | None
    report_type: str
    filled_qty: Decimal
    cumulative_filled_qty: Decimal
    remaining_qty: Decimal
    report_ts: datetime
    received_at: datetime
    exchange_order_id: str | None = None
    exchange_trade_id: str | None = None
    fill_id: str | None = None
    fill_price: Decimal | None = None
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    fee_source: str | None = None
    raw_payload: dict[str, Any] | None = None
    raw_report_id: str | None = None


@dataclass(frozen=True)
class BrokerCallbackTranslationResult:
    status: BrokerCallbackTranslationStatus
    raw_report: RawExecutionReport | None = None
    reason: str | None = None


def translate_callback_to_raw_execution_report(
    evidence: BrokerCallbackEvidence,
    *,
    quarantine: _Quarantine | None = None,
) -> BrokerCallbackTranslationResult:
    missing_reason = _missing_lineage_reason(evidence)
    if missing_reason is not None:
        if quarantine is not None:
            quarantine.append(evidence, reason=missing_reason)
        return BrokerCallbackTranslationResult(
            status=BrokerCallbackTranslationStatus.QUARANTINED_UNRESOLVED_LINEAGE,
            reason=missing_reason,
        )

    raw_report = RawExecutionReport(
        raw_report_id=evidence.raw_report_id or _build_mock_raw_report_id(evidence),
        adapter_name=evidence.adapter_name,
        execution_target=evidence.execution_target,
        command_id=evidence.command_id or "",
        order_id=evidence.order_id or "",
        client_order_id=evidence.client_order_id or "",
        adapter_order_ref=evidence.adapter_order_ref or "",
        exchange_order_id=evidence.exchange_order_id,
        exchange_trade_id=evidence.exchange_trade_id,
        fill_id=evidence.fill_id,
        report_type=evidence.report_type,
        filled_qty=evidence.filled_qty,
        fill_price=evidence.fill_price,
        cumulative_filled_qty=evidence.cumulative_filled_qty,
        remaining_qty=evidence.remaining_qty,
        fee_amount=evidence.fee_amount,
        fee_currency=evidence.fee_currency,
        fee_source=evidence.fee_source,
        report_ts=evidence.report_ts,
        received_at=evidence.received_at,
        raw_payload=evidence.raw_payload,
    )
    return BrokerCallbackTranslationResult(
        status=BrokerCallbackTranslationStatus.TRANSLATED,
        raw_report=raw_report,
    )


def _missing_lineage_reason(evidence: BrokerCallbackEvidence) -> str | None:
    required = {
        "command_id": evidence.command_id,
        "order_id": evidence.order_id,
        "client_order_id": evidence.client_order_id,
        "adapter_order_ref": evidence.adapter_order_ref,
    }
    for field_name, value in required.items():
        if value is None or value == "":
            return f"{field_name} is required"
    if evidence.raw_report_id in {None, ""} and not _can_build_mock_raw_report_id(evidence):
        return "raw_report_id is required"
    return None


def _can_build_mock_raw_report_id(evidence: BrokerCallbackEvidence) -> bool:
    return evidence.execution_target is ExecutionTarget.MOCK


def _build_mock_raw_report_id(evidence: BrokerCallbackEvidence) -> str:
    payload = {
        "adapter_name": evidence.adapter_name,
        "adapter_order_ref": evidence.adapter_order_ref,
        "command_id": evidence.command_id,
        "cumulative_filled_qty": _decimal_value(evidence.cumulative_filled_qty),
        "execution_target": evidence.execution_target.value,
        "exchange_order_id": evidence.exchange_order_id,
        "exchange_trade_id": evidence.exchange_trade_id,
        "fill_id": evidence.fill_id,
        "report_ts": evidence.report_ts.isoformat(),
        "report_type": evidence.report_type,
    }
    return "raw_broker_" + stable_json_sha256(payload)[:48]


def _decimal_value(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")
