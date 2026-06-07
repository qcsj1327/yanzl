from datetime import UTC, date, datetime
from decimal import Decimal
from types import TracebackType
from typing import get_type_hints

from futures_mvp.domain.enums import BarTimeframe, MarketDataResultStatus
from futures_mvp.domain.models import Bar, Tick
from futures_mvp.interfaces.repositories import MarketDataConflictError
from futures_mvp.modules.market import (
    DataQualityGate,
    DataQualityPolicy,
    MarketDataService,
    canonical_bar_payload,
    canonical_tick_payload,
    replay_market_facts,
)


def _tick(ts: datetime | None = None, *, price: Decimal = Decimal("500")) -> Tick:
    return Tick(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        ts=ts or datetime(2026, 6, 7, 9, tzinfo=UTC),
        price=price,
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


def _bar(
    bar_ts: datetime | None = None,
    *,
    high: Decimal = Decimal("505"),
) -> Bar:
    return Bar(
        symbol="au",
        instrument_id="au2606",
        trade_instrument_id="au2606",
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=BarTimeframe.M1,
        bar_ts=bar_ts or datetime(2026, 6, 7, 9, tzinfo=UTC),
        open=Decimal("500"),
        high=high,
        low=Decimal("499"),
        close=Decimal("501"),
        volume=Decimal("10"),
        turnover=Decimal("5000"),
        open_interest=Decimal("20"),
        source="adapter",
        quality_status=MarketDataResultStatus.ACCEPTED,
        raw_payload={"diagnostic": True},
    )


class FakeMarketTickRepository:
    def __init__(self) -> None:
        self.ticks: dict[tuple[str, str, datetime, str], Tick] = {}

    def append_tick(self, tick: Tick) -> Tick:
        key = (tick.exchange, tick.instrument_id, tick.ts, tick.source)
        existing = self.ticks.get(key)
        if existing is not None:
            if canonical_tick_payload(existing) != canonical_tick_payload(tick):
                raise MarketDataConflictError("tick conflict")
            return existing
        self.ticks[key] = tick
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
        key = (bar.exchange, bar.instrument_id, bar.timeframe, bar.bar_ts, bar.source)
        existing = self.bars.get(key)
        if existing is not None:
            if canonical_bar_payload(existing) != canonical_bar_payload(bar):
                raise MarketDataConflictError("bar conflict")
            return existing
        self.bars[key] = bar
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


class FakeUoW:
    def __init__(self) -> None:
        self.market_ticks = FakeMarketTickRepository()
        self.market_bars = FakeMarketBarRepository()
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def __enter__(self) -> "FakeUoW":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        del exc_type, exc, tb
        return None


def test_gate_rejects_missing_identity_bad_timestamp_and_out_of_session() -> None:
    gate = DataQualityGate()
    missing_identity = _tick().model_copy(update={"instrument_id": ""})
    missing_symbol = _tick().model_copy(update={"symbol": ""})
    missing_trade_instrument_id = _tick().model_copy(update={"trade_instrument_id": ""})
    missing_bar_symbol = _bar().model_copy(update={"symbol": ""})
    missing_bar_trade_instrument_id = _bar().model_copy(update={"trade_instrument_id": ""})
    bad_timestamp = _tick(datetime(2026, 6, 7, 9))

    assert (
        gate.validate_tick(missing_identity).status
        is MarketDataResultStatus.REJECTED_MISSING_IDENTITY
    )
    assert (
        gate.validate_tick(missing_symbol).status
        is MarketDataResultStatus.REJECTED_MISSING_IDENTITY
    )
    assert (
        gate.validate_tick(missing_trade_instrument_id).status
        is MarketDataResultStatus.REJECTED_MISSING_IDENTITY
    )
    assert (
        gate.validate_bar(missing_bar_symbol).status
        is MarketDataResultStatus.REJECTED_MISSING_IDENTITY
    )
    assert (
        gate.validate_bar(missing_bar_trade_instrument_id).status
        is MarketDataResultStatus.REJECTED_MISSING_IDENTITY
    )
    assert (
        gate.validate_tick(bad_timestamp).status
        is MarketDataResultStatus.REJECTED_BAD_TIMESTAMP
    )
    assert (
        gate.validate_tick(_tick(), in_session=False).status
        is MarketDataResultStatus.REJECTED_OUT_OF_SESSION
    )


def test_gate_rejects_bad_price_bad_ohlc_and_non_monotonic() -> None:
    gate = DataQualityGate()
    bad_tick = _tick().model_copy(update={"price": Decimal("0")})
    bad_bar = _bar().model_copy(update={"high": Decimal("499")})
    current = _tick(datetime(2026, 6, 7, 9, tzinfo=UTC))
    previous_ts = datetime(2026, 6, 7, 9, 1, tzinfo=UTC)

    assert gate.validate_tick(bad_tick).status is MarketDataResultStatus.REJECTED_BAD_PRICE
    assert gate.validate_bar(bad_bar).status is MarketDataResultStatus.REJECTED_BAD_PRICE
    assert (
        gate.validate_tick(current, previous_ts=previous_ts).status
        is MarketDataResultStatus.REJECTED_NON_MONOTONIC
    )


def test_gate_prioritizes_missing_identity_over_bad_price() -> None:
    gate = DataQualityGate()
    missing_symbol_bad_price = _tick().model_copy(
        update={"symbol": "", "price": Decimal("0")}
    )
    missing_trade_instrument_bad_price = _tick().model_copy(
        update={"trade_instrument_id": "", "price": Decimal("0")}
    )
    missing_bar_symbol_bad_price = _bar().model_copy(
        update={"symbol": "", "open": Decimal("0")}
    )
    missing_bar_trade_instrument_bad_price = _bar().model_copy(
        update={"trade_instrument_id": "", "open": Decimal("0")}
    )

    assert (
        gate.validate_tick(missing_symbol_bad_price).status
        is MarketDataResultStatus.REJECTED_MISSING_IDENTITY
    )
    assert (
        gate.validate_tick(missing_trade_instrument_bad_price).status
        is MarketDataResultStatus.REJECTED_MISSING_IDENTITY
    )
    assert (
        gate.validate_bar(missing_bar_symbol_bad_price).status
        is MarketDataResultStatus.REJECTED_MISSING_IDENTITY
    )
    assert (
        gate.validate_bar(missing_bar_trade_instrument_bad_price).status
        is MarketDataResultStatus.REJECTED_MISSING_IDENTITY
    )


def test_gap_policy_controls_persistence() -> None:
    uow = FakeUoW()
    service = MarketDataService(lambda: uow)  # type: ignore[arg-type]

    rejected = service.ingest_tick(_tick(), gap_detected=True)
    accepted = service.ingest_tick(
        _tick(datetime(2026, 6, 7, 9, 1, tzinfo=UTC)),
        policy=DataQualityPolicy(allow_gap=True),
        gap_detected=True,
    )

    assert rejected.result.status is MarketDataResultStatus.GAP_DETECTED
    assert rejected.tick is None
    assert accepted.result.status is MarketDataResultStatus.GAP_DETECTED
    assert accepted.tick is not None
    assert len(uow.market_ticks.ticks) == 1


def test_service_accepts_duplicates_and_conflicts() -> None:
    uow = FakeUoW()
    service = MarketDataService(lambda: uow)  # type: ignore[arg-type]
    tick = _tick()
    duplicate = tick.model_copy(update={"raw_payload": {"changed": True}})
    conflict = tick.model_copy(update={"price": Decimal("501")})

    first = service.ingest_tick(tick)
    second = service.ingest_tick(duplicate)
    third = service.ingest_tick(conflict)

    assert first.result.status is MarketDataResultStatus.ACCEPTED
    assert second.result.status is MarketDataResultStatus.DUPLICATE
    assert third.result.status is MarketDataResultStatus.ERROR
    assert third.result.reason == "canonical_conflict"
    assert len(uow.market_ticks.ticks) == 1


def test_service_rejected_result_does_not_persist() -> None:
    uow = FakeUoW()
    service = MarketDataService(lambda: uow)  # type: ignore[arg-type]

    result = service.ingest_bar(_bar(), in_session=False)

    assert result.result.status is MarketDataResultStatus.REJECTED_OUT_OF_SESSION
    assert len(uow.market_bars.bars) == 0


def test_replay_orders_market_facts_deterministically_and_noops_duplicates() -> None:
    uow = FakeUoW()
    service = MarketDataService(lambda: uow)  # type: ignore[arg-type]
    late = _tick(datetime(2026, 6, 7, 9, 2, tzinfo=UTC))
    early = _tick(datetime(2026, 6, 7, 9, 1, tzinfo=UTC))
    duplicate = early.model_copy(update={"raw_payload": {"changed": True}})

    first = replay_market_facts(service, [late, duplicate, early])
    second = replay_market_facts(service, [early, late])

    assert [result.result.status for result in first.results] == [
        MarketDataResultStatus.ACCEPTED,
        MarketDataResultStatus.DUPLICATE,
        MarketDataResultStatus.ACCEPTED,
    ]
    assert [result.result.status for result in second.results] == [
        MarketDataResultStatus.DUPLICATE,
        MarketDataResultStatus.DUPLICATE,
    ]


def test_replay_reports_different_canonical_as_error() -> None:
    uow = FakeUoW()
    service = MarketDataService(lambda: uow)  # type: ignore[arg-type]
    tick = _tick()
    conflict = tick.model_copy(update={"price": Decimal("501")})

    result = replay_market_facts(service, [tick, conflict])

    assert result.has_error
    assert result.results[-1].result.reason == "canonical_conflict"


def test_replay_same_tick_identity_conflict_is_order_independent() -> None:
    first_tick = _tick(price=Decimal("500"))
    second_tick = _tick(price=Decimal("501"))

    first_uow = FakeUoW()
    first_service = MarketDataService(lambda: first_uow)  # type: ignore[arg-type]
    first_result = replay_market_facts(first_service, [first_tick, second_tick])

    second_uow = FakeUoW()
    second_service = MarketDataService(lambda: second_uow)  # type: ignore[arg-type]
    second_result = replay_market_facts(second_service, [second_tick, first_tick])

    assert [result.result.status for result in first_result.results] == [
        MarketDataResultStatus.ACCEPTED,
        MarketDataResultStatus.ERROR,
    ]
    assert [result.result.status for result in second_result.results] == [
        MarketDataResultStatus.ACCEPTED,
        MarketDataResultStatus.ERROR,
    ]
    assert list(first_uow.market_ticks.ticks.values()) == list(
        second_uow.market_ticks.ticks.values()
    )


def test_replay_same_bar_identity_conflict_is_order_independent() -> None:
    first_bar = _bar().model_copy(update={"close": Decimal("501")})
    second_bar = _bar().model_copy(update={"close": Decimal("502")})

    first_uow = FakeUoW()
    first_service = MarketDataService(lambda: first_uow)  # type: ignore[arg-type]
    first_result = replay_market_facts(first_service, [first_bar, second_bar])

    second_uow = FakeUoW()
    second_service = MarketDataService(lambda: second_uow)  # type: ignore[arg-type]
    second_result = replay_market_facts(second_service, [second_bar, first_bar])

    assert [result.result.status for result in first_result.results] == [
        MarketDataResultStatus.ACCEPTED,
        MarketDataResultStatus.ERROR,
    ]
    assert [result.result.status for result in second_result.results] == [
        MarketDataResultStatus.ACCEPTED,
        MarketDataResultStatus.ERROR,
    ]
    assert list(first_uow.market_bars.bars.values()) == list(second_uow.market_bars.bars.values())


def test_market_data_service_depends_on_narrow_market_uow_protocol() -> None:
    hints = get_type_hints(MarketDataService.__init__)

    assert "MarketDataUnitOfWork" in str(hints["uow_factory"])
    assert "UnitOfWork" not in str(hints["uow_factory"]).replace("MarketDataUnitOfWork", "")


def test_raw_payload_excluded_from_canonical_payloads() -> None:
    tick = _tick()
    changed_tick = tick.model_copy(update={"raw_payload": {"changed": True}})
    bar = _bar()
    changed_bar = bar.model_copy(update={"raw_payload": {"changed": True}})

    assert canonical_tick_payload(tick) == canonical_tick_payload(changed_tick)
    assert canonical_bar_payload(bar) == canonical_bar_payload(changed_bar)
