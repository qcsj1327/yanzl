from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from futures_mvp.domain.enums import BarTimeframe, Offset, OrderType, RiskResultStatus, SignalSide
from futures_mvp.domain.models import OrderIntent, TradingRiskResult


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BarTimeframe | Offset | OrderType | RiskResultStatus | SignalSide):
        return value.value
    return value


def canonical_trading_risk_result_payload(result: TradingRiskResult) -> tuple[object, ...]:
    return (
        result.signal_id,
        result.evaluation_context_hash,
        result.risk_status.value,
        result.risk_reason,
        result.risk_level,
        result.requested_quantity,
        result.approved_quantity,
        result.max_quantity,
        result.expected_margin,
        result.expected_notional,
        result.config_hash,
    )


def trading_risk_result_id_payload(result: TradingRiskResult) -> dict[str, Any]:
    return {
        "approved_quantity": _value(result.approved_quantity),
        "config_hash": result.config_hash,
        "evaluation_context_hash": result.evaluation_context_hash,
        "expected_margin": _value(result.expected_margin),
        "expected_notional": _value(result.expected_notional),
        "max_quantity": _value(result.max_quantity),
        "requested_quantity": _value(result.requested_quantity),
        "risk_level": result.risk_level,
        "risk_reason": result.risk_reason,
        "risk_status": result.risk_status.value,
        "signal_id": result.signal_id,
    }


def canonical_order_intent_payload(intent: OrderIntent) -> tuple[object, ...]:
    return (
        intent.signal_id,
        intent.risk_result_id,
        intent.strategy_name,
        intent.strategy_version,
        intent.strategy_config_hash,
        intent.runtime_id,
        intent.symbol,
        intent.instrument_id,
        intent.trade_instrument_id,
        intent.exchange,
        _value(intent.trading_day),
        intent.timeframe.value,
        _value(intent.bar_ts),
        intent.feature_version,
        intent.feature_config_hash,
        intent.side.value,
        intent.offset.value,
        intent.quantity,
        intent.price,
        intent.order_type.value,
        intent.tif,
        intent.expected_margin,
        intent.expected_notional,
        intent.intent_reason,
    )


def order_intent_id_payload(intent: OrderIntent) -> dict[str, Any]:
    return {
        "bar_ts": _value(intent.bar_ts),
        "exchange": intent.exchange,
        "expected_margin": _value(intent.expected_margin),
        "expected_notional": _value(intent.expected_notional),
        "feature_config_hash": intent.feature_config_hash,
        "feature_version": intent.feature_version,
        "instrument_id": intent.instrument_id,
        "intent_reason": intent.intent_reason,
        "offset": intent.offset.value,
        "order_type": intent.order_type.value,
        "price": _value(intent.price),
        "quantity": _value(intent.quantity),
        "risk_result_id": intent.risk_result_id,
        "runtime_id": intent.runtime_id,
        "side": intent.side.value,
        "signal_id": intent.signal_id,
        "strategy_config_hash": intent.strategy_config_hash,
        "strategy_name": intent.strategy_name,
        "strategy_version": intent.strategy_version,
        "symbol": intent.symbol,
        "tif": intent.tif,
        "timeframe": intent.timeframe.value,
        "trade_instrument_id": intent.trade_instrument_id,
        "trading_day": _value(intent.trading_day),
    }
