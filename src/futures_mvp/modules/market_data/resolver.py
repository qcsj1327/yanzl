from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

from futures_mvp.modules.market_data.models import (
    ContractRole,
    InstrumentContract,
    InstrumentResolution,
    InstrumentResolveStatus,
)
from futures_mvp.modules.market_data.registry import InstrumentRegistry

_SYMBOL_PATTERN = re.compile(r"^[a-z][a-z0-9]*$")
_TRADING_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class InstrumentResolver:
    def __init__(self, registry: InstrumentRegistry | None = None) -> None:
        self._registry = registry or InstrumentRegistry()

    def resolve(self, symbol: str, trading_day: str | date) -> InstrumentResolution:
        normalized_symbol = _normalize_symbol(symbol)
        if normalized_symbol is None:
            return InstrumentResolution(
                status=InstrumentResolveStatus.INVALID_INPUT,
                symbol="",
                diagnostics=(
                    "symbol must be non-empty lowercase alphanumeric after normalization",
                ),
            )
        parsed_day = _normalize_trading_day(trading_day)
        if parsed_day is None:
            return InstrumentResolution(
                status=InstrumentResolveStatus.INVALID_INPUT,
                symbol=normalized_symbol,
                diagnostics=("trading_day must be an ISO date YYYY-MM-DD",),
            )

        contracts = self._registry.list_contracts(normalized_symbol)
        if not contracts:
            return InstrumentResolution(
                status=InstrumentResolveStatus.NOT_FOUND,
                symbol=normalized_symbol,
                diagnostics=(
                    "static fixture only, not live market source",
                    "no contract fixture for symbol",
                ),
            )

        active = tuple(
            contract
            for contract in contracts
            if contract.effective_from <= parsed_day <= contract.effective_to
        )
        if not active:
            return InstrumentResolution(
                status=InstrumentResolveStatus.EXPIRED,
                symbol=normalized_symbol,
                diagnostics=(
                    "static fixture only, not live market source",
                    "no contract effective window covers trading_day",
                ),
            )

        main = _contracts_by_role(active, ContractRole.CONTINUOUS_MAIN)
        trade = _contracts_by_role(active, ContractRole.TRADE_CONTRACT)
        if len(main) > 1 or len(trade) > 1:
            return InstrumentResolution(
                status=InstrumentResolveStatus.AMBIGUOUS,
                symbol=normalized_symbol,
                diagnostics=(
                    "static fixture only, not live market source",
                    "multiple main or trade contracts cover trading_day",
                ),
            )
        if len(main) != 1 or len(trade) != 1:
            return InstrumentResolution(
                status=InstrumentResolveStatus.NOT_FOUND,
                symbol=normalized_symbol,
                diagnostics=(
                    "static fixture only, not live market source",
                    "main contract and trade contract must both exist",
                ),
            )
        main_contract = main[0]
        trade_contract = trade[0]
        if main_contract.exchange != trade_contract.exchange:
            return InstrumentResolution(
                status=InstrumentResolveStatus.AMBIGUOUS,
                symbol=normalized_symbol,
                diagnostics=(
                    "static fixture only, not live market source",
                    "main and trade contracts resolve to different exchanges",
                ),
            )
        metadata_diagnostics = _metadata_invalid_diagnostics(main_contract, trade_contract)
        if metadata_diagnostics:
            return InstrumentResolution(
                status=InstrumentResolveStatus.METADATA_INVALID,
                symbol=normalized_symbol,
                instrument_id=main_contract.instrument_id,
                trade_instrument_id=trade_contract.instrument_id,
                exchange=main_contract.exchange,
                source=main_contract.source,
                confidence="none",
                effective_from=max(main_contract.effective_from, trade_contract.effective_from),
                effective_to=min(main_contract.effective_to, trade_contract.effective_to),
                diagnostics=(
                    "static fixture only, not live market source",
                    "metadata invalid / missing",
                    *metadata_diagnostics,
                ),
            )
        return InstrumentResolution(
            status=InstrumentResolveStatus.RESOLVED,
            symbol=normalized_symbol,
            instrument_id=main_contract.instrument_id,
            trade_instrument_id=trade_contract.instrument_id,
            exchange=main_contract.exchange,
            source=main_contract.source,
            confidence="static_fixture",
            effective_from=max(main_contract.effective_from, trade_contract.effective_from),
            effective_to=min(main_contract.effective_to, trade_contract.effective_to),
            metadata=trade_contract.metadata,
            diagnostics=(
                f"source={main_contract.source}",
                "static fixture only, not live market source",
                f"selected main contract={main_contract.instrument_id}",
                f"selected trade contract={trade_contract.instrument_id}",
                (
                    "effective window="
                    f"{max(main_contract.effective_from, trade_contract.effective_from)}"
                    f"/{min(main_contract.effective_to, trade_contract.effective_to)}"
                ),
                _metadata_summary(trade_contract),
                "resolver does not create signal, direction, price or quantity",
            ),
        )


