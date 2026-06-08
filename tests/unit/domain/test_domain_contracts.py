from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import (
    BarTimeframe,
    Direction,
    EventApplicationStatus,
    EventSource,
    MarginPriceBasis,
    MarginResultStatus,
    MarketDataEventType,
    MarketDataResultStatus,
    Offset,
    OMSEventApplyResultStatus,
    OrderStatus,
    OrderType,
    PnLPriceBasis,
    PnLResultStatus,
    PositionManagerResultStatus,
    SettlementResultStatus,
    TradeBridgeResultStatus,
    TradeIdentitySource,
)
from futures_mvp.domain.errors import DecimalRequiredError
from futures_mvp.domain.models import (
    AccountContext,
    Bar,
    CloseTradeContext,
    DataQualityResult,
    FillEvent,
    MarginRequirement,
    MarginResult,
    MarginRule,
    MarginSnapshot,
    MarketDataEvent,
    MarketDataSnapshot,
    OrderEvent,
    OrderEventApplicationResult,
    OrderRequest,
    OrderState,
    PnLResult,
    PnLSnapshot,
    Position,
    PositionEvent,
    PositionManagerResult,
    PositionSnapshot,
    RealizedPnL,
    SettlementContext,
    SettlementPrice,
    SettlementSnapshot,
    Signal,
    Tick,
    Trade,
    TradeBridgeResult,
    UnrealizedPnL,
)


def test_order_status_complete_state_machine() -> None:
    assert [status.value for status in OrderStatus] == [
        "CREATED",
        "RISK_CHECKING",
        "REJECTED_BY_RISK",
        "RISK_ACCEPTED",
        "SUBMITTING",
        "SUBMIT_TIMEOUT",
        "SUBMIT_FAILED",
        "SUBMITTED",
        "ACKED",
        "PARTIALLY_FILLED",
        "CANCEL_PENDING",
        "CANCEL_FAILED",
        "CANCELED",
        "FILLED",
        "REJECTED_BY_EXCHANGE",
        "EXPIRED",
        "UNKNOWN",
    ]


def test_event_application_status_complete_contract() -> None:
    assert [status.value for status in EventApplicationStatus] == [
        "APPLIED",
        "DUPLICATE",
        "OLD_IGNORED",
        "MISMATCH_REJECTED",
        "ENTERED_UNKNOWN",
        "RECOVERED_FROM_UNKNOWN",
        "IGNORED_TERMINAL",
        "EVENT_KEY_COLLISION",
    ]


def test_oms_event_apply_result_status_complete_contract() -> None:
    assert [status.value for status in OMSEventApplyResultStatus] == [
        "APPLIED",
        "DRY_RUN",
        "NO_OP",
        "DUPLICATE",
        "CONFLICT",
        "REJECTED_INVALID_CANDIDATE",
        "REJECTED_NO_EVENT",
        "ERROR",
    ]


def test_trade_bridge_result_status_complete_contract() -> None:
    assert [status.value for status in TradeBridgeResultStatus] == [
        "CREATED",
        "DUPLICATE",
        "REJECTED_NOT_FILLED",
        "REJECTED_OMS_NOT_APPLIED",
        "REJECTED_MISSING_TRADE_IDENTITY",
        "REJECTED_LINEAGE_MISMATCH",
        "CONFLICT",
        "ERROR",
    ]


def test_trade_identity_source_complete_contract() -> None:
    assert [source.value for source in TradeIdentitySource] == [
        "exchange_trade_id",
        "derived_from_report",
    ]


def test_position_manager_result_status_complete_contract() -> None:
    assert [status.value for status in PositionManagerResultStatus] == [
        "APPLIED",
        "DUPLICATE_IGNORED",
        "REJECTED_INSUFFICIENT_POSITION",
        "CONFLICT",
        "ERROR",
    ]


def test_margin_price_basis_complete_contract() -> None:
    assert [basis.value for basis in MarginPriceBasis] == [
        "LAST_PRICE",
        "SETTLEMENT_PRICE",
        "AVG_PRICE",
        "MANUAL",
    ]


def test_margin_result_status_complete_contract() -> None:
    assert [status.value for status in MarginResultStatus] == [
        "CALCULATED",
        "REJECTED_MISSING_RULE",
        "REJECTED_MISSING_POSITION",
        "REJECTED_MISSING_PRICE",
        "REJECTED_INSUFFICIENT_CASH",
        "CONFLICT",
        "ERROR",
    ]


def test_pnl_price_basis_complete_contract() -> None:
    assert [basis.value for basis in PnLPriceBasis] == [
        "LAST_PRICE",
        "SETTLEMENT_PRICE",
        "MANUAL",
    ]


def test_pnl_result_status_complete_contract() -> None:
    assert [status.value for status in PnLResultStatus] == [
        "CALCULATED",
        "REJECTED_MISSING_POSITION",
        "REJECTED_MISSING_PRICE",
        "REJECTED_MISSING_MULTIPLIER",
        "REJECTED_MISSING_FEE",
        "DOMAIN_FIELD_UNSUPPORTED",
        "CONFLICT",
        "ERROR",
    ]


