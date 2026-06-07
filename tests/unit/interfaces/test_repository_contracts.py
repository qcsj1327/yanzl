from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from futures_mvp.domain.enums import (
    BarTimeframe,
    Direction,
    EventSource,
    MarketDataResultStatus,
    Offset,
    OrderStatus,
    OrderType,
    PnLPriceBasis,
    SettlementResultStatus,
)
from futures_mvp.domain.models import (
    AccountSnapshot,
    Bar,
    MarginSnapshot,
    OrderEvent,
    OrderRequest,
    OrderState,
    PnLSnapshot,
    Position,
    PositionEvent,
    PositionSnapshot,
    SettlementSnapshot,
    Tick,
    Trade,
)
from futures_mvp.interfaces.repositories import (
    AccountSnapshotRepository,
    MarginSnapshotRepository,
    MarketBarRepository,
    MarketDataUnitOfWork,
    MarketTickRepository,
    OrderEventRepository,
    OrderRepository,
    PnLSnapshotRepository,
    PositionEventRepository,
    PositionRepository,
    SettlementSnapshotRepository,
    TradeRepository,
    UnitOfWork,
)


def _order_request(client_order_id: str = "client-1") -> OrderRequest:
    return OrderRequest(
        client_order_id=client_order_id,
        account_id="account-1",
        instrument_id="rb2601",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("3500"),
        quantity=Decimal("1"),
    )


def _order_state(order_id: str = "1") -> OrderState:
    return OrderState(order_id=order_id, request=_order_request(), status=OrderStatus.CREATED)


def _order_event(order_id: str = "1", external_event_id: str = "event-1") -> OrderEvent:
    return OrderEvent(
        order_id=order_id,
        previous_status=None,
        new_status=OrderStatus.CREATED,
        event_source=EventSource.OMS,
        external_event_id=external_event_id,
        raw_payload={"diagnostic": True},
        occurred_at=datetime.now(UTC),
    )


def _trade(order_id: str = "1", exchange_trade_id: str = "trade-1") -> Trade:
    return Trade(
        account_id="account-1",
        exchange="SHFE",
        exchange_trade_id=exchange_trade_id,
        order_id=order_id,
        instrument_id="rb2601",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        price=Decimal("3500"),
        quantity=Decimal("1"),
        trade_time=datetime.now(UTC),
        source_exchange_report_id="report-1",
    )


def _position_event(trade: Trade) -> PositionEvent:
    before = PositionSnapshot.from_position(
        Position(id="1", account_id=trade.account_id, instrument_id=trade.instrument_id)
    )
    after = PositionSnapshot.from_position(
        Position(
            id="1",
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
            long_today_qty=trade.quantity,
            long_avg_price=trade.price,
            version=1,
        )
    )
    return PositionEvent(
        account_id=trade.account_id,
        instrument_id=trade.instrument_id,
        exchange=trade.exchange,
        exchange_trade_id=trade.exchange_trade_id,
        trade_id=trade.id or "1",
        position_id="1",
        event_type="TRADE_APPLIED",
        direction=trade.direction,
        offset=trade.offset,
        price=trade.price,
        quantity=trade.quantity,
        before_snapshot=before,
        after_snapshot=after,
        occurred_at=trade.trade_time,
        created_at=datetime.now(UTC),
    )


def _margin_snapshot() -> MarginSnapshot:
    return MarginSnapshot(
        account_id="account-1",
        instrument_id="rb2601",
        position_version=1,
        rule_id="rule-1",
        rule_version="v1",
        calculation_key="account-1:rb2601:1:v1",
        long_qty=Decimal("1"),
        short_qty=Decimal("0"),
        price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        initial_margin=Decimal("3500"),
        maintenance_margin=Decimal("2000"),
        margin_used=Decimal("3500"),
        available_cash=Decimal("10000"),
        equity=Decimal("20000"),
        calculated_at=datetime.now(UTC),
    )


def _pnl_snapshot() -> PnLSnapshot:
    return PnLSnapshot(
        account_id="account-1",
        instrument_id="rb2601",
        position_version=1,
        trade_id="trade-1",
        margin_snapshot_id="margin-1",
        calculation_key="account-1:rb2601:1:pnl",
        price_basis=PnLPriceBasis.MANUAL,
        mark_price=Decimal("3500"),
        contract_multiplier=Decimal("10"),
        realized_pnl=Decimal("100"),
        unrealized_pnl=Decimal("50"),
        total_pnl=Decimal("150"),
        fee_amount=Decimal("2"),
        calculated_at=datetime.now(UTC),
    )


