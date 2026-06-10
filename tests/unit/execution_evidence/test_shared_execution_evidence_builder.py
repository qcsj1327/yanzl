from datetime import UTC, datetime
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import (
    Direction,
    ExecutionCommandType,
    ExecutionTarget,
    Offset,
    OrderType,
)
from futures_mvp.domain.models import ExecutionCommand
from futures_mvp.modules.execution_evidence import SharedExecutionEvidenceBuilder
from futures_mvp.modules.execution_gateway import build_execution_command_payload_hash

NOW = datetime(2026, 6, 10, 9, tzinfo=UTC)


def _command(*, command_id: str = "command-1") -> ExecutionCommand:
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
        quantity=Decimal("3"),
        price=Decimal("500"),
        order_type=OrderType.LIMIT,
        tif="GFD",
        command_type=ExecutionCommandType.SUBMIT_ORDER,
        execution_target=ExecutionTarget.MOCK,
        command_payload_hash="pending",
        created_at=NOW,
    )
    return command.model_copy(
        update={"command_payload_hash": build_execution_command_payload_hash(command)}
    )


def _builder(namespace: str = "sim") -> SharedExecutionEvidenceBuilder:
    return SharedExecutionEvidenceBuilder(
        namespace=namespace,
        adapter_name=f"{namespace}_harness",
    )


def test_namespace_controls_identity_prefixes_and_adapter_name() -> None:
    evidence = _builder("sim").build_filled(
        _command(),
        adapter_order_ref="sim-order-ref",
    )

    assert evidence.adapter_name == "sim_harness"
    assert evidence.raw_report_id is not None
    assert evidence.raw_report_id.startswith("sim_raw_")
    assert evidence.fill_id is not None
    assert evidence.fill_id.startswith("sim_fill_")
    assert evidence.exchange_trade_id is not None
    assert evidence.exchange_trade_id.startswith("sim_trade_")
    assert evidence.exchange_order_id is not None
    assert evidence.exchange_order_id.startswith("sim_order_")


def test_paper_and_sim_identity_domains_do_not_collide() -> None:
    command = _command()
    paper = _builder("paper").build_filled(command, adapter_order_ref="order-ref")
    sim = _builder("sim").build_filled(command, adapter_order_ref="order-ref")

    assert paper.raw_report_id != sim.raw_report_id
    assert paper.fill_id != sim.fill_id
    assert paper.exchange_trade_id != sim.exchange_trade_id
    assert paper.exchange_order_id != sim.exchange_order_id
    assert paper.raw_report_id is not None
    assert paper.raw_report_id.startswith("paper_raw_")
    assert sim.raw_report_id is not None
    assert sim.raw_report_id.startswith("sim_raw_")


def test_identities_are_deterministic_for_same_namespace_and_inputs() -> None:
    command = _command()
    first = _builder("sim").build_filled(command, adapter_order_ref="order-ref")
    second = _builder("sim").build_filled(command, adapter_order_ref="order-ref")

    assert first.raw_report_id == second.raw_report_id
    assert first.fill_id == second.fill_id
    assert first.exchange_trade_id == second.exchange_trade_id
    assert first.exchange_order_id == second.exchange_order_id
    assert first.raw_payload is None


def test_partial_fill_sequence_helper_calculates_cumulative_and_remaining_qty() -> None:
    reports = _builder("sim").build_fill_report_sequence(
        _command(),
        adapter_order_ref="sim-order-ref",
        fill_quantities=(Decimal("1"), Decimal("2")),
    )

    assert [report.report_type for report in reports] == [
        "acked",
        "partial_fill",
        "filled",
    ]
    assert [report.filled_qty for report in reports] == [
        Decimal("0"),
        Decimal("1"),
        Decimal("2"),
    ]
    assert [report.cumulative_filled_qty for report in reports] == [
        Decimal("0"),
        Decimal("1"),
        Decimal("3"),
    ]
    assert [report.remaining_qty for report in reports] == [
        Decimal("3"),
        Decimal("2"),
        Decimal("0"),
    ]
    assert reports[1].raw_report_id != reports[2].raw_report_id
    assert reports[1].fill_id != reports[2].fill_id


def test_partial_fill_sequence_rejects_overfill_and_incomplete_final_fill() -> None:
    builder = _builder("sim")
    command = _command()

    with pytest.raises(ValueError, match="overfill is forbidden"):
        builder.build_fill_report_sequence(
            command,
            adapter_order_ref="sim-order-ref",
            fill_quantities=(Decimal("2"), Decimal("2")),
        )
    with pytest.raises(
        ValueError,
        match="final filled cumulative quantity must equal order quantity",
    ):
        builder.build_fill_report_sequence(
            command,
            adapter_order_ref="sim-order-ref",
            fill_quantities=(Decimal("1"),),
        )