def test_settlement_result_status_complete_contract() -> None:
    assert [status.value for status in SettlementResultStatus] == [
        "SETTLED",
        "DUPLICATE",
        "REJECTED_NON_TRADING_DAY",
        "REJECTED_MISSING_POSITION",
        "REJECTED_MISSING_PNL",
        "REJECTED_MISSING_MARGIN",
        "REJECTED_MISSING_SETTLEMENT_PRICE",
        "REJECTED_FROZEN_POSITION",
        "CONFLICT",
        "ERROR",
    ]


def test_market_data_enums_complete_contract() -> None:
    assert [status.value for status in MarketDataResultStatus] == [
        "ACCEPTED",
        "REJECTED_MISSING_IDENTITY",
        "REJECTED_BAD_TIMESTAMP",
        "REJECTED_OUT_OF_SESSION",
        "REJECTED_BAD_PRICE",
        "REJECTED_NON_MONOTONIC",
        "DUPLICATE",
        "GAP_DETECTED",
        "ERROR",
    ]
    assert [event_type.value for event_type in MarketDataEventType] == [
        "TICK_ACCEPTED",
        "BAR_ACCEPTED",
        "TICK_REJECTED",
        "BAR_REJECTED",
        "DUPLICATE",
        "GAP_DETECTED",
        "ERROR",
    ]
    assert [timeframe.value for timeframe in BarTimeframe] == [
        "M1",
        "M5",
        "M15",
        "M30",
        "H1",
        "D1",
    ]


def test_tick_decimal_validation_and_raw_payload_diagnostic_only() -> None:
    tick = Tick(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
        price=Decimal("500"),
        volume=Decimal("1"),
        turnover=Decimal("500"),
        open_interest=Decimal("10"),
        bid_price_1=Decimal("499"),
        ask_price_1=Decimal("501"),
        bid_volume_1=Decimal("2"),
        ask_volume_1=Decimal("3"),
        source="adapter",
        raw_payload={"diagnostic": True},
    )

    assert tick.price == Decimal("500")
    assert tick.raw_payload == {"diagnostic": True}

    with pytest.raises(DecimalRequiredError):
        Tick(
            symbol="au",
            instrument_id="au2606",
            trade_instrument_id="au2606",
            exchange="SHFE",
            trading_day=date(2026, 6, 7),
            ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
            price=500.0,
            volume=Decimal("1"),
            turnover=Decimal("500"),
            open_interest=Decimal("10"),
            source="adapter",
        )
    with pytest.raises(ValueError):
        Tick(
            symbol="au",
            instrument_id="au2606",
            trade_instrument_id="au2606",
            exchange="SHFE",
            trading_day=date(2026, 6, 7),
            ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
            price=Decimal("0"),
            volume=Decimal("1"),
            turnover=Decimal("500"),
            open_interest=Decimal("10"),
            source="adapter",
        )
    with pytest.raises(ValueError):
        Tick(
            symbol="au",
            instrument_id="au2606",
            trade_instrument_id="au2606",
            exchange="SHFE",
            trading_day=date(2026, 6, 7),
            ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
            price=Decimal("500"),
            volume=Decimal("1"),
            turnover=Decimal("500"),
            open_interest=Decimal("10"),
            bid_price_1=Decimal("502"),
            ask_price_1=Decimal("501"),
            source="adapter",
        )


def test_bar_ohlc_validation_and_snapshot_contract() -> None:
    bar = Bar(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=BarTimeframe.M1,
        bar_ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
        open=Decimal("500"),
        high=Decimal("505"),
        low=Decimal("499"),
        close=Decimal("501"),
        volume=Decimal("10"),
        turnover=Decimal("5000"),
        open_interest=Decimal("20"),
        source="adapter",
        quality_status=MarketDataResultStatus.ACCEPTED,
    )

    snapshot = MarketDataSnapshot(
        symbol=bar.symbol,
        instrument_id=bar.instrument_id,
        trade_instrument_id=bar.trade_instrument_id,
        exchange=bar.exchange,
        trading_day=bar.trading_day,
        as_of_ts=bar.bar_ts,
        latest_tick=None,
        latest_bars={BarTimeframe.M1: bar},
        quality_status=MarketDataResultStatus.ACCEPTED,
    )

    assert snapshot.latest_bars[BarTimeframe.M1] == bar
    assert bar.bar_ts == datetime(2026, 6, 7, 9, tzinfo=UTC)

    with pytest.raises(ValueError):
        Bar(
            symbol="au",
            instrument_id="au2606",
            trade_instrument_id="au2606",
            exchange="SHFE",
            trading_day=date(2026, 6, 7),
            timeframe=BarTimeframe.M1,
            bar_ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
            open=Decimal("500"),
            high=Decimal("499"),
            low=Decimal("498"),
            close=Decimal("501"),
            volume=Decimal("10"),
            turnover=Decimal("5000"),
            open_interest=Decimal("20"),
            source="adapter",
            quality_status=MarketDataResultStatus.ACCEPTED,
        )


