from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol, cast

from futures_mvp.domain.enums import ExecutionCommandResultStatus, ExecutionTarget
from futures_mvp.domain.models import (
    ExecutionCommand,
    ExecutionCommandResult,
    RawExecutionReport,
    stable_json_sha256,
)
from futures_mvp.modules.execution_evidence import SharedExecutionEvidenceBuilder
from futures_mvp.modules.sim_trading.policy import SimExecutionPolicy


class _ExecutionEvidence(Protocol):
    raw_report_id: str | None
    adapter_name: str
    execution_target: ExecutionTarget
    command_id: str | None
    order_id: str | None
    client_order_id: str | None
    adapter_order_ref: str | None
    exchange_order_id: str | None
    exchange_trade_id: str | None
    fill_id: str | None
    report_type: str
    filled_qty: Decimal
    fill_price: Decimal | None
    cumulative_filled_qty: Decimal
    remaining_qty: Decimal
    fee_amount: Decimal | None
    fee_currency: str | None
    fee_source: str | None
    report_ts: datetime
    received_at: datetime
    raw_payload: dict[str, Any] | None


class SimExecutionStatus(StrEnum):
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class SimExecutionResult:
    status: SimExecutionStatus
    command_result: ExecutionCommandResult
    raw_reports: tuple[RawExecutionReport, ...] = ()
    reason: str | None = None


class SimExecutionHarness:
    """Local controlled SIM evidence generator without gateway target enablement."""

    def __init__(
        self,
        *,
        policy: SimExecutionPolicy = SimExecutionPolicy.IMMEDIATE_FULL_FILL,
    ) -> None:
        self._policy = policy
        self._evidence_builder = SharedExecutionEvidenceBuilder(
            namespace="sim",
            adapter_name="sim_harness",
        )

    def execute(self, command: ExecutionCommand) -> SimExecutionResult:
        if command.execution_target is not ExecutionTarget.MOCK:
            command_result = ExecutionCommandResult(
                command_id=command.command_id,
                order_id=command.order_id,
                status=ExecutionCommandResultStatus.REJECTED_BY_ADAPTER,
                reason=f"unsupported execution_target: {command.execution_target.value}",
            )
            return SimExecutionResult(
                status=SimExecutionStatus.REJECTED,
                command_result=command_result,
                reason="sim harness supports ExecutionTarget.MOCK only",
            )

        command_result = _command_result_for_policy(command, self._policy)
        if self._policy is SimExecutionPolicy.PRE_SEND_TIMEOUT:
            return SimExecutionResult(
                status=SimExecutionStatus.FAILED,
                command_result=command_result,
                reason="pre_send_timeout",
            )
        if self._policy is SimExecutionPolicy.POST_SEND_UNCERTAIN:
            return SimExecutionResult(
                status=SimExecutionStatus.UNCERTAIN,
                command_result=command_result,
                reason="post_send_uncertain",
            )
        if command_result.adapter_order_ref is None:
            return SimExecutionResult(
                status=SimExecutionStatus.FAILED,
                command_result=command_result,
                reason="adapter_order_ref is required",
            )

        raw_reports = _raw_reports_for_policy(
            self._evidence_builder,
            command,
            adapter_order_ref=command_result.adapter_order_ref,
            policy=self._policy,
        )
        status = (
            SimExecutionStatus.EXECUTED
            if self._policy is SimExecutionPolicy.IMMEDIATE_FULL_FILL
            else SimExecutionStatus.REJECTED
        )
        return SimExecutionResult(
            status=status,
            command_result=command_result,
            raw_reports=raw_reports,
        )


def _command_result_for_policy(
    command: ExecutionCommand,
    policy: SimExecutionPolicy,
) -> ExecutionCommandResult:
    if policy is SimExecutionPolicy.PRE_SEND_TIMEOUT:
        return ExecutionCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=ExecutionCommandResultStatus.ERROR,
            reason="pre_send_timeout",
            adapter_order_ref=None,
            submitted_at=None,
            raw_payload=None,
        )
    adapter_order_ref = _sim_adapter_order_ref(command.command_id)
    if policy is SimExecutionPolicy.POST_SEND_UNCERTAIN:
        return ExecutionCommandResult(
            command_id=command.command_id,
            order_id=command.order_id,
            status=ExecutionCommandResultStatus.ERROR,
            reason="post_send_uncertain",
            adapter_order_ref=adapter_order_ref,
            submitted_at=command.created_at,
            raw_payload=None,
        )
    return ExecutionCommandResult(
        command_id=command.command_id,
        order_id=command.order_id,
        status=ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER,
        reason="sim harness accepted command",
        adapter_order_ref=adapter_order_ref,
        submitted_at=command.created_at,
        raw_payload=None,
    )


def _raw_reports_for_policy(
    evidence_builder: SharedExecutionEvidenceBuilder,
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
    policy: SimExecutionPolicy,
) -> tuple[RawExecutionReport, ...]:
    evidences: tuple[_ExecutionEvidence, ...]
    if policy is SimExecutionPolicy.IMMEDIATE_FULL_FILL:
        evidences = cast(
            tuple[_ExecutionEvidence, ...],
            (
                evidence_builder.build_acknowledged(
                    command,
                    adapter_order_ref=adapter_order_ref,
                ),
                evidence_builder.build_filled(
                    command,
                    adapter_order_ref=adapter_order_ref,
                ),
            ),
        )
    elif policy is SimExecutionPolicy.IMMEDIATE_REJECT:
        evidences = cast(
            tuple[_ExecutionEvidence, ...],
            (
                evidence_builder.build_rejected(
                    command,
                    adapter_order_ref=adapter_order_ref,
                ),
            ),
        )
    else:
        evidences = ()
    return tuple(_raw_report_from_evidence(evidence) for evidence in evidences)


def _raw_report_from_evidence(evidence: _ExecutionEvidence) -> RawExecutionReport:
    return RawExecutionReport(
        raw_report_id=_required_str(evidence.raw_report_id),
        adapter_name=_required_str(evidence.adapter_name),
        execution_target=evidence.execution_target,
        command_id=_required_str(evidence.command_id),
        order_id=_required_str(evidence.order_id),
        client_order_id=_required_str(evidence.client_order_id),
        adapter_order_ref=_required_str(evidence.adapter_order_ref),
        exchange_order_id=evidence.exchange_order_id,
        exchange_trade_id=evidence.exchange_trade_id,
        fill_id=evidence.fill_id,
        report_type=_required_str(evidence.report_type),
        filled_qty=evidence.filled_qty,
        fill_price=evidence.fill_price,
        cumulative_filled_qty=evidence.cumulative_filled_qty,
        remaining_qty=evidence.remaining_qty,
        fee_amount=evidence.fee_amount,
        fee_currency=evidence.fee_currency,
        fee_source=evidence.fee_source,
        report_ts=_required_datetime(evidence.report_ts),
        received_at=_required_datetime(evidence.received_at),
        raw_payload=evidence.raw_payload,
    )


def _sim_adapter_order_ref(command_id: str) -> str:
    return "sim_order_ref_" + stable_json_sha256({"command_id": command_id})[:40]


def _required_str(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("required string evidence field is missing")
    return value


def _required_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("required datetime evidence field is missing")
    return value
