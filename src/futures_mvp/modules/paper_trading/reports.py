from decimal import Decimal

from futures_mvp.domain.models import ExecutionCommand, stable_json_sha256
from futures_mvp.modules.broker_adapter import BrokerCallbackEvidence
from futures_mvp.modules.paper_trading.policy import PaperFillPolicy


def build_paper_broker_callback_evidence(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
    policy: PaperFillPolicy,
) -> BrokerCallbackEvidence:
    return build_paper_broker_callback_evidences(
        command,
        adapter_order_ref=adapter_order_ref,
        policy=policy,
    )[0]


def build_paper_broker_callback_evidences(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
    policy: PaperFillPolicy,
) -> tuple[BrokerCallbackEvidence, ...]:
    if policy is PaperFillPolicy.IMMEDIATE_FULL_FILL:
        return (
            _acked_evidence(command, adapter_order_ref=adapter_order_ref),
            _filled_evidence(command, adapter_order_ref=adapter_order_ref),
        )
    if policy is PaperFillPolicy.IMMEDIATE_REJECT:
        return (_rejected_evidence(command, adapter_order_ref=adapter_order_ref),)
    raise ValueError(f"{policy.value} does not produce a paper execution report")


def _acked_evidence(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
) -> BrokerCallbackEvidence:
    return BrokerCallbackEvidence(
        adapter_name="paper_harness",
        execution_target=command.execution_target,
        command_id=command.command_id,
        order_id=command.order_id,
        client_order_id=command.client_order_id,
        adapter_order_ref=adapter_order_ref,
        exchange_order_id=_paper_exchange_order_id(command),
        exchange_trade_id=None,
        fill_id=None,
        report_type="acked",
        filled_qty=Decimal("0"),
        fill_price=None,
        cumulative_filled_qty=Decimal("0"),
        remaining_qty=command.quantity,
        report_ts=command.created_at,
        received_at=command.created_at,
        raw_payload=None,
        raw_report_id=_paper_raw_report_id(command, report_type="acked", sequence=1),
    )


def _filled_evidence(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
) -> BrokerCallbackEvidence:
    return BrokerCallbackEvidence(
        adapter_name="paper_harness",
        execution_target=command.execution_target,
        command_id=command.command_id,
        order_id=command.order_id,
        client_order_id=command.client_order_id,
        adapter_order_ref=adapter_order_ref,
        exchange_order_id=_paper_exchange_order_id(command),
        exchange_trade_id=_paper_exchange_trade_id(command, sequence=1),
        fill_id=_paper_fill_id(command, sequence=1),
        report_type="filled",
        filled_qty=command.quantity,
        fill_price=command.price,
        cumulative_filled_qty=command.quantity,
        remaining_qty=Decimal("0"),
        report_ts=command.created_at,
        received_at=command.created_at,
        raw_payload=None,
        raw_report_id=_paper_raw_report_id(command, report_type="filled", sequence=1),
    )


def _rejected_evidence(
    command: ExecutionCommand,
    *,
    adapter_order_ref: str,
) -> BrokerCallbackEvidence:
    return BrokerCallbackEvidence(
        adapter_name="paper_harness",
        execution_target=command.execution_target,
        command_id=command.command_id,
        order_id=command.order_id,
        client_order_id=command.client_order_id,
        adapter_order_ref=adapter_order_ref,
        exchange_order_id=_paper_exchange_order_id(command),
        exchange_trade_id=None,
        fill_id=None,
        report_type="rejected",
        filled_qty=Decimal("0"),
        fill_price=None,
        cumulative_filled_qty=Decimal("0"),
        remaining_qty=command.quantity,
        report_ts=command.created_at,
        received_at=command.created_at,
        raw_payload=None,
        raw_report_id=_paper_raw_report_id(command, report_type="rejected", sequence=1),
    )


def _paper_exchange_order_id(command: ExecutionCommand) -> str:
    return "paper_order_" + stable_json_sha256({"command_id": command.command_id})[:40]


def _paper_exchange_trade_id(command: ExecutionCommand, *, sequence: int) -> str:
    return (
        "paper_trade_"
        + stable_json_sha256({"command_id": command.command_id, "sequence": sequence})[:40]
    )


def _paper_fill_id(command: ExecutionCommand, *, sequence: int) -> str:
    return (
        "paper_fill_"
        + stable_json_sha256({"command_id": command.command_id, "sequence": sequence})[:40]
    )


def _paper_raw_report_id(
    command: ExecutionCommand,
    *,
    report_type: str,
    sequence: int,
) -> str:
    return (
        "paper_raw_"
        + stable_json_sha256(
            {
                "command_id": command.command_id,
                "order_id": command.order_id,
                "policy_report_type": report_type,
                "sequence": sequence,
            }
        )[:48]
    )
