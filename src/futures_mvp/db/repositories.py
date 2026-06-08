from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from futures_mvp.db.models import AccountSnapshot as AccountSnapshotOrm
from futures_mvp.db.models import ExecutionCommand as ExecutionCommandOrm
from futures_mvp.db.models import FeatureSnapshot as FeatureSnapshotOrm
from futures_mvp.db.models import MarginSnapshot as MarginSnapshotOrm
from futures_mvp.db.models import MarketBar as MarketBarOrm
from futures_mvp.db.models import MarketTick as MarketTickOrm
from futures_mvp.db.models import NormalizedExecutionReport as NormalizedExecutionReportOrm
from futures_mvp.db.models import Order
from futures_mvp.db.models import OrderEvent as OrderEventOrm
from futures_mvp.db.models import OrderIntent as OrderIntentOrm
from futures_mvp.db.models import PnLSnapshot as PnLSnapshotOrm
from futures_mvp.db.models import Position as PositionOrm
from futures_mvp.db.models import PositionEvent as PositionEventOrm
from futures_mvp.db.models import SettlementSnapshot as SettlementSnapshotOrm
from futures_mvp.db.models import SignalCandidate as SignalCandidateOrm
from futures_mvp.db.models import SignalEvent as SignalEventOrm
from futures_mvp.db.models import Trade as TradeOrm
from futures_mvp.db.models import TradingRiskResult as TradingRiskResultOrm
from futures_mvp.domain.enums import (
    BarTimeframe,
    Direction,
    EventSource,
    ExecutionCommandType,
    ExecutionReportStatus,
    ExecutionTarget,
    FeatureQualityStatus,
    MarketDataResultStatus,
    Offset,
    OrderStatus,
    OrderType,
    PnLPriceBasis,
    RiskResultStatus,
    SettlementResultStatus,
    SignalDecisionType,
    SignalLifecycleStatus,
    SignalPositionSide,
    SignalSide,
    TradeIdentitySource,
)
from futures_mvp.domain.models import (
    AccountSnapshot,
    Bar,
    ExecutionCommand,
    FeatureSnapshot,
    MarginSnapshot,
    NormalizedExecutionReport,
    OrderEvent,
    OrderIntent,
    OrderRequest,
    OrderState,
    PnLSnapshot,
    Position,
    PositionEvent,
    PositionSnapshot,
    SettlementSnapshot,
    SignalCandidate,
    SignalLifecycleEvent,
    Tick,
    Trade,
    TradingRiskResult,
)
from futures_mvp.interfaces.repositories import (
    EventAlreadyExistsError,
    ExecutionCommandConflictError,
    ExecutionReportConflictError,
    FeatureSnapshotConflictError,
    IdempotencyConflictError,
    MarginSnapshotConflictError,
    MarketDataConflictError,
    OptimisticLockError,
    OrderIntentConflictError,
    OrderNotFoundError,
    PnLSnapshotConflictError,
    PositionEventConflictError,
    RepositoryError,
    SettlementSnapshotConflictError,
    SignalCandidateConflictError,
    SignalLifecycleConflictError,
    TradeIdempotencyConflictError,
    TradingRiskResultConflictError,
)
from futures_mvp.modules.execution_gateway.canonical import canonical_execution_command_payload
from futures_mvp.modules.execution_reports.canonical import (
    canonical_normalized_execution_report_payload,
)
from futures_mvp.modules.feature.canonical import canonical_feature_snapshot_payload
from futures_mvp.modules.market.canonical import canonical_bar_payload, canonical_tick_payload
from futures_mvp.modules.strategy.canonical import (
    canonical_signal_candidate_payload,
    canonical_signal_event_payload,
)
from futures_mvp.modules.trading_workflow.canonical import (
    canonical_order_intent_payload,
    canonical_trading_risk_result_payload,
)

OPEN_RECOVERY_STATUSES = frozenset(
    {
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMIT_TIMEOUT,
        OrderStatus.SUBMITTED,
        OrderStatus.ACKED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCEL_FAILED,
        OrderStatus.UNKNOWN,
    }
)


def parse_order_id(order_id: str) -> int:
    try:
        return int(order_id)
    except ValueError as exc:
        raise RepositoryError(f"invalid order_id: {order_id}") from exc


def order_to_domain(order: Order) -> OrderState:
    request = OrderRequest(
        client_order_id=order.client_order_id,
        account_id=order.account_id,
        instrument_id=order.instrument_id,
        exchange=order.exchange,
        direction=Direction(order.direction),
        offset=Offset(order.offset),
        order_type=OrderType(order.order_type),
        limit_price=order.limit_price,
        quantity=order.quantity,
    )
    return OrderState(
        order_id=str(order.id),
        request=request,
        status=OrderStatus(order.status),
        filled_quantity=order.filled_quantity,
        reject_reason=order.reject_reason,
        version=order.version,
    )


def order_event_to_domain(event: OrderEventOrm) -> OrderEvent:
    return OrderEvent(
        order_id=str(event.order_id),
        previous_status=OrderStatus(event.previous_status) if event.previous_status else None,
        new_status=OrderStatus(event.new_status),
        event_source=EventSource(event.event_source),
        external_event_id=event.external_event_id,
        raw_payload=event.raw_payload,
        occurred_at=event.occurred_at,
    )


def signal_candidate_to_domain(candidate: SignalCandidateOrm) -> SignalCandidate:
    return SignalCandidate(
        signal_id=candidate.signal_id,
        strategy_name=candidate.strategy_name,
        strategy_version=candidate.strategy_version,
        strategy_config_hash=candidate.strategy_config_hash,
        runtime_id=candidate.runtime_id,
        symbol=candidate.symbol,
        instrument_id=candidate.instrument_id,
        trade_instrument_id=candidate.trade_instrument_id,
        exchange=candidate.exchange,
        trading_day=candidate.trading_day,
        timeframe=BarTimeframe(candidate.timeframe),
        bar_ts=candidate.bar_ts,
        feature_version=candidate.feature_version,
        feature_config_hash=candidate.feature_config_hash,
        decision=SignalDecisionType(candidate.decision),
        side=SignalSide(candidate.side),
        position_side=SignalPositionSide(candidate.position_side),
        confidence=candidate.confidence,
        strength=candidate.strength,
        reason=candidate.reason,
        expected_price=candidate.expected_price,
        stop_loss=candidate.stop_loss,
        take_profit=candidate.take_profit,
        holding_period_hint=candidate.holding_period_hint,
        tags=candidate.tags,
        features_ref=candidate.features_ref,
        raw_payload=candidate.raw_payload,
        created_at=candidate.created_at,
    )


def signal_event_to_domain(event: SignalEventOrm) -> SignalLifecycleEvent:
    return SignalLifecycleEvent(
        id=str(event.id),
        event_key=event.event_key,
        signal_id=event.signal_id,
        lifecycle_status=SignalLifecycleStatus(event.lifecycle_status),
        event_reason=event.event_reason,
        event_ts=event.event_ts,
        raw_payload=event.raw_payload,
        created_at=event.created_at,
    )


def trading_risk_result_to_domain(result: TradingRiskResultOrm) -> TradingRiskResult:
    return TradingRiskResult(
        signal_id=result.signal_id,
        risk_result_id=result.risk_result_id,
        evaluation_context_hash=result.evaluation_context_hash,
        risk_status=RiskResultStatus(result.risk_status),
        risk_reason=result.risk_reason,
        risk_level=result.risk_level,
        requested_quantity=result.requested_quantity,
        approved_quantity=result.approved_quantity,
        max_quantity=result.max_quantity,
        expected_margin=result.expected_margin,
        expected_notional=result.expected_notional,
        config_hash=result.config_hash,
        evaluation_ts=result.evaluation_ts,
        raw_payload=result.raw_payload,
    )


def order_intent_to_domain(intent: OrderIntentOrm) -> OrderIntent:
    return OrderIntent(
        intent_id=intent.intent_id,
        signal_id=intent.signal_id,
        risk_result_id=intent.risk_result_id,
        strategy_name=intent.strategy_name,
        strategy_version=intent.strategy_version,
        strategy_config_hash=intent.strategy_config_hash,
        runtime_id=intent.runtime_id,
        symbol=intent.symbol,
        instrument_id=intent.instrument_id,
        trade_instrument_id=intent.trade_instrument_id,
        exchange=intent.exchange,
        trading_day=intent.trading_day,
        timeframe=BarTimeframe(intent.timeframe),
        bar_ts=intent.bar_ts,
        feature_version=intent.feature_version,
        feature_config_hash=intent.feature_config_hash,
        side=SignalSide(intent.side),
        offset=Offset(intent.offset),
        quantity=intent.quantity,
        price=intent.price,
        order_type=OrderType(intent.order_type),
        tif=intent.tif,
        expected_margin=intent.expected_margin,
        expected_notional=intent.expected_notional,
        intent_reason=intent.intent_reason,
        raw_payload=intent.raw_payload,
    )


def execution_command_to_domain(command: ExecutionCommandOrm) -> ExecutionCommand:
    return ExecutionCommand(
        command_id=command.command_id,
        order_id=command.order_id,
        client_order_id=command.client_order_id,
        account_id=command.account_id,
        symbol=command.symbol,
        instrument_id=command.instrument_id,
        trade_instrument_id=command.trade_instrument_id,
        exchange=command.exchange,
        side=Direction(command.side),
        offset=Offset(command.offset),
        quantity=command.quantity,
        price=command.price,
        order_type=OrderType(command.order_type),
        tif=command.tif,
        command_type=ExecutionCommandType(command.command_type),
        execution_target=ExecutionTarget(command.execution_target),
        command_payload_hash=command.command_payload_hash,
        created_at=command.created_at,
        raw_payload=command.raw_payload,
    )


def normalized_execution_report_to_domain(
    report: NormalizedExecutionReportOrm,
) -> NormalizedExecutionReport:
    return NormalizedExecutionReport(
        report_id=report.report_id,
        raw_report_id=report.raw_report_id,
        adapter_name=report.adapter_name,
        execution_target=ExecutionTarget(report.execution_target),
        command_id=report.command_id,
        order_id=report.order_id,
        client_order_id=report.client_order_id,
        adapter_order_ref=report.adapter_order_ref,
        exchange_order_id=report.exchange_order_id,
        exchange_trade_id=report.exchange_trade_id,
        fill_id=report.fill_id,
        execution_status=ExecutionReportStatus(report.execution_status),
        filled_qty=report.filled_qty,
        fill_price=report.fill_price,
        cumulative_filled_qty=report.cumulative_filled_qty,
        remaining_qty=report.remaining_qty,
        fee_amount=report.fee_amount,
        fee_currency=report.fee_currency,
        fee_source=report.fee_source,
        report_ts=report.report_ts,
        normalized_at=report.normalized_at,
        reason=report.reason,
        source_report_hash=report.source_report_hash,
        raw_payload=report.raw_payload,
    )


def trade_to_domain(trade: TradeOrm) -> Trade:
    return Trade(
        id=str(trade.id),
        account_id=trade.account_id,
        exchange=trade.exchange,
        exchange_trade_id=trade.exchange_trade_id,
        identity_source=TradeIdentitySource(
            trade.identity_source or TradeIdentitySource.EXCHANGE_TRADE_ID
        ),
        order_id=str(trade.order_id),
        client_order_id=trade.client_order_id,
        instrument_id=trade.instrument_id,
        trade_instrument_id=trade.trade_instrument_id,
        symbol=trade.symbol,
        direction=Direction(trade.direction),
        offset=Offset(trade.offset),
        price=trade.price,
        quantity=trade.quantity,
        fee_amount=trade.fee_amount,
        fee_currency=trade.fee_currency,
        fee_source=trade.fee_source,
        trade_time=trade.trade_time,
        trading_day=trade.trading_day,
        source_report_id=trade.source_report_id,
        source_exchange_report_id=trade.source_exchange_report_id,
        source_order_event_id=trade.source_order_event_id,
        raw_payload=trade.raw_payload or {},
    )


def position_to_domain(position: PositionOrm) -> Position:
    return Position(
        id=str(position.id),
        account_id=position.account_id,
        instrument_id=position.instrument_id,
        long_today_qty=position.long_today_qty,
        long_yesterday_qty=position.long_yesterday_qty,
        short_today_qty=position.short_today_qty,
        short_yesterday_qty=position.short_yesterday_qty,
        frozen_long_qty=position.frozen_long_qty,
        frozen_short_qty=position.frozen_short_qty,
        long_avg_price=position.long_avg_price,
        short_avg_price=position.short_avg_price,
        settlement_price=position.settlement_price,
        last_price=position.last_price,
        realized_pnl=position.realized_pnl,
        unrealized_pnl=position.unrealized_pnl,
        margin_used=position.margin_used,
        version=position.version,
        updated_at=position.updated_at,
    )


