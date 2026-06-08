from datetime import UTC, datetime
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import (
    Direction,
    ExecutionCommandResultStatus,
    ExecutionCommandType,
    ExecutionGatewayResultStatus,
    ExecutionTarget,
    Offset,
    OrderType,
)
from futures_mvp.domain.models import (
    ExecutionCommand,
    ExecutionCommandResult,
    ExecutionGatewayResult,
)
from futures_mvp.modules.execution_gateway import (
    build_execution_command_id,
    build_execution_command_payload_hash,
    canonical_execution_command_payload,
)

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


def _command(**updates: object) -> ExecutionCommand:
    values = {
        "command_id": build_execution_command_id(
            "order-1",
            ExecutionCommandType.SUBMIT_ORDER,
            ExecutionTarget.MOCK,
        ),
        "order_id": "order-1",
        "client_order_id": "client-1",
        "account_id": "account-1",
        "symbol": "au",
        "instrument_id": "au2606",
        "trade_instrument_id": "au2606",
        "exchange": "SHFE",
        "side": Direction.BUY,
        "offset": Offset.OPEN,
        "quantity": Decimal("2"),
        "price": Decimal("500"),
        "order_type": OrderType.LIMIT,
        "tif": "GFD",
        "command_type": ExecutionCommandType.SUBMIT_ORDER,
        "execution_target": ExecutionTarget.MOCK,
        "command_payload_hash": "pending",
        "created_at": NOW,
        "raw_payload": {"diagnostic": "only"},
    }
    values.update(updates)
    command = ExecutionCommand(**values)
    if command.command_payload_hash == "pending":
        command = command.model_copy(
            update={"command_payload_hash": build_execution_command_payload_hash(command)}
        )
    return command


def test_execution_gateway_enums_freeze_contract() -> None:
    assert [target.value for target in ExecutionTarget] == ["MOCK", "PAPER", "SIM", "LIVE"]
    assert [command_type.value for command_type in ExecutionCommandType] == [
        "SUBMIT_ORDER",
        "CANCEL_ORDER",
    ]
    assert [status.value for status in ExecutionCommandResultStatus] == [
        "ACCEPTED_BY_ADAPTER",
        "REJECTED_BY_ADAPTER",
        "DUPLICATE",
        "CONFLICT",
        "ERROR",
    ]
    assert ExecutionGatewayResultStatus.REJECTED_UNSUPPORTED_TARGET.value == (
        "REJECTED_UNSUPPORTED_TARGET"
    )


def test_execution_command_validation_and_deterministic_command_id() -> None:
    first = build_execution_command_id(
        "order-1",
        ExecutionCommandType.SUBMIT_ORDER,
        ExecutionTarget.MOCK,
    )
    second = build_execution_command_id(
        "order-1",
        ExecutionCommandType.SUBMIT_ORDER,
        ExecutionTarget.MOCK,
    )
    different_target = build_execution_command_id(
        "order-1",
        ExecutionCommandType.SUBMIT_ORDER,
        ExecutionTarget.PAPER,
    )

    assert first == second
    assert first != different_target
    assert "order-1" not in first
    with pytest.raises(ValueError, match="quantity"):
        _command(quantity=Decimal("0"))
    with pytest.raises(ValueError, match="price"):
        _command(price=Decimal("0"))
    with pytest.raises(ValueError, match="CANCEL_ORDER"):
        _command(command_type=ExecutionCommandType.CANCEL_ORDER)


def test_execution_command_canonical_excludes_raw_and_timestamps() -> None:
    command = _command()
    changed_diagnostics = command.model_copy(
        update={
            "raw_payload": {"diagnostic": "changed"},
            "created_at": datetime(2026, 6, 8, 10, tzinfo=UTC),
        }
    )

    assert canonical_execution_command_payload(command) == canonical_execution_command_payload(
        changed_diagnostics
    )
    assert build_execution_command_payload_hash(command) == build_execution_command_payload_hash(
        changed_diagnostics
    )
    payload = canonical_execution_command_payload(command)
    assert "raw_payload" not in payload
    assert "created_at" not in payload
    assert "broker_response" not in payload
    assert "id" not in payload


def test_execution_command_result_semantics_do_not_imply_fill_or_trade() -> None:
    result = ExecutionCommandResult(
        command_id="command-1",
        order_id="order-1",
        status=ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER,
        reason="accepted by mock adapter only",
        adapter_order_ref="mock-ref",
        submitted_at=NOW,
        raw_payload={"diagnostic": "adapter"},
    )

    assert result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert "fill" not in ExecutionCommandResult.model_fields
    assert "trade" not in ExecutionCommandResult.model_fields
    assert "exchange_report" not in ExecutionCommandResult.model_fields


def test_gateway_result_requires_command_for_created_or_duplicate() -> None:
    command = _command()
    assert ExecutionGatewayResult(
        status=ExecutionGatewayResultStatus.COMMAND_CREATED,
        command=command,
        reason="dry_run",
    ).command == command
    with pytest.raises(ValueError, match="requires command"):
        ExecutionGatewayResult(status=ExecutionGatewayResultStatus.DUPLICATE)
