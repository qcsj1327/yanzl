from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from futures_mvp.domain.enums import BarTimeframe, Offset, OrderType, SignalSide
from futures_mvp.domain.models import OMSBridgeContext, stable_json_sha256


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BarTimeframe | Offset | OrderType | SignalSide):
        return value.value
    return value


def canonical_oms_bridge_payload(
    context: OMSBridgeContext,
    client_order_id: str,
) -> dict[str, Any]:
    intent = context.order_intent
    return {
        "account_id": context.account_id,
        "client_order_id": client_order_id,
        "exchange": intent.exchange,
        "feature_config_hash": intent.feature_config_hash,
        "feature_version": intent.feature_version,
        "instrument_id": intent.instrument_id,
        "intent_id": intent.intent_id,
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
        "trade_instrument_id": intent.trade_instrument_id,
    }


def build_bridge_payload_hash(payload: dict[str, Any]) -> str:
    return stable_json_sha256(payload)
