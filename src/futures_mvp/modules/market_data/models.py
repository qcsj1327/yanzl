from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class ContractRole(StrEnum):
    BASE_SYMBOL = "BASE_SYMBOL"
    CONTINUOUS_MAIN = "CONTINUOUS_MAIN"
    TRADE_CONTRACT = "TRADE_CONTRACT"
    EXPIRED_CONTRACT = "EXPIRED_CONTRACT"


class InstrumentResolveStatus(StrEnum):
    RESOLVED = "RESOLVED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    EXPIRED = "EXPIRED"
    INVALID_INPUT = "INVALID_INPUT"
    METADATA_INVALID = "METADATA_INVALID"


@dataclass(frozen=True)
class InstrumentMetadata:
    product_name: str
    tick_size: Decimal
    contract_multiplier: Decimal
    min_order_qty: Decimal
    price_limit_ref: str
    trading_session_ref: str


@dataclass(frozen=True)
class InstrumentContract:
    symbol: str
    instrument_id: str
    exchange: str
    role: ContractRole
    effective_from: date
    effective_to: date
    source: str = "static_fixture"
    metadata: InstrumentMetadata | None = None


@dataclass(frozen=True)
class InstrumentResolution:
    status: InstrumentResolveStatus
    symbol: str
    trading_day: date | None = None
    instrument_id: str | None = None
    trade_instrument_id: str | None = None
    exchange: str | None = None
    source: str | None = None
    confidence: str = "none"
    effective_from: date | None = None
    effective_to: date | None = None
    metadata: InstrumentMetadata | None = None
    diagnostics: tuple[str, ...] = ()