def _account_snapshot(snapshot_id: str | None = "1") -> AccountSnapshot:
    return AccountSnapshot(
        id=snapshot_id,
        account_id="account-1",
        equity=Decimal("10150"),
        available_cash=Decimal("6650"),
        margin_used=Decimal("3500"),
        frozen_margin=Decimal("0"),
        realized_pnl=Decimal("100"),
        unrealized_pnl=Decimal("50"),
        snapshot_time=datetime.now(UTC),
    )


def _settlement_snapshot() -> SettlementSnapshot:
    return SettlementSnapshot(
        account_id="account-1",
        trading_day=date(2026, 6, 4),
        calculation_key="account-1:2026-06-04:settlement",
        positions_before=(
            {
                "account_id": "account-1",
                "instrument_id": "rb2601",
                "long_today_qty": "1",
                "long_yesterday_qty": "0",
                "short_today_qty": "0",
                "short_yesterday_qty": "0",
                "version": 1,
            },
        ),
        positions_after=(
            {
                "account_id": "account-1",
                "instrument_id": "rb2601",
                "long_today_qty": "0",
                "long_yesterday_qty": "1",
                "short_today_qty": "0",
                "short_yesterday_qty": "0",
                "version": 2,
            },
        ),
        settlement_prices=({"instrument_id": "rb2601", "price": "3500"},),
        pnl_snapshot_ids=("1",),
        margin_snapshot_ids=("1",),
        account_snapshot_before_id="1",
        account_snapshot_after_id="2",
        cash_before=Decimal("10000"),
        cash_after=Decimal("10100"),
        realized_pnl=Decimal("100"),
        unrealized_pnl=Decimal("50"),
        margin_used=Decimal("3500"),
        status=SettlementResultStatus.SETTLED,
        created_at=datetime.now(UTC),
    )


def _tick() -> Tick:
    return Tick(
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
        source="adapter",
    )


def _bar() -> Bar:
    return Bar(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=BarTimeframe.M1,
        bar_ts=datetime(2026, 6, 7, 9, tzinfo=UTC),
        open=Decimal("500"),
        high=Decimal("501"),
        low=Decimal("499"),
        close=Decimal("500"),
        volume=Decimal("1"),
        turnover=Decimal("500"),
        open_interest=Decimal("10"),
        source="adapter",
        quality_status=MarketDataResultStatus.ACCEPTED,
    )


class FakeOrderRepository:
    def __init__(self) -> None:
        self.orders: dict[str, OrderState] = {}

    def create_order(self, order_request: OrderRequest, *, client_order_id: str) -> OrderState:
        order = OrderState(order_id=str(len(self.orders) + 1), request=order_request)
        self.orders[client_order_id] = order
        return order

    def get_by_id(self, order_id: str) -> OrderState | None:
        return next((order for order in self.orders.values() if order.order_id == order_id), None)

    def get_by_client_order_id(self, client_order_id: str) -> OrderState | None:
        return self.orders.get(client_order_id)

    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        *,
        expected_version: int | None = None,
    ) -> OrderState:
        del expected_version
        current = self.get_by_id(order_id)
        if current is None:
            raise KeyError(order_id)
        updated = current.model_copy(update={"status": new_status})
        self.orders[current.request.client_order_id] = updated
        return updated

    def list_open_orders(self) -> list[OrderState]:
        return list(self.orders.values())


class FakeOrderEventRepository:
    def __init__(self) -> None:
        self.events: list[OrderEvent] = []

    def append_event(self, event: OrderEvent) -> OrderEvent:
        self.events.append(event)
        return event

    def get_by_event_key(
        self,
        event_source: EventSource,
        external_event_id: str,
    ) -> OrderEvent | None:
        return next(
            (
                event
                for event in self.events
                if event.event_source == event_source
                and event.external_event_id == external_event_id
            ),
            None,
        )

    def list_by_order_id(self, order_id: str) -> list[OrderEvent]:
        return [event for event in self.events if event.order_id == order_id]


