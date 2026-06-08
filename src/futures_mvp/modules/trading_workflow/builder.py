from decimal import Decimal

from futures_mvp.domain.enums import Offset, OrderType, RiskResultStatus, SignalSide
from futures_mvp.domain.models import (
    OrderIntent,
    SignalDecision,
    TradingRiskResult,
    TradingWorkflowContext,
    stable_json_sha256,
)
from futures_mvp.modules.trading_workflow.canonical import (
    order_intent_id_payload,
    trading_risk_result_id_payload,
)


def build_trading_risk_result_id(result: TradingRiskResult) -> str:
    return stable_json_sha256(trading_risk_result_id_payload(result))


def build_order_intent_id(intent: OrderIntent) -> str:
    return stable_json_sha256(order_intent_id_payload(intent))


def normalize_reduce_result_if_needed(
    result: TradingRiskResult,
    requested_quantity: Decimal,
) -> TradingRiskResult:
    if result.approved_quantity > requested_quantity:
        raise ValueError("approved_quantity cannot exceed requested quantity")
    if result.risk_status is RiskResultStatus.ACCEPT:
        if result.approved_quantity != requested_quantity:
            raise ValueError("ACCEPT requires approved_quantity equal requested quantity")
        return result
    if result.risk_status is not RiskResultStatus.REDUCE:
        return result
    if result.approved_quantity <= 0:
        rejected = result.model_copy(
            update={
                "approved_quantity": Decimal("0"),
                "risk_reason": result.risk_reason or "reduced_quantity_not_positive",
                "risk_status": RiskResultStatus.REJECT,
            }
        )
        return rejected.model_copy(
            update={"risk_result_id": build_trading_risk_result_id(rejected)}
        )
    if result.approved_quantity == requested_quantity:
        accepted = result.model_copy(
            update={
                "risk_reason": result.risk_reason or "reduced_quantity_equals_requested",
                "risk_status": RiskResultStatus.ACCEPT,
            }
        )
        return accepted.model_copy(
            update={"risk_result_id": build_trading_risk_result_id(accepted)}
        )
    if result.approved_quantity > requested_quantity:
        raise ValueError("REDUCE requires approved_quantity less than requested quantity")
    return result


def build_order_intent(
    signal_decision: SignalDecision,
    risk_result: TradingRiskResult,
    context: TradingWorkflowContext,
) -> OrderIntent:
    if risk_result.risk_status not in {RiskResultStatus.ACCEPT, RiskResultStatus.REDUCE}:
        raise ValueError("OrderIntent can only be built from ACCEPT or REDUCE RiskResult")
    if risk_result.signal_id != signal_decision.signal_id:
        raise ValueError("OrderIntent signal_id must match RiskResult")
    if risk_result.approved_quantity <= 0:
        raise ValueError("OrderIntent requires positive approved_quantity")
    if signal_decision.side is SignalSide.NONE:
        raise ValueError("OrderIntent requires BUY or SELL side")
    if signal_decision.expected_price is None or signal_decision.expected_price <= 0:
        raise ValueError("OrderIntent requires positive expected_price")

    intent = OrderIntent(
        intent_id="pending",
        signal_id=signal_decision.signal_id,
        risk_result_id=risk_result.risk_result_id,
        strategy_name=signal_decision.strategy_name,
        strategy_version=signal_decision.strategy_version,
        strategy_config_hash=signal_decision.strategy_config_hash,
        runtime_id=signal_decision.runtime_id,
        symbol=signal_decision.symbol,
        instrument_id=signal_decision.instrument_id,
        trade_instrument_id=signal_decision.trade_instrument_id,
        exchange=signal_decision.exchange,
        trading_day=signal_decision.trading_day,
        timeframe=signal_decision.timeframe,
        bar_ts=signal_decision.bar_ts,
        feature_version=signal_decision.feature_version,
        feature_config_hash=signal_decision.feature_config_hash,
        side=signal_decision.side,
        offset=_offset_from_strategy_params(context),
        quantity=risk_result.approved_quantity,
        price=signal_decision.expected_price,
        order_type=_order_type_from_strategy_params(context),
        tif=_tif_from_strategy_params(context),
        expected_margin=risk_result.expected_margin,
        expected_notional=risk_result.expected_notional,
        intent_reason=risk_result.risk_reason,
        raw_payload=None,
    )
    return intent.model_copy(update={"intent_id": build_order_intent_id(intent)})


def _offset_from_strategy_params(context: TradingWorkflowContext) -> Offset:
    value = context.strategy_config.params.get("offset", Offset.OPEN.value)
    return value if isinstance(value, Offset) else Offset(str(value))


def _order_type_from_strategy_params(context: TradingWorkflowContext) -> OrderType:
    value = context.strategy_config.params.get("order_type", OrderType.LIMIT.value)
    return value if isinstance(value, OrderType) else OrderType(str(value))


def _tif_from_strategy_params(context: TradingWorkflowContext) -> str:
    return str(context.strategy_config.params.get("tif", "GFD"))
