from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from futures_mvp.modules.market_data.models import ContractRole, InstrumentContract

STATIC_FIXTURE_SOURCE = "static_fixture"


def _contract(
    symbol: str,
    instrument_id: str,
    exchange: str,
    role: ContractRole,
    effective_from: str,
    effective_to: str,
) -> InstrumentContract:
    return InstrumentContract(
        symbol=symbol,
        instrument_id=instrument_id,
        exchange=exchange,
        role=role,
        effective_from=date.fromisoformat(effective_from),
        effective_to=date.fromisoformat(effective_to),
        source=STATIC_FIXTURE_SOURCE,
    )


STATIC_INSTRUMENT_FIXTURE: tuple[InstrumentContract, ...] = (
    _contract("ao", "ao", "SHFE", ContractRole.BASE_SYMBOL, "2026-01-01", "2026-12-31"),
    _contract("ao", "ao9999", "SHFE", ContractRole.CONTINUOUS_MAIN, "2026-01-01", "2026-12-31"),
    _contract("ao", "ao2609", "SHFE", ContractRole.TRADE_CONTRACT, "2026-01-01", "2026-12-31"),
    _contract("ao", "ao2509", "SHFE", ContractRole.EXPIRED_CONTRACT, "2025-01-01", "2025-12-31"),
    _contract("rb", "rb", "SHFE", ContractRole.BASE_SYMBOL, "2026-01-01", "2026-12-31"),
    _contract("rb", "rb9999", "SHFE", ContractRole.CONTINUOUS_MAIN, "2026-01-01", "2026-12-31"),
    _contract("rb", "rb2610", "SHFE", ContractRole.TRADE_CONTRACT, "2026-01-01", "2026-12-31"),
    _contract("rb", "rb2510", "SHFE", ContractRole.EXPIRED_CONTRACT, "2025-01-01", "2025-12-31"),
    _contract("ag", "ag", "SHFE", ContractRole.BASE_SYMBOL, "2026-01-01", "2026-12-31"),
    _contract("ag", "ag9999", "SHFE", ContractRole.CONTINUOUS_MAIN, "2026-01-01", "2026-12-31"),
    _contract("ag", "ag2608", "SHFE", ContractRole.TRADE_CONTRACT, "2026-01-01", "2026-12-31"),
    _contract("cu", "cu", "SHFE", ContractRole.BASE_SYMBOL, "2026-01-01", "2026-12-31"),
    _contract("cu", "cu9999", "SHFE", ContractRole.CONTINUOUS_MAIN, "2026-01-01", "2026-12-31"),
    _contract("cu", "cu2608", "SHFE", ContractRole.TRADE_CONTRACT, "2026-01-01", "2026-12-31"),
)


@dataclass(frozen=True)
class InstrumentRegistry:
    contracts: tuple[InstrumentContract, ...] = STATIC_INSTRUMENT_FIXTURE

    @classmethod
    def from_contracts(cls, contracts: Iterable[InstrumentContract]) -> InstrumentRegistry:
        return cls(tuple(contracts))

    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted({contract.symbol for contract in self.contracts}))

    def list_contracts(self, symbol: str) -> tuple[InstrumentContract, ...]:
        normalized = symbol.strip().lower()
        return tuple(contract for contract in self.contracts if contract.symbol == normalized)