def position_event_to_domain(event: PositionEventOrm) -> PositionEvent:
    return PositionEvent(
        id=str(event.id),
        account_id=event.account_id,
        instrument_id=event.instrument_id,
        exchange=event.exchange,
        exchange_trade_id=event.exchange_trade_id,
        trade_id=str(event.trade_id),
        position_id=str(event.position_id),
        event_type=event.event_type,
        direction=Direction(event.direction),
        offset=Offset(event.offset),
        price=event.price,
        quantity=event.quantity,
        before_snapshot=PositionSnapshot.model_validate(event.before_snapshot),
        after_snapshot=PositionSnapshot.model_validate(event.after_snapshot),
        occurred_at=event.occurred_at,
        created_at=event.created_at,
        raw_payload=event.raw_payload or {},
    )


def margin_snapshot_to_domain(snapshot: MarginSnapshotOrm) -> MarginSnapshot:
    return MarginSnapshot(
        id=str(snapshot.id),
        account_id=snapshot.account_id,
        instrument_id=snapshot.instrument_id,
        position_version=snapshot.position_version,
        trading_day=snapshot.trading_day,
        config_hash=snapshot.config_hash,
        rule_id=snapshot.rule_id,
        rule_version=snapshot.rule_version,
        calculation_key=snapshot.calculation_key,
        long_qty=snapshot.long_qty,
        short_qty=snapshot.short_qty,
        price=snapshot.price,
        contract_multiplier=snapshot.contract_multiplier,
        initial_margin=snapshot.initial_margin,
        maintenance_margin=snapshot.maintenance_margin,
        margin_used=snapshot.margin_used,
        available_cash=snapshot.available_cash,
        equity=snapshot.equity,
        calculated_at=snapshot.calculated_at,
    )


def pnl_snapshot_to_domain(snapshot: PnLSnapshotOrm) -> PnLSnapshot:
    return PnLSnapshot(
        id=str(snapshot.id),
        account_id=snapshot.account_id,
        instrument_id=snapshot.instrument_id,
        position_version=snapshot.position_version,
        trading_day=snapshot.trading_day,
        config_hash=snapshot.config_hash,
        trade_id=snapshot.trade_id,
        margin_snapshot_id=snapshot.margin_snapshot_id,
        calculation_key=snapshot.calculation_key,
        price_basis=PnLPriceBasis(snapshot.price_basis),
        mark_price=snapshot.mark_price,
        contract_multiplier=snapshot.contract_multiplier,
        realized_pnl=snapshot.realized_pnl,
        unrealized_pnl=snapshot.unrealized_pnl,
        total_pnl=snapshot.total_pnl,
        fee_amount=snapshot.fee_amount,
        calculated_at=snapshot.calculated_at,
    )


def account_snapshot_to_domain(snapshot: AccountSnapshotOrm) -> AccountSnapshot:
    return AccountSnapshot(
        id=str(snapshot.id),
        account_id=snapshot.account_id,
        equity=snapshot.equity,
        available_cash=snapshot.available_cash,
        margin_used=snapshot.margin_used,
        frozen_margin=snapshot.frozen_margin,
        realized_pnl=snapshot.realized_pnl,
        unrealized_pnl=snapshot.unrealized_pnl,
        snapshot_time=snapshot.snapshot_time,
    )


def settlement_snapshot_to_domain(snapshot: SettlementSnapshotOrm) -> SettlementSnapshot:
    created_at = snapshot.created_at or datetime.now()
    return SettlementSnapshot(
        id=str(snapshot.id),
        account_id=snapshot.account_id,
        trading_day=snapshot.trading_day,
        calculation_key=snapshot.calculation_key,
        positions_before=tuple(cast(list[dict[str, object]], snapshot.positions_before)),
        positions_after=tuple(cast(list[dict[str, object]], snapshot.positions_after)),
        settlement_prices=tuple(cast(list[dict[str, object]], snapshot.settlement_prices)),
        pnl_snapshot_ids=tuple(snapshot.pnl_snapshot_ids),
        margin_snapshot_ids=tuple(snapshot.margin_snapshot_ids),
        account_snapshot_before_id=str(snapshot.account_snapshot_before_id)
        if snapshot.account_snapshot_before_id is not None
        else None,
        account_snapshot_after_id=str(snapshot.account_snapshot_after_id)
        if snapshot.account_snapshot_after_id is not None
        else None,
        cash_before=snapshot.cash_before,
        cash_after=snapshot.cash_after,
        realized_pnl=snapshot.realized_pnl,
        unrealized_pnl=snapshot.unrealized_pnl,
        margin_used=snapshot.margin_used,
        status=SettlementResultStatus(snapshot.status),
        reason=snapshot.reason,
        created_at=created_at,
    )


def market_tick_to_domain(tick: MarketTickOrm) -> Tick:
    return Tick(
        symbol=tick.symbol,
        instrument_id=tick.instrument_id,
        trade_instrument_id=tick.trade_instrument_id,
        exchange=tick.exchange,
        trading_day=tick.trading_day,
        ts=tick.ts,
        price=tick.price,
        volume=tick.volume,
        turnover=tick.turnover,
        open_interest=tick.open_interest,
        bid_price_1=tick.bid_price_1,
        ask_price_1=tick.ask_price_1,
        bid_volume_1=tick.bid_volume_1,
        ask_volume_1=tick.ask_volume_1,
        source=tick.source,
        raw_payload=tick.raw_payload,
    )


def market_bar_to_domain(bar: MarketBarOrm) -> Bar:
    return Bar(
        symbol=bar.symbol,
        instrument_id=bar.instrument_id,
        trade_instrument_id=bar.trade_instrument_id,
        exchange=bar.exchange,
        trading_day=bar.trading_day,
        timeframe=BarTimeframe(bar.timeframe),
        bar_ts=bar.bar_ts,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        turnover=bar.turnover,
        open_interest=bar.open_interest,
        source=bar.source,
        quality_status=MarketDataResultStatus(bar.quality_status),
        raw_payload=bar.raw_payload,
    )


def feature_snapshot_to_domain(snapshot: FeatureSnapshotOrm) -> FeatureSnapshot:
    return FeatureSnapshot(
        symbol=snapshot.symbol,
        instrument_id=snapshot.instrument_id,
        trade_instrument_id=snapshot.trade_instrument_id,
        exchange=snapshot.exchange,
        trading_day=snapshot.trading_day,
        timeframe=BarTimeframe(snapshot.timeframe),
        bar_ts=snapshot.bar_ts,
        feature_version=snapshot.feature_version,
        feature_config_hash=snapshot.feature_config_hash,
        source_bar_keys=tuple(snapshot.source_bar_keys),
        returns=snapshot.returns,
        bar_return=snapshot.bar_return,
        price_range=snapshot.price_range,
        range=snapshot.range,
        atr=snapshot.atr,
        volume_ratio=snapshot.volume_ratio,
        moving_average=snapshot.moving_average,
        bias=snapshot.bias,
        breakout_level=snapshot.breakout_level,
        volatility=snapshot.volatility,
        momentum=snapshot.momentum,
        source_window_start=snapshot.source_window_start,
        source_window_end=snapshot.source_window_end,
        warmup_complete=snapshot.warmup_complete,
        quality_status=FeatureQualityStatus(snapshot.quality_status),
        missing_bar_count=snapshot.missing_bar_count,
        gap_count=snapshot.gap_count,
        raw_payload=snapshot.raw_payload,
    )


def _snapshot_to_json(snapshot: PositionSnapshot) -> dict[str, object]:
    return cast(dict[str, object], snapshot.model_dump(mode="json"))


def _payload_tuple(
    payload: tuple[dict[str, object], ...] | list[dict[str, object]],
) -> tuple[object, ...]:
    return tuple(tuple(sorted(item.items())) for item in payload)


def _canonical_snapshot_payload(
    snapshot: PositionSnapshot | dict[str, object],
) -> tuple[object, ...]:
    typed_snapshot = (
        snapshot
        if isinstance(snapshot, PositionSnapshot)
        else PositionSnapshot.model_validate(snapshot)
    )
    return tuple(sorted(typed_snapshot.model_dump(mode="json").items()))


def _status_values(statuses: Iterable[OrderStatus]) -> list[str]:
    return [status.value for status in statuses]


def _canonical_order_payload_from_request(order_request: OrderRequest) -> tuple[object, ...]:
    return (
        order_request.account_id,
        order_request.instrument_id,
        order_request.exchange,
        order_request.direction.value,
        order_request.offset.value,
        order_request.order_type.value,
        order_request.limit_price,
        order_request.quantity,
    )


def _canonical_order_payload_from_orm(order: Order) -> tuple[object, ...]:
    return (
        order.account_id,
        order.instrument_id,
        order.exchange,
        order.direction,
        order.offset,
        order.order_type,
        order.limit_price,
        order.quantity,
    )


def _same_canonical_order_payload(order: Order, order_request: OrderRequest) -> bool:
    return _canonical_order_payload_from_orm(order) == _canonical_order_payload_from_request(
        order_request
    )


def _canonical_trade_payload_from_domain(trade: Trade) -> tuple[object, ...]:
    return (
        trade.account_id,
        trade.exchange,
        trade.exchange_trade_id,
        trade.identity_source.value,
        trade.order_id,
        trade.client_order_id,
        trade.instrument_id,
        trade.trade_instrument_id,
        trade.symbol,
        trade.direction.value,
        trade.offset.value,
        trade.price,
        trade.quantity,
        trade.fee_amount,
        trade.fee_currency,
        trade.fee_source,
        trade.trade_time,
        trade.trading_day,
        trade.source_report_id or trade.source_exchange_report_id,
        trade.source_order_event_id,
    )


def _canonical_trade_payload_from_orm(trade: TradeOrm) -> tuple[object, ...]:
    return (
        trade.account_id,
        trade.exchange,
        trade.exchange_trade_id,
        trade.identity_source or TradeIdentitySource.EXCHANGE_TRADE_ID.value,
        str(trade.order_id),
        trade.client_order_id,
        trade.instrument_id,
        trade.trade_instrument_id,
        trade.symbol,
        trade.direction,
        trade.offset,
        trade.price,
        trade.quantity,
        trade.fee_amount,
        trade.fee_currency,
        trade.fee_source,
        trade.trade_time,
        trade.trading_day,
        trade.source_report_id or trade.source_exchange_report_id,
        trade.source_order_event_id,
    )


def _same_canonical_trade_payload(existing: TradeOrm, trade: Trade) -> bool:
    return _canonical_trade_payload_from_orm(existing) == _canonical_trade_payload_from_domain(
        trade
    )


def _canonical_position_event_payload_from_domain(event: PositionEvent) -> tuple[object, ...]:
    return (
        event.account_id,
        event.instrument_id,
        event.exchange,
        event.exchange_trade_id,
        event.trade_id,
        event.position_id,
        event.event_type,
        event.direction.value,
        event.offset.value,
        event.price,
        event.quantity,
        _canonical_snapshot_payload(event.before_snapshot),
        _canonical_snapshot_payload(event.after_snapshot),
        event.occurred_at,
    )


def _canonical_position_event_payload_from_orm(event: PositionEventOrm) -> tuple[object, ...]:
    return (
        event.account_id,
        event.instrument_id,
        event.exchange,
        event.exchange_trade_id,
        str(event.trade_id),
        str(event.position_id),
        event.event_type,
        event.direction,
        event.offset,
        event.price,
        event.quantity,
        _canonical_snapshot_payload(event.before_snapshot),
        _canonical_snapshot_payload(event.after_snapshot),
        event.occurred_at,
    )


def _same_canonical_position_event_payload(
    existing: PositionEventOrm,
    event: PositionEvent,
) -> bool:
    return _canonical_position_event_payload_from_orm(
        existing
    ) == _canonical_position_event_payload_from_domain(event)


def _canonical_margin_snapshot_payload_from_domain(
    snapshot: MarginSnapshot,
) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.instrument_id,
        snapshot.position_version,
        snapshot.trading_day,
        snapshot.config_hash,
        snapshot.rule_id,
        snapshot.rule_version,
        snapshot.long_qty,
        snapshot.short_qty,
        snapshot.price,
        snapshot.contract_multiplier,
        snapshot.initial_margin,
        snapshot.maintenance_margin,
        snapshot.margin_used,
        snapshot.available_cash,
        snapshot.equity,
        snapshot.calculation_key,
    )


def _canonical_margin_snapshot_payload_from_orm(
    snapshot: MarginSnapshotOrm,
) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.instrument_id,
        snapshot.position_version,
        snapshot.trading_day,
        snapshot.config_hash,
        snapshot.rule_id,
        snapshot.rule_version,
        snapshot.long_qty,
        snapshot.short_qty,
        snapshot.price,
        snapshot.contract_multiplier,
        snapshot.initial_margin,
        snapshot.maintenance_margin,
        snapshot.margin_used,
        snapshot.available_cash,
        snapshot.equity,
        snapshot.calculation_key,
    )


def _same_canonical_margin_snapshot_payload(
    existing: MarginSnapshotOrm,
    snapshot: MarginSnapshot,
) -> bool:
    return _canonical_margin_snapshot_payload_from_orm(
        existing
    ) == _canonical_margin_snapshot_payload_from_domain(snapshot)


