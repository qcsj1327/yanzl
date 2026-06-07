from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from futures_mvp.domain.enums import (
    BarTimeframe,
    Direction,
    FeatureQualityStatus,
    Offset,
    SignalDecisionType,
    SignalLifecycleStatus,
    SignalPositionSide,
    SignalResultStatus,
    SignalSide,
    StrategyResultStatus,
)
from futures_mvp.domain.errors import DecimalRequiredError
from futures_mvp.domain.models import (
    FeatureSnapshot,
    Signal,
    SignalCandidate,
    SignalDecision,
    StrategyConfig,
    StrategyContext,
)
from futures_mvp.modules.strategy import (
    build_signal_id,
    canonical_signal_candidate_payload,
    signal_features_ref,
)


def _config(**updates: object) -> StrategyConfig:
    values = {
        "strategy_name": "breakout",
        "strategy_version": "strategy-v1",
        "feature_version": "feature-v1",
        "feature_config_hash": "feature-hash",
        "timeframe": BarTimeframe.M1,
        "params": {"threshold": Decimal("1.5"), "windows": [3, 5]},
        "allow_position_context": False,
        "allow_market_snapshot": False,
        "enabled": True,
    }
    values.update(updates)
    return StrategyConfig.build(**values)


def _snapshot(**updates: object) -> FeatureSnapshot:
    values = {
        "symbol": "au",
        "instrument_id": "au2606",
        "trade_instrument_id": "au2606",
        "exchange": "SHFE",
        "trading_day": date(2026, 6, 7),
        "timeframe": BarTimeframe.M1,
        "bar_ts": datetime(2026, 6, 7, 9, tzinfo=UTC),
        "feature_version": "feature-v1",
        "feature_config_hash": "feature-hash",
        "source_bar_keys": ("bar-key",),
        "returns": None,
        "bar_return": Decimal("1"),
        "price_range": Decimal("2"),
        "range": Decimal("2"),
        "atr": None,
        "volume_ratio": None,
        "moving_average": None,
        "bias": None,
        "breakout_level": None,
        "volatility": None,
        "momentum": None,
        "source_window_start": datetime(2026, 6, 7, 9, tzinfo=UTC),
        "source_window_end": datetime(2026, 6, 7, 9, tzinfo=UTC),
        "warmup_complete": False,
        "quality_status": FeatureQualityStatus.WARMUP_INCOMPLETE,
    }
    values.update(updates)
    return FeatureSnapshot(**values)


