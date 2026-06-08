from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import (
    BarTimeframe,
    Offset,
    OMSBridgeResultStatus,
    OrderType,
    RiskResultStatus,
    SignalSide,
)
from futures_mvp.domain.models import (
    OMSBridgeContext,
    OMSBridgeResult,
    OrderIntent,
    TradingRiskResult,
)
from futures_mvp.modules.oms_bridge import (
    build_bridge_payload_hash,
    build_client_order_id,
    canonical_oms_bridge_payload,
)


def _risk_result(**updates: object) -> TradingRiskResult:
    values = {
        "signal_id": "signal-1",
        "risk_result_id": "risk-1",
        "evaluation_context_hash": "eval-hash",
        "risk_status": RiskResultStatus.ACCEPT,
        "risk_reason": "accepted",
        "risk_level": "INFO",
        "requested_quantity": Decimal("2"),
        "approved_quantity": Decimal("2"),
        "max_quantity": Decimal("2"),
        "expected_margin": Decimal("1000"),
        "expected_notional": Decimal("1500"),
        "config_hash": "risk-config-hash",
        "evaluation_ts": datetime(2026, 6, 8, 9, tzinfo=UTC),
    }
    values.update(updates)
    return TradingRiskResult(**values)


def _intent(**updates: object) -> OrderIntent:
    values = {
        "intent_id": "intent-1",
        "signal_id": "signal-1",
        "risk_result_id": "risk-1",
        "strategy_name": "toy",
        "strategy_version": "strategy-v1",
        "strategy_config_hash": "strategy-config-hash",
        "runtime_id": "runtime-1",
        "symbol": "au",
        "instrument_id": "au2606",
        "trade_instrument_id": "au2606",
        "exchange": "SHFE",
        "trading_day": date(2026, 6, 8),
        "timeframe": BarTimeframe.M1,
        "bar_ts": datetime(2026, 6, 8, 9, tzinfo=UTC),
        "feature_version": "feature-v1",
        "feature_config_hash": "feature-hash",
        "side": SignalSide.BUY,
        "offset": Offset.OPEN,
        "quantity": Decimal("2"),
        "price": Decimal("500"),
        "order_type": OrderType.LIMIT,
        "tif": "GFD",
        "expected_margin": Decimal("1000"),
        "expected_notional": Decimal("1500"),
        "intent_reason": "accepted",
    }
    values.update(updates)
    return OrderIntent(**values)


def _context(**updates: object) -> OMSBridgeContext:
    values = {
        "order_intent": _intent(),
        "trading_risk_result": _risk_result(),
        "account_id": "account-1",
    }
    values.update(updates)
    return OMSBridgeContext(**values)


def test_client_order_id_is_deterministic_hash_from_intent_id() -> None:
    first = build_client_order_id("intent-1")
    second = build_client_order_id("intent-1")

    assert first == second
    assert first == "oi_" + build_client_order_id("intent-1")[3:]
    assert len(first) == 43
    assert build_client_order_id("intent-2") != first


def test_bridge_payload_hash_is_deterministic_and_excludes_raw_payload() -> None:
    context = _context()
    client_order_id = build_client_order_id(context.order_intent.intent_id)
    payload = canonical_oms_bridge_payload(context, client_order_id)
    same_context = context.model_copy(
        update={"order_intent": context.order_intent.model_copy(update={"raw_payload": {"x": 1}})}
    )
    same_payload = canonical_oms_bridge_payload(same_context, client_order_id)

    assert payload == same_payload
    assert "raw_payload" not in payload
    assert "bridge_ts" not in payload
    assert "created_at" not in payload
    assert build_bridge_payload_hash(payload) == build_bridge_payload_hash(same_payload)


def test_bridge_payload_includes_required_identity_and_order_fields() -> None:
    context = _context()
    client_order_id = build_client_order_id(context.order_intent.intent_id)
    payload = canonical_oms_bridge_payload(context, client_order_id)

    assert payload["intent_id"] == context.order_intent.intent_id
    assert payload["risk_result_id"] == context.order_intent.risk_result_id
    assert payload["strategy_name"] == context.order_intent.strategy_name
    assert payload["instrument_id"] == context.order_intent.instrument_id
    assert payload["side"] == context.order_intent.side.value
    assert payload["offset"] == context.order_intent.offset.value
    assert payload["quantity"] == "2"
    assert payload["price"] == "500"
    assert payload["order_type"] == context.order_intent.order_type.value
    assert payload["tif"] == context.order_intent.tif
    assert payload["account_id"] == "account-1"
    assert payload["client_order_id"] == client_order_id


def test_oms_bridge_result_validation() -> None:
    with pytest.raises(ValueError, match="CREATED"):
        OMSBridgeResult(
            status=OMSBridgeResultStatus.CREATED,
            intent_id="intent-1",
            client_order_id="client-1",
            order_id=None,
            bridge_payload_hash="hash",
            bridge_ts=datetime(2026, 6, 8, 9, tzinfo=UTC),
        )

    duplicate = OMSBridgeResult(
        status=OMSBridgeResultStatus.DUPLICATE,
        intent_id="intent-1",
        client_order_id="client-1",
        order_id="1",
        bridge_payload_hash="hash",
        bridge_ts=datetime(2026, 6, 8, 9, tzinfo=UTC),
    )
    assert duplicate.status is OMSBridgeResultStatus.DUPLICATE


def test_oms_bridge_context_rejects_raw_payload_bridge_config() -> None:
    with pytest.raises(ValueError, match="raw_payload"):
        _context(bridge_config={"raw_payload": {"fact": "forbidden"}})
