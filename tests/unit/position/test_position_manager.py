from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import TracebackType

from futures_mvp.domain.enums import Direction, Offset, PositionManagerResultStatus
from futures_mvp.domain.models import Position, PositionEvent, Trade
from futures_mvp.modules.position import PositionManager


def _trade(
    *,
    trade_id: str | None = "1",
    exchange_trade_id: str = "trade-1",
    direction: Direction = Direction.BUY,
    offset: Offset = Offset.OPEN,
    price: Decimal = Decimal("3500"),
    quantity: Decimal = Decimal("1"),
    trade_time: datetime | None = None,
) -> Trade:
    return Trade(
        id=trade_id,
        account_id="account-1",
        exchange="SHFE",
        exchange_trade_id=exchange_trade_id,
        order_id="1",
        instrument_id="rb2601",
        direction=direction,
        offset=offset,
        price=price,
        quantity=quantity,
        trade_time=trade_time or datetime(2026, 1, 1, 9, 1, tzinfo=UTC),
        source_exchange_report_id="report-1",
        raw_payload={"diagnostic": True},
    )


class FakePositionRepository:
    def __init__(self, positions: dict[tuple[str, str], Position]) -> None:
        self.positions = positions

    def get_by_account_instrument(self, account_id: str, instrument_id: str) -> Position | None:
        return self.positions.get((account_id, instrument_id))

    def create_or_get_position(self, account_id: str, instrument_id: str) -> Position:
        key = (account_id, instrument_id)
        if key not in self.positions:
            self.positions[key] = Position(
                id=str(len(self.positions) + 1),
                account_id=account_id,
                instrument_id=instrument_id,
            )
        return self.positions[key]

    def update_position(
        self,
        position: Position,
        *,
        expected_version: int | None = None,
    ) -> Position:
        key = (position.account_id, position.instrument_id)
        current = self.positions[key]
        if expected_version is not None and current.version != expected_version:
            raise RuntimeError("version mismatch")
        updated = position.model_copy(update={"version": current.version + 1})
        self.positions[key] = updated
        return updated

    def list_by_account(self, account_id: str) -> list[Position]:
        return [
            position
            for position in self.positions.values()
            if position.account_id == account_id
        ]


class FakePositionEventRepository:
    def __init__(self, events: dict[tuple[str, str, str], PositionEvent]) -> None:
        self.events = events

    def append_position_event(self, event: PositionEvent) -> PositionEvent:
        stored = event.model_copy(update={"id": str(len(self.events) + 1)})
        self.events[(event.account_id, event.exchange, event.exchange_trade_id)] = stored
        return stored

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


class FakeUoW:
    def __init__(
        self,
        positions: dict[tuple[str, str], Position],
        events: dict[tuple[str, str, str], PositionEvent],
    ) -> None:
        self.positions = FakePositionRepository(positions)
        self.position_events = FakePositionEventRepository(events)
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeUoW:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        del exc_type, exc, tb
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _manager(
    positions: dict[tuple[str, str], Position] | None = None,
    events: dict[tuple[str, str, str], PositionEvent] | None = None,
) -> tuple[
    PositionManager,
    dict[tuple[str, str], Position],
    dict[tuple[str, str, str], PositionEvent],
]:
    position_store = positions or {}
    event_store = events or {}
    return (
        PositionManager(lambda: FakeUoW(position_store, event_store)),
        position_store,
        event_store,
    )


def test_open_long_updates_long_today_and_weighted_average() -> None:
    manager, positions, events = _manager()

    first = manager.apply_trade(_trade(price=Decimal("3500"), quantity=Decimal("1")))
    second = manager.apply_trade(
        _trade(
            trade_id="2",
            exchange_trade_id="trade-2",
            price=Decimal("3700"),
            quantity=Decimal("3"),
        )
    )

    position = positions[("account-1", "rb2601")]
    assert first.status == PositionManagerResultStatus.APPLIED
    assert second.status == PositionManagerResultStatus.APPLIED
    assert position.long_today_qty == Decimal("4")
    assert position.long_avg_price == Decimal("3650")
    assert len(events) == 2


