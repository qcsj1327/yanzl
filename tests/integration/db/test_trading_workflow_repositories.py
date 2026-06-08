from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from futures_mvp.db.models import Base, OrderIntent, TradingRiskResult
from futures_mvp.db.repositories import (
    SQLAlchemyOrderIntentRepository,
    SQLAlchemyTradingRiskResultRepository,
)
from futures_mvp.db.unit_of_work import SQLAlchemyUnitOfWork
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
from futures_mvp.domain.models import OrderIntent as DomainOrderIntent
from futures_mvp.domain.models import SignalDecision, StrategyConfig, TradingWorkflowContext
from futures_mvp.domain.models import TradingRiskResult as DomainTradingRiskResult
from futures_mvp.interfaces.repositories import (
    OrderIntentConflictError,
    TradingRiskResultConflictError,
)
from futures_mvp.modules.strategy import build_signal_id
from futures_mvp.modules.trading_workflow import (
    TradingWorkflowService,
    build_order_intent,
    build_order_intent_id,
    build_trading_risk_result_id,
    canonical_order_intent_payload,
    canonical_trading_risk_result_payload,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _risk_result(**updates: object) -> DomainTradingRiskResult:
    values = {
        "signal_id": "signal-1",
        "risk_result_id": "pending",
        "evaluation_context_hash": "eval-context-hash",
        "risk_status": RiskResultStatus.ACCEPT,
        "risk_reason": "accepted",
        "risk_level": "INFO",
        "requested_quantity": Decimal("2"),
        "approved_quantity": Decimal("2"),
        "max_quantity": Decimal("3"),
        "expected_margin": Decimal("1000"),
        "expected_notional": Decimal("1500"),
        "config_hash": "risk-config-hash",
        "evaluation_ts": datetime(2026, 6, 7, 9, tzinfo=UTC),
        "raw_payload": {"diagnostic": "a"},
    }
    values.update(updates)
    result = DomainTradingRiskResult(**values)
    if result.risk_result_id == "pending":
        result = result.model_copy(update={"risk_result_id": build_trading_risk_result_id(result)})
    return result


def _intent(**updates: object) -> DomainOrderIntent:
    risk_result = _risk_result()
    values = {
        "intent_id": "pending",
        "signal_id": risk_result.signal_id,
        "risk_result_id": risk_result.risk_result_id,
        "strategy_name": "toy",
        "strategy_version": "strategy-v1",
        "strategy_config_hash": "strategy-config-hash",
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
        "side": SignalSide.BUY,
        "offset": Offset.OPEN,
        "quantity": Decimal("2"),
        "price": Decimal("500"),
        "order_type": OrderType.LIMIT,
        "tif": "GFD",
        "expected_margin": Decimal("1000"),
        "expected_notional": Decimal("1500"),
        "intent_reason": "accepted",
        "raw_payload": {"diagnostic": "a"},
    }
    values.update(updates)
    intent = DomainOrderIntent(**values)
    if intent.intent_id == "pending":
        intent = intent.model_copy(update={"intent_id": build_order_intent_id(intent)})
    return intent


def test_risk_results_and_order_intents_schema() -> None:
    assert "risk_results" in Base.metadata.tables
    assert "order_intents" in Base.metadata.tables
    assert "risk_result_id" in TradingRiskResult.__table__.columns
    assert "evaluation_context_hash" in TradingRiskResult.__table__.columns
    assert "requested_quantity" in TradingRiskResult.__table__.columns
    assert "intent_id" in OrderIntent.__table__.columns
    assert "ix_order_intents_trading_day" in {index.name for index in OrderIntent.__table__.indexes}
    assert "orders" not in {
        foreign_key.column.table.name
        for foreign_key in OrderIntent.__table__.foreign_keys
    }


def test_sqlite_schema_round_trip_has_stage_j_tables(session: Session) -> None:
    inspector = inspect(session.bind)

    assert "risk_results" in inspector.get_table_names()
    assert "order_intents" in inspector.get_table_names()


def test_trading_risk_result_repository_round_trip_and_idempotency(session: Session) -> None:
    repository = SQLAlchemyTradingRiskResultRepository(session)
    result = _risk_result()

    first = repository.append_risk_result(result)
    second = repository.append_risk_result(
        result.model_copy(update={"raw_payload": {"diagnostic": "changed"}})
    )

    assert canonical_trading_risk_result_payload(first) == canonical_trading_risk_result_payload(
        second
    )
    assert repository.get_by_risk_result_id(result.risk_result_id) is not None
    assert [item.risk_result_id for item in repository.list_by_signal_id("signal-1")] == [
        first.risk_result_id
    ]

    with pytest.raises(TradingRiskResultConflictError):
        repository.append_risk_result(result.model_copy(update={"risk_level": "WARN"}))

    different_context = _risk_result(evaluation_context_hash="other-eval-context")
    assert different_context.risk_result_id != result.risk_result_id
    assert repository.append_risk_result(different_context).risk_result_id == (
        different_context.risk_result_id
    )
    forced_context_conflict = different_context.model_copy(
        update={"risk_result_id": result.risk_result_id}
    )
    with pytest.raises(TradingRiskResultConflictError):
        repository.append_risk_result(forced_context_conflict)


def test_order_intent_repository_round_trip_and_idempotency(session: Session) -> None:
    repository = SQLAlchemyOrderIntentRepository(session)
    intent = _intent()

    first = repository.append_order_intent(intent)
    second = repository.append_order_intent(
        intent.model_copy(update={"raw_payload": {"diagnostic": "changed"}})
    )

    assert canonical_order_intent_payload(first) == canonical_order_intent_payload(second)
    assert repository.get_by_intent_id(intent.intent_id) is not None
    assert [item.intent_id for item in repository.list_by_signal_id("signal-1")] == [
        first.intent_id
    ]

    with pytest.raises(OrderIntentConflictError):
        repository.append_order_intent(intent.model_copy(update={"quantity": Decimal("1")}))


def _strategy_config() -> StrategyConfig:
    return StrategyConfig.build(
        strategy_name="toy",
        strategy_version="strategy-v1",
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        timeframe=BarTimeframe.M1,
        params={"offset": Offset.OPEN.value, "order_type": OrderType.LIMIT.value, "tif": "GFD"},
    )


def _decision() -> SignalDecision:
    config = _strategy_config()
    signal_id = build_signal_id(
        strategy_name=config.strategy_name,
        strategy_version=config.strategy_version,
        strategy_config_hash=config.strategy_config_hash,
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=BarTimeframe.M1,
        bar_ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        decision=SignalDecisionType.BUY,
        side=SignalSide.BUY,
        position_side=SignalPositionSide.LONG,
        expected_price=Decimal("500"),
    )
    return SignalDecision(
        decision=SignalDecisionType.BUY,
        side=SignalSide.BUY,
        strength=Decimal("2"),
        confidence=Decimal("0.9"),
        signal_id=signal_id,
        strategy_name=config.strategy_name,
        strategy_version=config.strategy_version,
        strategy_config_hash=config.strategy_config_hash,
        runtime_id="runtime-1",
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=BarTimeframe.M1,
        bar_ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        position_side=SignalPositionSide.LONG,
        expected_price=Decimal("500"),
    )


def _workflow_context(decision: SignalDecision) -> TradingWorkflowContext:
    return TradingWorkflowContext(
        signal_decision=decision,
        strategy_config=_strategy_config(),
        requested_quantity=Decimal("2"),
        risk_config_hash="risk-config-hash",
        evaluation_context_hash="eval-context-hash",
    )


class FixedRiskEvaluator:
    def __init__(self, result: DomainTradingRiskResult) -> None:
        self.result = result

    def evaluate(self, context: TradingWorkflowContext) -> DomainTradingRiskResult:
        del context
        return self.result


def test_workflow_intent_conflict_rolls_back_risk_result(session: Session) -> None:
    decision = _decision()
    context = _workflow_context(decision)
    risk_result = _risk_result(
        signal_id=decision.signal_id,
        requested_quantity=Decimal("2"),
        approved_quantity=Decimal("2"),
    )
    expected_intent = build_order_intent(decision, risk_result, context)
    conflicting_intent = expected_intent.model_copy(update={"quantity": Decimal("1")})
    SQLAlchemyOrderIntentRepository(session).append_order_intent(conflicting_intent)
    session.commit()

    result = TradingWorkflowService(
        lambda: SQLAlchemyUnitOfWork(session=session),
        FixedRiskEvaluator(risk_result),
    ).run(context)

    assert result.status is TradingWorkflowResultStatus.CONFLICT
    assert session.scalar(
        select(func.count()).select_from(TradingRiskResult).where(
            TradingRiskResult.risk_result_id == risk_result.risk_result_id
        )
    ) == 0
