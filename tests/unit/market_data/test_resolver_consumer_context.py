from datetime import date

from futures_mvp.modules.market_data.consumer import (
    build_resolver_consumer_context,
    resolver_context_command_mismatch,
)
from futures_mvp.modules.market_data.models import (
    InstrumentResolution,
    InstrumentResolveStatus,
)
from futures_mvp.modules.market_data.resolver import InstrumentResolver


def test_resolved_resolution_builds_resolver_consumer_context() -> None:
    resolution = InstrumentResolver().resolve("ao", "2026-06-12")

    result = build_resolver_consumer_context(resolution)

    assert result.blocked is False
    assert result.context is not None
    assert result.context.identity.symbol == "ao"
    assert result.context.identity.instrument_id == "ao9999"
    assert result.context.identity.trade_instrument_id == "ao2609"
    assert result.context.identity.exchange == "SHFE"
    assert result.context.identity.trading_day == date(2026, 6, 12)
    assert result.context.lineage.resolver_source == "static_fixture"
    assert result.context.lineage.resolver_confidence == "static_fixture"
    assert result.context.lineage.resolver_effective_from == date(2026, 1, 1)
    assert result.context.lineage.resolver_effective_to == date(2026, 12, 31)
    assert "static fixture only, not live market source" in (
        result.context.lineage.resolver_diagnostics_summary
    )
    assert result.context.lineage.metadata_summary is not None
    assert "product_name:" in result.context.lineage.metadata_summary


def test_unresolved_statuses_fail_to_build_context() -> None:
    for status in (
        InstrumentResolveStatus.NOT_FOUND,
        InstrumentResolveStatus.INVALID_INPUT,
        InstrumentResolveStatus.EXPIRED,
        InstrumentResolveStatus.AMBIGUOUS,
        InstrumentResolveStatus.METADATA_INVALID,
    ):
        result = build_resolver_consumer_context(
            InstrumentResolution(status=status, symbol="ao")
        )

        assert result.blocked is True
        assert result.context is None
        assert result.reason == f"resolver status is not RESOLVED: {status.value}"


def test_resolved_resolution_missing_identity_fields_fails_closed() -> None:
    result = build_resolver_consumer_context(
        InstrumentResolution(
            status=InstrumentResolveStatus.RESOLVED,
            symbol="ao",
        )
    )

    assert result.blocked is True
    assert result.context is None
    assert result.reason is not None
    assert "resolver resolved identity missing fields" in result.reason


def test_context_command_identity_mismatch_is_reported() -> None:
    context_result = build_resolver_consumer_context(
        InstrumentResolver().resolve("ao", "2026-06-12")
    )
    assert context_result.context is not None

    class Command:
        symbol = "ao"
        instrument_id = "ao9999"
        trade_instrument_id = "manual2609"
        exchange = "SHFE"

    assert (
        resolver_context_command_mismatch(context_result.context, Command())
        == "resolver identity mismatch: trade_instrument_id"
    )
