from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from futures_mvp.domain.enums import (
    BarTimeframe,
    SignalDecisionType,
    SignalPositionSide,
    SignalSide,
)
from futures_mvp.domain.models import (
    FeatureSnapshot,
    SignalCandidate,
    SignalLifecycleEvent,
    stable_json_sha256,
)


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BarTimeframe | SignalDecisionType | SignalSide | SignalPositionSide):
        return value.value
    return value


def signal_features_ref(snapshot: FeatureSnapshot) -> dict[str, Any]:
    return {
        "bar_ts": snapshot.bar_ts.isoformat(),
        "exchange": snapshot.exchange,
        "feature_config_hash": snapshot.feature_config_hash,
        "feature_version": snapshot.feature_version,
        "instrument_id": snapshot.instrument_id,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe.value,
        "trade_instrument_id": snapshot.trade_instrument_id,
        "trading_day": snapshot.trading_day.isoformat(),
    }


def signal_id_payload(
    *,
    strategy_name: str,
    strategy_version: str,
    strategy_config_hash: str,
    symbol: str,
    instrument_id: str,
    trade_instrument_id: str,
    exchange: str,
    trading_day: date,
    timeframe: BarTimeframe,
    bar_ts: datetime,
    feature_version: str,
    feature_config_hash: str,
    decision: SignalDecisionType,
    side: SignalSide,
    position_side: SignalPositionSide,
    expected_price: Decimal | None = None,
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "bar_ts": _value(bar_ts),
        "decision": decision.value,
        "exchange": exchange,
        "feature_config_hash": feature_config_hash,
        "feature_version": feature_version,
        "instrument_id": instrument_id,
        "position_side": position_side.value,
        "side": side.value,
        "strategy_config_hash": strategy_config_hash,
        "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "symbol": symbol,
        "timeframe": timeframe.value,
        "trade_instrument_id": trade_instrument_id,
        "trading_day": _value(trading_day),
    }
    if expected_price is not None:
        payload["expected_price"] = _value(expected_price)
    if stop_loss is not None:
        payload["stop_loss"] = _value(stop_loss)
    if take_profit is not None:
        payload["take_profit"] = _value(take_profit)
    return payload


def build_signal_id(
    *,
    strategy_name: str,
    strategy_version: str,
    strategy_config_hash: str,
    symbol: str,
    instrument_id: str,
    trade_instrument_id: str,
    exchange: str,
    trading_day: date,
    timeframe: BarTimeframe,
    bar_ts: datetime,
    feature_version: str,
    feature_config_hash: str,
    decision: SignalDecisionType,
    side: SignalSide,
    position_side: SignalPositionSide,
    expected_price: Decimal | None = None,
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
) -> str:
    return stable_json_sha256(
        signal_id_payload(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            strategy_config_hash=strategy_config_hash,
            symbol=symbol,
            instrument_id=instrument_id,
            trade_instrument_id=trade_instrument_id,
            exchange=exchange,
            trading_day=trading_day,
            timeframe=timeframe,
            bar_ts=bar_ts,
            feature_version=feature_version,
            feature_config_hash=feature_config_hash,
            decision=decision,
            side=side,
            position_side=position_side,
            expected_price=expected_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
    )


def signal_event_key_payload(
    *,
    signal_id: str,
    lifecycle_status: Any,
    event_ts: datetime,
    event_reason: str | None,
) -> dict[str, Any]:
    lifecycle_status_value = (
        lifecycle_status.value if hasattr(lifecycle_status, "value") else lifecycle_status
    )
    return {
        "event_reason": event_reason,
        "event_ts": _value(event_ts),
        "lifecycle_status": lifecycle_status_value,
        "signal_id": signal_id,
    }


def build_signal_event_key(
    *,
    signal_id: str,
    lifecycle_status: Any,
    event_ts: datetime,
    event_reason: str | None,
) -> str:
    return stable_json_sha256(
        signal_event_key_payload(
            signal_id=signal_id,
            lifecycle_status=lifecycle_status,
            event_ts=event_ts,
            event_reason=event_reason,
        )
    )


def canonical_signal_event_payload(event: SignalLifecycleEvent) -> tuple[object, ...]:
    return (
        event.event_key,
        event.signal_id,
        event.lifecycle_status.value,
        event.event_reason,
        _value(event.event_ts),
    )


def canonical_signal_candidate_payload(candidate: SignalCandidate) -> tuple[object, ...]:
    return (
        candidate.signal_id,
        candidate.strategy_name,
        candidate.strategy_version,
        candidate.strategy_config_hash,
        candidate.runtime_id,
        candidate.symbol,
        candidate.instrument_id,
        candidate.trade_instrument_id,
        candidate.exchange,
        _value(candidate.trading_day),
        candidate.timeframe.value,
        _value(candidate.bar_ts),
        candidate.feature_version,
        candidate.feature_config_hash,
        candidate.decision.value,
        candidate.side.value,
        candidate.position_side.value,
        candidate.confidence,
        candidate.strength,
        candidate.reason,
        candidate.expected_price,
        candidate.stop_loss,
        candidate.take_profit,
        candidate.holding_period_hint,
        tuple(sorted(candidate.tags.items())),
        tuple(sorted(candidate.features_ref.items())),
    )
