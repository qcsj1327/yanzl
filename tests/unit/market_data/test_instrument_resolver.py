from datetime import date
from decimal import Decimal

from futures_mvp.modules.market_data.models import (
    ContractRole,
    InstrumentContract,
    InstrumentMetadata,
    InstrumentResolveStatus,
)
from futures_mvp.modules.market_data.registry import InstrumentRegistry
from futures_mvp.modules.market_data.resolver import InstrumentResolver

_DEFAULT_METADATA = object()


def test_resolve_supported_symbols_valid_day_returns_static_main_and_trade_contracts() -> None:
    expected = {
        "ao": ("ao9999", "ao2609"),
        "rb": ("rb9999", "rb2610"),
        "ag": ("ag9999", "ag2608"),
        "cu": ("cu9999", "cu2608"),
    }

    for symbol, (main_contract, trade_contract) in expected.items():
        resolution = InstrumentResolver().resolve(symbol.upper(), date(2026, 6, 12))

        assert resolution.status is InstrumentResolveStatus.RESOLVED
        assert resolution.symbol == symbol
        assert resolution.instrument_id == main_contract
        assert resolution.trade_instrument_id == trade_contract
        assert resolution.exchange == "SHFE"
        assert resolution.source == "static_fixture"
        assert resolution.confidence == "static_fixture"
        assert resolution.effective_from == date(2026, 1, 1)
        assert resolution.effective_to == date(2026, 12, 31)
        assert resolution.metadata is not None
        assert resolution.metadata.tick_size > 0
        assert resolution.metadata.contract_multiplier > 0
        assert resolution.metadata.min_order_qty > 0
        assert "source=static_fixture" in resolution.diagnostics
        assert "static fixture only, not live market source" in resolution.diagnostics
        assert f"selected main contract={main_contract}" in resolution.diagnostics
        assert f"selected trade contract={trade_contract}" in resolution.diagnostics
        assert "effective window=2026-01-01/2026-12-31" in resolution.diagnostics
        assert any(item.startswith("metadata=product_name:") for item in resolution.diagnostics)


def test_all_fixture_contracts_have_static_metadata() -> None:
    registry = InstrumentRegistry()

    for contract in registry.contracts:
        assert contract.metadata is not None
        assert contract.metadata.product_name
        assert contract.metadata.tick_size > 0
        assert contract.metadata.contract_multiplier > 0
        assert contract.metadata.min_order_qty > 0
        assert contract.metadata.price_limit_ref
        assert contract.metadata.trading_session_ref


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


def test_missing_main_or_trade_returns_not_found_with_diagnostic() -> None:
    missing_main = InstrumentRegistry.from_contracts(
        (
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
    missing_trade = InstrumentRegistry.from_contracts(
        (
            InstrumentContract(
                symbol="ao",
                instrument_id="ao9999",
                exchange="SHFE",
                role=ContractRole.CONTINUOUS_MAIN,
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
            ),
        )
    )

    missing_main_resolution = InstrumentResolver(missing_main).resolve("ao", "2026-06-12")
    missing_trade_resolution = InstrumentResolver(missing_trade).resolve("ao", "2026-06-12")

    assert missing_main_resolution.status is InstrumentResolveStatus.NOT_FOUND
    assert "main contract and trade contract must both exist" in missing_main_resolution.diagnostics
    assert missing_trade_resolution.status is InstrumentResolveStatus.NOT_FOUND
    assert (
        "main contract and trade contract must both exist"
        in missing_trade_resolution.diagnostics
    )


def test_exchange_mismatch_returns_ambiguous_with_diagnostic() -> None:
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
                instrument_id="ao2609",
                exchange="DCE",
                role=ContractRole.TRADE_CONTRACT,
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
            ),
        )
    )

    resolution = InstrumentResolver(registry).resolve("ao", "2026-06-12")

    assert resolution.status is InstrumentResolveStatus.AMBIGUOUS
    assert "main and trade contracts resolve to different exchanges" in resolution.diagnostics


