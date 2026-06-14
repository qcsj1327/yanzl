from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from futures_mvp.modules.market_data.models import (
    InstrumentMetadata,
    InstrumentResolution,
    InstrumentResolveStatus,
)


@dataclass(frozen=True)
class ResolverLineage:
    resolver_source: str
    resolver_confidence: str
    resolver_effective_from: date
    resolver_effective_to: date
    resolver_diagnostics_summary: str
    metadata_summary: str | None = None


@dataclass(frozen=True)
class ResolvedInstrumentIdentity:
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date


@dataclass(frozen=True)
class ResolverConsumerContext:
    identity: ResolvedInstrumentIdentity
    lineage: ResolverLineage


@dataclass(frozen=True)
class ResolverConsumerContextBuildResult:
    blocked: bool
    context: ResolverConsumerContext | None = None
    reason: str | None = None


def build_resolver_consumer_context(
    resolution: InstrumentResolution,
) -> ResolverConsumerContextBuildResult:
    if resolution.status is not InstrumentResolveStatus.RESOLVED:
        return ResolverConsumerContextBuildResult(
            blocked=True,
            reason=f"resolver status is not RESOLVED: {resolution.status.value}",
        )
    missing = _missing_resolution_fields(resolution)
    if missing:
        return ResolverConsumerContextBuildResult(
            blocked=True,
            reason=f"resolver resolved identity missing fields: {', '.join(missing)}",
        )
    assert resolution.instrument_id is not None
    assert resolution.trade_instrument_id is not None
    assert resolution.exchange is not None
    assert resolution.source is not None
    assert resolution.effective_from is not None
    assert resolution.effective_to is not None
    assert resolution.trading_day is not None
    return ResolverConsumerContextBuildResult(
        blocked=False,
        context=ResolverConsumerContext(
            identity=ResolvedInstrumentIdentity(
                symbol=resolution.symbol,
                instrument_id=resolution.instrument_id,
                trade_instrument_id=resolution.trade_instrument_id,
                exchange=resolution.exchange,
                trading_day=resolution.trading_day,
            ),
            lineage=ResolverLineage(
                resolver_source=resolution.source,
                resolver_confidence=resolution.confidence,
                resolver_effective_from=resolution.effective_from,
                resolver_effective_to=resolution.effective_to,
                resolver_diagnostics_summary="; ".join(resolution.diagnostics),
                metadata_summary=_metadata_summary(resolution.metadata),
            ),
        ),
    )


def resolver_context_command_mismatch(
    context: ResolverConsumerContext,
    command: Any,
) -> str | None:
    expected = context.identity
    checks = (
        ("symbol", expected.symbol),
        ("instrument_id", expected.instrument_id),
        ("trade_instrument_id", expected.trade_instrument_id),
        ("exchange", expected.exchange),
    )
    for field_name, expected_value in checks:
        if getattr(command, field_name, None) != expected_value:
            return f"resolver identity mismatch: {field_name}"
    return None


def _missing_resolution_fields(resolution: InstrumentResolution) -> tuple[str, ...]:
    missing: list[str] = []
    if not resolution.symbol:
        missing.append("symbol")
    for field_name in (
        "instrument_id",
        "trade_instrument_id",
        "exchange",
        "source",
        "effective_from",
        "effective_to",
        "trading_day",
    ):
        if getattr(resolution, field_name) is None:
            missing.append(field_name)
    return tuple(missing)


def _metadata_summary(metadata: InstrumentMetadata | None) -> str | None:
    if metadata is None:
        return None
    return (
        f"product_name:{metadata.product_name}; "
        f"tick_size:{metadata.tick_size}; "
        f"contract_multiplier:{metadata.contract_multiplier}; "
        f"min_order_qty:{metadata.min_order_qty}; "
        f"price_limit_ref:{metadata.price_limit_ref}; "
        f"trading_session_ref:{metadata.trading_session_ref}"
    )
