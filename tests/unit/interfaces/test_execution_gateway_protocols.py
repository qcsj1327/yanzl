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
from futures_mvp.domain.models import ExecutionCommand, ExecutionCommandResult
from futures_mvp.interfaces.repositories import (
    ExecutionCommandRepository,
    ExecutionGatewayUnitOfWork,
    UnitOfWork,
)
from futures_mvp.modules.execution_gateway import (
    MockExecutionAdapter,
    build_execution_command_id,
    build_execution_command_payload_hash,
)
from futures_mvp.modules.execution_gateway.protocols import ExecutionAdapter

NOW = datetime(2026, 6, 8, 9, tzinfo=UTC)


class MinimalExecutionCommandRepository:
    def append_execution_command(self, command: ExecutionCommand) -> ExecutionCommand:
        return command

    def get_by_command_id(self, command_id: str) -> ExecutionCommand | None:
        del command_id
        return None

    def list_by_order_id(self, order_id: str) -> list[ExecutionCommand]:
        del order_id
        return []

    def list_by_target(
        self,
        execution_target: ExecutionTarget | str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[ExecutionCommand]:
        del execution_target, start_ts, end_ts
        return []


class MinimalExecutionGatewayUnitOfWork:
    def __init__(self) -> None:
        self.execution_commands = MinimalExecutionCommandRepository()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def __enter__(self) -> "MinimalExecutionGatewayUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool | None:
        del exc_type, exc, tb
        return None


def _command() -> ExecutionCommand:
    command = ExecutionCommand(
        command_id=build_execution_command_id(
            "order-1",
            ExecutionCommandType.SUBMIT_ORDER,
            ExecutionTarget.MOCK,
        ),
        order_id="order-1",
        client_order_id="client-1",
        account_id="account-1",
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        side=Direction.BUY,
        offset=Offset.OPEN,
        quantity=Decimal("1"),
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


def test_execution_command_repository_protocol_runtime_checkable() -> None:
    assert isinstance(MinimalExecutionCommandRepository(), ExecutionCommandRepository)


def test_execution_adapter_protocol_runtime_checkable() -> None:
    adapter = MockExecutionAdapter(clock=lambda: NOW)
    assert isinstance(adapter, ExecutionAdapter)
    result = adapter.submit(_command())
    assert isinstance(result, ExecutionCommandResult)
    assert result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER


def test_execution_gateway_uow_protocol_and_full_uow_attribute_contract() -> None:
    uow = MinimalExecutionGatewayUnitOfWork()
    assert isinstance(uow, ExecutionGatewayUnitOfWork)
    assert "execution_commands" in UnitOfWork.__annotations__
