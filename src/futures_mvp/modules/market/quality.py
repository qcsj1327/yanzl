from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from futures_mvp.domain.enums import MarketDataEventType, MarketDataResultStatus
from futures_mvp.domain.models import Bar, DataQualityResult, Tick


@dataclass(frozen=True)
class DataQualityPolicy:
    allow_gap: bool = False


class DataQualityGate:
    def validate_tick(
        self,
        tick: Tick,
        *,
        policy: DataQualityPolicy | None = None,
        in_session: bool = True,
        previous_ts: datetime | None = None,
        gap_detected: bool = False,
    ) -> DataQualityResult:
        return self._validate_common(
            symbol=tick.symbol,
            instrument_id=tick.instrument_id,
            trade_instrument_id=tick.trade_instrument_id,
            exchange=tick.exchange,
            trading_day=tick.trading_day,
            ts=tick.ts,
            source=tick.source,
            event_type=MarketDataEventType.TICK_ACCEPTED,
            rejected_event_type=MarketDataEventType.TICK_REJECTED,
            policy=policy or DataQualityPolicy(),
            in_session=in_session,
            previous_ts=previous_ts,
            gap_detected=gap_detected,
            bad_price_check=lambda: self._bad_tick_price(tick),
        )

    def validate_bar(
        self,
        bar: Bar,
        *,
        policy: DataQualityPolicy | None = None,
        in_session: bool = True,
        previous_ts: datetime | None = None,
        gap_detected: bool = False,
    ) -> DataQualityResult:
        return self._validate_common(
            symbol=bar.symbol,
            instrument_id=bar.instrument_id,
            trade_instrument_id=bar.trade_instrument_id,
            exchange=bar.exchange,
            trading_day=bar.trading_day,
            ts=bar.bar_ts,
            source=bar.source,
            event_type=MarketDataEventType.BAR_ACCEPTED,
            rejected_event_type=MarketDataEventType.BAR_REJECTED,
            policy=policy or DataQualityPolicy(),
            in_session=in_session,
            previous_ts=previous_ts,
            gap_detected=gap_detected,
            bad_price_check=lambda: self._bad_bar_price(bar),
        )

    def _validate_common(
        self,
        *,
        symbol: str,
        instrument_id: str,
        trade_instrument_id: str,
        exchange: str,
        trading_day: date,
        ts: datetime,
        source: str,
        event_type: MarketDataEventType,
        rejected_event_type: MarketDataEventType,
        policy: DataQualityPolicy,
        in_session: bool,
        previous_ts: datetime | None,
        gap_detected: bool,
        bad_price_check: Callable[[], str | None],
    ) -> DataQualityResult:
        if (
            not symbol
            or not instrument_id
            or not trade_instrument_id
            or not exchange
            or trading_day is None
            or not source
        ):
            return DataQualityResult(
                status=MarketDataResultStatus.REJECTED_MISSING_IDENTITY,
                event_type=rejected_event_type,
                instrument_id=instrument_id or None,
                exchange=exchange or None,
                reason="missing_identity",
            )
        if ts.tzinfo is None or ts.utcoffset() is None:
            return DataQualityResult(
                status=MarketDataResultStatus.REJECTED_BAD_TIMESTAMP,
                event_type=rejected_event_type,
                instrument_id=instrument_id,
                exchange=exchange,
                ts=ts,
                reason="bad_timestamp",
            )
        if not in_session:
            return DataQualityResult(
                status=MarketDataResultStatus.REJECTED_OUT_OF_SESSION,
                event_type=rejected_event_type,
                instrument_id=instrument_id,
                exchange=exchange,
                trading_day=trading_day,
                ts=ts,
                reason="out_of_session",
            )
        bad_price_reason = bad_price_check()
        if bad_price_reason is not None:
            return self._rejected_price_result(
                event_type=rejected_event_type,
                instrument_id=instrument_id,
                exchange=exchange,
                trading_day=trading_day,
                ts=ts,
                reason=bad_price_reason,
            )
        if previous_ts is not None and ts < previous_ts:
            return DataQualityResult(
                status=MarketDataResultStatus.REJECTED_NON_MONOTONIC,
                event_type=rejected_event_type,
                instrument_id=instrument_id,
                exchange=exchange,
                trading_day=trading_day,
                ts=ts,
                reason="non_monotonic",
            )
        if gap_detected:
            return DataQualityResult(
                status=MarketDataResultStatus.GAP_DETECTED,
                event_type=MarketDataEventType.GAP_DETECTED,
                instrument_id=instrument_id,
                exchange=exchange,
                trading_day=trading_day,
                ts=ts,
                reason="gap_detected" if policy.allow_gap else "gap_rejected",
            )
        return DataQualityResult(
            status=MarketDataResultStatus.ACCEPTED,
            event_type=event_type,
            instrument_id=instrument_id,
            exchange=exchange,
            trading_day=trading_day,
            ts=ts,
        )

    def _bad_tick_price(self, tick: Tick) -> str | None:
        if tick.price <= 0:
            return "bad_price"
        for field_name in ("volume", "turnover", "open_interest"):
            if getattr(tick, field_name) < 0:
                return "bad_price"
        for field_name in ("bid_price_1", "ask_price_1"):
            value = getattr(tick, field_name)
            if value is not None and value <= 0:
                return "bad_price"
        for field_name in ("bid_volume_1", "ask_volume_1"):
            value = getattr(tick, field_name)
            if value is not None and value < 0:
                return "bad_price"
        if (
            tick.bid_price_1 is not None
            and tick.ask_price_1 is not None
            and tick.bid_price_1 > tick.ask_price_1
        ):
            return "bad_price"
        return None

    def _bad_bar_price(self, bar: Bar) -> str | None:
        for field_name in ("open", "high", "low", "close"):
            if getattr(bar, field_name) <= 0:
                return "bad_price"
        for field_name in ("volume", "turnover", "open_interest"):
            if getattr(bar, field_name) < 0:
                return "bad_price"
        if bar.high < max(bar.open, bar.close, bar.low):
            return "bad_ohlc"
        if bar.low > min(bar.open, bar.close, bar.high):
            return "bad_ohlc"
        return None

    def _rejected_price_result(
        self,
        *,
        event_type: MarketDataEventType,
        instrument_id: str,
        exchange: str,
        trading_day: date,
        ts: datetime,
        reason: str,
    ) -> DataQualityResult:
        return DataQualityResult(
            status=MarketDataResultStatus.REJECTED_BAD_PRICE,
            event_type=event_type,
            instrument_id=instrument_id or None,
            exchange=exchange or None,
            trading_day=trading_day,
            ts=ts,
            reason=reason,
        )