def _market_tick_for_contract(
    *,
    instrument_id: str = "au2606",
    ts: datetime = datetime(2026, 6, 7, 9, tzinfo=UTC),
) -> Tick:
    return Tick(
        symbol="au",
        instrument_id=instrument_id,
        trade_instrument_id=instrument_id,
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        ts=ts,
        price=Decimal("500"),
        volume=Decimal("1"),
        turnover=Decimal("500"),
        open_interest=Decimal("10"),
        source="adapter",
    )


def _market_bar_for_contract(
    *,
    instrument_id: str = "au2606",
    trading_day: date = date(2026, 6, 7),
    timeframe: BarTimeframe = BarTimeframe.M1,
    bar_ts: datetime = datetime(2026, 6, 7, 9, tzinfo=UTC),
) -> Bar:
    return Bar(
        symbol="au",
        instrument_id=instrument_id,
        trade_instrument_id=instrument_id,
        exchange="SHFE",
        trading_day=trading_day,
        timeframe=timeframe,
        bar_ts=bar_ts,
        open=Decimal("500"),
        high=Decimal("505"),
        low=Decimal("499"),
        close=Decimal("501"),
        volume=Decimal("10"),
        turnover=Decimal("5000"),
        open_interest=Decimal("20"),
        source="adapter",
        quality_status=MarketDataResultStatus.ACCEPTED,
    )


def _market_quality_result(
    *,
    status: MarketDataResultStatus = MarketDataResultStatus.ACCEPTED,
    event_type: MarketDataEventType = MarketDataEventType.TICK_ACCEPTED,
    instrument_id: str = "au2606",
    ts: datetime = datetime(2026, 6, 7, 9, tzinfo=UTC),
) -> DataQualityResult:
    return DataQualityResult(
        status=status,
        event_type=event_type,
        instrument_id=instrument_id,
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        ts=ts,
    )


def test_market_data_event_rejects_incompatible_result_and_payload_shape() -> None:
    tick = _market_tick_for_contract()
    bar = _market_bar_for_contract()

    with pytest.raises(ValueError):
        MarketDataEvent(
            event_id="event-1",
            event_type=MarketDataEventType.TICK_ACCEPTED,
            instrument_id=tick.instrument_id,
            exchange=tick.exchange,
            trading_day=tick.trading_day,
            ts=tick.ts,
            source=tick.source,
            result=_market_quality_result(
                status=MarketDataResultStatus.ERROR,
                event_type=MarketDataEventType.ERROR,
            ),
            tick=tick,
        )
    with pytest.raises(ValueError):
        MarketDataEvent(
            event_id="event-2",
            event_type=MarketDataEventType.TICK_ACCEPTED,
            instrument_id=tick.instrument_id,
            exchange=tick.exchange,
            trading_day=tick.trading_day,
            ts=tick.ts,
            source=tick.source,
            result=_market_quality_result(),
            bar=bar,
        )
    with pytest.raises(ValueError):
        MarketDataEvent(
            event_id="event-3",
            event_type=MarketDataEventType.TICK_ACCEPTED,
            instrument_id=tick.instrument_id,
            exchange=tick.exchange,
            trading_day=tick.trading_day,
            ts=tick.ts,
            source=tick.source,
            result=_market_quality_result(),
            tick=tick,
            bar=bar,
        )
    with pytest.raises(ValueError):
        MarketDataEvent(
            event_id="event-4",
            event_type=MarketDataEventType.TICK_ACCEPTED,
            instrument_id=tick.instrument_id,
            exchange=tick.exchange,
            trading_day=tick.trading_day,
            ts=tick.ts,
            source=tick.source,
            result=_market_quality_result(),
        )


def test_market_data_event_rejects_payload_identity_mismatch() -> None:
    tick = _market_tick_for_contract()
    other_tick = _market_tick_for_contract(instrument_id="ag2606")
    bar = _market_bar_for_contract()
    other_bar = _market_bar_for_contract(instrument_id="ag2606")

    with pytest.raises(ValueError):
        MarketDataEvent(
            event_id="event-1",
            event_type=MarketDataEventType.TICK_ACCEPTED,
            instrument_id=tick.instrument_id,
            exchange=tick.exchange,
            trading_day=tick.trading_day,
            ts=tick.ts,
            source=tick.source,
            result=_market_quality_result(),
            tick=other_tick,
        )
    with pytest.raises(ValueError):
        MarketDataEvent(
            event_id="event-2",
            event_type=MarketDataEventType.BAR_ACCEPTED,
            instrument_id=bar.instrument_id,
            exchange=bar.exchange,
            trading_day=bar.trading_day,
            ts=bar.bar_ts,
            source=bar.source,
            result=_market_quality_result(event_type=MarketDataEventType.BAR_ACCEPTED),
            bar=other_bar,
        )


