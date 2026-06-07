from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from futures_mvp.domain.enums import (
    BarTimeframe,
    FeatureQualityStatus,
    FeatureResultStatus,
    MarketDataResultStatus,
)
from futures_mvp.domain.models import Bar, FeatureConfig
from futures_mvp.modules.feature import FeatureBuilder, source_bar_key


def _config(**updates: object) -> FeatureConfig:
    values = {
        "feature_version": "feature-v1",
        "timeframe": BarTimeframe.M1,
        "ma_window": 3,
        "atr_window": 3,
        "volume_window": 3,
        "breakout_window": 3,
        "volatility_window": 3,
        "momentum_window": 3,
        "allow_gap": False,
    }
    values.update(updates)
    return FeatureConfig(**values)


def _bar(
    minute: int,
    *,
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    volume: Decimal,
    instrument_id: str = "au2606",
    timeframe: BarTimeframe = BarTimeframe.M1,
) -> Bar:
    return Bar(
        symbol="au",
        instrument_id=instrument_id,
        trade_instrument_id=instrument_id,
        exchange="SHFE",
        trading_day=date(2026, 6, 7),
        timeframe=timeframe,
        bar_ts=datetime(2026, 6, 7, 9, minute, tzinfo=UTC),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        turnover=Decimal("1"),
        open_interest=Decimal("1"),
        source="adapter",
        quality_status=MarketDataResultStatus.ACCEPTED,
    )


def _bars() -> tuple[Bar, ...]:
    return (
        _bar(
            0,
            open_=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=Decimal("10"),
        ),
        _bar(
            1,
            open_=Decimal("101"),
            high=Decimal("106"),
            low=Decimal("100"),
            close=Decimal("103"),
            volume=Decimal("20"),
        ),
        _bar(
            2,
            open_=Decimal("103"),
            high=Decimal("108"),
            low=Decimal("102"),
            close=Decimal("107"),
            volume=Decimal("30"),
        ),
        _bar(
            3,
            open_=Decimal("107"),
            high=Decimal("110"),
            low=Decimal("106"),
            close=Decimal("109"),
            volume=Decimal("40"),
        ),
    )


def test_builder_calculates_minimum_feature_formulas() -> None:
    result = FeatureBuilder().build(_bars(), _config())
    snapshot = result.snapshot

    assert result.status is FeatureResultStatus.ACCEPTED
    assert snapshot is not None
    assert snapshot.bar_return == Decimal("2")
    assert snapshot.returns == Decimal("2")
    assert snapshot.price_range == Decimal("4")
    assert snapshot.range == Decimal("4")
    assert snapshot.moving_average == Decimal("319") / Decimal("3")
    assert snapshot.bias == Decimal("109") - (Decimal("319") / Decimal("3"))
    assert snapshot.atr == Decimal("16") / Decimal("3")
    assert snapshot.volume_ratio == Decimal("2")
    assert snapshot.breakout_level == Decimal("110")
    assert snapshot.volatility == Decimal("8") / Decimal("3")
    assert snapshot.momentum == Decimal("8")
    assert snapshot.warmup_complete is True
    assert snapshot.quality_status is FeatureQualityStatus.ACCEPTED
    assert snapshot.feature_config_hash == _config().config_hash()


def test_warmup_produces_none_without_zero_fill() -> None:
    result = FeatureBuilder().build(_bars()[:1], _config())
    snapshot = result.snapshot

    assert result.status is FeatureResultStatus.WARMUP_INCOMPLETE
    assert snapshot is not None
    assert snapshot.warmup_complete is False
    assert snapshot.quality_status is FeatureQualityStatus.WARMUP_INCOMPLETE
    assert snapshot.returns is None
    assert snapshot.moving_average is None
    assert snapshot.atr is None
    assert snapshot.volume_ratio is None
    assert snapshot.breakout_level is None
    assert snapshot.volatility is None
    assert snapshot.momentum is None
    assert snapshot.bar_return == Decimal("1")
    assert snapshot.range == Decimal("6")


def test_gap_policy_rejects_or_emits_gap_snapshot() -> None:
    bars = (
        _bar(
            0,
            open_=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("10"),
        ),
        _bar(
            2,
            open_=Decimal("100"),
            high=Decimal("103"),
            low=Decimal("100"),
            close=Decimal("102"),
            volume=Decimal("20"),
        ),
    )

    one_period_config = _config(
        ma_window=1,
        atr_window=1,
        volume_window=1,
        breakout_window=1,
        volatility_window=1,
        momentum_window=1,
    )
    rejected = FeatureBuilder().build(bars, one_period_config)
    accepted = FeatureBuilder().build(
        bars,
        _config(
            ma_window=1,
            atr_window=1,
            volume_window=1,
            breakout_window=1,
            volatility_window=1,
            momentum_window=1,
            allow_gap=True,
        ),
    )

    assert rejected.status is FeatureResultStatus.REJECTED_GAP
    assert rejected.snapshot is None
    assert accepted.snapshot is not None
    assert accepted.snapshot.quality_status is FeatureQualityStatus.GAP_DETECTED
    assert accepted.snapshot.gap_count == 1
    assert accepted.snapshot.missing_bar_count == 1


def test_source_validation_rejects_bad_inputs() -> None:
    builder = FeatureBuilder()
    bars = _bars()

    assert builder.build((), _config()).status is FeatureResultStatus.REJECTED_EMPTY_INPUT
    assert (
        builder.build(
            (bars[0], bars[1].model_copy(update={"instrument_id": "ag2606"})),
            _config(),
        ).status
        is FeatureResultStatus.REJECTED_IDENTITY_MISMATCH
    )
    assert (
        builder.build(
            (bars[0], bars[1].model_copy(update={"timeframe": BarTimeframe.M5})),
            _config(),
        ).status
        is FeatureResultStatus.REJECTED_TIMEFRAME_MISMATCH
    )
    assert (
        builder.build((bars[1], bars[0]), _config()).status
        is FeatureResultStatus.REJECTED_NON_MONOTONIC
    )
    assert (
        builder.build(bars, _config(timeframe=BarTimeframe.M5)).status
        is FeatureResultStatus.REJECTED_TIMEFRAME_MISMATCH
    )


def test_source_bar_key_is_deterministic_and_uses_no_database_identity() -> None:
    bar = _bars()[0]

    assert source_bar_key(bar) == "SHFE|au2606|M1|2026-06-07T09:00:00+00:00|adapter"


def test_builder_has_no_db_uow_strategy_signal_or_accounting_imports() -> None:
    source = Path("src/futures_mvp/modules/feature/builder.py").read_text()

    forbidden = [
        "futures_mvp.db",
        "UnitOfWork",
        "Strategy",
        "Signal",
        "Risk",
        "OMS",
        "Execution",
        "Accounting",
        "Broker",
        "Runtime",
    ]
    assert all(item not in source for item in forbidden)