def test_open_long_average_includes_yesterday_quantity() -> None:
    initial = Position(
        id="1",
        account_id="account-1",
        instrument_id="rb2601",
        long_yesterday_qty=Decimal("2"),
        long_avg_price=Decimal("3500"),
    )
    manager, positions, _events = _manager({("account-1", "rb2601"): initial})

    result = manager.apply_trade(
        _trade(price=Decimal("3800"), quantity=Decimal("1"))
    )

    position = positions[("account-1", "rb2601")]
    assert result.status == PositionManagerResultStatus.APPLIED
    assert position.long_today_qty == Decimal("1")
    assert position.long_yesterday_qty == Decimal("2")
    assert position.long_avg_price == Decimal("3600")


def test_open_short_updates_short_today_and_weighted_average() -> None:
    manager, positions, _events = _manager()

    result = manager.apply_trade(
        _trade(direction=Direction.SELL, offset=Offset.OPEN, price=Decimal("3510"))
    )

    position = positions[("account-1", "rb2601")]
    assert result.status == PositionManagerResultStatus.APPLIED
    assert position.short_today_qty == Decimal("1")
    assert position.short_avg_price == Decimal("3510")


def test_open_short_average_includes_yesterday_quantity() -> None:
    initial = Position(
        id="1",
        account_id="account-1",
        instrument_id="rb2601",
        short_yesterday_qty=Decimal("3"),
        short_avg_price=Decimal("3600"),
    )
    manager, positions, _events = _manager({("account-1", "rb2601"): initial})

    result = manager.apply_trade(
        _trade(
            direction=Direction.SELL,
            offset=Offset.OPEN,
            price=Decimal("3200"),
            quantity=Decimal("1"),
        )
    )

    position = positions[("account-1", "rb2601")]
    assert result.status == PositionManagerResultStatus.APPLIED
    assert position.short_today_qty == Decimal("1")
    assert position.short_yesterday_qty == Decimal("3")
    assert position.short_avg_price == Decimal("3500")


def test_close_today_long_deducts_long_today_without_changing_avg_or_pnl() -> None:
    initial = Position(
        id="1",
        account_id="account-1",
        instrument_id="rb2601",
        long_today_qty=Decimal("3"),
        long_avg_price=Decimal("3500"),
        realized_pnl=Decimal("12"),
        unrealized_pnl=Decimal("34"),
        margin_used=Decimal("56"),
    )
    manager, positions, _events = _manager({("account-1", "rb2601"): initial})

    result = manager.apply_trade(
        _trade(direction=Direction.SELL, offset=Offset.CLOSE_TODAY, quantity=Decimal("1"))
    )

    position = positions[("account-1", "rb2601")]
    assert result.status == PositionManagerResultStatus.APPLIED
    assert position.long_today_qty == Decimal("2")
    assert position.long_avg_price == Decimal("3500")
    assert position.realized_pnl == Decimal("12")
    assert position.unrealized_pnl == Decimal("34")
    assert position.margin_used == Decimal("56")


def test_close_yesterday_long_deducts_long_yesterday() -> None:
    manager, positions, _events = _manager(
        {
            ("account-1", "rb2601"): Position(
                id="1",
                account_id="account-1",
                instrument_id="rb2601",
                long_yesterday_qty=Decimal("2"),
                long_avg_price=Decimal("3500"),
            )
        }
    )

    result = manager.apply_trade(
        _trade(direction=Direction.SELL, offset=Offset.CLOSE_YESTERDAY, quantity=Decimal("1"))
    )

    assert result.status == PositionManagerResultStatus.APPLIED
    assert positions[("account-1", "rb2601")].long_yesterday_qty == Decimal("1")
    assert positions[("account-1", "rb2601")].long_avg_price == Decimal("3500")


def test_close_today_short_deducts_short_today() -> None:
    manager, positions, _events = _manager(
        {
            ("account-1", "rb2601"): Position(
                id="1",
                account_id="account-1",
                instrument_id="rb2601",
                short_today_qty=Decimal("2"),
            )
        }
    )

    result = manager.apply_trade(
        _trade(direction=Direction.BUY, offset=Offset.CLOSE_TODAY, quantity=Decimal("1"))
    )

    assert result.status == PositionManagerResultStatus.APPLIED
    assert positions[("account-1", "rb2601")].short_today_qty == Decimal("1")