def _margin_position_version_payload_from_domain(snapshot: MarginSnapshot) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.instrument_id,
        snapshot.position_version,
        snapshot.trading_day,
        snapshot.config_hash,
        snapshot.rule_id,
        snapshot.rule_version,
        snapshot.long_qty,
        snapshot.short_qty,
        snapshot.price,
        snapshot.contract_multiplier,
        snapshot.initial_margin,
        snapshot.maintenance_margin,
        snapshot.margin_used,
        snapshot.available_cash,
        snapshot.equity,
    )


def _margin_position_version_payload_from_orm(snapshot: MarginSnapshotOrm) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.instrument_id,
        snapshot.position_version,
        snapshot.trading_day,
        snapshot.config_hash,
        snapshot.rule_id,
        snapshot.rule_version,
        snapshot.long_qty,
        snapshot.short_qty,
        snapshot.price,
        snapshot.contract_multiplier,
        snapshot.initial_margin,
        snapshot.maintenance_margin,
        snapshot.margin_used,
        snapshot.available_cash,
        snapshot.equity,
    )


def _same_margin_position_version_payload(
    existing: MarginSnapshotOrm,
    snapshot: MarginSnapshot,
) -> bool:
    return _margin_position_version_payload_from_orm(
        existing
    ) == _margin_position_version_payload_from_domain(snapshot)


def _canonical_pnl_snapshot_payload_from_domain(snapshot: PnLSnapshot) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.instrument_id,
        snapshot.position_version,
        snapshot.trading_day,
        snapshot.config_hash,
        snapshot.trade_id,
        snapshot.margin_snapshot_id,
        snapshot.calculation_key,
        snapshot.price_basis.value,
        snapshot.mark_price,
        snapshot.contract_multiplier,
        snapshot.realized_pnl,
        snapshot.unrealized_pnl,
        snapshot.total_pnl,
        snapshot.fee_amount,
    )


def _canonical_pnl_snapshot_payload_from_orm(snapshot: PnLSnapshotOrm) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.instrument_id,
        snapshot.position_version,
        snapshot.trading_day,
        snapshot.config_hash,
        snapshot.trade_id,
        snapshot.margin_snapshot_id,
        snapshot.calculation_key,
        snapshot.price_basis,
        snapshot.mark_price,
        snapshot.contract_multiplier,
        snapshot.realized_pnl,
        snapshot.unrealized_pnl,
        snapshot.total_pnl,
        snapshot.fee_amount,
    )


def _same_canonical_pnl_snapshot_payload(
    existing: PnLSnapshotOrm,
    snapshot: PnLSnapshot,
) -> bool:
    return _canonical_pnl_snapshot_payload_from_orm(
        existing
    ) == _canonical_pnl_snapshot_payload_from_domain(snapshot)


def _pnl_position_version_payload_from_domain(snapshot: PnLSnapshot) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.instrument_id,
        snapshot.position_version,
        snapshot.trading_day,
        snapshot.config_hash,
        snapshot.trade_id,
        snapshot.margin_snapshot_id,
        snapshot.price_basis.value,
        snapshot.mark_price,
        snapshot.contract_multiplier,
        snapshot.realized_pnl,
        snapshot.unrealized_pnl,
        snapshot.total_pnl,
        snapshot.fee_amount,
    )


def _pnl_position_version_payload_from_orm(snapshot: PnLSnapshotOrm) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.instrument_id,
        snapshot.position_version,
        snapshot.trading_day,
        snapshot.config_hash,
        snapshot.trade_id,
        snapshot.margin_snapshot_id,
        snapshot.price_basis,
        snapshot.mark_price,
        snapshot.contract_multiplier,
        snapshot.realized_pnl,
        snapshot.unrealized_pnl,
        snapshot.total_pnl,
        snapshot.fee_amount,
    )


def _same_pnl_position_version_payload(
    existing: PnLSnapshotOrm,
    snapshot: PnLSnapshot,
) -> bool:
    return _pnl_position_version_payload_from_orm(
        existing
    ) == _pnl_position_version_payload_from_domain(snapshot)


def _canonical_settlement_snapshot_payload_from_domain(
    snapshot: SettlementSnapshot,
) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.trading_day,
        snapshot.calculation_key,
        _payload_tuple(snapshot.positions_before),
        _payload_tuple(snapshot.positions_after),
        _payload_tuple(snapshot.settlement_prices),
        snapshot.pnl_snapshot_ids,
        snapshot.margin_snapshot_ids,
        snapshot.cash_before,
        snapshot.cash_after,
        snapshot.realized_pnl,
        snapshot.unrealized_pnl,
        snapshot.margin_used,
        snapshot.status.value,
    )


def _canonical_settlement_snapshot_payload_from_orm(
    snapshot: SettlementSnapshotOrm,
) -> tuple[object, ...]:
    return (
        snapshot.account_id,
        snapshot.trading_day,
        snapshot.calculation_key,
        _payload_tuple(cast(list[dict[str, object]], snapshot.positions_before)),
        _payload_tuple(cast(list[dict[str, object]], snapshot.positions_after)),
        _payload_tuple(cast(list[dict[str, object]], snapshot.settlement_prices)),
        tuple(snapshot.pnl_snapshot_ids),
        tuple(snapshot.margin_snapshot_ids),
        snapshot.cash_before,
        snapshot.cash_after,
        snapshot.realized_pnl,
        snapshot.unrealized_pnl,
        snapshot.margin_used,
        snapshot.status,
    )


def _same_canonical_settlement_snapshot_payload(
    existing: SettlementSnapshotOrm,
    snapshot: SettlementSnapshot,
) -> bool:
    return _canonical_settlement_snapshot_payload_from_orm(
        existing
    ) == _canonical_settlement_snapshot_payload_from_domain(snapshot)


def _canonical_tick_payload_from_orm(tick: MarketTickOrm) -> tuple[object, ...]:
    return (
        tick.exchange,
        tick.instrument_id,
        tick.trade_instrument_id,
        tick.symbol,
        tick.trading_day,
        tick.ts,
        tick.price,
        tick.volume,
        tick.turnover,
        tick.open_interest,
        tick.bid_price_1,
        tick.ask_price_1,
        tick.bid_volume_1,
        tick.ask_volume_1,
        tick.source,
    )


def _same_canonical_tick_payload(existing: MarketTickOrm, tick: Tick) -> bool:
    return _canonical_tick_payload_from_orm(existing) == canonical_tick_payload(tick)


def _canonical_bar_payload_from_orm(bar: MarketBarOrm) -> tuple[object, ...]:
    return (
        bar.exchange,
        bar.instrument_id,
        bar.trade_instrument_id,
        bar.symbol,
        bar.trading_day,
        bar.timeframe,
        bar.bar_ts,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        bar.turnover,
        bar.open_interest,
        bar.source,
        bar.quality_status,
    )


def _same_canonical_bar_payload(existing: MarketBarOrm, bar: Bar) -> bool:
    return _canonical_bar_payload_from_orm(existing) == canonical_bar_payload(bar)


def _canonical_feature_snapshot_payload_from_orm(
    snapshot: FeatureSnapshotOrm,
) -> tuple[object, ...]:
    return canonical_feature_snapshot_payload(feature_snapshot_to_domain(snapshot))


def _same_canonical_feature_snapshot_payload(
    existing: FeatureSnapshotOrm,
    snapshot: FeatureSnapshot,
) -> bool:
    return _canonical_feature_snapshot_payload_from_orm(
        existing
    ) == canonical_feature_snapshot_payload(snapshot)


class SQLAlchemyMarketTickRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_tick(self, tick: Tick) -> Tick:
        existing = self._get_orm_by_identity(
            tick.exchange,
            tick.instrument_id,
            tick.ts,
            tick.source,
        )
        if existing is not None:
            return self._existing_tick_for_append(existing, tick)

        try:
            with self._session.begin_nested():
                tick_orm = self._new_tick(tick)
                self._session.add(tick_orm)
                self._session.flush()
            return market_tick_to_domain(tick_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_identity(
                tick.exchange,
                tick.instrument_id,
                tick.ts,
                tick.source,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "market tick unique conflict but tick not found: "
                    f"{tick.exchange}/{tick.instrument_id}/{tick.ts}/{tick.source}"
                ) from exc
            return self._existing_tick_for_append(existing_after_conflict, tick)

    def get_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        ts: datetime,
        source: str,
    ) -> Tick | None:
        tick = self._get_orm_by_identity(exchange, instrument_id, ts, source)
        return market_tick_to_domain(tick) if tick else None

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[Tick]:
        ticks = self._session.scalars(
            select(MarketTickOrm)
            .where(
                MarketTickOrm.exchange == exchange,
                MarketTickOrm.instrument_id == instrument_id,
                MarketTickOrm.ts >= start_ts,
                MarketTickOrm.ts <= end_ts,
            )
            .order_by(MarketTickOrm.ts.asc(), MarketTickOrm.id.asc())
        ).all()
        return [market_tick_to_domain(tick) for tick in ticks]

    def list_by_trading_day(
        self,
        exchange: str,
        instrument_id: str,
        trading_day: date,
    ) -> list[Tick]:
        ticks = self._session.scalars(
            select(MarketTickOrm)
            .where(
                MarketTickOrm.exchange == exchange,
                MarketTickOrm.instrument_id == instrument_id,
                MarketTickOrm.trading_day == trading_day,
            )
            .order_by(MarketTickOrm.ts.asc(), MarketTickOrm.id.asc())
        ).all()
        return [market_tick_to_domain(tick) for tick in ticks]

    def _new_tick(self, tick: Tick) -> MarketTickOrm:
        return MarketTickOrm(
            symbol=tick.symbol,
            instrument_id=tick.instrument_id,
            trade_instrument_id=tick.trade_instrument_id,
            exchange=tick.exchange,
            trading_day=tick.trading_day,
            ts=tick.ts,
            price=tick.price,
            volume=tick.volume,
            turnover=tick.turnover,
            open_interest=tick.open_interest,
            bid_price_1=tick.bid_price_1,
            ask_price_1=tick.ask_price_1,
            bid_volume_1=tick.bid_volume_1,
            ask_volume_1=tick.ask_volume_1,
            source=tick.source,
            raw_payload=tick.raw_payload,
        )

    def _get_orm_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        ts: datetime,
        source: str,
    ) -> MarketTickOrm | None:
        return self._session.scalar(
            select(MarketTickOrm).where(
                MarketTickOrm.exchange == exchange,
                MarketTickOrm.instrument_id == instrument_id,
                MarketTickOrm.ts == ts,
                MarketTickOrm.source == source,
            )
        )

    def _existing_tick_for_append(self, existing: MarketTickOrm, tick: Tick) -> Tick:
        if not _same_canonical_tick_payload(existing, tick):
            raise MarketDataConflictError(
                "market tick identity reused with different canonical payload: "
                f"{tick.exchange}/{tick.instrument_id}/{tick.ts}/{tick.source}"
            )
        return market_tick_to_domain(existing)


class SQLAlchemyMarketBarRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_bar(self, bar: Bar) -> Bar:
        existing = self._get_orm_by_identity(
            bar.exchange,
            bar.instrument_id,
            bar.timeframe,
            bar.bar_ts,
            bar.source,
        )
        if existing is not None:
            return self._existing_bar_for_append(existing, bar)

        try:
            with self._session.begin_nested():
                bar_orm = self._new_bar(bar)
                self._session.add(bar_orm)
                self._session.flush()
            return market_bar_to_domain(bar_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_identity(
                bar.exchange,
                bar.instrument_id,
                bar.timeframe,
                bar.bar_ts,
                bar.source,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "market bar unique conflict but bar not found: "
                    f"{bar.exchange}/{bar.instrument_id}/{bar.timeframe}/{bar.bar_ts}/{bar.source}"
                ) from exc
            return self._existing_bar_for_append(existing_after_conflict, bar)

    def get_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        bar_ts: datetime,
        source: str,
    ) -> Bar | None:
        bar = self._get_orm_by_identity(exchange, instrument_id, timeframe, bar_ts, source)
        return market_bar_to_domain(bar) if bar else None

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[Bar]:
        bars = self._session.scalars(
            select(MarketBarOrm)
            .where(
                MarketBarOrm.exchange == exchange,
                MarketBarOrm.instrument_id == instrument_id,
                MarketBarOrm.timeframe == timeframe.value,
                MarketBarOrm.bar_ts >= start_bar_ts,
                MarketBarOrm.bar_ts <= end_bar_ts,
            )
            .order_by(MarketBarOrm.bar_ts.asc(), MarketBarOrm.id.asc())
        ).all()
        return [market_bar_to_domain(bar) for bar in bars]

    def list_by_trading_day(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        trading_day: date,
    ) -> list[Bar]:
        bars = self._session.scalars(
            select(MarketBarOrm)
            .where(
                MarketBarOrm.exchange == exchange,
                MarketBarOrm.instrument_id == instrument_id,
                MarketBarOrm.timeframe == timeframe.value,
                MarketBarOrm.trading_day == trading_day,
            )
            .order_by(MarketBarOrm.bar_ts.asc(), MarketBarOrm.id.asc())
        ).all()
        return [market_bar_to_domain(bar) for bar in bars]

    def _new_bar(self, bar: Bar) -> MarketBarOrm:
        return MarketBarOrm(
            symbol=bar.symbol,
            instrument_id=bar.instrument_id,
            trade_instrument_id=bar.trade_instrument_id,
            exchange=bar.exchange,
            trading_day=bar.trading_day,
            timeframe=bar.timeframe.value,
            bar_ts=bar.bar_ts,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            turnover=bar.turnover,
            open_interest=bar.open_interest,
            source=bar.source,
            quality_status=bar.quality_status.value,
            raw_payload=bar.raw_payload,
        )

    def _get_orm_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        bar_ts: datetime,
        source: str,
    ) -> MarketBarOrm | None:
        return self._session.scalar(
            select(MarketBarOrm).where(
                MarketBarOrm.exchange == exchange,
                MarketBarOrm.instrument_id == instrument_id,
                MarketBarOrm.timeframe == timeframe.value,
                MarketBarOrm.bar_ts == bar_ts,
                MarketBarOrm.source == source,
            )
        )

    def _existing_bar_for_append(self, existing: MarketBarOrm, bar: Bar) -> Bar:
        if not _same_canonical_bar_payload(existing, bar):
            raise MarketDataConflictError(
                "market bar identity reused with different canonical payload: "
                f"{bar.exchange}/{bar.instrument_id}/{bar.timeframe}/{bar.bar_ts}/{bar.source}"
            )
        return market_bar_to_domain(existing)


class SQLAlchemyFeatureSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_feature_snapshot(self, snapshot: FeatureSnapshot) -> FeatureSnapshot:
        existing = self._get_orm_by_identity(
            snapshot.exchange,
            snapshot.instrument_id,
            snapshot.timeframe,
            snapshot.bar_ts,
            snapshot.feature_version,
            snapshot.feature_config_hash,
        )
        if existing is not None:
            return self._existing_snapshot_for_append(existing, snapshot)

        try:
            with self._session.begin_nested():
                snapshot_orm = self._new_snapshot(snapshot)
                self._session.add(snapshot_orm)
                self._session.flush()
            return feature_snapshot_to_domain(snapshot_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_identity(
                snapshot.exchange,
                snapshot.instrument_id,
                snapshot.timeframe,
                snapshot.bar_ts,
                snapshot.feature_version,
                snapshot.feature_config_hash,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "feature snapshot unique conflict but snapshot not found: "
                    f"{snapshot.exchange}/{snapshot.instrument_id}/"
                    f"{snapshot.timeframe}/{snapshot.bar_ts}/{snapshot.feature_version}/"
                    f"{snapshot.feature_config_hash}"
                ) from exc
            return self._existing_snapshot_for_append(existing_after_conflict, snapshot)

    def get_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        bar_ts: datetime,
        feature_version: str,
        feature_config_hash: str,
    ) -> FeatureSnapshot | None:
        snapshot = self._get_orm_by_identity(
            exchange,
            instrument_id,
            timeframe,
            bar_ts,
            feature_version,
            feature_config_hash,
        )
        return feature_snapshot_to_domain(snapshot) if snapshot else None

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[FeatureSnapshot]:
        snapshots = self._session.scalars(
            select(FeatureSnapshotOrm)
            .where(
                FeatureSnapshotOrm.exchange == exchange,
                FeatureSnapshotOrm.instrument_id == instrument_id,
                FeatureSnapshotOrm.timeframe == timeframe.value,
                FeatureSnapshotOrm.bar_ts >= start_bar_ts,
                FeatureSnapshotOrm.bar_ts <= end_bar_ts,
            )
            .order_by(FeatureSnapshotOrm.bar_ts.asc(), FeatureSnapshotOrm.id.asc())
        ).all()
        return [feature_snapshot_to_domain(snapshot) for snapshot in snapshots]

    def list_by_trading_day(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        trading_day: date,
    ) -> list[FeatureSnapshot]:
        snapshots = self._session.scalars(
            select(FeatureSnapshotOrm)
            .where(
                FeatureSnapshotOrm.exchange == exchange,
                FeatureSnapshotOrm.instrument_id == instrument_id,
                FeatureSnapshotOrm.timeframe == timeframe.value,
                FeatureSnapshotOrm.trading_day == trading_day,
            )
            .order_by(FeatureSnapshotOrm.bar_ts.asc(), FeatureSnapshotOrm.id.asc())
        ).all()
        return [feature_snapshot_to_domain(snapshot) for snapshot in snapshots]

    def _new_snapshot(self, snapshot: FeatureSnapshot) -> FeatureSnapshotOrm:
        return FeatureSnapshotOrm(
            symbol=snapshot.symbol,
            instrument_id=snapshot.instrument_id,
            trade_instrument_id=snapshot.trade_instrument_id,
            exchange=snapshot.exchange,
            trading_day=snapshot.trading_day,
            timeframe=snapshot.timeframe.value,
            bar_ts=snapshot.bar_ts,
            feature_version=snapshot.feature_version,
            feature_config_hash=snapshot.feature_config_hash,
            source_bar_keys=list(snapshot.source_bar_keys),
            returns=snapshot.returns,
            bar_return=snapshot.bar_return,
            price_range=snapshot.price_range,
            range=snapshot.range,
            atr=snapshot.atr,
            volume_ratio=snapshot.volume_ratio,
            moving_average=snapshot.moving_average,
            bias=snapshot.bias,
            breakout_level=snapshot.breakout_level,
            volatility=snapshot.volatility,
            momentum=snapshot.momentum,
            source_window_start=snapshot.source_window_start,
            source_window_end=snapshot.source_window_end,
            warmup_complete=snapshot.warmup_complete,
            quality_status=snapshot.quality_status.value,
            missing_bar_count=snapshot.missing_bar_count,
            gap_count=snapshot.gap_count,
            raw_payload=snapshot.raw_payload,
        )

    def _get_orm_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        bar_ts: datetime,
        feature_version: str,
        feature_config_hash: str,
    ) -> FeatureSnapshotOrm | None:
        return self._session.scalar(
            select(FeatureSnapshotOrm).where(
                FeatureSnapshotOrm.exchange == exchange,
                FeatureSnapshotOrm.instrument_id == instrument_id,
                FeatureSnapshotOrm.timeframe == timeframe.value,
                FeatureSnapshotOrm.bar_ts == bar_ts,
                FeatureSnapshotOrm.feature_version == feature_version,
                FeatureSnapshotOrm.feature_config_hash == feature_config_hash,
            )
        )

    def _existing_snapshot_for_append(
        self,
        existing: FeatureSnapshotOrm,
        snapshot: FeatureSnapshot,
    ) -> FeatureSnapshot:
        if not _same_canonical_feature_snapshot_payload(existing, snapshot):
            raise FeatureSnapshotConflictError(
                "feature snapshot identity reused with different canonical payload: "
                f"{snapshot.exchange}/{snapshot.instrument_id}/"
                f"{snapshot.timeframe}/{snapshot.bar_ts}/{snapshot.feature_version}/"
                f"{snapshot.feature_config_hash}"
            )
        return feature_snapshot_to_domain(existing)


class SQLAlchemySignalCandidateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_signal_candidate(self, candidate: SignalCandidate) -> SignalCandidate:
        existing = self.get_by_signal_id(candidate.signal_id)
        if existing is not None:
            return self._existing_candidate_for_append(existing, candidate)

        try:
            with self._session.begin_nested():
                candidate_orm = self._new_candidate(candidate)
                self._session.add(candidate_orm)
                self._session.flush()
            return signal_candidate_to_domain(candidate_orm)
        except IntegrityError as exc:
            existing_after_conflict = self.get_by_signal_id(candidate.signal_id)
            if existing_after_conflict is not None:
                return self._existing_candidate_for_append(existing_after_conflict, candidate)
            composite_conflict = self._get_by_composite_identity(candidate)
            if composite_conflict is not None:
                raise SignalCandidateConflictError(
                    "signal candidate composite identity reused with different signal_id: "
                    f"{candidate.strategy_name}/{candidate.strategy_version}/"
                    f"{candidate.instrument_id}/{candidate.timeframe}/{candidate.bar_ts}"
                ) from exc
            raise RepositoryError(
                "signal candidate unique conflict but candidate not found"
            ) from exc

    def get_by_signal_id(self, signal_id: str) -> SignalCandidate | None:
        candidate = self._session.scalar(
            select(SignalCandidateOrm).where(SignalCandidateOrm.signal_id == signal_id)
        )
        return signal_candidate_to_domain(candidate) if candidate else None

    def list_by_strategy(
        self,
        strategy_name: str,
        strategy_version: str,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[SignalCandidate]:
        candidates = self._session.scalars(
            select(SignalCandidateOrm)
            .where(
                SignalCandidateOrm.strategy_name == strategy_name,
                SignalCandidateOrm.strategy_version == strategy_version,
                SignalCandidateOrm.bar_ts >= start_bar_ts,
                SignalCandidateOrm.bar_ts <= end_bar_ts,
            )
            .order_by(SignalCandidateOrm.bar_ts.asc(), SignalCandidateOrm.signal_id.asc())
        ).all()
        return [signal_candidate_to_domain(candidate) for candidate in candidates]

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[SignalCandidate]:
        candidates = self._session.scalars(
            select(SignalCandidateOrm)
            .where(
                SignalCandidateOrm.exchange == exchange,
                SignalCandidateOrm.instrument_id == instrument_id,
                SignalCandidateOrm.timeframe == timeframe.value,
                SignalCandidateOrm.bar_ts >= start_bar_ts,
                SignalCandidateOrm.bar_ts <= end_bar_ts,
            )
            .order_by(SignalCandidateOrm.bar_ts.asc(), SignalCandidateOrm.signal_id.asc())
        ).all()
        return [signal_candidate_to_domain(candidate) for candidate in candidates]

    def _new_candidate(self, candidate: SignalCandidate) -> SignalCandidateOrm:
        return SignalCandidateOrm(
            signal_id=candidate.signal_id,
            strategy_name=candidate.strategy_name,
            strategy_version=candidate.strategy_version,
            strategy_config_hash=candidate.strategy_config_hash,
            runtime_id=candidate.runtime_id,
            symbol=candidate.symbol,
            instrument_id=candidate.instrument_id,
            trade_instrument_id=candidate.trade_instrument_id,
            exchange=candidate.exchange,
            trading_day=candidate.trading_day,
            timeframe=candidate.timeframe.value,
            bar_ts=candidate.bar_ts,
            feature_version=candidate.feature_version,
            feature_config_hash=candidate.feature_config_hash,
            decision=candidate.decision.value,
            side=candidate.side.value,
            position_side=candidate.position_side.value,
            confidence=candidate.confidence,
            strength=candidate.strength,
            reason=candidate.reason,
            expected_price=candidate.expected_price,
            stop_loss=candidate.stop_loss,
            take_profit=candidate.take_profit,
            holding_period_hint=candidate.holding_period_hint,
            tags=candidate.tags,
            features_ref=candidate.features_ref,
            raw_payload=candidate.raw_payload,
        )

    def _get_by_composite_identity(
        self,
        candidate: SignalCandidate,
    ) -> SignalCandidate | None:
        existing = self._session.scalar(
            select(SignalCandidateOrm).where(
                SignalCandidateOrm.strategy_name == candidate.strategy_name,
                SignalCandidateOrm.strategy_version == candidate.strategy_version,
                SignalCandidateOrm.strategy_config_hash == candidate.strategy_config_hash,
                SignalCandidateOrm.instrument_id == candidate.instrument_id,
                SignalCandidateOrm.timeframe == candidate.timeframe.value,
                SignalCandidateOrm.bar_ts == candidate.bar_ts,
                SignalCandidateOrm.feature_version == candidate.feature_version,
                SignalCandidateOrm.feature_config_hash == candidate.feature_config_hash,
            )
        )
        return signal_candidate_to_domain(existing) if existing else None

    def _existing_candidate_for_append(
        self,
        existing: SignalCandidate,
        candidate: SignalCandidate,
    ) -> SignalCandidate:
        if canonical_signal_candidate_payload(existing) != canonical_signal_candidate_payload(
            candidate
        ):
            raise SignalCandidateConflictError(
                f"signal candidate identity reused with different canonical payload: "
                f"{candidate.signal_id}"
            )
        return existing


class SQLAlchemySignalEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_signal_event(self, event: SignalLifecycleEvent) -> SignalLifecycleEvent:
        existing = self.get_by_event_key(event.event_key)
        if existing is not None:
            return self._existing_event_for_append(existing, event)

        try:
            with self._session.begin_nested():
                event_orm = SignalEventOrm(
                    event_key=event.event_key,
                    signal_id=event.signal_id,
                    lifecycle_status=event.lifecycle_status.value,
                    event_reason=event.event_reason,
                    event_ts=event.event_ts,
                    raw_payload=event.raw_payload,
                )
                self._session.add(event_orm)
                self._session.flush()
            return signal_event_to_domain(event_orm)
        except IntegrityError as exc:
            existing_after_conflict = self.get_by_event_key(event.event_key)
            if existing_after_conflict is not None:
                return self._existing_event_for_append(existing_after_conflict, event)
            raise SignalLifecycleConflictError(
                f"signal lifecycle event append failed: {event.signal_id}"
            ) from exc

    def get_by_event_key(self, event_key: str) -> SignalLifecycleEvent | None:
        event = self._session.scalar(
            select(SignalEventOrm).where(SignalEventOrm.event_key == event_key)
        )
        return signal_event_to_domain(event) if event else None

    def list_by_signal_id(self, signal_id: str) -> list[SignalLifecycleEvent]:
        events = self._session.scalars(
            select(SignalEventOrm)
            .where(SignalEventOrm.signal_id == signal_id)
            .order_by(SignalEventOrm.event_ts.asc(), SignalEventOrm.id.asc())
        ).all()
        return [signal_event_to_domain(event) for event in events]

    def get_latest_status(self, signal_id: str) -> SignalLifecycleEvent | None:
        event = self._session.scalar(
            select(SignalEventOrm)
            .where(SignalEventOrm.signal_id == signal_id)
            .order_by(SignalEventOrm.event_ts.desc(), SignalEventOrm.id.desc())
            .limit(1)
        )
        return signal_event_to_domain(event) if event else None

    def _existing_event_for_append(
        self,
        existing: SignalLifecycleEvent,
        event: SignalLifecycleEvent,
    ) -> SignalLifecycleEvent:
        if canonical_signal_event_payload(existing) != canonical_signal_event_payload(event):
            raise SignalLifecycleConflictError(
                f"signal lifecycle event key reused with different canonical payload: "
                f"{event.event_key}"
            )
        return existing


class SQLAlchemyTradingRiskResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_risk_result(self, result: TradingRiskResult) -> TradingRiskResult:
        existing = self.get_by_risk_result_id(result.risk_result_id)
        if existing is not None:
            return self._existing_result_for_append(existing, result)

        try:
            with self._session.begin_nested():
                result_orm = TradingRiskResultOrm(
                    risk_result_id=result.risk_result_id,
                    signal_id=result.signal_id,
                    evaluation_context_hash=result.evaluation_context_hash,
                    risk_status=result.risk_status.value,
                    risk_reason=result.risk_reason,
                    risk_level=result.risk_level,
                    requested_quantity=result.requested_quantity,
                    approved_quantity=result.approved_quantity,
                    max_quantity=result.max_quantity,
                    expected_margin=result.expected_margin,
                    expected_notional=result.expected_notional,
                    config_hash=result.config_hash,
                    evaluation_ts=result.evaluation_ts,
                    raw_payload=result.raw_payload,
                )
                self._session.add(result_orm)
                self._session.flush()
            return trading_risk_result_to_domain(result_orm)
        except IntegrityError as exc:
            existing_after_conflict = self.get_by_risk_result_id(result.risk_result_id)
            if existing_after_conflict is not None:
                return self._existing_result_for_append(existing_after_conflict, result)
            raise RepositoryError(
                f"trading risk result append failed: {result.risk_result_id}"
            ) from exc

    def get_by_risk_result_id(self, risk_result_id: str) -> TradingRiskResult | None:
        result = self._session.scalar(
            select(TradingRiskResultOrm).where(
                TradingRiskResultOrm.risk_result_id == risk_result_id
            )
        )
        return trading_risk_result_to_domain(result) if result else None

    def list_by_signal_id(self, signal_id: str) -> list[TradingRiskResult]:
        results = self._session.scalars(
            select(TradingRiskResultOrm)
            .where(TradingRiskResultOrm.signal_id == signal_id)
            .order_by(TradingRiskResultOrm.evaluation_ts.asc(), TradingRiskResultOrm.id.asc())
        ).all()
        return [trading_risk_result_to_domain(result) for result in results]

    def _existing_result_for_append(
        self,
        existing: TradingRiskResult,
        result: TradingRiskResult,
    ) -> TradingRiskResult:
        if canonical_trading_risk_result_payload(
            existing
        ) != canonical_trading_risk_result_payload(result):
            raise TradingRiskResultConflictError(
                "trading risk result identity reused with different canonical payload: "
                f"{result.risk_result_id}"
            )
        return existing


class SQLAlchemyOrderIntentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_order_intent(self, intent: OrderIntent) -> OrderIntent:
        existing = self.get_by_intent_id(intent.intent_id)
        if existing is not None:
            return self._existing_intent_for_append(existing, intent)

        try:
            with self._session.begin_nested():
                intent_orm = OrderIntentOrm(
                    intent_id=intent.intent_id,
                    signal_id=intent.signal_id,
                    risk_result_id=intent.risk_result_id,
                    strategy_name=intent.strategy_name,
                    strategy_version=intent.strategy_version,
                    strategy_config_hash=intent.strategy_config_hash,
                    runtime_id=intent.runtime_id,
                    symbol=intent.symbol,
                    instrument_id=intent.instrument_id,
                    trade_instrument_id=intent.trade_instrument_id,
                    exchange=intent.exchange,
                    trading_day=intent.trading_day,
                    timeframe=intent.timeframe.value,
                    bar_ts=intent.bar_ts,
                    feature_version=intent.feature_version,
                    feature_config_hash=intent.feature_config_hash,
                    side=intent.side.value,
                    offset=intent.offset.value,
                    quantity=intent.quantity,
                    price=intent.price,
                    order_type=intent.order_type.value,
                    tif=intent.tif,
                    expected_margin=intent.expected_margin,
                    expected_notional=intent.expected_notional,
                    intent_reason=intent.intent_reason,
                    raw_payload=intent.raw_payload,
                )
                self._session.add(intent_orm)
                self._session.flush()
            return order_intent_to_domain(intent_orm)
        except IntegrityError as exc:
            existing_after_conflict = self.get_by_intent_id(intent.intent_id)
            if existing_after_conflict is not None:
                return self._existing_intent_for_append(existing_after_conflict, intent)
            raise RepositoryError(f"order intent append failed: {intent.intent_id}") from exc

    def get_by_intent_id(self, intent_id: str) -> OrderIntent | None:
        intent = self._session.scalar(
            select(OrderIntentOrm).where(OrderIntentOrm.intent_id == intent_id)
        )
        return order_intent_to_domain(intent) if intent else None

    def list_by_signal_id(self, signal_id: str) -> list[OrderIntent]:
        intents = self._session.scalars(
            select(OrderIntentOrm)
            .where(OrderIntentOrm.signal_id == signal_id)
            .order_by(OrderIntentOrm.created_at.asc(), OrderIntentOrm.id.asc())
        ).all()
        return [order_intent_to_domain(intent) for intent in intents]

    def _existing_intent_for_append(
        self,
        existing: OrderIntent,
        intent: OrderIntent,
    ) -> OrderIntent:
        if canonical_order_intent_payload(existing) != canonical_order_intent_payload(intent):
            raise OrderIntentConflictError(
                "order intent identity reused with different canonical payload: "
                f"{intent.intent_id}"
            )
        return existing


class SQLAlchemyExecutionCommandRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_execution_command(self, command: ExecutionCommand) -> ExecutionCommand:
        existing = self.get_by_command_id(command.command_id)
        if existing is not None:
            return self._existing_command_for_append(existing, command)

        try:
            with self._session.begin_nested():
                command_orm = ExecutionCommandOrm(
                    command_id=command.command_id,
                    order_id=command.order_id,
                    client_order_id=command.client_order_id,
                    account_id=command.account_id,
                    symbol=command.symbol,
                    instrument_id=command.instrument_id,
                    trade_instrument_id=command.trade_instrument_id,
                    exchange=command.exchange,
                    side=command.side.value,
                    offset=command.offset.value,
                    quantity=command.quantity,
                    price=command.price,
                    order_type=command.order_type.value,
                    tif=command.tif,
                    command_type=command.command_type.value,
                    execution_target=command.execution_target.value,
                    command_payload_hash=command.command_payload_hash,
                    raw_payload=command.raw_payload,
                    created_at=command.created_at,
                )
                self._session.add(command_orm)
                self._session.flush()
            return execution_command_to_domain(command_orm)
        except IntegrityError as exc:
            existing_after_conflict = self.get_by_command_id(command.command_id)
            if existing_after_conflict is not None:
                return self._existing_command_for_append(existing_after_conflict, command)
            raise RepositoryError(
                f"execution command append failed: {command.command_id}"
            ) from exc

    def get_by_command_id(self, command_id: str) -> ExecutionCommand | None:
        command = self._session.scalar(
            select(ExecutionCommandOrm).where(ExecutionCommandOrm.command_id == command_id)
        )
        return execution_command_to_domain(command) if command else None

    def list_by_order_id(self, order_id: str) -> list[ExecutionCommand]:
        commands = self._session.scalars(
            select(ExecutionCommandOrm)
            .where(ExecutionCommandOrm.order_id == order_id)
            .order_by(ExecutionCommandOrm.created_at.asc(), ExecutionCommandOrm.id.asc())
        ).all()
        return [execution_command_to_domain(command) for command in commands]

    def list_by_target(
        self,
        execution_target: ExecutionTarget | str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[ExecutionCommand]:
        target_value = (
            execution_target.value
            if isinstance(execution_target, ExecutionTarget)
            else execution_target
        )
        statement = select(ExecutionCommandOrm).where(
            ExecutionCommandOrm.execution_target == target_value
        )
        if start_ts is not None:
            statement = statement.where(ExecutionCommandOrm.created_at >= start_ts)
        if end_ts is not None:
            statement = statement.where(ExecutionCommandOrm.created_at <= end_ts)
        commands = self._session.scalars(
            statement.order_by(ExecutionCommandOrm.created_at.asc(), ExecutionCommandOrm.id.asc())
        ).all()
        return [execution_command_to_domain(command) for command in commands]

    def _existing_command_for_append(
        self,
        existing: ExecutionCommand,
        command: ExecutionCommand,
    ) -> ExecutionCommand:
        if canonical_execution_command_payload(existing) != canonical_execution_command_payload(
            command
        ):
            raise ExecutionCommandConflictError(
                "execution command identity reused with different canonical payload: "
                f"{command.command_id}"
            )
        if existing.command_payload_hash != command.command_payload_hash:
            raise ExecutionCommandConflictError(
                "execution command payload hash conflict: " f"{command.command_id}"
            )
        return existing


class SQLAlchemyExecutionReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_normalized_report(
        self,
        report: NormalizedExecutionReport,
    ) -> NormalizedExecutionReport:
        existing = self.get_by_report_id(report.report_id)
        if existing is not None:
            return self._existing_report_for_append(existing, report)

        try:
            with self._session.begin_nested():
                report_orm = NormalizedExecutionReportOrm(
                    report_id=report.report_id,
                    raw_report_id=report.raw_report_id,
                    adapter_name=report.adapter_name,
                    execution_target=report.execution_target.value,
                    command_id=report.command_id,
                    order_id=report.order_id,
                    client_order_id=report.client_order_id,
                    adapter_order_ref=report.adapter_order_ref,
                    exchange_order_id=report.exchange_order_id,
                    exchange_trade_id=report.exchange_trade_id,
                    fill_id=report.fill_id,
                    execution_status=report.execution_status.value,
                    filled_qty=report.filled_qty,
                    fill_price=report.fill_price,
                    cumulative_filled_qty=report.cumulative_filled_qty,
                    remaining_qty=report.remaining_qty,
                    fee_amount=report.fee_amount,
                    fee_currency=report.fee_currency,
                    fee_source=report.fee_source,
                    report_ts=report.report_ts,
                    source_report_hash=report.source_report_hash,
                    reason=report.reason,
                    raw_payload=report.raw_payload,
                    normalized_at=report.normalized_at,
                )
                self._session.add(report_orm)
                self._session.flush()
            return normalized_execution_report_to_domain(report_orm)
        except IntegrityError as exc:
            existing_after_conflict = self.get_by_report_id(report.report_id)
            if existing_after_conflict is not None:
                return self._existing_report_for_append(existing_after_conflict, report)
            raise RepositoryError(
                f"normalized execution report append failed: {report.report_id}"
            ) from exc

    def get_by_report_id(self, report_id: str) -> NormalizedExecutionReport | None:
        report = self._session.scalar(
            select(NormalizedExecutionReportOrm).where(
                NormalizedExecutionReportOrm.report_id == report_id
            )
        )
        return normalized_execution_report_to_domain(report) if report else None

    def list_by_order_id(self, order_id: str) -> list[NormalizedExecutionReport]:
        reports = self._session.scalars(
            select(NormalizedExecutionReportOrm)
            .where(NormalizedExecutionReportOrm.order_id == order_id)
            .order_by(
                NormalizedExecutionReportOrm.report_ts.asc(),
                NormalizedExecutionReportOrm.id.asc(),
            )
        ).all()
        return [normalized_execution_report_to_domain(report) for report in reports]

    def list_by_command_id(self, command_id: str) -> list[NormalizedExecutionReport]:
        reports = self._session.scalars(
            select(NormalizedExecutionReportOrm)
            .where(NormalizedExecutionReportOrm.command_id == command_id)
            .order_by(
                NormalizedExecutionReportOrm.report_ts.asc(),
                NormalizedExecutionReportOrm.id.asc(),
            )
        ).all()
        return [normalized_execution_report_to_domain(report) for report in reports]

    def list_by_status(
        self,
        execution_status: ExecutionReportStatus | str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> list[NormalizedExecutionReport]:
        status_value = (
            execution_status.value
            if isinstance(execution_status, ExecutionReportStatus)
            else execution_status
        )
        statement = select(NormalizedExecutionReportOrm).where(
            NormalizedExecutionReportOrm.execution_status == status_value
        )
        if start_ts is not None:
            statement = statement.where(NormalizedExecutionReportOrm.report_ts >= start_ts)
        if end_ts is not None:
            statement = statement.where(NormalizedExecutionReportOrm.report_ts <= end_ts)
        reports = self._session.scalars(
            statement.order_by(
                NormalizedExecutionReportOrm.report_ts.asc(),
                NormalizedExecutionReportOrm.id.asc(),
            )
        ).all()
        return [normalized_execution_report_to_domain(report) for report in reports]

    def _existing_report_for_append(
        self,
        existing: NormalizedExecutionReport,
        report: NormalizedExecutionReport,
    ) -> NormalizedExecutionReport:
        if canonical_normalized_execution_report_payload(
            existing
        ) != canonical_normalized_execution_report_payload(report):
            raise ExecutionReportConflictError(
                "normalized execution report identity reused with different canonical payload: "
                f"{report.report_id}"
            )
        return existing


class SQLAlchemyOrderRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_order(self, order_request: OrderRequest, *, client_order_id: str) -> OrderState:
        existing = self._get_orm_by_client_order_id(client_order_id)
        if existing is not None:
            return self._existing_order_for_create(existing, order_request)

        try:
            with self._session.begin_nested():
                order = self._new_order(order_request, client_order_id=client_order_id)
                self._session.add(order)
                self._session.flush()
            return order_to_domain(order)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_client_order_id(client_order_id)
            if existing_after_conflict is None:
                raise RepositoryError(
                    f"client_order_id unique conflict but order not found: {client_order_id}"
                ) from exc
            return self._existing_order_for_create(existing_after_conflict, order_request)

    def _new_order(self, order_request: OrderRequest, *, client_order_id: str) -> Order:
        return Order(
            client_order_id=client_order_id,
            account_id=order_request.account_id,
            instrument_id=order_request.instrument_id,
            exchange=order_request.exchange,
            direction=order_request.direction.value,
            offset=order_request.offset.value,
            order_type=order_request.order_type.value,
            limit_price=order_request.limit_price,
            quantity=order_request.quantity,
            filled_quantity=order_request.quantity * 0,
            status=OrderStatus.CREATED.value,
            version=0,
        )

    def _existing_order_for_create(
        self, existing: Order, order_request: OrderRequest
    ) -> OrderState:
        if not _same_canonical_order_payload(existing, order_request):
            raise IdempotencyConflictError(
                f"client_order_id reused with different canonical payload: "
                f"{existing.client_order_id}"
            )
        return order_to_domain(existing)

    def _get_orm_by_client_order_id(self, client_order_id: str) -> Order | None:
        return self._session.scalar(
            select(Order).where(Order.client_order_id == client_order_id)
        )

    def get_by_id(self, order_id: str) -> OrderState | None:
        db_order_id = parse_order_id(order_id)
        order = self._session.get(Order, db_order_id)
        return order_to_domain(order) if order else None

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None:
        order = self._get_orm_by_client_order_id(client_order_id)
        return order_to_domain(order) if order else None

    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        *,
        expected_version: int | None = None,
    ) -> OrderState:
        db_order_id = parse_order_id(order_id)
        conditions = [Order.id == db_order_id]
        if expected_version is not None:
            conditions.append(Order.version == expected_version)

        result = cast(
            CursorResult[object],
            self._session.execute(
                update(Order)
                .where(*conditions)
                .values(status=new_status.value, version=Order.version + 1)
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            if expected_version is None:
                raise OrderNotFoundError(f"order not found: {order_id}")
            raise OptimisticLockError(
                f"order {order_id} version mismatch: expected {expected_version}"
            )
        self._session.flush()
        order = self._get_orm_by_id(db_order_id)
        if order is None:
            raise RepositoryError(f"order updated but not found: {order_id}")
        return order_to_domain(order)

    def _get_orm_by_id(self, db_order_id: int) -> Order | None:
        return self._session.scalar(
            select(Order)
            .where(Order.id == db_order_id)
            .execution_options(populate_existing=True)
        )

    def list_open_orders(self) -> list[OrderState]:
        orders = self._session.scalars(
            select(Order).where(Order.status.in_(_status_values(OPEN_RECOVERY_STATUSES)))
        ).all()
        return [order_to_domain(order) for order in orders]


class SQLAlchemyOrderEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_event(self, event: OrderEvent) -> OrderEvent:
        existing = self.get_by_event_key(event.event_source, event.external_event_id)
        if existing is not None:
            raise EventAlreadyExistsError(
                f"order event already exists: {event.event_source}/{event.external_event_id}"
            )
        try:
            with self._session.begin_nested():
                order_event = OrderEventOrm(
                    order_id=parse_order_id(event.order_id),
                    previous_status=event.previous_status.value if event.previous_status else None,
                    new_status=event.new_status.value,
                    event_source=event.event_source.value,
                    external_event_id=event.external_event_id,
                    raw_payload=event.raw_payload,
                    occurred_at=event.occurred_at,
                )
                self._session.add(order_event)
                self._session.flush()
            return order_event_to_domain(order_event)
        except IntegrityError as exc:
            existing_after_conflict = self.get_by_event_key(
                event.event_source,
                event.external_event_id,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "order event unique conflict but event not found: "
                    f"{event.event_source}/{event.external_event_id}"
                ) from exc
            raise EventAlreadyExistsError(
                f"order event already exists: {event.event_source}/{event.external_event_id}"
            ) from exc

    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None:
        event = self._session.scalar(
            select(OrderEventOrm).where(
                OrderEventOrm.event_source == event_source.value,
                OrderEventOrm.external_event_id == external_event_id,
            )
        )
        return order_event_to_domain(event) if event else None

    def list_by_order_id(self, order_id: str) -> list[OrderEvent]:
        db_order_id = parse_order_id(order_id)
        events = self._session.scalars(
            select(OrderEventOrm)
            .where(OrderEventOrm.order_id == db_order_id)
            .order_by(OrderEventOrm.id.asc())
        ).all()
        return [order_event_to_domain(event) for event in events]


class SQLAlchemyTradeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_or_get_trade(self, trade: Trade) -> Trade:
        existing = self._get_orm_by_exchange_trade_id(
            trade.account_id,
            trade.exchange,
            trade.exchange_trade_id,
        )
        if existing is not None:
            return self._existing_trade_for_create(existing, trade)

        try:
            with self._session.begin_nested():
                trade_orm = self._new_trade(trade)
                self._session.add(trade_orm)
                self._session.flush()
            return trade_to_domain(trade_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_exchange_trade_id(
                trade.account_id,
                trade.exchange,
                trade.exchange_trade_id,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "trade unique conflict but trade not found: "
                    f"{trade.account_id}/{trade.exchange}/{trade.exchange_trade_id}"
                ) from exc
            return self._existing_trade_for_create(existing_after_conflict, trade)

    def append_trade(self, trade: Trade) -> Trade:
        return self.create_or_get_trade(trade)

    def get_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        trade = self._get_orm_by_exchange_trade_id(account_id, exchange, exchange_trade_id)
        return trade_to_domain(trade) if trade else None

    def get_by_trade_identity(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        return self.get_by_exchange_trade_id(account_id, exchange, exchange_trade_id)

    def list_by_order_id(self, order_id: str) -> list[Trade]:
        db_order_id = parse_order_id(order_id)
        trades = self._session.scalars(
            select(TradeOrm)
            .where(TradeOrm.order_id == db_order_id)
            .order_by(TradeOrm.trade_time.asc(), TradeOrm.id.asc())
        )
        return [trade_to_domain(trade) for trade in trades]

    def _new_trade(self, trade: Trade) -> TradeOrm:
        return TradeOrm(
            account_id=trade.account_id,
            exchange=trade.exchange,
            exchange_trade_id=trade.exchange_trade_id,
            identity_source=trade.identity_source.value,
            order_id=parse_order_id(trade.order_id),
            client_order_id=trade.client_order_id,
            instrument_id=trade.instrument_id,
            trade_instrument_id=trade.trade_instrument_id,
            symbol=trade.symbol,
            direction=trade.direction.value,
            offset=trade.offset.value,
            price=trade.price,
            quantity=trade.quantity,
            fee_amount=trade.fee_amount,
            fee_currency=trade.fee_currency,
            fee_source=trade.fee_source,
            trade_time=trade.trade_time,
            trading_day=trade.trading_day,
            source_report_id=trade.source_report_id,
            source_exchange_report_id=trade.source_exchange_report_id,
            source_order_event_id=trade.source_order_event_id,
            raw_payload=trade.raw_payload,
        )

    def _get_orm_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> TradeOrm | None:
        return self._session.scalar(
            select(TradeOrm).where(
                TradeOrm.account_id == account_id,
                TradeOrm.exchange == exchange,
                TradeOrm.exchange_trade_id == exchange_trade_id,
            )
        )

    def _existing_trade_for_create(self, existing: TradeOrm, trade: Trade) -> Trade:
        if not _same_canonical_trade_payload(existing, trade):
            raise TradeIdempotencyConflictError(
                "exchange_trade_id reused with different canonical payload: "
                f"{trade.account_id}/{trade.exchange}/{trade.exchange_trade_id}"
            )
        return trade_to_domain(existing)


class SQLAlchemyPositionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_account_instrument(
        self,
        account_id: str,
        instrument_id: str,
    ) -> Position | None:
        position = self._get_orm_by_account_instrument(account_id, instrument_id)
        return position_to_domain(position) if position else None

    def create_or_get_position(self, account_id: str, instrument_id: str) -> Position:
        existing = self._get_orm_by_account_instrument(account_id, instrument_id)
        if existing is not None:
            return position_to_domain(existing)

        try:
            with self._session.begin_nested():
                position = PositionOrm(
                    account_id=account_id,
                    instrument_id=instrument_id,
                )
                self._session.add(position)
                self._session.flush()
            return position_to_domain(position)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_account_instrument(
                account_id,
                instrument_id,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "position unique conflict but position not found: "
                    f"{account_id}/{instrument_id}"
                ) from exc
            return position_to_domain(existing_after_conflict)

    def update_position(
        self,
        position: Position,
        *,
        expected_version: int | None = None,
    ) -> Position:
        if position.id is None:
            raise RepositoryError("position.id is required for update_position")
        db_position_id = parse_order_id(position.id)
        conditions = [PositionOrm.id == db_position_id]
        if expected_version is not None:
            conditions.append(PositionOrm.version == expected_version)

        result = cast(
            CursorResult[object],
            self._session.execute(
                update(PositionOrm)
                .where(*conditions)
                .values(
                    long_today_qty=position.long_today_qty,
                    long_yesterday_qty=position.long_yesterday_qty,
                    short_today_qty=position.short_today_qty,
                    short_yesterday_qty=position.short_yesterday_qty,
                    long_avg_price=position.long_avg_price,
                    short_avg_price=position.short_avg_price,
                    version=PositionOrm.version + 1,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            if expected_version is None:
                raise RepositoryError(f"position not found: {position.id}")
            raise OptimisticLockError(
                f"position {position.id} version mismatch: expected {expected_version}"
            )
        self._session.flush()
        updated = self._get_orm_by_id(db_position_id)
        if updated is None:
            raise RepositoryError(f"position updated but not found: {position.id}")
        return position_to_domain(updated)

    def update_margin_used(
        self,
        account_id: str,
        instrument_id: str,
        margin_used: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position:
        conditions = [
            PositionOrm.account_id == account_id,
            PositionOrm.instrument_id == instrument_id,
        ]
        if expected_version is not None:
            conditions.append(PositionOrm.version == expected_version)

        result = cast(
            CursorResult[object],
            self._session.execute(
                update(PositionOrm)
                .where(*conditions)
                .values(
                    margin_used=margin_used,
                    version=PositionOrm.version + 1,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            if expected_version is None:
                raise RepositoryError(f"position not found: {account_id}/{instrument_id}")
            raise OptimisticLockError(
                "position "
                f"{account_id}/{instrument_id} version mismatch: expected {expected_version}"
            )
        self._session.flush()
        updated = self._get_orm_by_account_instrument(account_id, instrument_id)
        if updated is None:
            raise RepositoryError(f"position updated but not found: {account_id}/{instrument_id}")
        return position_to_domain(updated)

    def update_pnl(
        self,
        account_id: str,
        instrument_id: str,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position:
        conditions = [
            PositionOrm.account_id == account_id,
            PositionOrm.instrument_id == instrument_id,
        ]
        if expected_version is not None:
            conditions.append(PositionOrm.version == expected_version)

        result = cast(
            CursorResult[object],
            self._session.execute(
                update(PositionOrm)
                .where(*conditions)
                .values(
                    realized_pnl=realized_pnl,
                    unrealized_pnl=unrealized_pnl,
                    version=PositionOrm.version + 1,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            if expected_version is None:
                raise RepositoryError(f"position not found: {account_id}/{instrument_id}")
            raise OptimisticLockError(
                "position "
                f"{account_id}/{instrument_id} version mismatch: expected {expected_version}"
            )
        self._session.flush()
        updated = self._get_orm_by_account_instrument(account_id, instrument_id)
        if updated is None:
            raise RepositoryError(f"position updated but not found: {account_id}/{instrument_id}")
        return position_to_domain(updated)

    def roll_today_to_yesterday_for_settlement(
        self,
        account_id: str,
        instrument_id: str,
        *,
        expected_version: int,
    ) -> Position:
        current = self._get_orm_by_account_instrument(account_id, instrument_id)
        if current is None:
            raise RepositoryError(f"position not found: {account_id}/{instrument_id}")
        conditions = [
            PositionOrm.account_id == account_id,
            PositionOrm.instrument_id == instrument_id,
            PositionOrm.version == expected_version,
        ]
        result = cast(
            CursorResult[object],
            self._session.execute(
                update(PositionOrm)
                .where(*conditions)
                .values(
                    long_yesterday_qty=current.long_yesterday_qty + current.long_today_qty,
                    short_yesterday_qty=current.short_yesterday_qty + current.short_today_qty,
                    long_today_qty=Decimal("0"),
                    short_today_qty=Decimal("0"),
                    version=PositionOrm.version + 1,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount != 1:
            raise OptimisticLockError(
                "position "
                f"{account_id}/{instrument_id} version mismatch: expected {expected_version}"
            )
        self._session.flush()
        updated = self._get_orm_by_account_instrument(account_id, instrument_id)
        if updated is None:
            raise RepositoryError(f"position updated but not found: {account_id}/{instrument_id}")
        return position_to_domain(updated)

    def list_by_account(self, account_id: str) -> list[Position]:
        positions = self._session.scalars(
            select(PositionOrm)
            .where(PositionOrm.account_id == account_id)
            .order_by(PositionOrm.instrument_id.asc())
        ).all()
        return [position_to_domain(position) for position in positions]

    def _get_orm_by_id(self, db_position_id: int) -> PositionOrm | None:
        return self._session.scalar(
            select(PositionOrm)
            .where(PositionOrm.id == db_position_id)
            .execution_options(populate_existing=True)
        )

    def _get_orm_by_account_instrument(
        self,
        account_id: str,
        instrument_id: str,
    ) -> PositionOrm | None:
        return self._session.scalar(
            select(PositionOrm).where(
                PositionOrm.account_id == account_id,
                PositionOrm.instrument_id == instrument_id,
            )
            .execution_options(populate_existing=True)
        )


class SQLAlchemyPositionEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_position_event(self, event: PositionEvent) -> PositionEvent:
        existing = self._get_orm_by_trade_key(
            event.account_id,
            event.exchange,
            event.exchange_trade_id,
        )
        if existing is not None:
            return self._existing_position_event_for_append(existing, event)

        try:
            with self._session.begin_nested():
                event_orm = PositionEventOrm(
                    account_id=event.account_id,
                    instrument_id=event.instrument_id,
                    exchange=event.exchange,
                    exchange_trade_id=event.exchange_trade_id,
                    trade_id=parse_order_id(event.trade_id),
                    position_id=parse_order_id(event.position_id),
                    event_type=event.event_type,
                    direction=event.direction.value,
                    offset=event.offset.value,
                    price=event.price,
                    quantity=event.quantity,
                    before_snapshot=_snapshot_to_json(event.before_snapshot),
                    after_snapshot=_snapshot_to_json(event.after_snapshot),
                    occurred_at=event.occurred_at,
                    created_at=event.created_at,
                    raw_payload=event.raw_payload,
                )
                self._session.add(event_orm)
                self._session.flush()
            return position_event_to_domain(event_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_trade_key(
                event.account_id,
                event.exchange,
                event.exchange_trade_id,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "position event unique conflict but event not found: "
                    f"{event.account_id}/{event.exchange}/{event.exchange_trade_id}"
                ) from exc
            return self._existing_position_event_for_append(existing_after_conflict, event)

    def get_by_trade_key(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> PositionEvent | None:
        event = self._get_orm_by_trade_key(account_id, exchange, exchange_trade_id)
        return position_event_to_domain(event) if event else None

    def list_by_position(self, account_id: str, instrument_id: str) -> list[PositionEvent]:
        events = self._session.scalars(
            select(PositionEventOrm)
            .where(
                PositionEventOrm.account_id == account_id,
                PositionEventOrm.instrument_id == instrument_id,
            )
            .order_by(PositionEventOrm.id.asc())
        ).all()
        return [position_event_to_domain(event) for event in events]

    def list_by_account(self, account_id: str) -> list[PositionEvent]:
        events = self._session.scalars(
            select(PositionEventOrm)
            .where(PositionEventOrm.account_id == account_id)
            .order_by(PositionEventOrm.id.asc())
        ).all()
        return [position_event_to_domain(event) for event in events]

    def _get_orm_by_trade_key(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> PositionEventOrm | None:
        return self._session.scalar(
            select(PositionEventOrm).where(
                PositionEventOrm.account_id == account_id,
                PositionEventOrm.exchange == exchange,
                PositionEventOrm.exchange_trade_id == exchange_trade_id,
            )
        )

    def _existing_position_event_for_append(
        self,
        existing: PositionEventOrm,
        event: PositionEvent,
    ) -> PositionEvent:
        if not _same_canonical_position_event_payload(existing, event):
            raise PositionEventConflictError(
                "exchange_trade_id reused with different position event payload: "
                f"{event.account_id}/{event.exchange}/{event.exchange_trade_id}"
            )
        return position_event_to_domain(existing)


class SQLAlchemyMarginSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_margin_snapshot(self, snapshot: MarginSnapshot) -> MarginSnapshot:
        existing = self._get_orm_by_calculation_key(
            snapshot.account_id,
            snapshot.instrument_id,
            snapshot.calculation_key,
        )
        if existing is not None:
            return self._existing_margin_snapshot_for_append(existing, snapshot)
        existing_by_accounting_identity = self._get_orm_by_accounting_identity(
            snapshot.account_id,
            snapshot.instrument_id,
            snapshot.position_version,
            snapshot.trading_day,
            snapshot.config_hash,
        )
        if existing_by_accounting_identity is not None:
            return self._existing_margin_snapshot_for_accounting_identity(
                existing_by_accounting_identity,
                snapshot,
            )

        try:
            with self._session.begin_nested():
                snapshot_orm = MarginSnapshotOrm(
                    account_id=snapshot.account_id,
                    instrument_id=snapshot.instrument_id,
                    position_version=snapshot.position_version,
                    trading_day=snapshot.trading_day,
                    config_hash=snapshot.config_hash,
                    rule_id=snapshot.rule_id,
                    rule_version=snapshot.rule_version,
                    calculation_key=snapshot.calculation_key,
                    long_qty=snapshot.long_qty,
                    short_qty=snapshot.short_qty,
                    price=snapshot.price,
                    contract_multiplier=snapshot.contract_multiplier,
                    initial_margin=snapshot.initial_margin,
                    maintenance_margin=snapshot.maintenance_margin,
                    margin_used=snapshot.margin_used,
                    available_cash=snapshot.available_cash,
                    equity=snapshot.equity,
                    calculated_at=snapshot.calculated_at,
                )
                self._session.add(snapshot_orm)
                self._session.flush()
            return margin_snapshot_to_domain(snapshot_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_calculation_key(
                snapshot.account_id,
                snapshot.instrument_id,
                snapshot.calculation_key,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "margin snapshot unique conflict but snapshot not found: "
                    f"{snapshot.account_id}/{snapshot.instrument_id}/"
                    f"{snapshot.calculation_key}"
                ) from exc
            return self._existing_margin_snapshot_for_append(
                existing_after_conflict,
                snapshot,
            )

    def get_latest(self, account_id: str, instrument_id: str) -> MarginSnapshot | None:
        snapshot = self._session.scalar(
            select(MarginSnapshotOrm)
            .where(
                MarginSnapshotOrm.account_id == account_id,
                MarginSnapshotOrm.instrument_id == instrument_id,
            )
            .order_by(
                MarginSnapshotOrm.calculated_at.desc(),
                MarginSnapshotOrm.created_at.desc(),
                MarginSnapshotOrm.id.desc(),
            )
        )
        return margin_snapshot_to_domain(snapshot) if snapshot else None

    def list_by_account(self, account_id: str) -> list[MarginSnapshot]:
        snapshots = self._session.scalars(
            select(MarginSnapshotOrm)
            .where(MarginSnapshotOrm.account_id == account_id)
            .order_by(
                MarginSnapshotOrm.calculated_at.asc(),
                MarginSnapshotOrm.id.asc(),
            )
        ).all()
        return [margin_snapshot_to_domain(snapshot) for snapshot in snapshots]

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> MarginSnapshot | None:
        snapshot = self._get_orm_by_position_version(account_id, instrument_id, position_version)
        return margin_snapshot_to_domain(snapshot) if snapshot else None

    def get_by_accounting_identity(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
        trading_day: date,
        config_hash: str,
    ) -> MarginSnapshot | None:
        snapshot = self._get_orm_by_accounting_identity(
            account_id,
            instrument_id,
            position_version,
            trading_day,
            config_hash,
        )
        return margin_snapshot_to_domain(snapshot) if snapshot else None

    def _get_orm_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> MarginSnapshotOrm | None:
        snapshots = self._session.scalars(
            select(MarginSnapshotOrm)
            .where(
                MarginSnapshotOrm.account_id == account_id,
                MarginSnapshotOrm.instrument_id == instrument_id,
                MarginSnapshotOrm.position_version == position_version,
            )
            .order_by(
                MarginSnapshotOrm.calculated_at.desc(),
                MarginSnapshotOrm.created_at.desc(),
                MarginSnapshotOrm.id.desc(),
            )
        ).all()
        if len(snapshots) != 1:
            return None
        return snapshots[0]

    def _get_orm_by_calculation_key(
        self,
        account_id: str,
        instrument_id: str,
        calculation_key: str,
    ) -> MarginSnapshotOrm | None:
        return self._session.scalar(
            select(MarginSnapshotOrm).where(
                MarginSnapshotOrm.account_id == account_id,
                MarginSnapshotOrm.instrument_id == instrument_id,
                MarginSnapshotOrm.calculation_key == calculation_key,
            )
        )

    def _get_orm_by_accounting_identity(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
        trading_day: date,
        config_hash: str,
    ) -> MarginSnapshotOrm | None:
        return self._session.scalar(
            select(MarginSnapshotOrm)
            .where(
                MarginSnapshotOrm.account_id == account_id,
                MarginSnapshotOrm.instrument_id == instrument_id,
                MarginSnapshotOrm.position_version == position_version,
                MarginSnapshotOrm.trading_day == trading_day,
                MarginSnapshotOrm.config_hash == config_hash,
            )
            .order_by(
                MarginSnapshotOrm.calculated_at.desc(),
                MarginSnapshotOrm.created_at.desc(),
                MarginSnapshotOrm.id.desc(),
            )
        )

    def _existing_margin_snapshot_for_append(
        self,
        existing: MarginSnapshotOrm,
        snapshot: MarginSnapshot,
    ) -> MarginSnapshot:
        if not _same_canonical_margin_snapshot_payload(existing, snapshot):
            raise MarginSnapshotConflictError(
                "calculation_key reused with different margin snapshot payload: "
                f"{snapshot.account_id}/{snapshot.instrument_id}/"
                f"{snapshot.calculation_key}"
            )
        return margin_snapshot_to_domain(existing)

    def _existing_margin_snapshot_for_accounting_identity(
        self,
        existing: MarginSnapshotOrm,
        snapshot: MarginSnapshot,
    ) -> MarginSnapshot:
        if not _same_margin_position_version_payload(existing, snapshot):
            raise MarginSnapshotConflictError(
                "accounting identity reused with different margin snapshot payload: "
                f"{snapshot.account_id}/{snapshot.instrument_id}/"
                f"{snapshot.position_version}/{snapshot.trading_day}/{snapshot.config_hash}"
            )
        return margin_snapshot_to_domain(existing)


class SQLAlchemyPnLSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_pnl_snapshot(self, snapshot: PnLSnapshot) -> PnLSnapshot:
        existing = self._get_orm_by_calculation_key(
            snapshot.account_id,
            snapshot.instrument_id,
            snapshot.calculation_key,
        )
        if existing is not None:
            return self._existing_pnl_snapshot_for_append(existing, snapshot)
        existing_by_accounting_identity = self._get_orm_by_accounting_identity(
            snapshot.account_id,
            snapshot.instrument_id,
            snapshot.position_version,
            snapshot.trading_day,
            snapshot.config_hash,
        )
        if existing_by_accounting_identity is not None:
            return self._existing_pnl_snapshot_for_accounting_identity(
                existing_by_accounting_identity,
                snapshot,
            )

        try:
            with self._session.begin_nested():
                snapshot_orm = PnLSnapshotOrm(
                    account_id=snapshot.account_id,
                    instrument_id=snapshot.instrument_id,
                    position_version=snapshot.position_version,
                    trading_day=snapshot.trading_day,
                    config_hash=snapshot.config_hash,
                    trade_id=snapshot.trade_id,
                    margin_snapshot_id=snapshot.margin_snapshot_id,
                    calculation_key=snapshot.calculation_key,
                    price_basis=snapshot.price_basis.value,
                    mark_price=snapshot.mark_price,
                    contract_multiplier=snapshot.contract_multiplier,
                    realized_pnl=snapshot.realized_pnl,
                    unrealized_pnl=snapshot.unrealized_pnl,
                    total_pnl=snapshot.total_pnl,
                    fee_amount=snapshot.fee_amount,
                    calculated_at=snapshot.calculated_at,
                )
                self._session.add(snapshot_orm)
                self._session.flush()
            return pnl_snapshot_to_domain(snapshot_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_calculation_key(
                snapshot.account_id,
                snapshot.instrument_id,
                snapshot.calculation_key,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "pnl snapshot unique conflict but snapshot not found: "
                    f"{snapshot.account_id}/{snapshot.instrument_id}/"
                    f"{snapshot.calculation_key}"
                ) from exc
            return self._existing_pnl_snapshot_for_append(
                existing_after_conflict,
                snapshot,
            )

    def get_latest(self, account_id: str, instrument_id: str) -> PnLSnapshot | None:
        snapshot = self._session.scalar(
            select(PnLSnapshotOrm)
            .where(
                PnLSnapshotOrm.account_id == account_id,
                PnLSnapshotOrm.instrument_id == instrument_id,
            )
            .order_by(
                PnLSnapshotOrm.calculated_at.desc(),
                PnLSnapshotOrm.created_at.desc(),
                PnLSnapshotOrm.id.desc(),
            )
        )
        return pnl_snapshot_to_domain(snapshot) if snapshot else None

    def list_by_account(self, account_id: str) -> list[PnLSnapshot]:
        snapshots = self._session.scalars(
            select(PnLSnapshotOrm)
            .where(PnLSnapshotOrm.account_id == account_id)
            .order_by(
                PnLSnapshotOrm.calculated_at.asc(),
                PnLSnapshotOrm.id.asc(),
            )
        ).all()
        return [pnl_snapshot_to_domain(snapshot) for snapshot in snapshots]

    def get_by_calculation_key(
        self,
        account_id: str,
        instrument_id: str,
        calculation_key: str,
    ) -> PnLSnapshot | None:
        snapshot = self._get_orm_by_calculation_key(account_id, instrument_id, calculation_key)
        return pnl_snapshot_to_domain(snapshot) if snapshot else None

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> PnLSnapshot | None:
        snapshot = self._get_orm_by_position_version(account_id, instrument_id, position_version)
        return pnl_snapshot_to_domain(snapshot) if snapshot else None

    def get_by_accounting_identity(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
        trading_day: date,
        config_hash: str,
    ) -> PnLSnapshot | None:
        snapshot = self._get_orm_by_accounting_identity(
            account_id,
            instrument_id,
            position_version,
            trading_day,
            config_hash,
        )
        return pnl_snapshot_to_domain(snapshot) if snapshot else None

    def _get_orm_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> PnLSnapshotOrm | None:
        snapshots = self._session.scalars(
            select(PnLSnapshotOrm)
            .where(
                PnLSnapshotOrm.account_id == account_id,
                PnLSnapshotOrm.instrument_id == instrument_id,
                PnLSnapshotOrm.position_version == position_version,
            )
            .order_by(
                PnLSnapshotOrm.calculated_at.desc(),
                PnLSnapshotOrm.created_at.desc(),
                PnLSnapshotOrm.id.desc(),
            )
        ).all()
        if len(snapshots) != 1:
            return None
        return snapshots[0]

    def _get_orm_by_calculation_key(
        self,
        account_id: str,
        instrument_id: str,
        calculation_key: str,
    ) -> PnLSnapshotOrm | None:
        return self._session.scalar(
            select(PnLSnapshotOrm).where(
                PnLSnapshotOrm.account_id == account_id,
                PnLSnapshotOrm.instrument_id == instrument_id,
                PnLSnapshotOrm.calculation_key == calculation_key,
            )
        )

    def _get_orm_by_accounting_identity(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
        trading_day: date,
        config_hash: str,
    ) -> PnLSnapshotOrm | None:
        return self._session.scalar(
            select(PnLSnapshotOrm)
            .where(
                PnLSnapshotOrm.account_id == account_id,
                PnLSnapshotOrm.instrument_id == instrument_id,
                PnLSnapshotOrm.position_version == position_version,
                PnLSnapshotOrm.trading_day == trading_day,
                PnLSnapshotOrm.config_hash == config_hash,
            )
            .order_by(
                PnLSnapshotOrm.calculated_at.desc(),
                PnLSnapshotOrm.created_at.desc(),
                PnLSnapshotOrm.id.desc(),
            )
        )

    def _existing_pnl_snapshot_for_append(
        self,
        existing: PnLSnapshotOrm,
        snapshot: PnLSnapshot,
    ) -> PnLSnapshot:
        if not _same_canonical_pnl_snapshot_payload(existing, snapshot):
            raise PnLSnapshotConflictError(
                "calculation_key reused with different pnl snapshot payload: "
                f"{snapshot.account_id}/{snapshot.instrument_id}/"
                f"{snapshot.calculation_key}"
            )
        return pnl_snapshot_to_domain(existing)

    def _existing_pnl_snapshot_for_accounting_identity(
        self,
        existing: PnLSnapshotOrm,
        snapshot: PnLSnapshot,
    ) -> PnLSnapshot:
        if not _same_pnl_position_version_payload(existing, snapshot):
            raise PnLSnapshotConflictError(
                "accounting identity reused with different pnl snapshot payload: "
                f"{snapshot.account_id}/{snapshot.instrument_id}/"
                f"{snapshot.position_version}/{snapshot.trading_day}/{snapshot.config_hash}"
            )
        return pnl_snapshot_to_domain(existing)


class SQLAlchemyAccountSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_account_snapshot(self, snapshot: AccountSnapshot) -> AccountSnapshot:
        snapshot_orm = AccountSnapshotOrm(
            account_id=snapshot.account_id,
            equity=snapshot.equity,
            available_cash=snapshot.available_cash,
            margin_used=snapshot.margin_used,
            frozen_margin=snapshot.frozen_margin,
            realized_pnl=snapshot.realized_pnl,
            unrealized_pnl=snapshot.unrealized_pnl,
            snapshot_time=snapshot.snapshot_time,
        )
        self._session.add(snapshot_orm)
        self._session.flush()
        return account_snapshot_to_domain(snapshot_orm)

    def get_by_id(self, snapshot_id: str) -> AccountSnapshot | None:
        snapshot = self._session.scalar(
            select(AccountSnapshotOrm).where(AccountSnapshotOrm.id == parse_order_id(snapshot_id))
        )
        return account_snapshot_to_domain(snapshot) if snapshot else None

    def get_latest(self, account_id: str) -> AccountSnapshot | None:
        snapshot = self._session.scalar(
            select(AccountSnapshotOrm)
            .where(AccountSnapshotOrm.account_id == account_id)
            .order_by(AccountSnapshotOrm.snapshot_time.desc(), AccountSnapshotOrm.id.desc())
        )
        return account_snapshot_to_domain(snapshot) if snapshot else None

    def list_by_account(self, account_id: str) -> list[AccountSnapshot]:
        snapshots = self._session.scalars(
            select(AccountSnapshotOrm)
            .where(AccountSnapshotOrm.account_id == account_id)
            .order_by(AccountSnapshotOrm.snapshot_time.asc(), AccountSnapshotOrm.id.asc())
        ).all()
        return [account_snapshot_to_domain(snapshot) for snapshot in snapshots]


class SQLAlchemySettlementSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_settlement_snapshot(self, snapshot: SettlementSnapshot) -> SettlementSnapshot:
        existing = self._get_orm_by_account_trading_day(
            snapshot.account_id,
            snapshot.trading_day,
        )
        if existing is not None:
            return self._existing_settlement_snapshot_for_append(existing, snapshot)

        try:
            with self._session.begin_nested():
                snapshot_orm = SettlementSnapshotOrm(
                    account_id=snapshot.account_id,
                    trading_day=snapshot.trading_day,
                    calculation_key=snapshot.calculation_key,
                    status=snapshot.status.value,
                    reason=snapshot.reason,
                    cash_before=snapshot.cash_before,
                    cash_after=snapshot.cash_after,
                    realized_pnl=snapshot.realized_pnl,
                    unrealized_pnl=snapshot.unrealized_pnl,
                    margin_used=snapshot.margin_used,
                    positions_before=list(snapshot.positions_before),
                    positions_after=list(snapshot.positions_after),
                    settlement_prices=list(snapshot.settlement_prices),
                    pnl_snapshot_ids=list(snapshot.pnl_snapshot_ids),
                    margin_snapshot_ids=list(snapshot.margin_snapshot_ids),
                    account_snapshot_before_id=parse_order_id(snapshot.account_snapshot_before_id)
                    if snapshot.account_snapshot_before_id
                    else None,
                    account_snapshot_after_id=parse_order_id(snapshot.account_snapshot_after_id)
                    if snapshot.account_snapshot_after_id
                    else None,
                    raw_payload={},
                    created_at=snapshot.created_at,
                )
                self._session.add(snapshot_orm)
                self._session.flush()
            return settlement_snapshot_to_domain(snapshot_orm)
        except IntegrityError as exc:
            existing_after_conflict = self._get_orm_by_account_trading_day(
                snapshot.account_id,
                snapshot.trading_day,
            )
            if existing_after_conflict is None:
                raise RepositoryError(
                    "settlement snapshot unique conflict but snapshot not found: "
                    f"{snapshot.account_id}/{snapshot.trading_day}"
                ) from exc
            return self._existing_settlement_snapshot_for_append(
                existing_after_conflict,
                snapshot,
            )

    def get_by_account_trading_day(
        self,
        account_id: str,
        trading_day: date,
    ) -> SettlementSnapshot | None:
        snapshot = self._get_orm_by_account_trading_day(account_id, trading_day)
        return settlement_snapshot_to_domain(snapshot) if snapshot else None

    def get_by_calculation_key(
        self,
        account_id: str,
        trading_day: date,
        calculation_key: str,
    ) -> SettlementSnapshot | None:
        snapshot = self._session.scalar(
            select(SettlementSnapshotOrm).where(
                SettlementSnapshotOrm.account_id == account_id,
                SettlementSnapshotOrm.trading_day == trading_day,
                SettlementSnapshotOrm.calculation_key == calculation_key,
            )
        )
        return settlement_snapshot_to_domain(snapshot) if snapshot else None

    def list_by_account(self, account_id: str) -> list[SettlementSnapshot]:
        snapshots = self._session.scalars(
            select(SettlementSnapshotOrm)
            .where(SettlementSnapshotOrm.account_id == account_id)
            .order_by(SettlementSnapshotOrm.trading_day.asc(), SettlementSnapshotOrm.id.asc())
        ).all()
        return [settlement_snapshot_to_domain(snapshot) for snapshot in snapshots]

    def list_by_trading_day(self, trading_day: date) -> list[SettlementSnapshot]:
        snapshots = self._session.scalars(
            select(SettlementSnapshotOrm)
            .where(SettlementSnapshotOrm.trading_day == trading_day)
            .order_by(SettlementSnapshotOrm.account_id.asc(), SettlementSnapshotOrm.id.asc())
        ).all()
        return [settlement_snapshot_to_domain(snapshot) for snapshot in snapshots]

    def _get_orm_by_account_trading_day(
        self,
        account_id: str,
        trading_day: date,
    ) -> SettlementSnapshotOrm | None:
        return self._session.scalar(
            select(SettlementSnapshotOrm).where(
                SettlementSnapshotOrm.account_id == account_id,
                SettlementSnapshotOrm.trading_day == trading_day,
            )
        )

    def _existing_settlement_snapshot_for_append(
        self,
        existing: SettlementSnapshotOrm,
        snapshot: SettlementSnapshot,
    ) -> SettlementSnapshot:
        if not _same_canonical_settlement_snapshot_payload(existing, snapshot):
            raise SettlementSnapshotConflictError(
                "account/trading_day reused with different settlement snapshot payload: "
                f"{snapshot.account_id}/{snapshot.trading_day}"
            )
        return settlement_snapshot_to_domain(existing)
