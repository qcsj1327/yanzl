from datetime import UTC, date, datetime
from decimal import Decimal

from futures_mvp.domain.enums import (
    BarTimeframe,
    Direction,
    Offset,
    OMSBridgeResultStatus,
    OrderStatus,
    OrderType,
    RiskResultStatus,
    SignalSide,
)
from futures_mvp.domain.models import (
    OMSBridgeContext,
    OrderIntent,
    OrderRequest,
    OrderState,
    TradingRiskResult,
)
from futures_mvp.modules.oms_bridge import (
    OMSBridgeService,
    build_client_order_id,
    replay_oms_bridge,
)


def _clock() -> datetime:
    return datetime(2026, 6, 8, 9, tzinfo=UTC)


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
        "evaluation_ts": _clock(),
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
        "bar_ts": _clock(),
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


def _context(
    *,
    intent: OrderIntent | None = None,
    risk_result: TradingRiskResult | None = None,
) -> OMSBridgeContext:
    return OMSBridgeContext(
        order_intent=intent or _intent(),
        trading_risk_result=risk_result or _risk_result(),
        account_id="account-1",
    )


class FakeOMS:
    def __init__(self) -> None:
        self.orders: dict[str, OrderState] = {}
        self.calls: list[tuple[OrderRequest, str]] = []
        self.fail_next = False

    def create_order(
        self,
        request: OrderRequest,
        *,
        client_order_id: str,
        bridge_payload_hash: str | None = None,
        intent_id: str | None = None,
        risk_result_id: str | None = None,
        signal_id: str | None = None,
    ) -> OrderState:
        self.calls.append((request, client_order_id))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("oms unavailable")
        existing = self.orders.get(client_order_id)
        if existing is not None:
            return existing
        order = OrderState(
            order_id=str(len(self.orders) + 1),
            request=request,
            status=OrderStatus.CREATED,
            bridge_payload_hash=bridge_payload_hash,
            intent_id=intent_id,
            risk_result_id=risk_result_id,
            signal_id=signal_id,
        )
        self.orders[client_order_id] = order
        return order

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None:
        return self.orders.get(client_order_id)


def test_valid_intent_builds_order_request_and_calls_oms_once() -> None:
    fake = FakeOMS()
    service = OMSBridgeService(fake, clock=_clock)
    context = _context()

    result = service.create_order(context)

    assert result.status is OMSBridgeResultStatus.CREATED
    assert result.order_id == "1"
    assert len(fake.calls) == 1
    request, client_order_id = fake.calls[0]
    assert client_order_id == build_client_order_id(context.order_intent.intent_id)
    assert request.client_order_id == client_order_id
    assert request.account_id == "account-1"
    assert request.instrument_id == context.order_intent.instrument_id
    assert request.exchange == context.order_intent.exchange
    assert request.direction is Direction.BUY
    assert request.offset is context.order_intent.offset
    assert request.order_type is context.order_intent.order_type
    assert request.limit_price == context.order_intent.price
    assert request.quantity == context.order_intent.quantity


def test_missing_risk_result_id_rejects_without_oms_call() -> None:
    fake = FakeOMS()
    intent = OrderIntent.model_construct(**(_intent().model_dump() | {"risk_result_id": ""}))
    context = OMSBridgeContext.model_construct(
        order_intent=intent,
        trading_risk_result=_risk_result(),
        account_id="account-1",
        order_source="oms_bridge",
        bridge_config=None,
    )

    result = OMSBridgeService(fake, clock=_clock).create_order(context)

    assert result.status is OMSBridgeResultStatus.REJECTED_INVALID_INTENT
    assert fake.calls == []


def test_risk_not_accepted_rejects_without_oms_call() -> None:
    fake = FakeOMS()
    risk_result = _risk_result(
        risk_status=RiskResultStatus.REJECT,
        approved_quantity=Decimal("0"),
        expected_margin=Decimal("0"),
        expected_notional=Decimal("0"),
    )
    context = _context(risk_result=risk_result)

    result = OMSBridgeService(fake, clock=_clock).create_order(context)

    assert result.status is OMSBridgeResultStatus.REJECTED_RISK_NOT_ACCEPTED
    assert fake.calls == []


def test_quantity_non_positive_rejects_without_oms_call() -> None:
    fake = FakeOMS()
    intent = OrderIntent.model_construct(**(_intent().model_dump() | {"quantity": Decimal("0")}))
    risk_result = TradingRiskResult.model_construct(
        **(_risk_result().model_dump() | {"approved_quantity": Decimal("0")})
    )
    context = OMSBridgeContext.model_construct(
        order_intent=intent,
        trading_risk_result=risk_result,
        account_id="account-1",
        order_source="oms_bridge",
        bridge_config=None,
    )

    result = OMSBridgeService(fake, clock=_clock).create_order(context)

    assert result.status is OMSBridgeResultStatus.REJECTED_INVALID_INTENT
    assert fake.calls == []


