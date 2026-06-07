import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from futures_mvp.domain.decimal import require_decimal
from futures_mvp.domain.enums import (
    BarTimeframe,
    Direction,
    EventApplicationStatus,
    EventSource,
    FeatureQualityStatus,
    FeatureResultStatus,
    MarginPriceBasis,
    MarginResultStatus,
    MarketDataEventType,
    MarketDataResultStatus,
    Offset,
    OrderStatus,
    OrderType,
    PnLPriceBasis,
    PnLResultStatus,
    PositionManagerResultStatus,
    RiskDecision,
    SettlementResultStatus,
    SignalDecisionType,
    SignalLifecycleStatus,
    SignalPositionSide,
    SignalResultStatus,
    SignalSide,
    StrategyResultStatus,
)


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def require_positive_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return value


def require_non_negative_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return value


def require_non_empty_string(value: str, *, field_name: str) -> str:
    if not value:
        raise ValueError(f"{field_name} is required")
    return value


class Signal(DomainModel):
    signal_id: str
    account_id: str
    instrument_id: str
    exchange: str
    direction: Direction
    offset: Offset
    limit_price: Decimal
    quantity: Decimal
    created_at: datetime

    @field_validator("limit_price", "quantity", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class OrderRequest(DomainModel):
    client_order_id: str
    account_id: str
    instrument_id: str
    exchange: str
    direction: Direction
    offset: Offset
    order_type: OrderType = OrderType.LIMIT
    limit_price: Decimal
    quantity: Decimal

    @field_validator("limit_price", "quantity", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class OrderState(DomainModel):
    order_id: str
    request: OrderRequest
    status: OrderStatus = OrderStatus.CREATED
    filled_quantity: Decimal = Field(default=Decimal("0"))
    reject_reason: str | None = None
    version: int = 0

    @field_validator("filled_quantity", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class RiskResult(DomainModel):
    decision: RiskDecision
    rule_name: str
    reason: str | None = None


class OrderEvent(DomainModel):
    order_id: str
    previous_status: OrderStatus | None
    new_status: OrderStatus
    event_source: EventSource
    external_event_id: str
    raw_payload: dict[str, Any]
    occurred_at: datetime


class OrderEventApplicationResult(DomainModel):
    status: EventApplicationStatus
    order: OrderState
    reason: str | None = None


class Tick(DomainModel):
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    ts: datetime
    price: Decimal
    volume: Decimal
    turnover: Decimal
    open_interest: Decimal
    bid_price_1: Decimal | None = None
    ask_price_1: Decimal | None = None
    bid_volume_1: Decimal | None = None
    ask_volume_1: Decimal | None = None
    source: str
    raw_payload: dict[str, Any] | None = None

    @field_validator(
        "price",
        "volume",
        "turnover",
        "open_interest",
        "bid_price_1",
        "ask_price_1",
        "bid_volume_1",
        "ask_volume_1",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("symbol", "instrument_id", "trade_instrument_id", "exchange", "source")
    @classmethod
    def _required_identity(cls, value: str, info: Any) -> str:
        return require_non_empty_string(value, field_name=info.field_name)

    @field_validator("price", "bid_price_1", "ask_price_1")
    @classmethod
    def _positive_price(cls, value: Decimal | None, info: Any) -> Decimal | None:
        if value is None:
            return None
        return require_positive_decimal(value, field_name=info.field_name)

    @field_validator("volume", "turnover", "open_interest", "bid_volume_1", "ask_volume_1")
    @classmethod
    def _non_negative_quantity(cls, value: Decimal | None, info: Any) -> Decimal | None:
        if value is None:
            return None
        return require_non_negative_decimal(value, field_name=info.field_name)

    @model_validator(mode="after")
    def _bid_price_not_above_ask(self) -> "Tick":
        if (
            self.bid_price_1 is not None
            and self.ask_price_1 is not None
            and self.bid_price_1 > self.ask_price_1
        ):
            raise ValueError("bid_price_1 must be less than or equal to ask_price_1")
        return self


class Bar(DomainModel):
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    timeframe: BarTimeframe
    bar_ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal
    open_interest: Decimal
    source: str
    quality_status: MarketDataResultStatus
    raw_payload: dict[str, Any] | None = None

    @field_validator(
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "open_interest",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("symbol", "instrument_id", "trade_instrument_id", "exchange", "source")
    @classmethod
    def _required_identity(cls, value: str, info: Any) -> str:
        return require_non_empty_string(value, field_name=info.field_name)

    @field_validator("open", "high", "low", "close")
    @classmethod
    def _positive_price(cls, value: Decimal, info: Any) -> Decimal:
        return require_positive_decimal(value, field_name=info.field_name)

    @field_validator("volume", "turnover", "open_interest")
    @classmethod
    def _non_negative_quantity(cls, value: Decimal, info: Any) -> Decimal:
        return require_non_negative_decimal(value, field_name=info.field_name)

    @model_validator(mode="after")
    def _valid_ohlc(self) -> "Bar":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be greater than or equal to open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be less than or equal to open, close, and high")
        return self


class DataQualityResult(DomainModel):
    status: MarketDataResultStatus
    event_type: MarketDataEventType | None = None
    instrument_id: str | None = None
    exchange: str | None = None
    trading_day: date | None = None
    ts: datetime | None = None
    reason: str | None = None


class MarketDataEvent(DomainModel):
    event_id: str
    event_type: MarketDataEventType
    instrument_id: str
    exchange: str
    trading_day: date
    ts: datetime
    source: str
    result: DataQualityResult
    tick: Tick | None = None
    bar: Bar | None = None

    @field_validator("event_id", "instrument_id", "exchange", "source")
    @classmethod
    def _required_identity(cls, value: str, info: Any) -> str:
        return require_non_empty_string(value, field_name=info.field_name)

    @model_validator(mode="after")
    def _valid_event_envelope(self) -> "MarketDataEvent":
        self._validate_result_compatibility()
        self._validate_payload_shape()
        self._validate_result_identity()
        return self

    def _validate_result_compatibility(self) -> None:
        expected_statuses = {
            MarketDataEventType.TICK_ACCEPTED: {MarketDataResultStatus.ACCEPTED},
            MarketDataEventType.BAR_ACCEPTED: {MarketDataResultStatus.ACCEPTED},
            MarketDataEventType.TICK_REJECTED: _MARKET_DATA_REJECTED_STATUSES,
            MarketDataEventType.BAR_REJECTED: _MARKET_DATA_REJECTED_STATUSES,
            MarketDataEventType.DUPLICATE: {MarketDataResultStatus.DUPLICATE},
            MarketDataEventType.GAP_DETECTED: {MarketDataResultStatus.GAP_DETECTED},
            MarketDataEventType.ERROR: {MarketDataResultStatus.ERROR},
        }
        if self.result.status not in expected_statuses[self.event_type]:
            raise ValueError("event_type and result.status are incompatible")
        if self.result.event_type is not None and self.result.event_type is not self.event_type:
            raise ValueError("event_type and result.event_type must match")

    def _validate_payload_shape(self) -> None:
        if self.tick is not None and self.bar is not None:
            raise ValueError("MarketDataEvent cannot contain both tick and bar")
        if self.event_type in {
            MarketDataEventType.TICK_ACCEPTED,
            MarketDataEventType.TICK_REJECTED,
        }:
            if self.tick is None or self.bar is not None:
                raise ValueError("tick event requires tick payload only")
            self._validate_tick_identity(self.tick)
        elif self.event_type in {
            MarketDataEventType.BAR_ACCEPTED,
            MarketDataEventType.BAR_REJECTED,
        }:
            if self.bar is None or self.tick is not None:
                raise ValueError("bar event requires bar payload only")
            self._validate_bar_identity(self.bar)
        elif self.tick is not None:
            self._validate_tick_identity(self.tick)
        elif self.bar is not None:
            self._validate_bar_identity(self.bar)

    def _validate_tick_identity(self, tick: Tick) -> None:
        if (
            self.instrument_id != tick.instrument_id
            or self.exchange != tick.exchange
            or self.trading_day != tick.trading_day
            or self.ts != tick.ts
            or self.source != tick.source
        ):
            raise ValueError("MarketDataEvent identity must match tick payload")

    def _validate_bar_identity(self, bar: Bar) -> None:
        if (
            self.instrument_id != bar.instrument_id
            or self.exchange != bar.exchange
            or self.trading_day != bar.trading_day
            or self.ts != bar.bar_ts
            or self.source != bar.source
        ):
            raise ValueError("MarketDataEvent identity must match bar payload")

    def _validate_result_identity(self) -> None:
        if (
            self.result.instrument_id is not None
            and self.result.instrument_id != self.instrument_id
        ):
            raise ValueError("MarketDataEvent result instrument_id must match envelope")
        if self.result.exchange is not None and self.result.exchange != self.exchange:
            raise ValueError("MarketDataEvent result exchange must match envelope")
        if self.result.trading_day is not None and self.result.trading_day != self.trading_day:
            raise ValueError("MarketDataEvent result trading_day must match envelope")
        if self.result.ts is not None and self.result.ts != self.ts:
            raise ValueError("MarketDataEvent result ts must match envelope")


class MarketDataSnapshot(DomainModel):
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    as_of_ts: datetime
    latest_tick: Tick | None = None
    latest_bars: Mapping[BarTimeframe, Bar]
    quality_status: MarketDataResultStatus

    @field_validator("symbol", "instrument_id", "trade_instrument_id", "exchange")
    @classmethod
    def _required_identity(cls, value: str, info: Any) -> str:
        return require_non_empty_string(value, field_name=info.field_name)

    @model_validator(mode="after")
    def _valid_market_view(self) -> "MarketDataSnapshot":
        if self.latest_tick is not None:
            self._validate_tick_view(self.latest_tick)
        for timeframe, bar in self.latest_bars.items():
            if timeframe is not bar.timeframe:
                raise ValueError("latest_bars key must match bar.timeframe")
            self._validate_bar_view(bar)
        return self

    def _validate_tick_view(self, tick: Tick) -> None:
        if (
            self.symbol != tick.symbol
            or self.instrument_id != tick.instrument_id
            or self.trade_instrument_id != tick.trade_instrument_id
            or self.exchange != tick.exchange
            or self.trading_day != tick.trading_day
        ):
            raise ValueError("MarketDataSnapshot identity must match latest_tick")
        if tick.ts > self.as_of_ts:
            raise ValueError("latest_tick.ts must be less than or equal to as_of_ts")

    def _validate_bar_view(self, bar: Bar) -> None:
        if (
            self.symbol != bar.symbol
            or self.instrument_id != bar.instrument_id
            or self.trade_instrument_id != bar.trade_instrument_id
            or self.exchange != bar.exchange
            or self.trading_day != bar.trading_day
        ):
            raise ValueError("MarketDataSnapshot identity must match latest_bars")
        if bar.bar_ts > self.as_of_ts:
            raise ValueError("bar.bar_ts must be less than or equal to as_of_ts")


class FeatureConfig(DomainModel):
    feature_version: str
    timeframe: BarTimeframe
    ma_window: int
    atr_window: int
    volume_window: int
    breakout_window: int
    volatility_window: int
    momentum_window: int
    allow_gap: bool = False

    @field_validator("feature_version")
    @classmethod
    def _required_feature_version(cls, value: str) -> str:
        return require_non_empty_string(value, field_name="feature_version")

    @field_validator(
        "ma_window",
        "atr_window",
        "volume_window",
        "breakout_window",
        "volatility_window",
        "momentum_window",
        mode="before",
    )
    @classmethod
    def _window_not_bool(cls, value: Any, info: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError(f"{info.field_name} must be an integer")
        return value

    @field_validator(
        "ma_window",
        "atr_window",
        "volume_window",
        "breakout_window",
        "volatility_window",
        "momentum_window",
    )
    @classmethod
    def _positive_window(cls, value: int, info: Any) -> int:
        if value <= 0:
            raise ValueError(f"{info.field_name} must be greater than 0")
        return value

    def config_hash(self) -> str:
        payload = {
            "allow_gap": self.allow_gap,
            "atr_window": self.atr_window,
            "breakout_window": self.breakout_window,
            "feature_version": self.feature_version,
            "ma_window": self.ma_window,
            "momentum_window": self.momentum_window,
            "timeframe": self.timeframe.value,
            "volatility_window": self.volatility_window,
            "volume_window": self.volume_window,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class FeatureSnapshot(DomainModel):
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    timeframe: BarTimeframe
    bar_ts: datetime
    feature_version: str
    feature_config_hash: str
    source_bar_keys: tuple[str, ...]
    returns: Decimal | None = None
    bar_return: Decimal | None = None
    price_range: Decimal | None = None
    range: Decimal | None = None
    atr: Decimal | None = None
    volume_ratio: Decimal | None = None
    moving_average: Decimal | None = None
    bias: Decimal | None = None
    breakout_level: Decimal | None = None
    volatility: Decimal | None = None
    momentum: Decimal | None = None
    source_window_start: datetime
    source_window_end: datetime
    warmup_complete: bool
    quality_status: FeatureQualityStatus
    missing_bar_count: int = 0
    gap_count: int = 0
    raw_payload: dict[str, Any] | None = None

    @field_validator(
        "symbol",
        "instrument_id",
        "trade_instrument_id",
            "exchange",
            "feature_version",
            "feature_config_hash",
        )
    @classmethod
    def _required_identity(cls, value: str, info: Any) -> str:
        return require_non_empty_string(value, field_name=info.field_name)

    @field_validator("source_bar_keys", mode="before")
    @classmethod
    def _source_bar_keys_tuple(cls, value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            raise ValueError("source_bar_keys must be a non-empty sequence")
        try:
            keys = tuple(value)
        except TypeError as exc:
            raise ValueError("source_bar_keys must be a non-empty sequence") from exc
        if not keys:
            raise ValueError("source_bar_keys is required")
        for key in keys:
            if not isinstance(key, str) or not key:
                raise ValueError("source_bar_keys must contain non-empty strings")
        return keys

    @field_validator(
        "returns",
        "bar_return",
        "price_range",
        "range",
        "atr",
        "volume_ratio",
        "moving_average",
        "bias",
        "breakout_level",
        "volatility",
        "momentum",
        mode="before",
    )
    @classmethod
    def _decimal_or_none(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("missing_bar_count", "gap_count")
    @classmethod
    def _non_negative_count(cls, value: int, info: Any) -> int:
        if value < 0:
            raise ValueError(f"{info.field_name} must be greater than or equal to 0")
        return value

    @model_validator(mode="after")
    def _valid_feature_quality_state(self) -> "FeatureSnapshot":
        feature_values = (
            self.returns,
            self.bar_return,
            self.price_range,
            self.range,
            self.atr,
            self.volume_ratio,
            self.moving_average,
            self.bias,
            self.breakout_level,
            self.volatility,
            self.momentum,
        )
        all_features_ready = all(value is not None for value in feature_values)

        if self.warmup_complete and not all_features_ready:
            raise ValueError("warmup_complete requires all feature values")
        if self.warmup_complete and self.quality_status is FeatureQualityStatus.WARMUP_INCOMPLETE:
            raise ValueError("warmup_complete cannot use WARMUP_INCOMPLETE quality")
        if not self.warmup_complete and self.quality_status is FeatureQualityStatus.ACCEPTED:
            raise ValueError("ACCEPTED quality requires warmup_complete")

        if self.quality_status is FeatureQualityStatus.ACCEPTED:
            if not self.warmup_complete:
                raise ValueError("ACCEPTED quality requires warmup_complete")
            if self.gap_count != 0:
                raise ValueError("ACCEPTED quality requires gap_count to be 0")
            if self.missing_bar_count != 0:
                raise ValueError("ACCEPTED quality requires missing_bar_count to be 0")
            if not all_features_ready:
                raise ValueError("ACCEPTED quality requires all feature values")

        if self.quality_status is FeatureQualityStatus.GAP_DETECTED and self.gap_count <= 0:
            raise ValueError("GAP_DETECTED quality requires gap_count greater than 0")
        if self.quality_status is FeatureQualityStatus.WARMUP_INCOMPLETE and self.warmup_complete:
            raise ValueError("WARMUP_INCOMPLETE quality requires warmup_complete=False")
        if self.gap_count > 0 and self.quality_status is not FeatureQualityStatus.GAP_DETECTED:
            raise ValueError("gap_count requires GAP_DETECTED quality")
        if self.missing_bar_count > 0 and self.gap_count == 0:
            raise ValueError("missing_bar_count requires gap_count")
        if self.quality_status is FeatureQualityStatus.GAP_DETECTED:
            if self.missing_bar_count < self.gap_count:
                raise ValueError("missing_bar_count must be greater than or equal to gap_count")

        return self


class FeatureBuildResult(DomainModel):
    status: FeatureResultStatus
    snapshot: FeatureSnapshot | None = None
    reason: str | None = None


def _canonical_json_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise ValueError("canonical mapping keys must be strings")
        return {
            key: _canonical_json_value(value[key])
            for key in sorted(value.keys())
        }
    raise ValueError(f"unsupported canonical JSON value type: {type(value).__name__}")


def stable_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_json_value(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class StrategyConfig(DomainModel):
    strategy_name: str
    strategy_version: str
    strategy_config_hash: str
    feature_version: str
    feature_config_hash: str
    timeframe: BarTimeframe
    params: dict[str, Any] = Field(default_factory=dict)
    allow_position_context: bool = False
    allow_market_snapshot: bool = False
    enabled: bool = True

    @field_validator(
        "strategy_name",
        "strategy_version",
        "strategy_config_hash",
        "feature_version",
        "feature_config_hash",
    )
    @classmethod
    def _required_identity(cls, value: str, info: Any) -> str:
        return require_non_empty_string(value, field_name=info.field_name)

    @field_validator("params", mode="before")
    @classmethod
    def _params_dict(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("params must be a mapping")
        return dict(_canonical_json_value(value))

    @classmethod
    def build(
        cls,
        *,
        strategy_name: str,
        strategy_version: str,
        feature_version: str,
        feature_config_hash: str,
        timeframe: BarTimeframe,
        params: Mapping[str, Any] | None = None,
        allow_position_context: bool = False,
        allow_market_snapshot: bool = False,
        enabled: bool = True,
    ) -> "StrategyConfig":
        payload = cls.hash_payload(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            feature_version=feature_version,
            feature_config_hash=feature_config_hash,
            timeframe=timeframe,
            params=params or {},
            allow_position_context=allow_position_context,
            allow_market_snapshot=allow_market_snapshot,
            enabled=enabled,
        )
        return cls(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            strategy_config_hash=stable_json_sha256(payload),
            feature_version=feature_version,
            feature_config_hash=feature_config_hash,
            timeframe=timeframe,
            params=dict(_canonical_json_value(params or {})),
            allow_position_context=allow_position_context,
            allow_market_snapshot=allow_market_snapshot,
            enabled=enabled,
        )

    @staticmethod
    def hash_payload(
        *,
        strategy_name: str,
        strategy_version: str,
        feature_version: str,
        feature_config_hash: str,
        timeframe: BarTimeframe,
        params: Mapping[str, Any],
        allow_position_context: bool,
        allow_market_snapshot: bool,
        enabled: bool,
    ) -> dict[str, Any]:
        return {
            "allow_market_snapshot": allow_market_snapshot,
            "allow_position_context": allow_position_context,
            "enabled": enabled,
            "feature_config_hash": feature_config_hash,
            "feature_version": feature_version,
            "params": _canonical_json_value(params),
            "strategy_name": strategy_name,
            "strategy_version": strategy_version,
            "timeframe": timeframe.value,
        }

    def config_hash(self) -> str:
        return stable_json_sha256(
            self.hash_payload(
                strategy_name=self.strategy_name,
                strategy_version=self.strategy_version,
                feature_version=self.feature_version,
                feature_config_hash=self.feature_config_hash,
                timeframe=self.timeframe,
                params=self.params,
                allow_position_context=self.allow_position_context,
                allow_market_snapshot=self.allow_market_snapshot,
                enabled=self.enabled,
            )
        )

    @model_validator(mode="after")
    def _valid_strategy_config_hash(self) -> "StrategyConfig":
        if self.strategy_config_hash != self.config_hash():
            raise ValueError("strategy_config_hash must match deterministic config hash")
        return self


class PositionContext(DomainModel):
    positions: tuple[Mapping[str, Any], ...] = ()


class PortfolioContext(DomainModel):
    portfolio_id: str | None = None
    exposures: Mapping[str, Decimal] = Field(default_factory=dict)

    @field_validator("exposures", mode="before")
    @classmethod
    def _decimal_exposures(cls, value: Any) -> Mapping[str, Decimal]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("exposures must be a mapping")
        return {str(key): require_decimal(item) for key, item in value.items()}


class CalendarSessionContext(DomainModel):
    exchange: str
    trading_day: date
    session_name: str | None = None
    is_trading_session: bool | None = None

    @field_validator("exchange")
    @classmethod
    def _required_exchange(cls, value: str) -> str:
        return require_non_empty_string(value, field_name="exchange")


class StrategyContext(DomainModel):
    feature_snapshot: FeatureSnapshot
    market_snapshot: MarketDataSnapshot | None = None
    position_context: PositionContext | None = None
    portfolio_context: PortfolioContext | None = None
    calendar_session_context: CalendarSessionContext | None = None
    strategy_config: StrategyConfig

    @model_validator(mode="after")
    def _valid_context(self) -> "StrategyContext":
        snapshot = self.feature_snapshot
        config = self.strategy_config
        if snapshot.feature_version != config.feature_version:
            raise ValueError("StrategyContext feature_version must match StrategyConfig")
        if snapshot.feature_config_hash != config.feature_config_hash:
            raise ValueError("StrategyContext feature_config_hash must match StrategyConfig")
        if snapshot.timeframe is not config.timeframe:
            raise ValueError("StrategyContext timeframe must match StrategyConfig")
        if self.market_snapshot is not None and not config.allow_market_snapshot:
            raise ValueError("market_snapshot is not allowed by StrategyConfig")
        if self.position_context is not None and not config.allow_position_context:
            raise ValueError("position_context is not allowed by StrategyConfig")
        return self


class SignalDecision(DomainModel):
    decision: SignalDecisionType
    side: SignalSide
    strength: Decimal
    confidence: Decimal
    reason: str | None = None
    signal_id: str
    strategy_name: str
    strategy_version: str
    strategy_config_hash: str
    runtime_id: str
    symbol: str
    instrument_id: str
    trade_instrument_id: str
    exchange: str
    trading_day: date
    timeframe: BarTimeframe
    bar_ts: datetime
    feature_version: str
    feature_config_hash: str
    position_side: SignalPositionSide = SignalPositionSide.NONE
    expected_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    tags: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] | None = None

    @field_validator(
        "strength",
        "confidence",
        "expected_price",
        "stop_loss",
        "take_profit",
        mode="before",
    )
    @classmethod
    def _decimal_or_none(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator(
        "signal_id",
        "strategy_name",
        "strategy_version",
        "strategy_config_hash",
        "runtime_id",
        "symbol",
        "instrument_id",
        "trade_instrument_id",
        "exchange",
        "feature_version",
        "feature_config_hash",
    )
    @classmethod
    def _required_identity(cls, value: str, info: Any) -> str:
        return require_non_empty_string(value, field_name=info.field_name)

    @model_validator(mode="after")
    def _valid_signal_decision(self) -> "SignalDecision":
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.decision is SignalDecisionType.HOLD and self.side is not SignalSide.NONE:
            raise ValueError("HOLD decision requires side NONE")
        if self.decision is not SignalDecisionType.HOLD:
            if self.side is SignalSide.NONE:
                raise ValueError("non-HOLD decision requires BUY or SELL side")
            if self.expected_price is None or self.expected_price <= 0:
                raise ValueError("non-HOLD decision requires expected_price greater than 0")
        if self.expected_price is not None:
            require_positive_decimal(self.expected_price, field_name="expected_price")
        if self.stop_loss is not None:
            require_positive_decimal(self.stop_loss, field_name="stop_loss")
        if self.take_profit is not None:
            require_positive_decimal(self.take_profit, field_name="take_profit")
        return self


class SignalCandidate(SignalDecision):
    holding_period_hint: str | None = None
    features_ref: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    @model_validator(mode="after")
    def _valid_features_ref(self) -> "SignalCandidate":
        required = {
            "symbol": self.symbol,
            "instrument_id": self.instrument_id,
            "trade_instrument_id": self.trade_instrument_id,
            "exchange": self.exchange,
            "trading_day": self.trading_day.isoformat(),
            "timeframe": self.timeframe.value,
            "bar_ts": self.bar_ts.isoformat(),
            "feature_version": self.feature_version,
            "feature_config_hash": self.feature_config_hash,
        }
        for key, expected in required.items():
            actual = self.features_ref.get(key)
            if key == "bar_ts" and isinstance(actual, str):
                actual_ts = datetime.fromisoformat(actual)
                expected_ts = self.bar_ts
                if actual_ts.tzinfo is not None and expected_ts.tzinfo is None:
                    actual_ts = actual_ts.replace(tzinfo=None)
                if actual_ts != expected_ts:
                    raise ValueError(f"features_ref must propagate {key}")
                continue
            if actual != expected:
                raise ValueError(f"features_ref must propagate {key}")
        return self


class SignalLifecycleEvent(DomainModel):
    id: str | None = None
    event_key: str
    signal_id: str
    lifecycle_status: SignalLifecycleStatus
    event_reason: str | None = None
    event_ts: datetime
    raw_payload: dict[str, Any] | None = None
    created_at: datetime | None = None

    @field_validator("event_key", "signal_id")
    @classmethod
    def _required_identity(cls, value: str, info: Any) -> str:
        return require_non_empty_string(value, field_name=info.field_name)


class TriggerResult(DomainModel):
    status: SignalResultStatus
    signal_id: str
    reason: str | None = None
    intent: dict[str, Any] | None = None

    @field_validator("signal_id")
    @classmethod
    def _required_signal_id(cls, value: str) -> str:
        return require_non_empty_string(value, field_name="signal_id")


class StrategyResult(DomainModel):
    status: StrategyResultStatus
    decision: SignalDecision | None = None
    candidate: SignalCandidate | None = None
    reason: str | None = None


_MARKET_DATA_REJECTED_STATUSES = frozenset(
    {
        MarketDataResultStatus.REJECTED_MISSING_IDENTITY,
        MarketDataResultStatus.REJECTED_BAD_TIMESTAMP,
        MarketDataResultStatus.REJECTED_OUT_OF_SESSION,
        MarketDataResultStatus.REJECTED_BAD_PRICE,
        MarketDataResultStatus.REJECTED_NON_MONOTONIC,
    }
)


class FillEvent(DomainModel):
    id: str | None = None
    order_id: str
    account_id: str
    exchange: str
    instrument_id: str
    exchange_report_id: str
    exchange_trade_id: str
    fill_id: str | None = None
    direction: Direction
    offset: Offset
    price: Decimal
    quantity: Decimal
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    fee_source: str | None = None
    traded_at: datetime
    trading_day: date | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price", "quantity", "fee_amount", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="quantity")

    @model_validator(mode="after")
    def _fee_currency_required_when_fee_known(self) -> "FillEvent":
        if self.fee_amount is not None and self.fee_currency is None:
            raise ValueError("fee_currency is required when fee_amount is not None")
        if self.fee_amount is None and self.fee_currency is not None:
            raise ValueError("fee_currency requires fee_amount")
        return self


class Trade(DomainModel):
    id: str | None = None
    account_id: str
    exchange: str
    exchange_trade_id: str
    order_id: str
    instrument_id: str
    direction: Direction
    offset: Offset
    price: Decimal
    quantity: Decimal
    fee_amount: Decimal | None = None
    fee_currency: str | None = None
    fee_source: str | None = None
    trade_time: datetime
    trading_day: date | None = None
    source_exchange_report_id: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price", "quantity", "fee_amount", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="quantity")

    @model_validator(mode="after")
    def _fee_currency_required_when_fee_known(self) -> "Trade":
        if self.fee_amount is not None and self.fee_currency is None:
            raise ValueError("fee_currency is required when fee_amount is not None")
        if self.fee_amount is None and self.fee_currency is not None:
            raise ValueError("fee_currency requires fee_amount")
        return self


class Position(DomainModel):
    id: str | None = None
    account_id: str
    instrument_id: str
    long_today_qty: Decimal = Decimal("0")
    long_yesterday_qty: Decimal = Decimal("0")
    short_today_qty: Decimal = Decimal("0")
    short_yesterday_qty: Decimal = Decimal("0")
    frozen_long_qty: Decimal = Decimal("0")
    frozen_short_qty: Decimal = Decimal("0")
    long_avg_price: Decimal = Decimal("0")
    short_avg_price: Decimal = Decimal("0")
    settlement_price: Decimal = Decimal("0")
    last_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    margin_used: Decimal = Decimal("0")
    version: int = 0
    updated_at: datetime | None = None

    @field_validator(
        "long_today_qty",
        "long_yesterday_qty",
        "short_today_qty",
        "short_yesterday_qty",
        "frozen_long_qty",
        "frozen_short_qty",
        "long_avg_price",
        "short_avg_price",
        "settlement_price",
        "last_price",
        "realized_pnl",
        "unrealized_pnl",
        "margin_used",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class PositionSnapshot(DomainModel):
    account_id: str
    instrument_id: str
    long_today_qty: Decimal
    long_yesterday_qty: Decimal
    short_today_qty: Decimal
    short_yesterday_qty: Decimal
    long_avg_price: Decimal
    short_avg_price: Decimal
    version: int

    @field_validator(
        "long_today_qty",
        "long_yesterday_qty",
        "short_today_qty",
        "short_yesterday_qty",
        "long_avg_price",
        "short_avg_price",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @classmethod
    def from_position(cls, position: Position) -> "PositionSnapshot":
        return cls(
            account_id=position.account_id,
            instrument_id=position.instrument_id,
            long_today_qty=position.long_today_qty,
            long_yesterday_qty=position.long_yesterday_qty,
            short_today_qty=position.short_today_qty,
            short_yesterday_qty=position.short_yesterday_qty,
            long_avg_price=position.long_avg_price,
            short_avg_price=position.short_avg_price,
            version=position.version,
        )


class PositionEvent(DomainModel):
    id: str | None = None
    account_id: str
    instrument_id: str
    exchange: str
    exchange_trade_id: str
    trade_id: str
    position_id: str
    event_type: str
    direction: Direction
    offset: Offset
    price: Decimal
    quantity: Decimal
    before_snapshot: PositionSnapshot
    after_snapshot: PositionSnapshot
    occurred_at: datetime
    created_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("quantity")
    @classmethod
    def _quantity_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="quantity")


class PositionManagerResult(DomainModel):
    status: PositionManagerResultStatus
    position: Position | None = None
    position_event: PositionEvent | None = None
    reason: str | None = None
    trade_id: str | None = None
    account_id: str | None = None
    instrument_id: str | None = None


class MarginRule(DomainModel):
    rule_id: str | None = None
    instrument_id: str
    exchange: str
    contract_multiplier: Decimal
    long_initial_margin_rate: Decimal
    short_initial_margin_rate: Decimal
    long_maintenance_margin_rate: Decimal
    short_maintenance_margin_rate: Decimal
    price_basis: MarginPriceBasis
    price: Decimal | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    rule_version: str | None = None

    @field_validator(
        "contract_multiplier",
        "long_initial_margin_rate",
        "short_initial_margin_rate",
        "long_maintenance_margin_rate",
        "short_maintenance_margin_rate",
        "price",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("contract_multiplier")
    @classmethod
    def _contract_multiplier_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="contract_multiplier")

    @field_validator(
        "long_initial_margin_rate",
        "short_initial_margin_rate",
        "long_maintenance_margin_rate",
        "short_maintenance_margin_rate",
    )
    @classmethod
    def _rates_non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="margin_rate")


class AccountContext(DomainModel):
    account_id: str
    equity: Decimal
    available_cash: Decimal
    frozen_cash: Decimal
    currency: str | None = None
    snapshot_time: datetime

    @field_validator("equity", "available_cash", "frozen_cash", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("available_cash")
    @classmethod
    def _available_cash_non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="available_cash")


class AccountSnapshot(DomainModel):
    id: str | None = None
    account_id: str
    equity: Decimal
    available_cash: Decimal
    margin_used: Decimal
    frozen_margin: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    snapshot_time: datetime

    @field_validator(
        "equity",
        "available_cash",
        "margin_used",
        "frozen_margin",
        "realized_pnl",
        "unrealized_pnl",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("available_cash", "margin_used", "frozen_margin")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="account_snapshot_value")


class MarginRequirement(DomainModel):
    account_id: str
    instrument_id: str
    long_initial_margin: Decimal
    short_initial_margin: Decimal
    total_initial_margin: Decimal
    long_maintenance_margin: Decimal
    short_maintenance_margin: Decimal
    total_maintenance_margin: Decimal
    margin_used: Decimal
    required_cash: Decimal
    is_sufficient: bool
    reason: str | None = None

    @field_validator(
        "long_initial_margin",
        "short_initial_margin",
        "total_initial_margin",
        "long_maintenance_margin",
        "short_maintenance_margin",
        "total_maintenance_margin",
        "margin_used",
        "required_cash",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)


class MarginSnapshot(DomainModel):
    id: str | None = None
    account_id: str
    instrument_id: str
    position_version: int
    rule_id: str | None = None
    rule_version: str | None = None
    calculation_key: str
    long_qty: Decimal
    short_qty: Decimal
    price: Decimal
    contract_multiplier: Decimal
    initial_margin: Decimal
    maintenance_margin: Decimal
    margin_used: Decimal
    available_cash: Decimal
    equity: Decimal
    calculated_at: datetime

    @field_validator(
        "long_qty",
        "short_qty",
        "price",
        "contract_multiplier",
        "initial_margin",
        "maintenance_margin",
        "margin_used",
        "available_cash",
        "equity",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("calculation_key")
    @classmethod
    def _calculation_key_required(cls, value: str) -> str:
        if not value:
            raise ValueError("calculation_key is required")
        return value


class MarginResult(DomainModel):
    status: MarginResultStatus
    requirement: MarginRequirement | None = None
    snapshot: MarginSnapshot | None = None
    reason: str | None = None
    account_id: str | None = None
    instrument_id: str | None = None


class CloseTradeContext(DomainModel):
    account_id: str
    instrument_id: str
    position_version: int
    avg_cost: Decimal
    available_qty: Decimal
    contract_multiplier: Decimal
    context_time: datetime | None = None

    @field_validator("avg_cost", "available_qty", "contract_multiplier", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("avg_cost", "available_qty")
    @classmethod
    def _non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="pnl_context_value")

    @field_validator("contract_multiplier")
    @classmethod
    def _contract_multiplier_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="contract_multiplier")


class RealizedPnL(DomainModel):
    account_id: str
    instrument_id: str
    trade_id: str
    direction: Direction
    offset: Offset
    quantity: Decimal
    close_price: Decimal
    avg_cost: Decimal
    contract_multiplier: Decimal
    gross_realized_pnl: Decimal
    fee_amount: Decimal | None = None
    net_realized_pnl: Decimal | None = None
    currency: str | None = None
    calculated_at: datetime

    @field_validator(
        "quantity",
        "close_price",
        "avg_cost",
        "contract_multiplier",
        "gross_realized_pnl",
        "fee_amount",
        "net_realized_pnl",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("quantity", "contract_multiplier")
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="pnl_positive_value")


class UnrealizedPnL(DomainModel):
    account_id: str
    instrument_id: str
    long_qty: Decimal
    short_qty: Decimal
    long_avg_price: Decimal
    short_avg_price: Decimal
    price_basis: PnLPriceBasis
    mark_price: Decimal
    contract_multiplier: Decimal
    gross_unrealized_pnl: Decimal
    net_unrealized_pnl: Decimal

    @field_validator(
        "long_qty",
        "short_qty",
        "long_avg_price",
        "short_avg_price",
        "mark_price",
        "contract_multiplier",
        "gross_unrealized_pnl",
        "net_unrealized_pnl",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("contract_multiplier")
    @classmethod
    def _contract_multiplier_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="contract_multiplier")


class PnLSnapshot(DomainModel):
    id: str | None = None
    account_id: str
    instrument_id: str
    position_version: int
    trade_id: str | None = None
    margin_snapshot_id: str | None = None
    calculation_key: str
    price_basis: PnLPriceBasis
    mark_price: Decimal
    contract_multiplier: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    fee_amount: Decimal | None = None
    calculated_at: datetime

    @field_validator(
        "mark_price",
        "contract_multiplier",
        "realized_pnl",
        "unrealized_pnl",
        "total_pnl",
        "fee_amount",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        return require_decimal(value)

    @field_validator("contract_multiplier")
    @classmethod
    def _contract_multiplier_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="contract_multiplier")

    @field_validator("calculation_key")
    @classmethod
    def _calculation_key_required(cls, value: str) -> str:
        if not value:
            raise ValueError("calculation_key is required")
        return value


class PnLResult(DomainModel):
    status: PnLResultStatus
    realized: RealizedPnL | None = None
    unrealized: UnrealizedPnL | None = None
    snapshot: PnLSnapshot | None = None
    reason: str | None = None
    account_id: str | None = None
    instrument_id: str | None = None


class SettlementPrice(DomainModel):
    instrument_id: str
    exchange: str
    trading_day: date
    price: Decimal
    source: str | None = None
    received_at: datetime

    @field_validator("price", mode="before")
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("price")
    @classmethod
    def _price_positive(cls, value: Decimal) -> Decimal:
        return require_positive_decimal(value, field_name="settlement_price")


class SettlementContext(DomainModel):
    account_id: str
    trading_day: date
    account_before: AccountContext | AccountSnapshot
    positions: tuple[Position, ...]
    pnl_snapshots: tuple[PnLSnapshot, ...]
    margin_snapshots: tuple[MarginSnapshot, ...]
    settlement_prices: tuple[SettlementPrice, ...]
    calculation_key: str
    settled_at: datetime

    @field_validator("calculation_key")
    @classmethod
    def _calculation_key_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("calculation_key is required")
        return value

    @model_validator(mode="after")
    def _account_identity_matches(self) -> "SettlementContext":
        if self.account_before.account_id != self.account_id:
            raise ValueError("account_before.account_id must match account_id")
        return self


class SettlementSnapshot(DomainModel):
    id: str | None = None
    account_id: str
    trading_day: date
    calculation_key: str
    positions_before: tuple[dict[str, Any], ...]
    positions_after: tuple[dict[str, Any], ...]
    settlement_prices: tuple[dict[str, Any], ...]
    pnl_snapshot_ids: tuple[str, ...]
    margin_snapshot_ids: tuple[str, ...]
    account_snapshot_before_id: str | None = None
    account_snapshot_after_id: str | None = None
    cash_before: Decimal
    cash_after: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    margin_used: Decimal
    status: SettlementResultStatus
    reason: str | None = None
    created_at: datetime

    @field_validator(
        "cash_before",
        "cash_after",
        "realized_pnl",
        "unrealized_pnl",
        "margin_used",
        mode="before",
    )
    @classmethod
    def _decimal_only(cls, value: Any) -> Decimal:
        return require_decimal(value)

    @field_validator("margin_used")
    @classmethod
    def _margin_used_non_negative(cls, value: Decimal) -> Decimal:
        return require_non_negative_decimal(value, field_name="margin_used")

    @field_validator("calculation_key")
    @classmethod
    def _snapshot_calculation_key_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("calculation_key is required")
        return value


class SettlementResult(DomainModel):
    status: SettlementResultStatus
    snapshot: SettlementSnapshot | None = None
    reason: str | None = None
    account_id: str | None = None
    trading_day: date | None = None


class TradingCalendar(DomainModel):
    exchange: str
    trading_day: date
    is_trading_day: bool
    night_session_trading_day: date | None = None
    note: str | None = None


class TradingSession(DomainModel):
    exchange: str
    product_id: str | None = None
    instrument_id: str | None = None
    session_name: str
    start_time: str
    end_time: str
    is_night: bool = False
    effective_from: date | None = None
    effective_to: date | None = None
