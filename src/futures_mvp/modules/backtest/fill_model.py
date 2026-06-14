from __future__ import annotations

from dataclasses import dataclass

from futures_mvp.modules.backtest.models import (
    FillModelResult,
    FillModelStatus,
    SimulatedOrder,
)


@dataclass(frozen=True)
class NoFillModel:
    reason: str = "no fill model selected"

    def fill(self, order: SimulatedOrder) -> FillModelResult:
        return FillModelResult(
            status=FillModelStatus.NO_FILL,
            simulated_trade=None,
            diagnostics=(
                self.reason,
                "research-only no-fill model",
                "no Trade ledger, Accounting fact, OMS truth, or equity change",
                f"order_id={order.order_id}",
            ),
        )
