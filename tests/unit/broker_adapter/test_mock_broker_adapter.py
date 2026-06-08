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
    OrderStatus,
    OrderType,
)
from futures_mvp.domain.models import ExecutionCommand, OrderRequest, OrderState
from futures_mvp.interfaces.repositories import ExecutionCommandConflictError
from futures_mvp.modules.broker_adapter import MockBrokerAdapter, MockBrokerSubmitMode
from futures_mvp.modules.execution_gateway import ExecutionGatewayService
from futures_mvp.modules.execution_gateway.canonical import canonical_execution_command_payload

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


class InMemoryExecutionCommandRepository:
    def __init__(self) -> None:
        self.commands: dict[str, ExecutionCommand] = {}

    def append_execution_command(self, command: ExecutionCommand) -> ExecutionCommand:
        existing = self.commands.get(command.command_id)
        if existing is not None:
            if canonical_execution_command_payload(
                existing
            ) != canonical_execution_command_payload(command):
                raise ExecutionCommandConflictError("conflict")
            return existing
        self.commands[command.command_id] = command
        return command

    def get_by_command_id(self, command_id: str) -> ExecutionCommand | None:
        return self.commands.get(command_id)

    def list_by_order_id(self, order_id: str) -> list[ExecutionCommand]:
        return [command for command in self.commands.values() if command.order_id == order_id]

    def list_by_target(
        self,
        execution_target: ExecutionTarget | str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[ExecutionCommand]:
        del start_ts, end_ts
        target = (
            execution_target.value
            if isinstance(execution_target, ExecutionTarget)
            else execution_target
        )
        return [
            command
            for command in self.commands.values()
            if command.execution_target.value == target
        ]


class FakeExecutionGatewayUnitOfWork:
    def __init__(self, repository: InMemoryExecutionCommandRepository) -> None:
        self.execution_commands = repository
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> "FakeExecutionGatewayUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        del exc_type, exc, tb

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _order(order_id: str = "order-1") -> OrderState:
    return OrderState(
        order_id=order_id,
        request=OrderRequest(
            client_order_id="client-1",
            account_id="account-1",
            instrument_id="au2606",
            exchange="SHFE",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("500"),
            quantity=Decimal("2"),
        ),
        status=OrderStatus.RISK_ACCEPTED,
    )


def _command(order_id: str = "order-1") -> ExecutionCommand:
    repository = InMemoryExecutionCommandRepository()
    adapter = MockBrokerAdapter(clock=lambda: NOW)
    service = ExecutionGatewayService(
        lambda: FakeExecutionGatewayUnitOfWork(repository),
        adapter,
        clock=lambda: NOW,
    )
    command = service.build_command(
        _order(order_id),
        execution_target=ExecutionTarget.MOCK,
        command_type=ExecutionCommandType.SUBMIT_ORDER,
        symbol="au",
        trade_instrument_id="au2606",
        tif="GFD",
    )
    assert command.command_type is ExecutionCommandType.SUBMIT_ORDER
    return command


def test_submit_success_returns_deterministic_adapter_order_ref() -> None:
    command = _command()
    adapter = MockBrokerAdapter(clock=lambda: NOW)

    result = adapter.submit(command)
    repeat_adapter = MockBrokerAdapter(clock=lambda: NOW)
    repeat = repeat_adapter.submit(command)

    assert result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert result.adapter_order_ref == repeat.adapter_order_ref
    assert result.adapter_order_ref is not None
    assert result.adapter_order_ref.startswith("mock_broker_")
    assert adapter.submitted_commands == [command]


def test_pre_send_timeout_returns_typed_failure_without_adapter_order_ref() -> None:
    command = _command()
    adapter = MockBrokerAdapter(
        submit_modes=[MockBrokerSubmitMode.PRE_SEND_TIMEOUT],
        clock=lambda: NOW,
    )

    result = adapter.submit(command)

    assert result.status is ExecutionCommandResultStatus.ERROR
    assert result.reason == "pre_send_timeout"
    assert result.adapter_order_ref is None
    assert result.raw_payload is None


def test_post_send_uncertain_returns_typed_failure_without_blind_retry() -> None:
    command = _command()
    adapter = MockBrokerAdapter(
        submit_modes=[MockBrokerSubmitMode.POST_SEND_UNCERTAIN],
        clock=lambda: NOW,
    )

    first = adapter.submit(command)
    duplicate = adapter.submit(command)

    assert first.status is ExecutionCommandResultStatus.ERROR
    assert first.reason == "post_send_uncertain"
    assert first.adapter_order_ref is not None
    assert duplicate.status is ExecutionCommandResultStatus.DUPLICATE
    assert duplicate.adapter_order_ref == first.adapter_order_ref
    assert len(adapter.submitted_commands) == 1


def test_duplicate_submit_same_canonical_is_deterministic_noop() -> None:
    command = _command()
    adapter = MockBrokerAdapter(clock=lambda: NOW)

    first = adapter.submit(command)
    duplicate = adapter.submit(command)

    assert first.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert duplicate.status is ExecutionCommandResultStatus.DUPLICATE
    assert duplicate.adapter_order_ref == first.adapter_order_ref
    assert len(adapter.submitted_commands) == 1


def test_cancel_is_unsupported_in_stage_n() -> None:
    command = _command()
    adapter = MockBrokerAdapter(clock=lambda: NOW)

    assert not hasattr(adapter, "cancel")
    with pytest.raises(ValueError, match="CANCEL_ORDER is reserved"):
        ExecutionCommand(
            **{
                **command.model_dump(),
                "command_type": ExecutionCommandType.CANCEL_ORDER,
            }
        )


def test_mock_broker_adapter_can_be_injected_through_execution_gateway() -> None:
    repository = InMemoryExecutionCommandRepository()
    adapter = MockBrokerAdapter(clock=lambda: NOW)
    service = ExecutionGatewayService(
        lambda: FakeExecutionGatewayUnitOfWork(repository),
        adapter,
        clock=lambda: NOW,
    )

    result = service.submit(
        _order(),
        symbol="au",
        trade_instrument_id="au2606",
        tif="GFD",
        execution_target=ExecutionTarget.MOCK,
    )

    assert result.status is ExecutionGatewayResultStatus.COMMAND_CREATED
    assert result.command_result is not None
    assert result.command_result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert adapter.submitted_commands == [result.command]