def test_market_data_snapshot_rejects_mixed_identity_time_and_timeframe() -> None:
    tick = _market_tick_for_contract()
    bar = _market_bar_for_contract()

    with pytest.raises(ValueError):
        MarketDataSnapshot(
            symbol="au",
            instrument_id="au2606",
            trade_instrument_id="au2606",
            exchange="SHFE",
            trading_day=date(2026, 6, 7),
            as_of_ts=datetime(2026, 6, 7, 10, tzinfo=UTC),
            latest_tick=_market_tick_for_contract(instrument_id="ag2606"),
            latest_bars={BarTimeframe.M1: bar},
            quality_status=MarketDataResultStatus.ACCEPTED,
        )
    with pytest.raises(ValueError):
        MarketDataSnapshot(
            symbol="au",
            instrument_id="au2606",
            trade_instrument_id="au2606",
            exchange="SHFE",
            trading_day=date(2026, 6, 7),
            as_of_ts=datetime(2026, 6, 7, 8, tzinfo=UTC),
            latest_tick=tick,
            latest_bars={BarTimeframe.M1: bar},
            quality_status=MarketDataResultStatus.ACCEPTED,
        )
    with pytest.raises(ValueError):
        MarketDataSnapshot(
            symbol="au",
            instrument_id="au2606",
            trade_instrument_id="au2606",
            exchange="SHFE",
            trading_day=date(2026, 6, 7),
            as_of_ts=datetime(2026, 6, 7, 10, tzinfo=UTC),
            latest_tick=tick,
            latest_bars={BarTimeframe.M5: bar},
            quality_status=MarketDataResultStatus.ACCEPTED,
        )
    with pytest.raises(ValueError):
        MarketDataSnapshot(
            symbol="au",
            instrument_id="au2606",
            trade_instrument_id="au2606",
            exchange="SHFE",
            trading_day=date(2026, 6, 7),
            as_of_ts=datetime(2026, 6, 7, 10, tzinfo=UTC),
            latest_tick=tick,
            latest_bars={BarTimeframe.M1: _market_bar_for_contract(trading_day=date(2026, 6, 8))},
            quality_status=MarketDataResultStatus.ACCEPTED,
        )


def test_market_data_snapshot_accepts_same_instrument_mixed_timeframes() -> None:
    tick = _market_tick_for_contract(ts=datetime(2026, 6, 7, 9, 2, tzinfo=UTC))
    m1 = _market_bar_for_contract(timeframe=BarTimeframe.M1)
    m5 = _market_bar_for_contract(
        timeframe=BarTimeframe.M5,
        bar_ts=datetime(2026, 6, 7, 9, 5, tzinfo=UTC),
    )

    snapshot = MarketDataSnapshot(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        as_of_ts=datetime(2026, 6, 7, 10, tzinfo=UTC),
        latest_tick=tick,
        latest_bars={BarTimeframe.M1: m1, BarTimeframe.M5: m5},
        quality_status=MarketDataResultStatus.ACCEPTED,
    )

    assert snapshot.latest_bars[BarTimeframe.M5] == m5


def test_settlement_domain_validators_and_no_raw_payload_facts() -> None:
    price = SettlementPrice(
        instrument_id="rb2610",
        exchange="SHFE",
        trading_day=date(2026, 6, 4),
        price=Decimal("3500"),
        source=None,
        received_at=datetime.now(UTC),
    )

    assert price.price == Decimal("3500")
    assert "raw_payload" not in SettlementPrice.model_fields
    assert "raw_payload" not in SettlementSnapshot.model_fields

    with pytest.raises(DecimalRequiredError):
        SettlementPrice(
            instrument_id="rb2610",
            exchange="SHFE",
            trading_day=date(2026, 6, 4),
            price=3500.0,
            received_at=datetime.now(UTC),
        )
    with pytest.raises(ValueError):
        SettlementPrice(
            instrument_id="rb2610",
            exchange="SHFE",
            trading_day=date(2026, 6, 4),
            price=Decimal("0"),
            received_at=datetime.now(UTC),
        )
    with pytest.raises(ValueError):
        SettlementContext(
            account_id="acct-1",
            trading_day=date(2026, 6, 4),
            account_before=AccountContext(
                account_id="acct-1",
                equity=Decimal("10000"),
                available_cash=Decimal("10000"),
                frozen_cash=Decimal("0"),
                snapshot_time=datetime.now(UTC),
            ),
            positions=(),
            pnl_snapshots=(),
            margin_snapshots=(),
            settlement_prices=(),
            calculation_key=" ",
            settled_at=datetime.now(UTC),
        )


def test_core_models_reject_float_prices_and_quantities() -> None:
    with pytest.raises(DecimalRequiredError):
        Signal(
            signal_id="sig-1",
            account_id="acct-1",
            instrument_id="rb2610",
            exchange="SHFE",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            limit_price=3500.0,
            quantity=Decimal("1"),
            created_at=datetime.now(UTC),
        )

    with pytest.raises(DecimalRequiredError):
        OrderRequest(
            client_order_id="coid-1",
            account_id="acct-1",
            instrument_id="rb2610",
            exchange="SHFE",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            order_type=OrderType.LIMIT,
            limit_price=Decimal("3500"),
            quantity=1.0,
        )


def test_strategy_signal_contains_no_order_identity_or_status() -> None:
    signal = Signal(
        signal_id="sig-1",
        account_id="acct-1",
        instrument_id="rb2610",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        limit_price=Decimal("3500"),
        quantity=Decimal("1"),
        created_at=datetime.now(UTC),
    )

    dumped = signal.model_dump()
    assert "client_order_id" not in dumped
    assert "status" not in dumped


