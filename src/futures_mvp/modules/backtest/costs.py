from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from futures_mvp.modules.backtest.models import SimulatedOrder, SimulatedOrderIntent


@dataclass(frozen=True)
class FixedCommissionModel:
    commission_rate: Decimal = Decimal("0.0001")

    def commission(self, *, fill_price: Decimal, fill_qty: Decimal) -> Decimal:
        return fill_price * fill_qty * self.commission_rate


@dataclass(frozen=True)
class FixedSlippageModel:
    ticks: Decimal = Decimal("1")
    tick_size: Decimal = Decimal("1")

    def slippage(self) -> Decimal:
        return self.ticks * self.tick_size

    def apply(self, *, order: SimulatedOrder, base_price: Decimal) -> Decimal:
        adjustment = self.slippage()
        if order.intent is SimulatedOrderIntent.ENTRY:
            return base_price + adjustment
        return base_price - adjustment
