from collections.abc import Iterable

from futures_mvp.domain.enums import (
    ExecutionCommandType,
    ExecutionGatewayResultStatus,
    ExecutionTarget,
    OrderStatus,
)
from futures_mvp.domain.models import ExecutionGatewayResult, OrderState
from futures_mvp.modules.execution_gateway.service import ExecutionGatewayService

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


def replay_execution_gateway(
    service: ExecutionGatewayService,
    orders: Iterable[OrderState],
    *,
    execution_target: ExecutionTarget = ExecutionTarget.MOCK,
    symbol: str,
    trade_instrument_id: str,
    tif: str,
    dry_run: bool = True,
    allow_submit: bool = False,
    stop_on_conflict: bool = True,
) -> list[ExecutionGatewayResult]:
    ordered = sorted(
        orders,
        key=lambda order: (
            order.request.exchange,
            order.request.instrument_id,
            order.order_id,
            order.request.client_order_id,
        ),
    )
    if not dry_run and not allow_submit:
        return [
            ExecutionGatewayResult(
                status=ExecutionGatewayResultStatus.ERROR,
                reason="live replay submit requires allow_submit=True",
            )
            for _ in ordered
        ]
    if dry_run:
        return [
            _preview_order(
                service,
                order,
                execution_target=execution_target,
                symbol=symbol,
                trade_instrument_id=trade_instrument_id,
                tif=tif,
            )
            for order in ordered
        ]

    results: list[ExecutionGatewayResult] = []
    for order in ordered:
        result = service.submit(
            order,
            execution_target=execution_target,
            symbol=symbol,
            trade_instrument_id=trade_instrument_id,
            tif=tif,
            dry_run=False,
        )
        results.append(result)
        if stop_on_conflict and result.status in {
            ExecutionGatewayResultStatus.CONFLICT,
            ExecutionGatewayResultStatus.ERROR,
        }:
            break
    return results


def _preview_order(
    service: ExecutionGatewayService,
    order: OrderState,
    *,
    execution_target: ExecutionTarget,
    symbol: str,
    trade_instrument_id: str,
    tif: str,
) -> ExecutionGatewayResult:
    invalid_reason = _invalid_order_reason(
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
    try:
        command = service.build_command(
            order,
            execution_target=execution_target,
            command_type=ExecutionCommandType.SUBMIT_ORDER,
            symbol=symbol,
            trade_instrument_id=trade_instrument_id,
            tif=tif,
        )
    except ValueError as exc:
        return ExecutionGatewayResult(
            status=ExecutionGatewayResultStatus.ERROR,
            reason=str(exc),
        )
    return ExecutionGatewayResult(
        status=ExecutionGatewayResultStatus.COMMAND_CREATED,
        command=command,
        reason="dry_run_preview",
    )


def _invalid_order_reason(
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
