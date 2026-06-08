from datetime import UTC, date, datetime
from decimal import Decimal
from types import TracebackType

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
from futures_mvp.domain.models import (
    OrderIntent,
    SignalDecision,
    StrategyConfig,
    TradingRiskResult,
    TradingWorkflowContext,
)
from futures_mvp.interfaces.repositories import (
    OrderIntentConflictError,
    TradingRiskResultConflictError,
)
from futures_mvp.modules.strategy import build_signal_id
from futures_mvp.modules.trading_workflow import (
    TradingWorkflowReplay,
    TradingWorkflowService,
    build_trading_risk_result_id,
    canonical_order_intent_payload,
    canonical_trading_risk_result_payload,
)


def _config() -> StrategyConfig:
    return StrategyConfig.build(
        strategy_name="toy",
        strategy_version="strategy-v1",
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        timeframe=BarTimeframe.M1,
        params={"offset": Offset.OPEN.value, "order_type": OrderType.LIMIT.value, "tif": "GFD"},
    )


def _decision(bar_ts: datetime | None = None) -> SignalDecision:
    config = _config()
    ts = bar_ts or datetime(2026, 6, 7, 9, tzinfo=UTC)
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
        bar_ts=ts,
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
        strength=Decimal("3"),
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
        bar_ts=ts,
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        position_side=SignalPositionSide.LONG,
        expected_price=Decimal("500"),
    )


def _context(decision: SignalDecision | None = None) -> TradingWorkflowContext:
    return TradingWorkflowContext(
        signal_decision=decision or _decision(),
        strategy_config=_config(),
        requested_quantity=Decimal("3"),
        risk_config_hash="risk-config-hash",
        evaluation_context_hash="eval-context-hash",
    )


def _risk_result(
    signal_id: str,
    *,
    status: RiskResultStatus = RiskResultStatus.ACCEPT,
    requested_quantity: Decimal = Decimal("3"),
    approved_quantity: Decimal = Decimal("3"),
    reason: str | None = "accepted",
    config_hash: str = "risk-config-hash",
    evaluation_context_hash: str = "eval-context-hash",
) -> TradingRiskResult:
    result = TradingRiskResult(
        signal_id=signal_id,
        risk_result_id="pending",
        evaluation_context_hash=evaluation_context_hash,
        risk_status=status,
        risk_reason=reason,
        risk_level="INFO",
        requested_quantity=requested_quantity,
        approved_quantity=approved_quantity,
        max_quantity=Decimal("3"),
        expected_margin=Decimal("1000"),
        expected_notional=Decimal("1500"),
        config_hash=config_hash,
        evaluation_ts=datetime(2026, 6, 7, 9, 1, tzinfo=UTC),
    )
    return result.model_copy(update={"risk_result_id": build_trading_risk_result_id(result)})


def _unsafe_risk_result(
    signal_id: str,
    *,
    status: RiskResultStatus,
    approved_quantity: Decimal,
    config_hash: str = "risk-config-hash",
    evaluation_context_hash: str = "eval-context-hash",
) -> TradingRiskResult:
    payload = {
        "signal_id": signal_id,
        "risk_result_id": "pending",
        "evaluation_context_hash": evaluation_context_hash,
        "risk_status": status,
        "risk_reason": "unsafe",
        "risk_level": "INFO",
        "requested_quantity": Decimal("3"),
        "approved_quantity": approved_quantity,
        "max_quantity": Decimal("3"),
        "expected_margin": Decimal("1000"),
        "expected_notional": Decimal("1500"),
        "config_hash": config_hash,
        "evaluation_ts": datetime(2026, 6, 7, 9, 1, tzinfo=UTC),
        "raw_payload": None,
    }
    result = TradingRiskResult.model_construct(**payload)
    return result.model_copy(update={"risk_result_id": build_trading_risk_result_id(result)})


class FakeRiskEvaluator:
    def __init__(
        self,
        status: RiskResultStatus = RiskResultStatus.ACCEPT,
        approved_quantity: Decimal = Decimal("3"),
        *,
        config_hash: str = "risk-config-hash",
        unsafe: bool = False,
    ) -> None:
        self.status = status
        self.approved_quantity = approved_quantity
        self.config_hash = config_hash
        self.unsafe = unsafe
        self.calls: list[TradingWorkflowContext] = []

    def evaluate(self, context: TradingWorkflowContext) -> TradingRiskResult:
        self.calls.append(context)
        if self.unsafe:
            return _unsafe_risk_result(
                context.signal_decision.signal_id,
                status=self.status,
                approved_quantity=self.approved_quantity,
                config_hash=self.config_hash,
            )
        return _risk_result(
            context.signal_decision.signal_id,
            status=self.status,
            approved_quantity=self.approved_quantity,
            config_hash=self.config_hash,
        )


