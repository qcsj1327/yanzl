from collections.abc import Callable
from datetime import UTC, datetime

from futures_mvp.domain.enums import (
    ExecutionCommandResultStatus,
    ExecutionCommandType,
    ExecutionGatewayResultStatus,
    ExecutionTarget,
    OrderStatus,
)
from futures_mvp.domain.models import (
    ExecutionCommand,
    ExecutionCommandResult,
    ExecutionGatewayResult,
    OrderState,
)
from futures_mvp.interfaces.repositories import (
    ExecutionCommandConflictError,
    ExecutionGatewayUnitOfWork,
)
from futures_mvp.modules.execution_gateway.canonical import (
    build_execution_command_payload_hash,
    canonical_execution_command_payload,
)
from futures_mvp.modules.execution_gateway.ids import build_execution_command_id
from futures_mvp.modules.execution_gateway.protocols import ExecutionAdapter

_TERMINAL_REJECT_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED_BY_RISK,
        OrderStatus.SUBMIT_FAILED,
        OrderStatus.REJECTED_BY_EXCHANGE,
        OrderStatus.EXPIRED,
    }
)


class ExecutionGatewayService:
    def __init__(
        self,
        uow_factory: Callable[[], ExecutionGatewayUnitOfWork],
        adapter: ExecutionAdapter,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._adapter = adapter
        self._clock = clock or (lambda: datetime.now(UTC))

    def submit(
        self,
        order: OrderState,
        *,
        symbol: str,
        trade_instrument_id: str,
        tif: str,
        execution_target: ExecutionTarget = ExecutionTarget.MOCK,
        command_type: ExecutionCommandType = ExecutionCommandType.SUBMIT_ORDER,
        dry_run: bool = False,
    ) -> ExecutionGatewayResult:
        invalid_reason = self._invalid_order_reason(
            order,
            symbol=symbol,
            trade_instrument_id=trade_instrument_id,
            tif=tif,
        )
        if invalid_reason is not None:
            return ExecutionGatewayResult(
                status=ExecutionGatewayResultStatus.REJECTED_INVALID_ORDER,
                reason=invalid_reason,
            )
        if execution_target is not ExecutionTarget.MOCK:
            return ExecutionGatewayResult(
                status=ExecutionGatewayResultStatus.REJECTED_UNSUPPORTED_TARGET,
                reason=f"unsupported execution_target: {execution_target.value}",
            )
        if command_type is not ExecutionCommandType.SUBMIT_ORDER:
            return ExecutionGatewayResult(
                status=ExecutionGatewayResultStatus.REJECTED_INVALID_ORDER,
                reason=f"unsupported command_type: {command_type.value}",
            )

        command = self.build_command(
            order,
            execution_target=execution_target,
            command_type=command_type,
            symbol=symbol,
            trade_instrument_id=trade_instrument_id,
            tif=tif,
        )
        if command.command_payload_hash != build_execution_command_payload_hash(command):
            return ExecutionGatewayResult(
                status=ExecutionGatewayResultStatus.ERROR,
                command=command,
                reason="command_payload_hash mismatch",
            )

        with self._uow_factory() as uow:
            existing = uow.execution_commands.get_by_command_id(command.command_id)
            if existing is not None:
                if canonical_execution_command_payload(
                    existing
                ) != canonical_execution_command_payload(command):
                    uow.rollback()
                    return ExecutionGatewayResult(
                        status=ExecutionGatewayResultStatus.CONFLICT,
                        command=existing,
                        reason="execution_command_canonical_conflict",
                    )
                uow.commit()
                return ExecutionGatewayResult(
                    status=ExecutionGatewayResultStatus.DUPLICATE,
                    command=existing,
                    command_result=ExecutionCommandResult(
                        command_id=existing.command_id,
                        order_id=existing.order_id,
                        status=ExecutionCommandResultStatus.DUPLICATE,
                        reason="duplicate",
                    ),
                    reason="duplicate",
                )
            try:
                persisted = uow.execution_commands.append_execution_command(command)
            except ExecutionCommandConflictError:
                uow.rollback()
                return ExecutionGatewayResult(
                    status=ExecutionGatewayResultStatus.CONFLICT,
                    command=command,
                    reason="execution_command_canonical_conflict",
                )
            uow.commit()

        if dry_run:
            return ExecutionGatewayResult(
                status=ExecutionGatewayResultStatus.COMMAND_CREATED,
                command=persisted,
                reason="dry_run",
            )

        command_result = self._adapter.submit(persisted)
        return ExecutionGatewayResult(
            status=ExecutionGatewayResultStatus.COMMAND_CREATED,
            command=persisted,
            command_result=command_result,
        )

    def build_command(
        self,
        order: OrderState,
        *,
        execution_target: ExecutionTarget,
        command_type: ExecutionCommandType,
        symbol: str,
        trade_instrument_id: str,
        tif: str,
    ) -> ExecutionCommand:
        command_id = build_execution_command_id(order.order_id, command_type, execution_target)
        request = order.request
        command = ExecutionCommand(
            command_id=command_id,
            order_id=order.order_id,
            client_order_id=request.client_order_id,
            account_id=request.account_id,
            symbol=symbol,
            instrument_id=request.instrument_id,
            trade_instrument_id=trade_instrument_id,
            exchange=request.exchange,
            side=request.direction,
            offset=request.offset,
            quantity=request.quantity,
            price=request.limit_price,
            order_type=request.order_type,
            tif=tif,
            command_type=command_type,
            execution_target=execution_target,
            command_payload_hash="pending",
            created_at=self._clock(),
        )
        return command.model_copy(
            update={"command_payload_hash": build_execution_command_payload_hash(command)}
        )

    def _invalid_order_reason(
        self,
        order: OrderState,
        *,
        symbol: str,
        trade_instrument_id: str,
        tif: str,
    ) -> str | None:
        if not order.order_id:
            return "order_id is required"
        request = order.request
        if not request.client_order_id:
            return "client_order_id is required"
        if not request.account_id:
            return "account_id is required"
        if not request.instrument_id:
            return "instrument_id is required"
        if not symbol:
            return "symbol is required"
        if not trade_instrument_id:
            return "trade_instrument_id is required"
        if not request.exchange:
            return "exchange is required"
        if not tif:
            return "tif is required"
        if request.quantity <= 0:
            return "quantity must be greater than 0"
        if request.limit_price <= 0:
            return "price must be greater than 0"
        if order.status in _TERMINAL_REJECT_STATUSES:
            return f"order status is not executable: {order.status.value}"
        return None
