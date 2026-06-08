from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import (
    BarTimeframe,
    Offset,
    OrderType,
    RiskResultStatus,
    SignalDecisionType,
    SignalPositionSide,
    SignalSide,
    TradingWorkflowResultStatus,
)
from futures_mvp.domain.errors import DecimalRequiredError
from futures_mvp.domain.models import (
    OrderIntent,
    SignalDecision,
    StrategyConfig,
    TradingRiskResult,
    TradingWorkflowContext,
)
from futures_mvp.modules.strategy import build_signal_id
from futures_mvp.modules.trading_workflow import (
    build_order_intent,
    build_order_intent_id,
    build_trading_risk_result_id,
    canonical_order_intent_payload,
    canonical_trading_risk_result_payload,
    normalize_reduce_result_if_needed,
)


def _config() -> StrategyConfig:
    return StrategyConfig.build(
        strategy_name="breakout",
        strategy_version="strategy-v1",
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        timeframe=BarTimeframe.M1,
        params={"offset": Offset.OPEN.value, "order_type": OrderType.LIMIT.value, "tif": "GFD"},
    )


def _decision(**updates: object) -> SignalDecision:
    config = _config()
    values = {
        "decision": SignalDecisionType.BUY,
        "side": SignalSide.BUY,
        "position_side": SignalPositionSide.LONG,
        "strength": Decimal("3"),
        "confidence": Decimal("0.9"),
        "reason": "breakout",
        "strategy_name": config.strategy_name,
        "strategy_version": config.strategy_version,
        "strategy_config_hash": config.strategy_config_hash,
        "runtime_id": "runtime-1",
        "symbol": "au",
        "instrument_id": "au2606",
        "trade_instrument_id": "au2606",
        "exchange": "SHFE",
        "trading_day": date(2026, 6, 7),
        "timeframe": BarTimeframe.M1,
        "bar_ts": datetime(2026, 6, 7, 9, tzinfo=UTC),
        "feature_version": "feature-v1",
        "feature_config_hash": "feature-hash",
        "expected_price": Decimal("500"),
        "tags": {"rule": "toy"},
        "raw_payload": {"diagnostic": "signal"},
    }
    values["signal_id"] = build_signal_id(
        strategy_name=str(values["strategy_name"]),
        strategy_version=str(values["strategy_version"]),
        strategy_config_hash=str(values["strategy_config_hash"]),
        symbol=str(values["symbol"]),
        instrument_id=str(values["instrument_id"]),
        trade_instrument_id=str(values["trade_instrument_id"]),
        exchange=str(values["exchange"]),
        trading_day=values["trading_day"],
        timeframe=values["timeframe"],
        bar_ts=values["bar_ts"],
        feature_version=str(values["feature_version"]),
        feature_config_hash=str(values["feature_config_hash"]),
        decision=values["decision"],
        side=values["side"],
        position_side=values["position_side"],
        expected_price=values["expected_price"],
    )
    values.update(updates)
    return SignalDecision(**values)


def _context(decision: SignalDecision | None = None) -> TradingWorkflowContext:
    return TradingWorkflowContext(
        signal_decision=decision or _decision(),
        strategy_config=_config(),
        requested_quantity=Decimal("3"),
        risk_config_hash="risk-config-hash",
        evaluation_context_hash="eval-context-hash",
    )


def _risk_result(
    *,
    status: RiskResultStatus = RiskResultStatus.ACCEPT,
    requested_quantity: Decimal = Decimal("3"),
    approved_quantity: Decimal | None = Decimal("3"),
    max_quantity: Decimal | None = Decimal("3"),
    expected_margin: Decimal | None = Decimal("1000"),
    expected_notional: Decimal | None = Decimal("1500"),
    risk_reason: str | None = "accepted",
    evaluation_context_hash: str = "eval-context-hash",
    raw_payload: dict[str, object] | None = None,
) -> TradingRiskResult:
    result = TradingRiskResult(
        signal_id=_decision().signal_id,
        risk_result_id="pending",
        evaluation_context_hash=evaluation_context_hash,
        risk_status=status,
        risk_reason=risk_reason,
        risk_level="INFO",
        requested_quantity=requested_quantity,
        approved_quantity=approved_quantity,
        max_quantity=max_quantity,
        expected_margin=expected_margin,
        expected_notional=expected_notional,
        config_hash="risk-config-hash",
        evaluation_ts=datetime(2026, 6, 7, 9, 1, tzinfo=UTC),
        raw_payload=raw_payload,
    )
    return result.model_copy(update={"risk_result_id": build_trading_risk_result_id(result)})


