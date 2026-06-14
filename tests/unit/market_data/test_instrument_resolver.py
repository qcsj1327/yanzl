from datetime import date

from futures_mvp.modules.market_data.models import (
    ContractRole,
    InstrumentContract,
    InstrumentResolveStatus,
)
from futures_mvp.modules.market_data.registry import InstrumentRegistry
from futures_mvp.modules.market_data.resolver import InstrumentResolver


def test_resolve_ao_valid_day_returns_static_main_and_trade_contract() -> None:
    resolution = InstrumentResolver().resolve("AO", "2026-06-12")

    assert resolution.status is InstrumentResolveStatus.RESOLVED
    assert resolution.symbol == "ao"
    assert resolution.instrument_id == "ao9999"
    assert resolution.trade_instrument_id == "ao2609"
    assert resolution.exchange == "SHFE"
    assert resolution.source == "static_fixture"
    assert resolution.confidence == "static_fixture"
    assert resolution.effective_from == date(2026, 1, 1)
    assert resolution.effective_to == date(2026, 12, 31)
    assert "static fixture only, not live market source" in resolution.diagnostics


def test_resolve_rb_valid_day_returns_resolved() -> None:
    resolution = InstrumentResolver().resolve("rb", date(2026, 6, 12))

    assert resolution.status is InstrumentResolveStatus.RESOLVED
    assert resolution.instrument_id == "rb9999"
    assert resolution.trade_instrument_id == "rb2610"


def test_unknown_symbol_returns_not_found() -> None:
    resolution = InstrumentResolver().resolve("zz", "2026-06-12")

    assert resolution.status is InstrumentResolveStatus.NOT_FOUND
    assert resolution.instrument_id is None
    assert resolution.trade_instrument_id is None


def test_invalid_symbol_or_trading_day_returns_invalid_input() -> None:
    bad_symbol = InstrumentResolver().resolve("ao-2609", "2026-06-12")
    bad_day = InstrumentResolver().resolve("ao", "20260612")

    assert bad_symbol.status is InstrumentResolveStatus.INVALID_INPUT
    assert bad_day.status is InstrumentResolveStatus.INVALID_INPUT


def test_expired_trading_day_returns_expired() -> None:
    resolution = InstrumentResolver().resolve("ao", "2027-01-01")

    assert resolution.status is InstrumentResolveStatus.EXPIRED
    assert resolution.instrument_id is None
    assert resolution.trade_instrument_id is None


def test_ambiguous_fixture_returns_ambiguous() -> None:
    registry = InstrumentRegistry.from_contracts(
        (
            InstrumentContract(
                symbol="ao",
                instrument_id="ao9999",
                exchange="SHFE",
                role=ContractRole.CONTINUOUS_MAIN,
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
            ),
            InstrumentContract(
                symbol="ao",
                instrument_id="ao8888",
                exchange="SHFE",
                role=ContractRole.CONTINUOUS_MAIN,
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
            ),
            InstrumentContract(
                symbol="ao",
                instrument_id="ao2609",
                exchange="SHFE",
                role=ContractRole.TRADE_CONTRACT,
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
            ),
        )
    )

    resolution = InstrumentResolver(registry).resolve("ao", "2026-06-12")

    assert resolution.status is InstrumentResolveStatus.AMBIGUOUS