def test_close_yesterday_short_deducts_short_yesterday() -> None:
    manager, positions, _events = _manager(
        {
            ("account-1", "rb2601"): Position(
                id="1",
                account_id="account-1",
                instrument_id="rb2601",
                short_yesterday_qty=Decimal("2"),
            )
        }
    )

    result = manager.apply_trade(
        _trade(direction=Direction.BUY, offset=Offset.CLOSE_YESTERDAY, quantity=Decimal("1"))
    )

    assert result.status == PositionManagerResultStatus.APPLIED
    assert positions[("account-1", "rb2601")].short_yesterday_qty == Decimal("1")


def test_partial_close_only_deducts_trade_quantity() -> None:
    manager, positions, _events = _manager(
        {
            ("account-1", "rb2601"): Position(
                id="1",
                account_id="account-1",
                instrument_id="rb2601",
                long_today_qty=Decimal("5"),
            )
        }
    )

    result = manager.apply_trade(
        _trade(direction=Direction.SELL, offset=Offset.CLOSE_TODAY, quantity=Decimal("2"))
    )

    assert result.status == PositionManagerResultStatus.APPLIED
    assert positions[("account-1", "rb2601")].long_today_qty == Decimal("3")


def test_insufficient_today_bucket_rejects_without_event() -> None:
    manager, positions, events = _manager(
        {
            ("account-1", "rb2601"): Position(
                id="1",
                account_id="account-1",
                instrument_id="rb2601",
                long_today_qty=Decimal("1"),
            )
        }
    )

    result = manager.apply_trade(
        _trade(direction=Direction.SELL, offset=Offset.CLOSE_TODAY, quantity=Decimal("2"))
    )

    assert result.status == PositionManagerResultStatus.REJECTED_INSUFFICIENT_POSITION
    position = positions[("account-1", "rb2601")]
    assert position.long_today_qty == Decimal("1")
    assert position.version == 0
    assert events == {}


def test_insufficient_close_without_position_does_not_create_position_or_event() -> None:
    manager, positions, events = _manager()

    result = manager.apply_trade(
        _trade(direction=Direction.SELL, offset=Offset.CLOSE_TODAY, quantity=Decimal("1"))
    )

    assert result.status == PositionManagerResultStatus.REJECTED_INSUFFICIENT_POSITION
    assert positions == {}
    assert events == {}


def test_insufficient_yesterday_bucket_rejects_without_event() -> None:
    manager, positions, events = _manager(
        {
            ("account-1", "rb2601"): Position(
                id="1",
                account_id="account-1",
                instrument_id="rb2601",
                short_yesterday_qty=Decimal("1"),
            )
        }
    )

    result = manager.apply_trade(
        _trade(direction=Direction.BUY, offset=Offset.CLOSE_YESTERDAY, quantity=Decimal("2"))
    )

    assert result.status == PositionManagerResultStatus.REJECTED_INSUFFICIENT_POSITION
    assert positions[("account-1", "rb2601")].short_yesterday_qty == Decimal("1")
    assert events == {}


def test_close_rejects_when_frozen_quantity_would_be_consumed() -> None:
    manager, positions, events = _manager(
        {
            ("account-1", "rb2601"): Position(
                id="1",
                account_id="account-1",
                instrument_id="rb2601",
                long_today_qty=Decimal("3"),
                frozen_long_qty=Decimal("2"),
            )
        }
    )

    result = manager.apply_trade(
        _trade(direction=Direction.SELL, offset=Offset.CLOSE_TODAY, quantity=Decimal("2"))
    )

    assert result.status == PositionManagerResultStatus.REJECTED_INSUFFICIENT_POSITION
    assert result.reason == "insufficient unfrozen position: 3 - 2 < 2"
    assert positions[("account-1", "rb2601")].long_today_qty == Decimal("3")
    assert positions[("account-1", "rb2601")].frozen_long_qty == Decimal("2")
    assert events == {}


def test_unsupported_offset_returns_error() -> None:
    manager, _positions, events = _manager()

    result = manager.apply_trade(_trade(offset=Offset.CLOSE))

    assert result.status == PositionManagerResultStatus.ERROR
    assert events == {}


def test_duplicate_trade_is_no_op() -> None:
    manager, positions, events = _manager()
    trade = _trade()

    first = manager.apply_trade(trade)
    second = manager.apply_trade(trade)

    assert first.status == PositionManagerResultStatus.APPLIED
    assert second.status == PositionManagerResultStatus.DUPLICATE_IGNORED
    assert positions[("account-1", "rb2601")].long_today_qty == Decimal("1")
    assert len(events) == 1


