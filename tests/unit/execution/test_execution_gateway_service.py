from datetime import UTC, datetime
from decimal import Decimal

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
from futures_mvp.modules.execution_gateway import (
    ExecutionGatewayService,
    MockExecutionAdapter,
    build_execution_command_id,
    build_execution_command_payload_hash,
    replay_execution_gateway,
)
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
        value = (
            execution_target.value
            if isinstance(execution_target, ExecutionTarget)
            else execution_target
        )
        return [
            command for command in self.commands.values() if command.execution_target.value == value
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
    ) -> bool | None:
        del exc_type, exc, tb
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _order(
    *,
    order_id: str = "order-1",
    status: OrderStatus = OrderStatus.RISK_ACCEPTED,
    quantity: Decimal = Decimal("2"),
    price: Decimal = Decimal("500"),
) -> OrderState:
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
            limit_price=price,
            quantity=quantity,
        ),
        status=status,
    )


def _service(
    repository: InMemoryExecutionCommandRepository,
    adapter: MockExecutionAdapter | None = None,
) -> tuple[ExecutionGatewayService, MockExecutionAdapter]:
    mock_adapter = adapter or MockExecutionAdapter(clock=lambda: NOW)
    service = ExecutionGatewayService(
        lambda: FakeExecutionGatewayUnitOfWork(repository),
        mock_adapter,
        clock=lambda: NOW,
    )
    return service, mock_adapter


def _submit_kwargs() -> dict[str, object]:
    return {"symbol": "au", "trade_instrument_id": "au2606", "tif": "GFD"}


def test_valid_mock_submit_persists_and_calls_mock_adapter() -> None:
    repository = InMemoryExecutionCommandRepository()
    service, adapter = _service(repository)

    result = service.submit(_order(), **_submit_kwargs())

    assert result.status is ExecutionGatewayResultStatus.COMMAND_CREATED
    assert result.command is not None
    assert result.command_result is not None
    assert result.command_result.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert result.command_result.adapter_order_ref is not None
    assert result.command_result.adapter_order_ref.startswith("mock_")
    assert adapter.submitted_commands == [result.command]


def test_mock_adapter_deterministic_and_accepted_is_not_fill_or_trade() -> None:
    repository = InMemoryExecutionCommandRepository()
    service, adapter = _service(repository)

    first = service.submit(_order(), **_submit_kwargs())
    command = first.command
    assert command is not None
    direct = MockExecutionAdapter(clock=lambda: NOW).submit(command)
    repeat = MockExecutionAdapter(clock=lambda: NOW).submit(command)

    assert direct.adapter_order_ref == repeat.adapter_order_ref
    assert direct.status is ExecutionCommandResultStatus.ACCEPTED_BY_ADAPTER
    assert "fill" not in direct.__class__.model_fields
    assert "trade" not in direct.__class__.model_fields
    assert len(adapter.submitted_commands) == 1


def test_unsupported_targets_and_cancel_order_are_rejected_without_adapter_call() -> None:
    for target in [ExecutionTarget.PAPER, ExecutionTarget.SIM, ExecutionTarget.LIVE]:
        repository = InMemoryExecutionCommandRepository()
        service, adapter = _service(repository)
        result = service.submit(_order(), execution_target=target, **_submit_kwargs())

        assert result.status is ExecutionGatewayResultStatus.REJECTED_UNSUPPORTED_TARGET
        assert adapter.submitted_commands == []

    repository = InMemoryExecutionCommandRepository()
    service, adapter = _service(repository)
    result = service.submit(
        _order(),
        command_type=ExecutionCommandType.CANCEL_ORDER,
        **_submit_kwargs(),
    )

    assert result.status is ExecutionGatewayResultStatus.REJECTED_INVALID_ORDER
    assert adapter.submitted_commands == []


def test_invalid_order_rejected_without_adapter_call() -> None:
    for order in [
        _order(order_id=""),
        _order(status=OrderStatus.FILLED),
        _order(status=OrderStatus.CANCELED),
        _order(status=OrderStatus.REJECTED_BY_RISK),
        _order(status=OrderStatus.SUBMIT_FAILED),
        _order(status=OrderStatus.REJECTED_BY_EXCHANGE),
        _order(status=OrderStatus.EXPIRED),
    ]:
        repository = InMemoryExecutionCommandRepository()
        service, adapter = _service(repository)
        result = service.submit(order, **_submit_kwargs())

        assert result.status is ExecutionGatewayResultStatus.REJECTED_INVALID_ORDER
        assert repository.commands == {}
        assert adapter.submitted_commands == []


