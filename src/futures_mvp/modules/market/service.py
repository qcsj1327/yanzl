from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from futures_mvp.domain.enums import MarketDataEventType, MarketDataResultStatus
from futures_mvp.domain.models import Bar, DataQualityResult, Tick
from futures_mvp.interfaces.repositories import MarketDataConflictError, MarketDataUnitOfWork
from futures_mvp.modules.market.canonical import canonical_bar_payload, canonical_tick_payload
from futures_mvp.modules.market.quality import DataQualityGate, DataQualityPolicy


@dataclass(frozen=True)
class MarketDataIngestResult:
    result: DataQualityResult
    tick: Tick | None = None
    bar: Bar | None = None


class MarketDataService:
    def __init__(
        self,
        uow_factory: Callable[[], MarketDataUnitOfWork],
        gate: DataQualityGate | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._gate = gate or DataQualityGate()

    def ingest_tick(
        self,
        tick: Tick,
        *,
        policy: DataQualityPolicy | None = None,
        in_session: bool = True,
        previous_ts: datetime | None = None,
        gap_detected: bool = False,
    ) -> MarketDataIngestResult:
        quality = self._gate.validate_tick(
            tick,
            policy=policy,
            in_session=in_session,
            previous_ts=previous_ts,
            gap_detected=gap_detected,
        )
        if not _should_persist(quality, policy or DataQualityPolicy()):
            return MarketDataIngestResult(result=quality)
        with self._uow_factory() as uow:
            existing = uow.market_ticks.get_by_identity(
                tick.exchange,
                tick.instrument_id,
                tick.ts,
                tick.source,
            )
            if existing is not None:
                if canonical_tick_payload(existing) == canonical_tick_payload(tick):
                    return MarketDataIngestResult(
                        result=_duplicate_result(tick=tick),
                        tick=existing,
                    )
                return MarketDataIngestResult(result=_canonical_conflict_result(tick=tick))
            try:
                persisted = uow.market_ticks.append_tick(tick)
            except MarketDataConflictError:
                return MarketDataIngestResult(result=_canonical_conflict_result(tick=tick))
            uow.commit()
            return MarketDataIngestResult(result=quality, tick=persisted)

    def ingest_bar(
        self,
        bar: Bar,
        *,
        policy: DataQualityPolicy | None = None,
        in_session: bool = True,
        previous_ts: datetime | None = None,
        gap_detected: bool = False,
    ) -> MarketDataIngestResult:
        quality = self._gate.validate_bar(
            bar,
            policy=policy,
            in_session=in_session,
            previous_ts=previous_ts,
            gap_detected=gap_detected,
        )
        if not _should_persist(quality, policy or DataQualityPolicy()):
            return MarketDataIngestResult(result=quality)
        with self._uow_factory() as uow:
            existing = uow.market_bars.get_by_identity(
                bar.exchange,
                bar.instrument_id,
                bar.timeframe,
                bar.bar_ts,
                bar.source,
            )
            if existing is not None:
                if canonical_bar_payload(existing) == canonical_bar_payload(bar):
                    return MarketDataIngestResult(
                        result=_duplicate_result(bar=bar),
                        bar=existing,
                    )
                return MarketDataIngestResult(result=_canonical_conflict_result(bar=bar))
            try:
                persisted = uow.market_bars.append_bar(bar)
            except MarketDataConflictError:
                return MarketDataIngestResult(result=_canonical_conflict_result(bar=bar))
            uow.commit()
            return MarketDataIngestResult(result=quality, bar=persisted)


def _should_persist(result: DataQualityResult, policy: DataQualityPolicy) -> bool:
    if result.status is MarketDataResultStatus.ACCEPTED:
        return True
    return result.status is MarketDataResultStatus.GAP_DETECTED and policy.allow_gap


def _duplicate_result(*, tick: Tick | None = None, bar: Bar | None = None) -> DataQualityResult:
    fact = tick or bar
    if fact is None:
        raise ValueError("tick or bar is required")
    ts = fact.ts if isinstance(fact, Tick) else fact.bar_ts
    return DataQualityResult(
        status=MarketDataResultStatus.DUPLICATE,
        event_type=MarketDataEventType.DUPLICATE,
        instrument_id=fact.instrument_id,
        exchange=fact.exchange,
        trading_day=fact.trading_day,
        ts=ts,
        reason="duplicate",
    )


def _canonical_conflict_result(
    *,
    tick: Tick | None = None,
    bar: Bar | None = None,
) -> DataQualityResult:
    fact = tick or bar
    if fact is None:
        raise ValueError("tick or bar is required")
    ts = fact.ts if isinstance(fact, Tick) else fact.bar_ts
    return DataQualityResult(
        status=MarketDataResultStatus.ERROR,
        event_type=MarketDataEventType.ERROR,
        instrument_id=fact.instrument_id,
        exchange=fact.exchange,
        trading_day=fact.trading_day,
        ts=ts,
        reason="canonical_conflict",
    )
