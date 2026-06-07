from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import (
    BarTimeframe,
    FeatureQualityStatus,
    FeatureResultStatus,
)
from futures_mvp.domain.errors import DecimalRequiredError
from futures_mvp.domain.models import FeatureBuildResult, FeatureConfig, FeatureSnapshot
from futures_mvp.modules.feature import canonical_feature_snapshot_payload


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


def _snapshot(**updates: object) -> FeatureSnapshot:
    values = {
        "symbol": "au",
        "instrument_id": "au2606",
        "trade_instrument_id": "au2606",
        "exchange": "SHFE",
        "trading_day": date(2026, 6, 7),
        "timeframe": BarTimeframe.M1,
        "bar_ts": datetime(2026, 6, 7, 9, 2, tzinfo=UTC),
        "feature_version": "feature-v1",
        "feature_config_hash": _config().config_hash(),
        "source_bar_keys": ("SHFE|au2606|M1|2026-06-07T09:02:00+00:00|adapter",),
        "returns": Decimal("1"),
        "bar_return": Decimal("2"),
        "price_range": Decimal("4"),
        "range": Decimal("4"),
        "atr": Decimal("5"),
        "volume_ratio": Decimal("1.5"),
        "moving_average": Decimal("501"),
        "bias": Decimal("1"),
        "breakout_level": Decimal("505"),
        "volatility": Decimal("1"),
        "momentum": Decimal("3"),
        "source_window_start": datetime(2026, 6, 7, 9, tzinfo=UTC),
        "source_window_end": datetime(2026, 6, 7, 9, 2, tzinfo=UTC),
        "warmup_complete": True,
        "quality_status": FeatureQualityStatus.ACCEPTED,
        "missing_bar_count": 0,
        "gap_count": 0,
        "raw_payload": {"diagnostic": True},
    }
    values.update(updates)
    return FeatureSnapshot(**values)


def test_feature_enums_complete_contract() -> None:
    assert [status.value for status in FeatureQualityStatus] == [
        "ACCEPTED",
        "WARMUP_INCOMPLETE",
        "GAP_DETECTED",
    ]
    assert [status.value for status in FeatureResultStatus] == [
        "ACCEPTED",
        "WARMUP_INCOMPLETE",
        "REJECTED_EMPTY_INPUT",
        "REJECTED_IDENTITY_MISMATCH",
        "REJECTED_TIMEFRAME_MISMATCH",
        "REJECTED_NON_MONOTONIC",
        "REJECTED_GAP",
        "DUPLICATE",
        "CONFLICT",
        "ERROR",
    ]


def test_feature_config_validation() -> None:
    assert _config().feature_version == "feature-v1"
    with pytest.raises(ValueError, match="feature_version"):
        _config(feature_version="")
    with pytest.raises(ValueError, match="ma_window"):
        _config(ma_window=0)
    with pytest.raises(ValueError, match="ma_window"):
        _config(ma_window=True)


def test_feature_config_hash_is_deterministic_and_config_sensitive() -> None:
    config = _config()

    assert config.config_hash() == _config().config_hash()
    assert config.config_hash() != _config(ma_window=4).config_hash()
    assert config.config_hash() != _config(atr_window=4).config_hash()
    assert config.config_hash() != _config(volume_window=4).config_hash()
    assert config.config_hash() != _config(breakout_window=4).config_hash()
    assert config.config_hash() != _config(volatility_window=4).config_hash()
    assert config.config_hash() != _config(momentum_window=4).config_hash()
    assert config.config_hash() != _config(allow_gap=True).config_hash()


def test_feature_snapshot_decimal_none_and_identity_validation() -> None:
    warmup = _snapshot(
        returns=None,
        moving_average=None,
        bias=None,
        warmup_complete=False,
        quality_status=FeatureQualityStatus.WARMUP_INCOMPLETE,
    )

    assert warmup.returns is None
    assert warmup.moving_average is None
    assert warmup.bias is None
    with pytest.raises(DecimalRequiredError):
        _snapshot(returns=1.0)
    with pytest.raises(ValueError, match="instrument_id"):
        _snapshot(instrument_id="")
    with pytest.raises(ValueError, match="source_bar_keys"):
        _snapshot(source_bar_keys=())
    with pytest.raises(ValueError, match="feature_config_hash"):
        _snapshot(feature_config_hash="")


def test_feature_snapshot_rejects_inconsistent_warmup_and_quality_state() -> None:
    with pytest.raises(ValueError, match="warmup_complete requires all feature values"):
        _snapshot(atr=None)
    with pytest.raises(ValueError, match="ACCEPTED quality requires gap_count"):
        _snapshot(gap_count=1)
    with pytest.raises(ValueError, match="ACCEPTED quality requires missing_bar_count"):
        _snapshot(missing_bar_count=1)
    with pytest.raises(ValueError, match="warmup_complete cannot use WARMUP_INCOMPLETE"):
        _snapshot(quality_status=FeatureQualityStatus.WARMUP_INCOMPLETE)
    with pytest.raises(ValueError, match="GAP_DETECTED quality requires gap_count"):
        _snapshot(quality_status=FeatureQualityStatus.GAP_DETECTED)


def test_feature_snapshot_accepts_valid_quality_states() -> None:
    accepted = _snapshot()
    warmup = _snapshot(
        returns=None,
        atr=None,
        warmup_complete=False,
        quality_status=FeatureQualityStatus.WARMUP_INCOMPLETE,
    )
    gap = _snapshot(
        quality_status=FeatureQualityStatus.GAP_DETECTED,
        gap_count=1,
        missing_bar_count=1,
    )

    assert accepted.quality_status is FeatureQualityStatus.ACCEPTED
    assert warmup.warmup_complete is False
    assert gap.gap_count == 1


def test_feature_build_result_accepts_snapshot_or_rejection() -> None:
    accepted = FeatureBuildResult(status=FeatureResultStatus.ACCEPTED, snapshot=_snapshot())
    rejected = FeatureBuildResult(
        status=FeatureResultStatus.REJECTED_EMPTY_INPUT,
        reason="bars are required",
    )

    assert accepted.snapshot is not None
    assert rejected.snapshot is None


def test_raw_payload_excluded_from_canonical() -> None:
    first = _snapshot(raw_payload={"diagnostic": "a"})
    second = _snapshot(raw_payload={"diagnostic": "b"})

    assert canonical_feature_snapshot_payload(first) == canonical_feature_snapshot_payload(second)
