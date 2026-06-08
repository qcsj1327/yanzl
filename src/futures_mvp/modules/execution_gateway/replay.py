from collections.abc import Iterable

from futures_mvp.domain.enums import ExecutionGatewayResultStatus, ExecutionTarget
from futures_mvp.domain.models import ExecutionGatewayResult, OrderState
from futures_mvp.modules.execution_gateway.service import ExecutionGatewayService


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
    return [
        service.submit(
            order,
            execution_target=execution_target,
            symbol=symbol,
            trade_instrument_id=trade_instrument_id,
            tif=tif,
            dry_run=dry_run,
        )
        for order in ordered
    ]