def test_submit_failed_order_rejected_without_command_or_adapter_in_all_submit_modes() -> None:
    for dry_run in [True, False]:
        repository = InMemoryExecutionCommandRepository()
        service, adapter = _service(repository)

        result = service.submit(
            _order(status=OrderStatus.SUBMIT_FAILED),
            dry_run=dry_run,
            **_submit_kwargs(),
        )

        assert result.status is ExecutionGatewayResultStatus.REJECTED_INVALID_ORDER
        assert result.command is None
        assert result.command_result is None
        assert repository.commands == {}
        assert adapter.submitted_commands == []


def test_duplicate_same_canonical_returns_duplicate_without_adapter_call() -> None:
    repository = InMemoryExecutionCommandRepository()
    service, adapter = _service(repository)

    first = service.submit(_order(), **_submit_kwargs())
    second = service.submit(
        _order(),
        symbol="au",
        trade_instrument_id="au2606",
        tif="GFD",
    )

    assert first.status is ExecutionGatewayResultStatus.COMMAND_CREATED
    assert second.status is ExecutionGatewayResultStatus.DUPLICATE
    assert second.command_result is not None
    assert second.command_result.status is ExecutionCommandResultStatus.DUPLICATE
    assert len(adapter.submitted_commands) == 1


def test_duplicate_conflict_returns_conflict_without_adapter_call() -> None:
    repository = InMemoryExecutionCommandRepository()
    service, adapter = _service(repository)
    existing_result = service.submit(_order(), **_submit_kwargs())
    assert existing_result.command is not None
    adapter.submitted_commands.clear()

    conflict = service.submit(
        _order(),
        symbol="ag",
        trade_instrument_id="au2606",
        tif="GFD",
    )

    assert conflict.status is ExecutionGatewayResultStatus.CONFLICT
    assert adapter.submitted_commands == []


def test_build_command_id_and_hash_from_service_are_stable() -> None:
    repository = InMemoryExecutionCommandRepository()
    service, _adapter = _service(repository)

    command = service.build_command(
        _order(),
        execution_target=ExecutionTarget.MOCK,
        command_type=ExecutionCommandType.SUBMIT_ORDER,
        symbol="au",
        trade_instrument_id="au2606",
        tif="GFD",
    )

    assert command.command_id == build_execution_command_id(
        "order-1",
        ExecutionCommandType.SUBMIT_ORDER,
        ExecutionTarget.MOCK,
    )
    assert command.command_payload_hash == build_execution_command_payload_hash(command)


def test_replay_dry_run_no_adapter_call_and_live_flag_submits() -> None:
    repository = InMemoryExecutionCommandRepository()
    service, adapter = _service(repository)
    orders = [_order(order_id="order-2"), _order(order_id="order-1")]

    dry_results = replay_execution_gateway(
        service,
        orders,
        symbol="au",
        trade_instrument_id="au2606",
        tif="GFD",
    )

    assert [result.command.order_id for result in dry_results if result.command] == [
        "order-1",
        "order-2",
    ]
    assert adapter.submitted_commands == []

    blocked_live = replay_execution_gateway(
        service,
        [_order(order_id="order-3")],
        symbol="au",
        trade_instrument_id="au2606",
        tif="GFD",
        dry_run=False,
        allow_submit=False,
    )
    assert blocked_live[0].status is ExecutionGatewayResultStatus.ERROR

    live_results = replay_execution_gateway(
        service,
        [_order(order_id="order-3")],
        symbol="au",
        trade_instrument_id="au2606",
        tif="GFD",
        dry_run=False,
        allow_submit=True,
    )
    assert live_results[0].status is ExecutionGatewayResultStatus.COMMAND_CREATED
    assert len(adapter.submitted_commands) == 1


def test_replay_submit_failed_order_rejected_without_command_or_adapter() -> None:
    for dry_run, allow_submit in [(True, False), (False, True)]:
        repository = InMemoryExecutionCommandRepository()
        service, adapter = _service(repository)

        results = replay_execution_gateway(
            service,
            [_order(status=OrderStatus.SUBMIT_FAILED)],
            symbol="au",
            trade_instrument_id="au2606",
            tif="GFD",
            dry_run=dry_run,
            allow_submit=allow_submit,
        )

        assert results[0].status is ExecutionGatewayResultStatus.REJECTED_INVALID_ORDER
        assert results[0].command is None
        assert repository.commands == {}
        assert adapter.submitted_commands == []