class FakeRiskResultRepository:
    def __init__(self) -> None:
        self.results: dict[str, TradingRiskResult] = {}
        self.force_conflict = False

    def append_risk_result(self, result: TradingRiskResult) -> TradingRiskResult:
        if self.force_conflict:
            raise TradingRiskResultConflictError("conflict")
        existing = self.results.get(result.risk_result_id)
        if existing is not None:
            if canonical_trading_risk_result_payload(
                existing
            ) != canonical_trading_risk_result_payload(result):
                raise TradingRiskResultConflictError("conflict")
            return existing
        self.results[result.risk_result_id] = result
        return result

    def get_by_risk_result_id(self, risk_result_id: str) -> TradingRiskResult | None:
        return self.results.get(risk_result_id)

    def list_by_signal_id(self, signal_id: str) -> list[TradingRiskResult]:
        return [result for result in self.results.values() if result.signal_id == signal_id]


class FakeOrderIntentRepository:
    def __init__(self) -> None:
        self.intents: dict[str, OrderIntent] = {}
        self.force_conflict = False

    def append_order_intent(self, intent: OrderIntent) -> OrderIntent:
        if self.force_conflict:
            raise OrderIntentConflictError("conflict")
        existing = self.intents.get(intent.intent_id)
        if existing is not None:
            if canonical_order_intent_payload(existing) != canonical_order_intent_payload(intent):
                raise OrderIntentConflictError("conflict")
            return existing
        self.intents[intent.intent_id] = intent
        return intent

    def get_by_intent_id(self, intent_id: str) -> OrderIntent | None:
        return self.intents.get(intent_id)

    def list_by_signal_id(self, signal_id: str) -> list[OrderIntent]:
        return [intent for intent in self.intents.values() if intent.signal_id == signal_id]


class FakeUow:
    def __init__(self) -> None:
        self.trading_risk_results = FakeRiskResultRepository()
        self.order_intents = FakeOrderIntentRepository()
        self.committed = 0
        self.rolled_back = 0
        self._risk_snapshot: dict[str, TradingRiskResult] = {}
        self._intent_snapshot: dict[str, OrderIntent] = {}

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1
        self.trading_risk_results.results = dict(self._risk_snapshot)
        self.order_intents.intents = dict(self._intent_snapshot)

    def __enter__(self) -> "FakeUow":
        self._risk_snapshot = dict(self.trading_risk_results.results)
        self._intent_snapshot = dict(self.order_intents.intents)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        del exc_type, exc, tb
        return None


def test_accept_builds_and_persists_order_intent() -> None:
    uow = FakeUow()
    evaluator = FakeRiskEvaluator()
    service = TradingWorkflowService(lambda: uow, evaluator)

    result = service.run(_context())

    assert result.status is TradingWorkflowResultStatus.INTENT_CREATED
    assert result.order_intent is not None
    assert result.order_intent.quantity == Decimal("3")
    assert evaluator.calls
    assert uow.committed == 1


def test_reduce_builds_reduced_intent_and_zero_reduce_rejects() -> None:
    reduced_service = TradingWorkflowService(
        lambda: FakeUow(),
        FakeRiskEvaluator(RiskResultStatus.REDUCE, Decimal("1")),
    )
    reduced = reduced_service.run(_context())

    assert reduced.status is TradingWorkflowResultStatus.INTENT_CREATED
    assert reduced.order_intent is not None
    assert reduced.order_intent.quantity == Decimal("1")

    rejected_service = TradingWorkflowService(
        lambda: FakeUow(),
        FakeRiskEvaluator(RiskResultStatus.REDUCE, Decimal("0"), unsafe=True),
    )
    rejected = rejected_service.run(_context())
    assert rejected.status is TradingWorkflowResultStatus.RISK_REJECTED
    assert rejected.order_intent is None