def _signal_id(
    *,
    decision: SignalDecisionType = SignalDecisionType.BUY,
    side: SignalSide = SignalSide.BUY,
    position_side: SignalPositionSide = SignalPositionSide.LONG,
    expected_price: Decimal | None = Decimal("500"),
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
) -> str:
    config = _config()
    snapshot = _snapshot()
    return build_signal_id(
        strategy_name=config.strategy_name,
        strategy_version=config.strategy_version,
        strategy_config_hash=config.strategy_config_hash,
        symbol=snapshot.symbol,
        instrument_id=snapshot.instrument_id,
        trade_instrument_id=snapshot.trade_instrument_id,
        exchange=snapshot.exchange,
        trading_day=snapshot.trading_day,
        timeframe=snapshot.timeframe,
        bar_ts=snapshot.bar_ts,
        feature_version=snapshot.feature_version,
        feature_config_hash=snapshot.feature_config_hash,
        decision=decision,
        side=side,
        position_side=position_side,
        expected_price=expected_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


def _decision(**updates: object) -> SignalDecision:
    config = _config()
    snapshot = _snapshot()
    values = {
        "signal_id": _signal_id(),
        "strategy_name": config.strategy_name,
        "strategy_version": config.strategy_version,
        "strategy_config_hash": config.strategy_config_hash,
        "runtime_id": "runtime-1",
        "symbol": snapshot.symbol,
        "instrument_id": snapshot.instrument_id,
        "trade_instrument_id": snapshot.trade_instrument_id,
        "exchange": snapshot.exchange,
        "trading_day": snapshot.trading_day,
        "timeframe": snapshot.timeframe,
        "bar_ts": snapshot.bar_ts,
        "feature_version": snapshot.feature_version,
        "feature_config_hash": snapshot.feature_config_hash,
        "decision": SignalDecisionType.BUY,
        "side": SignalSide.BUY,
        "position_side": SignalPositionSide.LONG,
        "confidence": Decimal("0.8"),
        "strength": Decimal("1.2"),
        "reason": "breakout",
        "expected_price": Decimal("500"),
        "tags": {"rule": "toy"},
        "raw_payload": {"diagnostic": "a"},
    }
    values.update(updates)
    return SignalDecision(**values)


def _candidate(**updates: object) -> SignalCandidate:
    snapshot = _snapshot()
    values = _decision().model_dump()
    values.update(
        {
            "holding_period_hint": "intraday",
            "features_ref": signal_features_ref(snapshot),
            "created_at": datetime(2026, 6, 7, 9, 1, tzinfo=UTC),
        }
    )
    values.update(updates)
    return SignalCandidate(**values)


def test_strategy_enums_freeze_stage_i_contract() -> None:
    assert [status.value for status in SignalLifecycleStatus] == [
        "CANDIDATE",
        "CONFIRMED",
        "TRIGGERED",
        "DUPLICATE",
        "BLOCKED",
        "EXPIRED",
    ]
    assert SignalResultStatus.TRIGGERED.value == "TRIGGERED"
    assert StrategyResultStatus.GENERATED.value == "GENERATED"
    assert StrategyResultStatus.REJECTED_INVALID_SIGNAL_ID.value == "REJECTED_INVALID_SIGNAL_ID"


def test_strategy_config_hash_is_deterministic_and_sensitive() -> None:
    config = _config(params={"windows": [3, 5], "threshold": Decimal("1.5")})

    assert config.strategy_config_hash == _config().strategy_config_hash
    assert (
        config.strategy_config_hash
        != _config(strategy_version="strategy-v2").strategy_config_hash
    )
    assert config.strategy_config_hash != _config(feature_config_hash="other").strategy_config_hash
    assert (
        config.strategy_config_hash
        != _config(params={"threshold": Decimal("2")}).strategy_config_hash
    )
    with pytest.raises(ValueError, match="strategy_config_hash"):
        StrategyConfig(
            strategy_config_hash="bad",
            **config.model_dump(exclude={"strategy_config_hash"}),
        )


def test_strategy_config_params_reject_unstable_values() -> None:
    stable = _config(
        params={
            "date": date(2026, 6, 7),
            "decimal": Decimal("1.5"),
            "enum": BarTimeframe.M1,
            "nested": {"enabled": True, "window": [3, None, "x"]},
        }
    )
    stable_reordered = _config(
        params={
            "nested": {"window": [3, None, "x"], "enabled": True},
            "enum": BarTimeframe.M1,
            "decimal": Decimal("1.5"),
            "date": date(2026, 6, 7),
        }
    )

    assert stable.strategy_config_hash == stable_reordered.strategy_config_hash
    with pytest.raises(ValueError, match="canonical mapping keys"):
        _config(params={object(): "x"})
    with pytest.raises(ValueError, match="unsupported canonical JSON value type"):
        _config(params={"x": object()})
    with pytest.raises(ValueError, match="canonical mapping keys"):
        _config(params={1: "x"})
    with pytest.raises(ValueError, match="unsupported canonical JSON value type"):
        _config(params={"x": 1.1})
    with pytest.raises(ValueError, match="unsupported canonical JSON value type"):
        _config(params={"x": {"a"}})


def test_strategy_context_requires_feature_config_identity_match() -> None:
    StrategyContext(feature_snapshot=_snapshot(), strategy_config=_config())
    with pytest.raises(ValueError, match="feature_config_hash"):
        StrategyContext(
            feature_snapshot=_snapshot(feature_config_hash="other"),
            strategy_config=_config(),
        )


def test_signal_decision_validation() -> None:
    assert _decision().expected_price == Decimal("500")
    with pytest.raises(ValueError, match="confidence"):
        _decision(confidence=Decimal("1.1"))
    with pytest.raises(DecimalRequiredError):
        _decision(confidence=0.5)
    with pytest.raises(ValueError, match="HOLD"):
        _decision(decision=SignalDecisionType.HOLD, side=SignalSide.BUY, expected_price=None)
    with pytest.raises(ValueError, match="expected_price"):
        _decision(expected_price=None)


def test_signal_candidate_feature_ref_and_canonical_exclude_raw_and_created_at() -> None:
    first = _candidate(
        raw_payload={"diagnostic": "a"},
        created_at=datetime(2026, 6, 7, 9, tzinfo=UTC),
    )
    second = _candidate(
        raw_payload={"diagnostic": "b"},
        created_at=datetime(2026, 6, 7, 10, tzinfo=UTC),
    )

    assert canonical_signal_candidate_payload(first) == canonical_signal_candidate_payload(second)
    with pytest.raises(ValueError, match="features_ref"):
        _candidate(features_ref={"feature_version": "feature-v1"})


def test_signal_id_is_deterministic_and_excludes_raw_payload_and_time_fields() -> None:
    assert _signal_id() == _signal_id()
    assert _signal_id(expected_price=Decimal("500")) != _signal_id(expected_price=Decimal("501"))
    assert _signal_id(stop_loss=Decimal("490")) != _signal_id(stop_loss=Decimal("491"))
    assert (
        _decision(runtime_id="runtime-1").signal_id
        == _decision(runtime_id="runtime-2").signal_id
    )


def test_legacy_signal_is_not_stage_i_signal_candidate() -> None:
    legacy = Signal(
        signal_id="legacy",
        account_id="acct",
        instrument_id="au2606",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        limit_price=Decimal("500"),
        quantity=Decimal("1"),
        created_at=datetime(2026, 6, 7, 9, tzinfo=UTC),
    )

    assert not isinstance(legacy, SignalCandidate)
