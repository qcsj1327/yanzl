from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class FixedQuantitySizing:
    quantity: Decimal = Decimal("1")

    def quantity_for_price(self, expected_price: Decimal) -> Decimal:
        return self.quantity


@dataclass(frozen=True)
class FixedCashSizing:
    cash_per_symbol: Decimal

    def quantity_for_price(self, expected_price: Decimal) -> Decimal:
        return self.cash_per_symbol / expected_price