def test_order_event_requires_idempotency_fields_and_raw_payload() -> None:
    event = OrderEvent(
        order_id="order-1",
        previous_status=OrderStatus.SUBMITTED,
        new_status=OrderStatus.ACKED,
        event_source=EventSource.EXCHANGE,
        external_event_id="exchange-report-1",
        raw_payload={"raw": "payload"},
        occurred_at=datetime.now(UTC),
    )

    assert event.external_event_id == "exchange-report-1"
    assert event.raw_payload == {"raw": "payload"}


def test_margin_rule_decimal_rate_and_multiplier_contract() -> None:
    rule = MarginRule(
        instrument_id="rb2610",
        exchange="SHFE",
        contract_multiplier=Decimal("10"),
        long_initial_margin_rate=Decimal("0.12"),
        short_initial_margin_rate=Decimal("0.13"),
        long_maintenance_margin_rate=Decimal("0.08"),
        short_maintenance_margin_rate=Decimal("0.09"),
        price_basis=MarginPriceBasis.MANUAL,
        price=Decimal("3500"),
    )

    assert rule.contract_multiplier == Decimal("10")
    assert rule.long_initial_margin_rate == Decimal("0.12")
    assert "raw_payload" not in MarginRule.model_fields

    with pytest.raises(ValueError):
        MarginRule(
            instrument_id="rb2610",
            exchange="SHFE",
            contract_multiplier=Decimal("0"),
            long_initial_margin_rate=Decimal("0.12"),
            short_initial_margin_rate=Decimal("0.13"),
            long_maintenance_margin_rate=Decimal("0.08"),
            short_maintenance_margin_rate=Decimal("0.09"),
            price_basis=MarginPriceBasis.MANUAL,
        )
    with pytest.raises(ValueError):
        MarginRule(
            instrument_id="rb2610",
            exchange="SHFE",
            contract_multiplier=Decimal("10"),
            long_initial_margin_rate=Decimal("-0.01"),
            short_initial_margin_rate=Decimal("0.13"),
            long_maintenance_margin_rate=Decimal("0.08"),
            short_maintenance_margin_rate=Decimal("0.09"),
            price_basis=MarginPriceBasis.MANUAL,
        )
    with pytest.raises(DecimalRequiredError):
        MarginRule(
            instrument_id="rb2610",
            exchange="SHFE",
            contract_multiplier=10.0,
            long_initial_margin_rate=Decimal("0.12"),
            short_initial_margin_rate=Decimal("0.13"),
            long_maintenance_margin_rate=Decimal("0.08"),
            short_maintenance_margin_rate=Decimal("0.09"),
            price_basis=MarginPriceBasis.MANUAL,
        )


def test_margin_account_context_decimal_contract_allows_zero_available_cash() -> None:
    account = AccountContext(
        account_id="acct-1",
        equity=Decimal("1000"),
        available_cash=Decimal("0"),
        frozen_cash=Decimal("0"),
        snapshot_time=datetime.now(UTC),
    )

    assert account.available_cash == Decimal("0")
    assert "raw_payload" not in AccountContext.model_fields

    with pytest.raises(DecimalRequiredError):
        AccountContext(
            account_id="acct-1",
            equity=1000.0,
            available_cash=Decimal("0"),
            frozen_cash=Decimal("0"),
            snapshot_time=datetime.now(UTC),
        )


def test_margin_requirement_snapshot_and_result_contracts() -> None:
    requirement = MarginRequirement(
        account_id="acct-1",
        instrument_id="rb2610",
        long_initial_margin=Decimal("100"),
        short_initial_margin=Decimal("50"),
        total_initial_margin=Decimal("150"),
        long_maintenance_margin=Decimal("80"),
        short_maintenance_margin=Decimal("40"),
        total_maintenance_margin=Decimal("120"),
        margin_used=Decimal("150"),
        required_cash=Decimal("150"),
        is_sufficient=True,
    )
    snapshot = MarginSnapshot(
        account_id="acct-1",
        instrument_id="rb2610",
        position_version=1,
        trading_day=date(2026, 1, 1),
        config_hash="margin-config-v1",
        rule_id="rule-1",
        rule_version="v1",
        calculation_key="acct-1:rb2610:1:v1",
        long_qty=Decimal("2"),
        short_qty=Decimal("1"),
        price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        initial_margin=Decimal("150"),
        maintenance_margin=Decimal("120"),
        margin_used=Decimal("150"),
        available_cash=Decimal("1000"),
        equity=Decimal("2000"),
        calculated_at=datetime.now(UTC),
    )
    result = MarginResult(
        status=MarginResultStatus.CALCULATED,
        requirement=requirement,
        snapshot=snapshot,
    )

    assert result.requirement == requirement
    assert result.snapshot == snapshot
    assert "calculation_key" in MarginSnapshot.model_fields
    assert "trading_day" in MarginSnapshot.model_fields
    assert "config_hash" in MarginSnapshot.model_fields
    assert "raw_payload" not in MarginSnapshot.model_fields
    with pytest.raises(ValueError):
        MarginSnapshot(
            account_id="acct-1",
            instrument_id="rb2610",
            position_version=1,
            trading_day=date(2026, 1, 1),
            config_hash="",
            calculation_key="acct-1:rb2610:1:v1",
            long_qty=Decimal("2"),
            short_qty=Decimal("1"),
            price=Decimal("3500"),
            contract_multiplier=Decimal("10"),
            initial_margin=Decimal("150"),
            maintenance_margin=Decimal("120"),
            margin_used=Decimal("150"),
            available_cash=Decimal("1000"),
            equity=Decimal("2000"),
            calculated_at=datetime.now(UTC),
        )


