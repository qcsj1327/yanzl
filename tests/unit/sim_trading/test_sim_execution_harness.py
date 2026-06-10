from datetime import UTC, datetime
from decimal import Decimal

from futures_mvp.domain.enums import (
    Direction,
    ExecutionCommandResultStatus,
    ExecutionCommandType,
    ExecutionTarget,
    Offset,
    OrderType,
)
from futures_mvp.domain.models import ExecutionCommand
from futures_mvp.modules.execution_gateway import build_execution_command_payload_hash
from futures_mvp.modules.sim_trading import (
    SimExecutionHarness,
    SimExecutionPolicy,
    SimExecutionStatus,
)

NOW = datetime(2026, 6, 10, 9, tzinfo=UTC)


def _command(
    *,
    command_id: str = "command-1",
    execution_target: ExecutionTarget = ExecutionTarget.MOCK,
) -> ExecutionCommand:
    command = ExecutionCommand(
        command_id=command_id,
        order_id="order-1",
        client_order_id="client-1",
        account_id="account-1",
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        side=Direction.BUY,
        offset=Offset.OPEN,
        quantity=Decimal("2"),
        price=Decimal("500"),
        order_type=OrderType.LIMIT,
        tif="GFD",
        command_type=ExecutionCommandType.SUBMIT_ORDER,
        execution_target=execution_target,
        command_payload_hash="pending",
        created_at=NOW,
    )
    return command.model_copy(
        update={"command_payload_hash": build_execution_command_payload_hash(command)}
    )


def test_full_fill_emits_acked_then_filled_with_sim_namespace() -> None:
    result = SimExecutionHarness(
        policy=SimExecutionPolicy.IMMEDIATE_FULL_FILL,
    ).execute(_command())

    assert result.status is SimExecutionStatus.EXECUTED
    assert result.command_result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert result.command_result.adapter_order_ref is not None
    assert result.command_result.adapter_order_ref.startswith("sim_order_ref_")
    assert [report.report_type for report in result.raw_reports] == ["acked", "filled"]
    acked, filled = result.raw_reports
    assert acked.adapter_name == "sim_harness"
    assert acked.raw_report_id.startswith("sim_raw_")
    assert acked.exchange_order_id is not None
    assert acked.exchange_order_id.startswith("sim_order_")
    assert acked.fill_id is None
    assert acked.exchange_trade_id is None
    assert filled.adapter_name == "sim_harness"
    assert filled.raw_report_id.startswith("sim_raw_")
    assert filled.exchange_order_id is not None
    assert filled.exchange_order_id.startswith("sim_order_")
    assert filled.fill_id is not None
    assert filled.fill_id.startswith("sim_fill_")
    assert filled.exchange_trade_id is not None
    assert filled.exchange_trade_id.startswith("sim_trade_")
    assert filled.filled_qty == Decimal("2")
    assert filled.fill_price == Decimal("500")
    assert filled.cumulative_filled_qty == Decimal("2")
    assert filled.remaining_qty == Decimal("0")
    assert filled.raw_payload is None


def test_reject_emits_rejected_report_without_fill_identity() -> None:
    result = SimExecutionHarness(
        policy=SimExecutionPolicy.IMMEDIATE_REJECT,
    ).execute(_command())

    assert result.status is SimExecutionStatus.REJECTED
    assert result.command_result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert len(result.raw_reports) == 1
    raw = result.raw_reports[0]
    assert raw.adapter_name == "sim_harness"
    assert raw.report_type == "rejected"
    assert raw.raw_report_id.startswith("sim_raw_")
    assert raw.filled_qty == Decimal("0")
    assert raw.fill_price is None
    assert raw.exchange_trade_id is None
    assert raw.fill_id is None


def test_pre_send_timeout_returns_failure_and_no_report() -> None:
    result = SimExecutionHarness(
        policy=SimExecutionPolicy.PRE_SEND_TIMEOUT,
    ).execute(_command())

    assert result.status is SimExecutionStatus.FAILED
    assert result.command_result.status is ExecutionCommandResultStatus.ERROR
    assert result.command_result.reason == "pre_send_timeout"
    assert result.command_result.adapter_order_ref is None
    assert result.raw_reports == ()


def test_post_send_uncertain_returns_uncertain_and_no_report() -> None:
    result = SimExecutionHarness(
        policy=SimExecutionPolicy.POST_SEND_UNCERTAIN,
    ).execute(_command())

    assert result.status is SimExecutionStatus.UNCERTAIN
    assert result.command_result.status is ExecutionCommandResultStatus.ERROR
    assert result.command_result.reason == "post_send_uncertain"
    assert result.command_result.adapter_order_ref is not None
    assert result.command_result.adapter_order_ref.startswith("sim_order_ref_")
    assert result.raw_reports == ()


def test_sim_identities_are_deterministic_and_do_not_use_paper_prefixes() -> None:
    command = _command()
    first = SimExecutionHarness().execute(command)
    second = SimExecutionHarness().execute(command)

    assert first.command_result.adapter_order_ref == second.command_result.adapter_order_ref
    assert len(first.raw_reports) == 2
    assert len(second.raw_reports) == 2
    assert first.raw_reports[0].raw_report_id == second.raw_reports[0].raw_report_id
    assert first.raw_reports[1].raw_report_id == second.raw_reports[1].raw_report_id
    assert first.raw_reports[1].fill_id == second.raw_reports[1].fill_id
    assert first.raw_reports[1].exchange_trade_id == second.raw_reports[1].exchange_trade_id
    assert all(report.raw_report_id.startswith("sim_raw_") for report in first.raw_reports)
    assert all(not report.raw_report_id.startswith("paper_raw_") for report in first.raw_reports)


def test_non_mock_targets_are_rejected_without_reports() -> None:
    for target in [ExecutionTarget.PAPER, ExecutionTarget.SIM, ExecutionTarget.LIVE]:
        result = SimExecutionHarness().execute(
            _command(command_id=f"command-{target.value}", execution_target=target)
        )

        assert result.status is SimExecutionStatus.REJECTED
        assert result.command_result.status is ExecutionCommandResultStatus.REJECTED_BY_ADAPTER
        assert result.reason == "sim harness supports ExecutionTarget.MOCK only"
        assert result.raw_reports == ()