def test_main_contract_metadata_missing_returns_metadata_invalid() -> None:
    registry = InstrumentRegistry.from_contracts(
        (
            _contract("ao9999", ContractRole.CONTINUOUS_MAIN, metadata=None),
            _contract("ao2609", ContractRole.TRADE_CONTRACT),
        )
    )

    resolution = InstrumentResolver(registry).resolve("ao", "2026-06-12")

    assert resolution.status is InstrumentResolveStatus.METADATA_INVALID
    assert "static fixture only, not live market source" in resolution.diagnostics
    assert "metadata invalid / missing" in resolution.diagnostics
    assert "main contract ao9999 metadata missing" in resolution.diagnostics


def test_trade_contract_metadata_missing_returns_metadata_invalid() -> None:
    registry = InstrumentRegistry.from_contracts(
        (
            _contract("ao9999", ContractRole.CONTINUOUS_MAIN),
            _contract("ao2609", ContractRole.TRADE_CONTRACT, metadata=None),
        )
    )

    resolution = InstrumentResolver(registry).resolve("ao", "2026-06-12")

    assert resolution.status is InstrumentResolveStatus.METADATA_INVALID
    assert "trade contract ao2609 metadata missing" in resolution.diagnostics


def test_invalid_positive_metadata_fields_return_metadata_invalid() -> None:
    invalid_cases = (
        (_metadata(tick_size="0"), "tick_size <= 0"),
        (_metadata(contract_multiplier="0"), "contract_multiplier <= 0"),
        (_metadata(min_order_qty="0"), "min_order_qty <= 0"),
    )

    for metadata, diagnostic in invalid_cases:
        registry = InstrumentRegistry.from_contracts(
            (
                _contract("ao9999", ContractRole.CONTINUOUS_MAIN),
                _contract("ao2609", ContractRole.TRADE_CONTRACT, metadata=metadata),
            )
        )

        resolution = InstrumentResolver(registry).resolve("ao", "2026-06-12")

        assert resolution.status is InstrumentResolveStatus.METADATA_INVALID
        assert f"trade contract ao2609 metadata invalid: {diagnostic}" in resolution.diagnostics


def test_invalid_text_metadata_fields_return_metadata_invalid() -> None:
    invalid_cases = (
        (_metadata(product_name=""), "product_name empty"),
        (_metadata(price_limit_ref=""), "price_limit_ref empty"),
        (_metadata(trading_session_ref=""), "trading_session_ref empty"),
    )

    for metadata, diagnostic in invalid_cases:
        registry = InstrumentRegistry.from_contracts(
            (
                _contract("ao9999", ContractRole.CONTINUOUS_MAIN),
                _contract("ao2609", ContractRole.TRADE_CONTRACT, metadata=metadata),
            )
        )

        resolution = InstrumentResolver(registry).resolve("ao", "2026-06-12")

        assert resolution.status is InstrumentResolveStatus.METADATA_INVALID
        assert f"trade contract ao2609 metadata invalid: {diagnostic}" in resolution.diagnostics


def _contract(
    instrument_id: str,
    role: ContractRole,
    *,
    metadata: InstrumentMetadata | None | object = _DEFAULT_METADATA,
) -> InstrumentContract:
    resolved_metadata = _metadata() if metadata is _DEFAULT_METADATA else metadata
    assert resolved_metadata is None or isinstance(resolved_metadata, InstrumentMetadata)
    return InstrumentContract(
        symbol="ao",
        instrument_id=instrument_id,
        exchange="SHFE",
        role=role,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        metadata=resolved_metadata,
    )


def _metadata(
    *,
    product_name: str = "氧化铝",
    tick_size: str = "1",
    contract_multiplier: str = "20",
    min_order_qty: str = "1",
    price_limit_ref: str = "static_fixture_price_limit_placeholder",
    trading_session_ref: str = "static_fixture_day_night_session_placeholder",
) -> InstrumentMetadata:
    return InstrumentMetadata(
        product_name=product_name,
        tick_size=Decimal(tick_size),
        contract_multiplier=Decimal(contract_multiplier),
        min_order_qty=Decimal(min_order_qty),
        price_limit_ref=price_limit_ref,
        trading_session_ref=trading_session_ref,
    )