class FakeTradeRepository:
    def __init__(self) -> None:
        self.trades: dict[tuple[str, str, str], Trade] = {}

    def create_or_get_trade(self, trade: Trade) -> Trade:
        key = (trade.account_id, trade.exchange, trade.exchange_trade_id)
        self.trades.setdefault(key, trade)
        return self.trades[key]

    def get_by_exchange_trade_id(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> Trade | None:
        return self.trades.get((account_id, exchange, exchange_trade_id))


class FakePositionRepository:
    def __init__(self) -> None:
        self.positions: dict[tuple[str, str], Position] = {}

    def get_by_account_instrument(self, account_id: str, instrument_id: str) -> Position | None:
        return self.positions.get((account_id, instrument_id))

    def create_or_get_position(self, account_id: str, instrument_id: str) -> Position:
        return self.positions.setdefault(
            (account_id, instrument_id),
            Position(id="1", account_id=account_id, instrument_id=instrument_id),
        )

    def update_position(
        self,
        position: Position,
        *,
        expected_version: int | None = None,
    ) -> Position:
        del expected_version
        self.positions[(position.account_id, position.instrument_id)] = position
        return position

    def update_margin_used(
        self,
        account_id: str,
        instrument_id: str,
        margin_used: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position:
        del expected_version
        current = self.positions.get((account_id, instrument_id))
        if current is None:
            current = Position(id="1", account_id=account_id, instrument_id=instrument_id)
        updated = current.model_copy(update={"margin_used": margin_used})
        self.positions[(account_id, instrument_id)] = updated
        return updated

    def update_pnl(
        self,
        account_id: str,
        instrument_id: str,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal,
        *,
        expected_version: int | None = None,
    ) -> Position:
        del expected_version
        current = self.positions.get((account_id, instrument_id))
        if current is None:
            current = Position(id="1", account_id=account_id, instrument_id=instrument_id)
        updated = current.model_copy(
            update={"realized_pnl": realized_pnl, "unrealized_pnl": unrealized_pnl}
        )
        self.positions[(account_id, instrument_id)] = updated
        return updated

    def roll_today_to_yesterday_for_settlement(
        self,
        account_id: str,
        instrument_id: str,
        *,
        expected_version: int,
    ) -> Position:
        current = self.positions[(account_id, instrument_id)]
        assert current.version == expected_version
        updated = current.model_copy(
            update={
                "long_yesterday_qty": current.long_yesterday_qty + current.long_today_qty,
                "short_yesterday_qty": current.short_yesterday_qty + current.short_today_qty,
                "long_today_qty": Decimal("0"),
                "short_today_qty": Decimal("0"),
                "version": current.version + 1,
            }
        )
        self.positions[(account_id, instrument_id)] = updated
        return updated

    def list_by_account(self, account_id: str) -> list[Position]:
        return [
            position
            for position in self.positions.values()
            if position.account_id == account_id
        ]


class FakePositionEventRepository:
    def __init__(self) -> None:
        self.events: dict[tuple[str, str, str], PositionEvent] = {}

    def append_position_event(self, event: PositionEvent) -> PositionEvent:
        self.events[(event.account_id, event.exchange, event.exchange_trade_id)] = event
        return event

    def get_by_trade_key(
        self,
        account_id: str,
        exchange: str,
        exchange_trade_id: str,
    ) -> PositionEvent | None:
        return self.events.get((account_id, exchange, exchange_trade_id))

    def list_by_position(self, account_id: str, instrument_id: str) -> list[PositionEvent]:
        return [
            event
            for event in self.events.values()
            if event.account_id == account_id and event.instrument_id == instrument_id
        ]

    def list_by_account(self, account_id: str) -> list[PositionEvent]:
        return [event for event in self.events.values() if event.account_id == account_id]


class FakeMarginSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: dict[tuple[str, str, int], MarginSnapshot] = {}

    def append_margin_snapshot(self, snapshot: MarginSnapshot) -> MarginSnapshot:
        self.snapshots[
            (snapshot.account_id, snapshot.instrument_id, snapshot.position_version)
        ] = snapshot
        return snapshot

    def get_latest(self, account_id: str, instrument_id: str) -> MarginSnapshot | None:
        matches = [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.account_id == account_id and snapshot.instrument_id == instrument_id
        ]
        return matches[-1] if matches else None

    def list_by_account(self, account_id: str) -> list[MarginSnapshot]:
        return [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.account_id == account_id
        ]

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> MarginSnapshot | None:
        return self.snapshots.get((account_id, instrument_id, position_version))


class FakePnLSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: dict[tuple[str, str, str], PnLSnapshot] = {}

    def append_pnl_snapshot(self, snapshot: PnLSnapshot) -> PnLSnapshot:
        self.snapshots[
            (snapshot.account_id, snapshot.instrument_id, snapshot.calculation_key)
        ] = snapshot
        return snapshot

    def get_latest(self, account_id: str, instrument_id: str) -> PnLSnapshot | None:
        matches = [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.account_id == account_id and snapshot.instrument_id == instrument_id
        ]
        return matches[-1] if matches else None

    def list_by_account(self, account_id: str) -> list[PnLSnapshot]:
        return [
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.account_id == account_id
        ]

    def get_by_calculation_key(
        self,
        account_id: str,
        instrument_id: str,
        calculation_key: str,
    ) -> PnLSnapshot | None:
        return self.snapshots.get((account_id, instrument_id, calculation_key))

    def get_by_position_version(
        self,
        account_id: str,
        instrument_id: str,
        position_version: int,
    ) -> PnLSnapshot | None:
        return next(
            (
                snapshot
                for snapshot in self.snapshots.values()
                if snapshot.account_id == account_id
                and snapshot.instrument_id == instrument_id
                and snapshot.position_version == position_version
            ),
            None,
        )


class FakeAccountSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: dict[str, AccountSnapshot] = {}

    def append_account_snapshot(self, snapshot: AccountSnapshot) -> AccountSnapshot:
        snapshot_id = snapshot.id or str(len(self.snapshots) + 1)
        saved = snapshot.model_copy(update={"id": snapshot_id})
        self.snapshots[snapshot_id] = saved
        return saved

    def get_by_id(self, snapshot_id: str) -> AccountSnapshot | None:
        return self.snapshots.get(snapshot_id)

    def get_latest(self, account_id: str) -> AccountSnapshot | None:
        matches = [
            snapshot for snapshot in self.snapshots.values() if snapshot.account_id == account_id
        ]
        return matches[-1] if matches else None

    def list_by_account(self, account_id: str) -> list[AccountSnapshot]:
        return [
            snapshot for snapshot in self.snapshots.values() if snapshot.account_id == account_id
        ]


class FakeSettlementSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: dict[tuple[str, date], SettlementSnapshot] = {}

    def append_settlement_snapshot(self, snapshot: SettlementSnapshot) -> SettlementSnapshot:
        self.snapshots[(snapshot.account_id, snapshot.trading_day)] = snapshot
        return snapshot

    def get_by_account_trading_day(
        self,
        account_id: str,
        trading_day: date,
    ) -> SettlementSnapshot | None:
        return self.snapshots.get((account_id, trading_day))

    def get_by_calculation_key(
        self,
        account_id: str,
        trading_day: date,
        calculation_key: str,
    ) -> SettlementSnapshot | None:
        snapshot = self.snapshots.get((account_id, trading_day))
        if snapshot and snapshot.calculation_key == calculation_key:
            return snapshot
        return None

    def list_by_account(self, account_id: str) -> list[SettlementSnapshot]:
        return [
            snapshot for snapshot in self.snapshots.values() if snapshot.account_id == account_id
        ]

    def list_by_trading_day(self, trading_day: date) -> list[SettlementSnapshot]:
        return [
            snapshot for snapshot in self.snapshots.values() if snapshot.trading_day == trading_day
        ]


class FakeMarketTickRepository:
    def __init__(self) -> None:
        self.ticks: dict[tuple[str, str, datetime, str], Tick] = {}

    def append_tick(self, tick: Tick) -> Tick:
        self.ticks[(tick.exchange, tick.instrument_id, tick.ts, tick.source)] = tick
        return tick

    def get_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        ts: datetime,
        source: str,
    ) -> Tick | None:
        return self.ticks.get((exchange, instrument_id, ts, source))

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[Tick]:
        return [
            tick
            for tick in self.ticks.values()
            if tick.exchange == exchange
            and tick.instrument_id == instrument_id
            and start_ts <= tick.ts <= end_ts
        ]

    def list_by_trading_day(
        self,
        exchange: str,
        instrument_id: str,
        trading_day: date,
    ) -> list[Tick]:
        return [
            tick
            for tick in self.ticks.values()
            if tick.exchange == exchange
            and tick.instrument_id == instrument_id
            and tick.trading_day == trading_day
        ]


class FakeMarketBarRepository:
    def __init__(self) -> None:
        self.bars: dict[tuple[str, str, BarTimeframe, datetime, str], Bar] = {}

    def append_bar(self, bar: Bar) -> Bar:
        self.bars[(bar.exchange, bar.instrument_id, bar.timeframe, bar.bar_ts, bar.source)] = bar
        return bar

    def get_by_identity(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        bar_ts: datetime,
        source: str,
    ) -> Bar | None:
        return self.bars.get((exchange, instrument_id, timeframe, bar_ts, source))

    def list_by_instrument(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        start_bar_ts: datetime,
        end_bar_ts: datetime,
    ) -> list[Bar]:
        return [
            bar
            for bar in self.bars.values()
            if bar.exchange == exchange
            and bar.instrument_id == instrument_id
            and bar.timeframe == timeframe
            and start_bar_ts <= bar.bar_ts <= end_bar_ts
        ]

    def list_by_trading_day(
        self,
        exchange: str,
        instrument_id: str,
        timeframe: BarTimeframe,
        trading_day: date,
    ) -> list[Bar]:
        return [
            bar
            for bar in self.bars.values()
            if bar.exchange == exchange
            and bar.instrument_id == instrument_id
            and bar.timeframe == timeframe
            and bar.trading_day == trading_day
        ]


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.orders = FakeOrderRepository()
        self.order_events = FakeOrderEventRepository()
        self.trades = FakeTradeRepository()
        self.positions = FakePositionRepository()
        self.position_events = FakePositionEventRepository()
        self.margin_snapshots = FakeMarginSnapshotRepository()
        self.pnl_snapshots = FakePnLSnapshotRepository()
        self.account_snapshots = FakeAccountSnapshotRepository()
        self.settlement_snapshots = FakeSettlementSnapshotRepository()
        self.market_ticks = FakeMarketTickRepository()
        self.market_bars = FakeMarketBarRepository()
        self.commit_count = 0
        self.rollback_count = 0

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool | None:
        del exc_type, exc, tb
        return None


class FakeMarketDataUnitOfWork:
    def __init__(self) -> None:
        self.market_ticks = FakeMarketTickRepository()
        self.market_bars = FakeMarketBarRepository()
        self.commit_count = 0
        self.rollback_count = 0

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def __enter__(self) -> "FakeMarketDataUnitOfWork":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool | None:
        del exc_type, exc, tb
        return None


def test_repository_protocols_can_be_implemented_by_fakes() -> None:
    order_repo = FakeOrderRepository()
    event_repo = FakeOrderEventRepository()
    trade_repo = FakeTradeRepository()
    position_repo = FakePositionRepository()
    position_event_repo = FakePositionEventRepository()
    margin_snapshot_repo = FakeMarginSnapshotRepository()
    pnl_snapshot_repo = FakePnLSnapshotRepository()
    account_snapshot_repo = FakeAccountSnapshotRepository()
    settlement_snapshot_repo = FakeSettlementSnapshotRepository()
    market_tick_repo = FakeMarketTickRepository()
    market_bar_repo = FakeMarketBarRepository()

    assert isinstance(order_repo, OrderRepository)
    assert isinstance(event_repo, OrderEventRepository)
    assert isinstance(trade_repo, TradeRepository)
    assert isinstance(position_repo, PositionRepository)
    assert isinstance(position_event_repo, PositionEventRepository)
    assert isinstance(margin_snapshot_repo, MarginSnapshotRepository)
    assert isinstance(pnl_snapshot_repo, PnLSnapshotRepository)
    assert isinstance(account_snapshot_repo, AccountSnapshotRepository)
    assert isinstance(settlement_snapshot_repo, SettlementSnapshotRepository)
    assert isinstance(market_tick_repo, MarketTickRepository)
    assert isinstance(market_bar_repo, MarketBarRepository)

    order = order_repo.create_order(_order_request(), client_order_id="client-1")
    event = event_repo.append_event(_order_event(order.order_id))
    trade = trade_repo.create_or_get_trade(_trade(order.order_id))
    position = position_repo.create_or_get_position("account-1", "rb2601")
    position_event = position_event_repo.append_position_event(_position_event(trade))
    margin_snapshot = margin_snapshot_repo.append_margin_snapshot(_margin_snapshot())
    pnl_snapshot = pnl_snapshot_repo.append_pnl_snapshot(_pnl_snapshot())
    account_snapshot = account_snapshot_repo.append_account_snapshot(_account_snapshot())
    settlement_snapshot = settlement_snapshot_repo.append_settlement_snapshot(
        _settlement_snapshot()
    )
    tick = market_tick_repo.append_tick(_tick())
    bar = market_bar_repo.append_bar(_bar())

    assert order_repo.get_by_id(order.order_id) == order
    assert order_repo.get_by_client_order_id("client-1") == order
    assert event_repo.get_by_event_key(EventSource.OMS, event.external_event_id) == event
    assert event_repo.list_by_order_id(order.order_id) == [event]
    assert trade_repo.get_by_exchange_trade_id("account-1", "SHFE", "trade-1") == trade
    assert position_repo.get_by_account_instrument("account-1", "rb2601") == position
    assert position_event_repo.get_by_trade_key("account-1", "SHFE", "trade-1") == position_event
    assert margin_snapshot_repo.get_latest("account-1", "rb2601") == margin_snapshot
    assert margin_snapshot_repo.get_by_position_version("account-1", "rb2601", 1) == margin_snapshot
    assert pnl_snapshot_repo.get_latest("account-1", "rb2601") == pnl_snapshot
    assert (
        pnl_snapshot_repo.get_by_calculation_key("account-1", "rb2601", "account-1:rb2601:1:pnl")
        == pnl_snapshot
    )
    assert account_snapshot_repo.get_latest("account-1") == account_snapshot
    assert account_snapshot_repo.get_by_id("1") == account_snapshot
    assert (
        settlement_snapshot_repo.get_by_account_trading_day("account-1", date(2026, 6, 4))
        == settlement_snapshot
    )
    assert (
        settlement_snapshot_repo.get_by_calculation_key(
            "account-1",
            date(2026, 6, 4),
            "account-1:2026-06-04:settlement",
        )
        == settlement_snapshot
    )
    assert market_tick_repo.get_by_identity("SHFE", "au2606", tick.ts, "adapter") == tick
    assert (
        market_bar_repo.get_by_identity(
            "SHFE",
            "au2606",
            BarTimeframe.M1,
            bar.bar_ts,
            "adapter",
        )
        == bar
    )


def test_unit_of_work_protocol_supports_commit_and_rollback() -> None:
    uow = FakeUnitOfWork()

    assert isinstance(uow, UnitOfWork)

    with uow as current:
        assert current is uow
        current.commit()
        current.rollback()

    assert uow.commit_count == 1
    assert uow.rollback_count == 1


def test_market_data_unit_of_work_protocol_is_narrow() -> None:
    uow = FakeMarketDataUnitOfWork()

    assert isinstance(uow, MarketDataUnitOfWork)
    assert not hasattr(uow, "orders")
    assert not hasattr(uow, "trades")
    assert not hasattr(uow, "positions")
    assert not hasattr(uow, "margin_snapshots")
    assert not hasattr(uow, "pnl_snapshots")
    assert not hasattr(uow, "settlement_snapshots")

    with uow as current:
        current.market_ticks.append_tick(_tick())
        current.market_bars.append_bar(_bar())
        current.commit()

    assert uow.commit_count == 1


def test_interfaces_repository_module_does_not_import_sqlalchemy_or_oms_state_machine() -> None:
    source = Path("src/futures_mvp/interfaces/repositories.py").read_text()

    assert "sqlalchemy" not in source.lower()
    assert "futures_mvp.modules.oms" not in source
    assert "state_machine" not in source


def test_order_repository_contract_does_not_expose_state_transition_functions() -> None:
    forbidden = {
        "can_transition",
        "validate_transition",
        "is_terminal",
        "is_recoverable",
        "should_enter_unknown",
    }

    assert forbidden.isdisjoint(dir(OrderRepository))


def test_order_event_repository_contract_does_not_expose_unknown_or_ordering_handlers() -> None:
    forbidden = {
        "handle_out_of_order",
        "resolve_previous_status_mismatch",
        "enter_unknown",
        "should_enter_unknown",
        "interpret_raw_payload",
    }

    assert forbidden.isdisjoint(dir(OrderEventRepository))


def test_repository_methods_do_not_auto_commit_unit_of_work() -> None:
    uow = FakeUnitOfWork()

    order = uow.orders.create_order(_order_request(), client_order_id="client-1")
    uow.orders.update_status(order.order_id, OrderStatus.RISK_CHECKING)
    uow.order_events.append_event(_order_event(order.order_id))
    uow.trades.create_or_get_trade(_trade(order.order_id))

    assert uow.commit_count == 0
    assert uow.rollback_count == 0
