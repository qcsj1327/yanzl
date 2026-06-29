from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from futures_mvp.db.models import Base
from futures_mvp.db.repositories import HistoricalBarRepository
from futures_mvp.modules.market_data.contracts import (
    BarTimeframe,
    HistoricalBar,
    HistoricalDataStatus,
    MarketDataSource,
)


class _Identity:
    symbol = "ao"
    instrument_id = "ao9999"
    trade_instrument_id = "ao2609"
    exchange = "SHFE"
    trading_day = date(2026, 6, 12)


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    assert "historical_bars" in inspect(engine).get_table_names()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _bar(minute: int = 1, close: str = "3205") -> HistoricalBar:
    return HistoricalBar(
        symbol="ao",
        instrument_id="ao9999",
        trade_instrument_id="ao2609",
        exchange="SHFE",
        trading_day=date(2026, 6, 12),
        session_id="test",
        timeframe=BarTimeframe.M1,
        bar_ts=datetime(2026, 6, 12, 9, minute),
        open=Decimal("3200"),
        high=Decimal("3210"),
        low=Decimal("3190"),
        close=Decimal(close),
        volume=Decimal("10"),
        turnover=Decimal("0"),
        open_interest=Decimal("20"),
    )


def test_repository_upsert_is_idempotent_and_reports_coverage() -> None:
    factory = _session_factory()

    with factory.begin() as session:
        repo = HistoricalBarRepository(session)
        assert repo.upsert_bars(
            (_bar(),),
            source=MarketDataSource.READ_ONLY_ADAPTER.value,
            resolver_source="static_fixture",
            resolver_confidence="static_fixture",
        ) == 1
        assert repo.upsert_bars(
            (_bar(close="3206"),),
            source=MarketDataSource.READ_ONLY_ADAPTER.value,
            resolver_source="static_fixture",
            resolver_confidence="static_fixture",
        ) == 0

        result = repo.get_bars(_Identity(), BarTimeframe.M1)
        coverage = repo.get_coverage(_Identity(), BarTimeframe.M1)

    assert result.status is HistoricalDataStatus.OK
    assert len(result.bars) == 1
    assert result.bars[0].close == Decimal("3206.00000000")
    assert coverage["status"] == "OK"
    assert coverage["bar_count"] == 1


def test_repository_get_bars_blocks_when_local_db_has_no_data() -> None:
    factory = _session_factory()

    with factory.begin() as session:
        result = HistoricalBarRepository(session).get_bars(_Identity(), BarTimeframe.M1)

    assert result.status is HistoricalDataStatus.BLOCKED
    assert "本地历史行情库无数据" in result.diagnostics