def test_quantity_mismatch_rejects_without_oms_call() -> None:
    fake = FakeOMS()
    intent = _intent(quantity=Decimal("1"))
    context = _context(intent=intent)

    result = OMSBridgeService(fake, clock=_clock).create_order(context)

    assert result.status is OMSBridgeResultStatus.REJECTED_INVALID_INTENT
    assert result.reason == "order intent quantity must equal approved_quantity"
    assert fake.calls == []


def test_duplicate_same_canonical_returns_duplicate_without_create_call() -> None:
    fake = FakeOMS()
    service = OMSBridgeService(fake, clock=_clock)
    context = _context()
    first = service.create_order(context)
    fake.calls.clear()

    duplicate = service.create_order(context)

    assert first.status is OMSBridgeResultStatus.CREATED
    assert duplicate.status is OMSBridgeResultStatus.DUPLICATE
    assert duplicate.order_id == first.order_id
    assert fake.calls == []


def test_duplicate_different_order_payload_conflicts_without_create_call() -> None:
    fake = FakeOMS()
    service = OMSBridgeService(fake, clock=_clock)
    context = _context()
    service.create_order(context)
    fake.calls.clear()
    changed_intent = OrderIntent.model_construct(
        **(context.order_intent.model_dump() | {"quantity": Decimal("1")})
    )
    changed_risk = TradingRiskResult.model_construct(
        **(context.trading_risk_result.model_dump() | {"approved_quantity": Decimal("1")})
    )
    changed_context = OMSBridgeContext.model_construct(
        order_intent=changed_intent,
        trading_risk_result=changed_risk,
        account_id="account-1",
        order_source="oms_bridge",
        bridge_config=None,
    )

    conflict = service.create_order(changed_context)

    assert conflict.status is OMSBridgeResultStatus.CONFLICT
    assert fake.calls == []


def test_duplicate_different_bridge_hash_conflicts_even_when_order_request_matches() -> None:
    fake = FakeOMS()
    service = OMSBridgeService(fake, clock=_clock)
    context = _context()
    service.create_order(context)
    fake.calls.clear()
    existing = fake.orders[build_client_order_id(context.order_intent.intent_id)]
    fake.orders[existing.request.client_order_id] = existing.model_copy(
        update={"bridge_payload_hash": "different-bridge-hash"}
    )

    conflict = service.create_order(context)

    assert conflict.status is OMSBridgeResultStatus.CONFLICT
    assert conflict.reason == "client_order_id_canonical_conflict"
    assert fake.calls == []


def test_duplicate_same_bridge_hash_returns_duplicate_without_create_call() -> None:
    fake = FakeOMS()
    service = OMSBridgeService(fake, clock=_clock)
    context = _context()
    first = service.create_order(context)
    fake.calls.clear()

    duplicate = service.create_order(context)

    assert first.bridge_payload_hash == duplicate.bridge_payload_hash
    assert duplicate.status is OMSBridgeResultStatus.DUPLICATE
    assert fake.calls == []


def test_duplicate_missing_hash_same_lineage_falls_back_to_request_duplicate() -> None:
    fake = FakeOMS()
    service = OMSBridgeService(fake, clock=_clock)
    context = _context()
    service.create_order(context)
    fake.calls.clear()
    existing = fake.orders[build_client_order_id(context.order_intent.intent_id)]
    fake.orders[existing.request.client_order_id] = existing.model_copy(
        update={"bridge_payload_hash": None}
    )

    duplicate = service.create_order(context)

    assert duplicate.status is OMSBridgeResultStatus.DUPLICATE
    assert fake.calls == []


def test_duplicate_missing_hash_different_lineage_conflicts_without_create_call() -> None:
    fake = FakeOMS()
    service = OMSBridgeService(fake, clock=_clock)
    context = _context()
    service.create_order(context)
    fake.calls.clear()
    existing = fake.orders[build_client_order_id(context.order_intent.intent_id)]
    fake.orders[existing.request.client_order_id] = existing.model_copy(
        update={
            "bridge_payload_hash": None,
            "risk_result_id": "different-risk-result",
        }
    )

    conflict = service.create_order(context)

    assert conflict.status is OMSBridgeResultStatus.CONFLICT
    assert fake.calls == []


def test_oms_creator_error_returns_controlled_error() -> None:
    fake = FakeOMS()
    fake.fail_next = True

    result = OMSBridgeService(fake, clock=_clock).create_order(_context())

    assert result.status is OMSBridgeResultStatus.ERROR
    assert result.order_id is None
    assert result.reason == "oms unavailable"


def test_replay_dry_run_is_deterministic_and_does_not_call_oms() -> None:
    fake = FakeOMS()
    service = OMSBridgeService(fake, clock=_clock)
    context = _context()

    previews = replay_oms_bridge([context, context], service=service)

    assert [preview.status for preview in previews] == ["WOULD_CREATE", "DUPLICATE"]
    assert previews[0].client_order_id == build_client_order_id(context.order_intent.intent_id)
    assert fake.calls == []