def resolve(symbol: str, trading_day: str | date) -> InstrumentResolution:
    return InstrumentResolver().resolve(symbol, trading_day)


def _normalize_symbol(symbol: str) -> str | None:
    normalized = symbol.strip().lower()
    if not normalized or _SYMBOL_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def _normalize_trading_day(trading_day: str | date) -> date | None:
    if isinstance(trading_day, date):
        return trading_day
    if _TRADING_DAY_PATTERN.fullmatch(trading_day.strip()) is None:
        return None
    try:
        return date.fromisoformat(trading_day.strip())
    except ValueError:
        return None


def _contracts_by_role(
    contracts: Iterable[InstrumentContract],
    role: ContractRole,
) -> tuple[InstrumentContract, ...]:
    return tuple(contract for contract in contracts if contract.role is role)


def _metadata_summary(contract: InstrumentContract) -> str:
    metadata = contract.metadata
    if metadata is None:
        return "metadata unavailable"
    return (
        "metadata="
        f"product_name:{metadata.product_name},"
        f"tick_size:{metadata.tick_size},"
        f"contract_multiplier:{metadata.contract_multiplier},"
        f"min_order_qty:{metadata.min_order_qty},"
        f"price_limit_ref:{metadata.price_limit_ref},"
        f"trading_session_ref:{metadata.trading_session_ref}"
    )


def _metadata_invalid_diagnostics(
    main_contract: InstrumentContract,
    trade_contract: InstrumentContract,
) -> tuple[str, ...]:
    return (
        *_contract_metadata_invalid_diagnostics("main", main_contract),
        *_contract_metadata_invalid_diagnostics("trade", trade_contract),
    )


def _contract_metadata_invalid_diagnostics(
    role_name: str,
    contract: InstrumentContract,
) -> tuple[str, ...]:
    metadata = contract.metadata
    prefix = f"{role_name} contract {contract.instrument_id}"
    if metadata is None:
        return (f"{prefix} metadata missing",)
    diagnostics: list[str] = []
    if not metadata.product_name.strip():
        diagnostics.append(f"{prefix} metadata invalid: product_name empty")
    if metadata.tick_size <= 0:
        diagnostics.append(f"{prefix} metadata invalid: tick_size <= 0")
    if metadata.contract_multiplier <= 0:
        diagnostics.append(f"{prefix} metadata invalid: contract_multiplier <= 0")
    if metadata.min_order_qty <= 0:
        diagnostics.append(f"{prefix} metadata invalid: min_order_qty <= 0")
    if not metadata.price_limit_ref.strip():
        diagnostics.append(f"{prefix} metadata invalid: price_limit_ref empty")
    if not metadata.trading_session_ref.strip():
        diagnostics.append(f"{prefix} metadata invalid: trading_session_ref empty")
    return tuple(diagnostics)