def test_accept_quantity_must_equal_requested_quantity() -> None:
    uow = FakeUow()
    service = TradingWorkflowService(
        lambda: uow,
        FakeRiskEvaluator(RiskResultStatus.ACCEPT, Decimal("1"), unsafe=True),
    )

    result = service.run(_context())

    assert result.status is TradingWorkflowResultStatus.ERROR
    assert result.reason == "ACCEPT requires approved_quantity equal requested quantity"
    assert not uow.trading_risk_results.results
    assert not uow.order_intents.intents


def test_reduce_equal_requested_normalizes_to_accept() -> None:
    result = TradingWorkflowService(
        lambda: FakeUow(),
        FakeRiskEvaluator(RiskResultStatus.REDUCE, Decimal("3"), unsafe=True),
    ).run(_context())

    assert result.status is TradingWorkflowResultStatus.INTENT_CREATED
    assert result.risk_result is not None
    assert result.risk_result.risk_status is RiskResultStatus.ACCEPT
    assert result.order_intent is not None
    assert result.order_intent.quantity == Decimal("3")


def test_approved_quantity_above_requested_errors_without_persistence() -> None:
    uow = FakeUow()
    result = TradingWorkflowService(
        lambda: uow,
        FakeRiskEvaluator(RiskResultStatus.REDUCE, Decimal("4"), unsafe=True),
    ).run(_context())

    assert result.status is TradingWorkflowResultStatus.ERROR
    assert result.reason == "approved_quantity cannot exceed requested quantity"
    assert not uow.trading_risk_results.results
    assert not uow.order_intents.intents


def test_risk_config_hash_mismatch_errors_without_persistence() -> None:
    uow = FakeUow()
    result = TradingWorkflowService(
        lambda: uow,
        FakeRiskEvaluator(config_hash="stale-risk-config"),
    ).run(_context())

    assert result.status is TradingWorkflowResultStatus.ERROR
    assert result.reason == "risk config hash mismatch"
    assert not uow.trading_risk_results.results
    assert not uow.order_intents.intents


def test_reject_block_unknown_do_not_create_intent() -> None:
    expected = {
        RiskResultStatus.REJECT: TradingWorkflowResultStatus.RISK_REJECTED,
        RiskResultStatus.BLOCK: TradingWorkflowResultStatus.RISK_BLOCKED,
        RiskResultStatus.UNKNOWN: TradingWorkflowResultStatus.RISK_UNKNOWN,
    }
    for risk_status, workflow_status in expected.items():
        uow = FakeUow()

        def uow_factory(current_uow: FakeUow = uow) -> FakeUow:
            return current_uow

        result = TradingWorkflowService(
            uow_factory,
            FakeRiskEvaluator(risk_status, Decimal("0")),
        ).run(_context())

        assert result.status is workflow_status
        assert result.order_intent is None
        assert not uow.order_intents.intents


def test_duplicate_same_canonical_and_conflict() -> None:
    uow = FakeUow()
    service = TradingWorkflowService(lambda: uow, FakeRiskEvaluator())

    first = service.run(_context())
    duplicate = service.run(_context())

    assert first.status is TradingWorkflowResultStatus.INTENT_CREATED
    assert duplicate.status is TradingWorkflowResultStatus.DUPLICATE

    uow.order_intents.force_conflict = True
    conflict_decision = _decision(datetime(2026, 6, 7, 9, 1, tzinfo=UTC))
    conflict = service.run(_context(conflict_decision))
    assert conflict.status is TradingWorkflowResultStatus.CONFLICT
    assert uow.rolled_back == 1
    assert uow.trading_risk_results.list_by_signal_id(conflict_decision.signal_id) == []


def test_replay_is_deterministic_and_uses_service_path() -> None:
    uow = FakeUow()
    evaluator = FakeRiskEvaluator()
    service = TradingWorkflowService(lambda: uow, evaluator)
    replay = TradingWorkflowReplay(service)
    contexts = [
        _context(_decision(datetime(2026, 6, 7, 9, 1, tzinfo=UTC))),
        _context(_decision(datetime(2026, 6, 7, 9, tzinfo=UTC))),
    ]

    first = replay.replay(contexts)
    second = replay.replay(contexts)

    assert [result.status for result in first] == [
        TradingWorkflowResultStatus.INTENT_CREATED,
        TradingWorkflowResultStatus.INTENT_CREATED,
    ]
    assert [result.status for result in second] == [
        TradingWorkflowResultStatus.DUPLICATE,
        TradingWorkflowResultStatus.DUPLICATE,
    ]
    assert len(evaluator.calls) == 4