def test_pnl_domain_contracts_and_decimal_validation() -> None:
    context = CloseTradeContext(
        account_id="acct-1",
        instrument_id="rb2610",
        position_version=1,
        avg_cost=Decimal("100"),
        available_qty=Decimal("2"),
        contract_multiplier=Decimal("10"),
    )
    realized = RealizedPnL(
        account_id="acct-1",
        instrument_id="rb2610",
        trade_id="trade-1",
        direction=Direction.SELL,
        offset=Offset.CLOSE_TODAY,
        quantity=Decimal("1"),
        close_price=Decimal("110"),
        avg_cost=context.avg_cost,
        contract_multiplier=context.contract_multiplier,
        gross_realized_pnl=Decimal("100"),
        fee_amount=None,
        net_realized_pnl=None,
        calculated_at=datetime.now(UTC),
    )
    unrealized = UnrealizedPnL(
        account_id="acct-1",
        instrument_id="rb2610",
        long_qty=Decimal("1"),
        short_qty=Decimal("0"),
        long_avg_price=Decimal("100"),
        short_avg_price=Decimal("0"),
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("105"),
        contract_multiplier=Decimal("10"),
        gross_unrealized_pnl=Decimal("50"),
        net_unrealized_pnl=Decimal("50"),
    )
    snapshot = PnLSnapshot(
        account_id="acct-1",
        instrument_id="rb2610",
        position_version=1,
        trading_day=date(2026, 1, 1),
        config_hash="pnl-config-v1",
        trade_id="trade-1",
        margin_snapshot_id="margin-1",
        calculation_key="acct-1:rb2610:1:pnl",
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("105"),
        contract_multiplier=Decimal("10"),
        realized_pnl=Decimal("100"),
        unrealized_pnl=Decimal("50"),
        total_pnl=Decimal("150"),
        fee_amount=None,
        calculated_at=datetime.now(UTC),
    )
    result = PnLResult(
        status=PnLResultStatus.CALCULATED,
        realized=realized,
        unrealized=unrealized,
        snapshot=snapshot,
        reason="fee_unknown",
    )

    assert result.snapshot == snapshot
    assert result.realized is not None
    assert result.realized.fee_amount is None
    assert result.realized.net_realized_pnl is None
    assert "raw_payload" not in CloseTradeContext.model_fields
    assert "trading_day" in PnLSnapshot.model_fields
    assert "config_hash" in PnLSnapshot.model_fields
    assert "raw_payload" not in PnLSnapshot.model_fields
    with pytest.raises(ValueError):
        CloseTradeContext(
            account_id="acct-1",
            instrument_id="rb2610",
            position_version=1,
            avg_cost=Decimal("100"),
            available_qty=Decimal("1"),
            contract_multiplier=Decimal("0"),
        )
    with pytest.raises(DecimalRequiredError):
        PnLSnapshot(
            account_id="acct-1",
            instrument_id="rb2610",
            position_version=1,
            trading_day=date(2026, 1, 1),
            config_hash="pnl-config-v1",
            calculation_key="acct-1:rb2610:1:pnl",
            price_basis=PnLPriceBasis.MANUAL,
            mark_price=105.0,
            contract_multiplier=Decimal("10"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            calculated_at=datetime.now(UTC),
        )
    with pytest.raises(ValueError):
        PnLSnapshot(
            account_id="acct-1",
            instrument_id="rb2610",
            position_version=1,
            trading_day=date(2026, 1, 1),
            config_hash="pnl-config-v1",
            calculation_key="",
            price_basis=PnLPriceBasis.MANUAL,
            mark_price=Decimal("105"),
            contract_multiplier=Decimal("10"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            calculated_at=datetime.now(UTC),
        )
    with pytest.raises(ValueError):
        PnLSnapshot(
            account_id="acct-1",
            instrument_id="rb2610",
            position_version=1,
            trading_day=date(2026, 1, 1),
            config_hash="",
            calculation_key="acct-1:rb2610:1:pnl",
            price_basis=PnLPriceBasis.MANUAL,
            mark_price=Decimal("105"),
            contract_multiplier=Decimal("10"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("0"),
            calculated_at=datetime.now(UTC),
        )


def test_order_state_version_defaults_to_zero_for_optimistic_locking() -> None:
    state = OrderState(order_id="order-1", request=_order_request())

    assert state.version == 0


def test_order_event_application_result_uses_typed_status_and_order() -> None:
    state = OrderState(order_id="order-1", request=_order_request())
    result = OrderEventApplicationResult(
        status=EventApplicationStatus.APPLIED,
        order=state,
    )

    assert result.status == EventApplicationStatus.APPLIED
    assert result.order == state
    assert result.reason is None


def _order_request() -> OrderRequest:
    return OrderRequest(
        client_order_id="coid-1",
        account_id="acct-1",
        instrument_id="rb2610",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("3500"),
        quantity=Decimal("1"),
    )


def test_trade_identity_uses_account_exchange_and_exchange_trade_id() -> None:
    trade = Trade(
        account_id="acct-1",
        exchange="SHFE",
        exchange_trade_id="trade-1",
        identity_source=TradeIdentitySource.EXCHANGE_TRADE_ID,
        order_id="order-1",
        client_order_id="client-1",
        instrument_id="rb2610",
        trade_instrument_id="rb2610",
        symbol="rb",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        price=Decimal("3500"),
        quantity=Decimal("1"),
        trade_time=datetime.now(UTC),
    )

    assert (trade.account_id, trade.exchange, trade.exchange_trade_id) == (
        "acct-1",
        "SHFE",
        "trade-1",
    )


def test_fill_event_decimal_contract_and_fee_semantics() -> None:
    fill_event = FillEvent(
        order_id="order-1",
        account_id="acct-1",
        exchange="SHFE",
        instrument_id="rb2610",
        exchange_report_id="report-1",
        exchange_trade_id="trade-1",
        fill_id="fill-1",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        price=Decimal("3500"),
        quantity=Decimal("1"),
        fee_amount=Decimal("0"),
        fee_currency="CNY",
        fee_source="EXCHANGE_REPORT",
        traded_at=datetime.now(UTC),
        trading_day=date(2026, 1, 1),
        raw_payload={"diagnostic": True},
    )

    assert fill_event.price == Decimal("3500")
    assert fill_event.quantity == Decimal("1")
    assert fill_event.fee_amount == Decimal("0")
    assert fill_event.fee_currency == "CNY"


def test_fill_event_rejects_float_facts() -> None:
    with pytest.raises(DecimalRequiredError):
        FillEvent(
            order_id="order-1",
            account_id="acct-1",
            exchange="SHFE",
            instrument_id="rb2610",
            exchange_report_id="report-1",
            exchange_trade_id="trade-1",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=3500.0,
            quantity=Decimal("1"),
            traded_at=datetime.now(UTC),
        )


def test_trade_decimal_contract_and_stage_b_fields() -> None:
    trade = Trade(
        account_id="acct-1",
        exchange="SHFE",
        exchange_trade_id="trade-1",
        order_id="order-1",
        client_order_id="client-1",
        instrument_id="rb2610",
        trade_instrument_id="rb2610",
        symbol="rb",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        price=Decimal("3500"),
        quantity=Decimal("1"),
        fee_amount=None,
        fee_currency=None,
        fee_source=None,
        trade_time=datetime.now(UTC),
        trading_day=date(2026, 1, 1),
        source_report_id="report-1",
        source_exchange_report_id="report-1",
        source_order_event_id="event-1",
        raw_payload={"diagnostic": True},
    )

    assert trade.price == Decimal("3500")
    assert trade.quantity == Decimal("1")
    assert trade.fee_amount is None
    assert trade.identity_source is TradeIdentitySource.EXCHANGE_TRADE_ID
    assert trade.client_order_id == "client-1"
    assert trade.trade_instrument_id == "rb2610"
    assert trade.symbol == "rb"
    assert trade.source_report_id == "report-1"
    assert trade.source_exchange_report_id == "report-1"
    assert trade.source_order_event_id == "event-1"


def test_trade_bridge_result_requires_trade_for_success_status() -> None:
    trade = Trade(
        account_id="acct-1",
        exchange="SHFE",
        exchange_trade_id="trade-1",
        order_id="order-1",
        instrument_id="rb2610",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        price=Decimal("3500"),
        quantity=Decimal("1"),
        trade_time=datetime.now(UTC),
    )

    result = TradeBridgeResult(
        status=TradeBridgeResultStatus.CREATED,
        trade=trade,
        source_report_id="report-1",
    )

    assert result.trade == trade

    with pytest.raises(ValueError):
        TradeBridgeResult(
            status=TradeBridgeResultStatus.CREATED,
            source_report_id="report-1",
        )


def test_trade_rejects_float_facts() -> None:
    with pytest.raises(DecimalRequiredError):
        Trade(
            account_id="acct-1",
            exchange="SHFE",
            exchange_trade_id="trade-1",
            order_id="order-1",
            instrument_id="rb2610",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=Decimal("3500"),
            quantity=1.0,
            trade_time=datetime.now(UTC),
        )


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1")])
def test_fill_event_trade_and_position_event_require_positive_quantity(
    quantity: Decimal,
) -> None:
    with pytest.raises(ValueError, match="quantity must be greater than 0"):
        FillEvent(
            order_id="order-1",
            account_id="acct-1",
            exchange="SHFE",
            instrument_id="rb2610",
            exchange_report_id="report-1",
            exchange_trade_id="trade-1",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=Decimal("3500"),
            quantity=quantity,
            traded_at=datetime.now(UTC),
        )

    with pytest.raises(ValueError, match="quantity must be greater than 0"):
        Trade(
            account_id="acct-1",
            exchange="SHFE",
            exchange_trade_id="trade-1",
            order_id="order-1",
            instrument_id="rb2610",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=Decimal("3500"),
            quantity=quantity,
            trade_time=datetime.now(UTC),
        )

    snapshot = PositionSnapshot.from_position(Position(account_id="acct-1", instrument_id="rb2610"))
    with pytest.raises(ValueError, match="quantity must be greater than 0"):
        PositionEvent(
            account_id="acct-1",
            instrument_id="rb2610",
            exchange="SHFE",
            exchange_trade_id="trade-1",
            trade_id="1",
            position_id="1",
            event_type="TRADE_APPLIED",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=Decimal("3500"),
            quantity=quantity,
            before_snapshot=snapshot,
            after_snapshot=snapshot,
            occurred_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )


def test_fee_currency_is_required_iff_fee_amount_is_known() -> None:
    with pytest.raises(ValueError):
        Trade(
            account_id="acct-1",
            exchange="SHFE",
            exchange_trade_id="trade-1",
            order_id="order-1",
            instrument_id="rb2610",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=Decimal("3500"),
            quantity=Decimal("1"),
            fee_amount=Decimal("1.2"),
            trade_time=datetime.now(UTC),
        )

    with pytest.raises(ValueError):
        FillEvent(
            order_id="order-1",
            account_id="acct-1",
            exchange="SHFE",
            instrument_id="rb2610",
            exchange_report_id="report-1",
            exchange_trade_id="trade-1",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=Decimal("3500"),
            quantity=Decimal("1"),
            fee_currency="CNY",
            traded_at=datetime.now(UTC),
        )


def test_position_is_single_row_with_long_short_today_yesterday_fields() -> None:
    position = Position(account_id="acct-1", instrument_id="rb2610")

    assert position.version == 0
    assert position.long_today_qty == Decimal("0")
    assert position.long_yesterday_qty == Decimal("0")
    assert position.short_today_qty == Decimal("0")
    assert position.short_yesterday_qty == Decimal("0")
    assert position.frozen_long_qty == Decimal("0")
    assert position.frozen_short_qty == Decimal("0")
    assert position.margin_used == Decimal("0")


def test_position_snapshot_decimal_contract() -> None:
    snapshot = PositionSnapshot.from_position(
        Position(
            id="1",
            account_id="acct-1",
            instrument_id="rb2610",
            long_today_qty=Decimal("2"),
            long_avg_price=Decimal("3500.5"),
            version=3,
        )
    )

    assert snapshot.account_id == "acct-1"
    assert snapshot.long_today_qty == Decimal("2")
    assert snapshot.long_avg_price == Decimal("3500.5")
    assert snapshot.version == 3


def test_position_snapshot_rejects_float_facts() -> None:
    with pytest.raises(DecimalRequiredError):
        PositionSnapshot(
            account_id="acct-1",
            instrument_id="rb2610",
            long_today_qty=1.0,
            long_yesterday_qty=Decimal("0"),
            short_today_qty=Decimal("0"),
            short_yesterday_qty=Decimal("0"),
            long_avg_price=Decimal("0"),
            short_avg_price=Decimal("0"),
            version=0,
        )


def test_position_event_decimal_and_snapshot_contract() -> None:
    before = PositionSnapshot.from_position(Position(account_id="acct-1", instrument_id="rb2610"))
    after = PositionSnapshot.from_position(
        Position(
            account_id="acct-1",
            instrument_id="rb2610",
            long_today_qty=Decimal("1"),
            long_avg_price=Decimal("3500"),
            version=1,
        )
    )
    event = PositionEvent(
        account_id="acct-1",
        instrument_id="rb2610",
        exchange="SHFE",
        exchange_trade_id="trade-1",
        trade_id="1",
        position_id="1",
        event_type="TRADE_APPLIED",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        price=Decimal("3500"),
        quantity=Decimal("1"),
        before_snapshot=before,
        after_snapshot=after,
        occurred_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        raw_payload={"diagnostic": True},
    )

    assert event.price == Decimal("3500")
    assert event.quantity == Decimal("1")
    assert event.before_snapshot.long_today_qty == Decimal("0")
    assert event.after_snapshot.long_today_qty == Decimal("1")


def test_position_event_rejects_float_facts() -> None:
    snapshot = PositionSnapshot.from_position(Position(account_id="acct-1", instrument_id="rb2610"))

    with pytest.raises(DecimalRequiredError):
        PositionEvent(
            account_id="acct-1",
            instrument_id="rb2610",
            exchange="SHFE",
            exchange_trade_id="trade-1",
            trade_id="1",
            position_id="1",
            event_type="TRADE_APPLIED",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=3500.0,
            quantity=Decimal("1"),
            before_snapshot=snapshot,
            after_snapshot=snapshot,
            occurred_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )


def test_position_manager_result_uses_typed_status() -> None:
    result = PositionManagerResult(
        status=PositionManagerResultStatus.APPLIED,
        account_id="acct-1",
        instrument_id="rb2610",
        trade_id="1",
    )

    assert result.status == PositionManagerResultStatus.APPLIED