def test_duplicate_trade_conflict_is_typed_conflict() -> None:
    manager, _positions, _events = _manager()
    trade = _trade()

    manager.apply_trade(trade)
    conflict = manager.apply_trade(trade.model_copy(update={"quantity": Decimal("2")}))

    assert conflict.status == PositionManagerResultStatus.CONFLICT


def test_trade_preflight_rejects_before_position_mutation() -> None:
    manager, positions, events = _manager()

    result = manager.apply_trade(_trade(trade_id=None))

    assert result.status == PositionManagerResultStatus.ERROR
    assert result.reason == "id is required to apply position"
    assert positions == {}
    assert events == {}


def test_trade_preflight_rejects_non_positive_price() -> None:
    manager, positions, events = _manager()

    result = manager.apply_trade(_trade(price=Decimal("0")))

    assert result.status == PositionManagerResultStatus.ERROR
    assert result.reason == "trade.price must be positive to apply position"
    assert positions == {}
    assert events == {}


def test_duplicate_trade_detects_position_projection_divergence() -> None:
    manager, positions, events = _manager()
    trade = _trade()

    first = manager.apply_trade(trade)
    positions[("account-1", "rb2601")] = positions[("account-1", "rb2601")].model_copy(
        update={"long_today_qty": Decimal("2")}
    )
    replay = manager.replay_trades([trade])

    assert first.status == PositionManagerResultStatus.APPLIED
    assert replay.results[0].status == PositionManagerResultStatus.CONFLICT
    assert replay.results[0].reason == "position_projection_diverged_from_event_snapshot"
    assert replay.has_divergence
    assert len(events) == 1


def test_replay_trades_stops_on_conflict() -> None:
    manager, positions, events = _manager()
    first = _trade()
    after_conflict = _trade(
        trade_id="2",
        exchange_trade_id="trade-2",
        trade_time=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
    )

    manager.apply_trade(first)
    positions[("account-1", "rb2601")] = positions[("account-1", "rb2601")].model_copy(
        update={"long_today_qty": Decimal("2")}
    )

    replay = manager.replay_trades([first, after_conflict])

    assert [result.status for result in replay.results] == [
        PositionManagerResultStatus.CONFLICT,
    ]
    assert events.keys() == {("account-1", "SHFE", "trade-1")}
    assert positions[("account-1", "rb2601")].long_today_qty == Decimal("2")


def test_replay_trades_orders_by_trade_time_then_stable_key() -> None:
    manager, positions, _events = _manager()
    late = _trade(
        trade_id="2",
        exchange_trade_id="trade-2",
        trade_time=datetime(2026, 1, 1, 9, 2, tzinfo=UTC),
    )
    early = _trade(
        trade_id="1",
        exchange_trade_id="trade-1",
        trade_time=datetime(2026, 1, 1, 9, 1, tzinfo=UTC),
    )
    same_time = _trade(
        trade_id="3",
        exchange_trade_id="trade-0",
        price=Decimal("3800"),
        trade_time=datetime(2026, 1, 1, 9, 1, tzinfo=UTC),
    )

    result = manager.replay_trades([late, same_time, early])

    assert not result.has_divergence
    assert [item.status for item in result.results] == [
        PositionManagerResultStatus.APPLIED,
        PositionManagerResultStatus.APPLIED,
        PositionManagerResultStatus.APPLIED,
    ]
    assert positions[("account-1", "rb2601")].long_today_qty == Decimal("3")


def test_incremental_replay_duplicate_is_no_op() -> None:
    manager, positions, _events = _manager()
    trade = _trade()

    first = manager.replay_trades([trade])
    second = manager.replay_trades([trade])

    assert first.results[0].status == PositionManagerResultStatus.APPLIED
    assert second.results[0].status == PositionManagerResultStatus.DUPLICATE_IGNORED
    assert positions[("account-1", "rb2601")].long_today_qty == Decimal("1")


def test_position_manager_boundary_imports() -> None:
    source = Path("src/futures_mvp/modules/position/manager.py").read_text()

    forbidden = [
        "modules.oms",
        "modules.risk",
        "modules.execution",
        "broker",
        "FastAPI",
        "Kafka",
        "Redis",
        "Margin",
        "PnL",
        "Settlement",
        "OrderStatus",
        "OrderEvent",
        "ExchangeReport",
    ]
    for token in forbidden:
        assert token not in source
