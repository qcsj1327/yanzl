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
from futures_mvp.modules.oms_bridge import OMSBridgeService, replay_oms_bridge


def _clock() -> datetime:
    return datetime(2026, 6, 8, 9, tzinfo=UTC)


def _context() -> OMSBridgeContext:
    risk_result = TradingRiskResult(
        signal_id="signal-1",
        risk_result_id="risk-1",
        evaluation_context_hash="eval-hash",
        risk_status=RiskResultStatus.ACCEPT,
        risk_reason="accepted",
        risk_level="INFO",
        requested_quantity=Decimal("2"),
        approved_quantity=Decimal("2"),
        max_quantity=Decimal("2"),
        expected_margin=Decimal("1000"),
        expected_notional=Decimal("1500"),
        config_hash="risk-config-hash",
        evaluation_ts=_clock(),
    )
    intent = OrderIntent(
        intent_id="intent-1",
        signal_id="signal-1",
        risk_result_id=risk_result.risk_result_id,
        strategy_name="toy",
        strategy_version="strategy-v1",
        strategy_config_hash="strategy-config-hash",
        runtime_id="runtime-1",
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 8),
        timeframe=BarTimeframe.M1,
        bar_ts=_clock(),
        feature_version="feature-v1",
        feature_config_hash="feature-hash",
        side=SignalSide.BUY,
        offset=Offset.OPEN,
        quantity=Decimal("2"),
        price=Decimal("500"),
        order_type=OrderType.LIMIT,
        tif="GFD",
        expected_margin=Decimal("1000"),
        expected_notional=Decimal("1500"),
        intent_reason="accepted",
    )
    return OMSBridgeContext(
        order_intent=intent,
        trading_risk_result=risk_result,
        account_id="account-1",
    )


class FakeOMSAdapter:
    def __init__(self) -> None:
        self.orders: dict[str, OrderState] = {}
        self.create_calls = 0

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
        self.create_calls += 1
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


def test_oms_bridge_fake_adapter_duplicate_and_dry_run_replay() -> None:
    fake = FakeOMSAdapter()
    service = OMSBridgeService(fake, clock=_clock)
    context = _context()

    first = service.create_order(context)
    duplicate = service.create_order(context)
    previews = replay_oms_bridge([context, context], service=service)

    assert first.status is OMSBridgeResultStatus.CREATED
    assert duplicate.status is OMSBridgeResultStatus.DUPLICATE
    assert fake.create_calls == 1
    assert first.order_id == duplicate.order_id
    assert fake.orders[first.client_order_id].request.direction is Direction.BUY
    assert [preview.status for preview in previews] == ["WOULD_CREATE", "DUPLICATE"]
    assert fake.create_calls == 1