def test_stage_j_enums_freeze_contract() -> None:
    assert [status.value for status in RiskResultStatus] == [
        "ACCEPT",
        "REDUCE",
        "REJECT",
        "BLOCK",
        "UNKNOWN",
    ]
    assert TradingWorkflowResultStatus.INTENT_CREATED.value == "INTENT_CREATED"


def test_trading_risk_result_validation_and_deterministic_id() -> None:
    first = _risk_result(raw_payload={"a": 1})
    second = _risk_result(raw_payload={"a": 2})

    assert first.risk_result_id == second.risk_result_id
    assert canonical_trading_risk_result_payload(first) == canonical_trading_risk_result_payload(
        second
    )
    different_context = _risk_result(evaluation_context_hash="other-context")
    assert different_context.risk_result_id != first.risk_result_id
    with pytest.raises(ValueError, match="ACCEPT"):
        _risk_result(approved_quantity=Decimal("0"))
    with pytest.raises(DecimalRequiredError):
        _risk_result(approved_quantity=1.0)
    with pytest.raises(DecimalRequiredError):
        _risk_result(approved_quantity=None)
    with pytest.raises(DecimalRequiredError):
        _risk_result(expected_margin=None)


def test_reduce_quantity_rule_and_zero_reduce_converts_reject() -> None:
    reduced = _risk_result(status=RiskResultStatus.REDUCE, approved_quantity=Decimal("1"))
    assert normalize_reduce_result_if_needed(reduced, Decimal("3")).risk_status is (
        RiskResultStatus.REDUCE
    )
    equal_payload = reduced.model_dump()
    equal_payload["approved_quantity"] = Decimal("3")
    equal_reduce = TradingRiskResult.model_construct(**equal_payload)
    normalized_equal = normalize_reduce_result_if_needed(equal_reduce, Decimal("3"))
    assert normalized_equal.risk_status is RiskResultStatus.ACCEPT

    zero_payload = reduced.model_dump()
    zero_payload["approved_quantity"] = Decimal("0")
    zero_reduce = TradingRiskResult.model_construct(**zero_payload)
    normalized = normalize_reduce_result_if_needed(zero_reduce, Decimal("3"))
    assert normalized.risk_status is RiskResultStatus.REJECT
    assert normalized.approved_quantity == Decimal("0")

    too_large_payload = reduced.model_dump()
    too_large_payload["approved_quantity"] = Decimal("4")
    too_large = TradingRiskResult.model_construct(**too_large_payload)
    with pytest.raises(ValueError, match="exceed requested"):
        normalize_reduce_result_if_needed(too_large, Decimal("3"))


def test_reduce_invalid_domain_facts_are_rejected() -> None:
    with pytest.raises(ValueError, match="approved_quantity"):
        _risk_result(status=RiskResultStatus.REDUCE, approved_quantity=Decimal("0"))
    with pytest.raises(ValueError, match="REDUCE"):
        _risk_result(status=RiskResultStatus.REDUCE, approved_quantity=Decimal("3"))

    rejected = _risk_result(
        status=RiskResultStatus.REJECT,
        approved_quantity=Decimal("0"),
        expected_margin=Decimal("0"),
        expected_notional=Decimal("0"),
        risk_reason="blocked",
    )
    assert rejected.approved_quantity == Decimal("0")


def test_order_intent_is_deterministic_and_excludes_raw_payload() -> None:
    context = _context()
    risk_result = _risk_result()
    intent = build_order_intent(context.signal_decision, risk_result, context)
    same = intent.model_copy(update={"raw_payload": {"diagnostic": "changed"}})

    assert intent.intent_id == build_order_intent_id(intent)
    assert intent.quantity == risk_result.approved_quantity
    assert canonical_order_intent_payload(intent) == canonical_order_intent_payload(same)
    assert "status" not in OrderIntent.model_fields
    assert "order_status" not in OrderIntent.model_fields


def test_rejected_statuses_cannot_build_order_intent() -> None:
    context = _context()
    for status in (RiskResultStatus.REJECT, RiskResultStatus.BLOCK, RiskResultStatus.UNKNOWN):
        result = _risk_result(
            status=status,
            approved_quantity=Decimal("0"),
            expected_margin=Decimal("0"),
            expected_notional=Decimal("0"),
        )
        with pytest.raises(ValueError, match="ACCEPT or REDUCE"):
            build_order_intent(context.signal_decision, result, context)
