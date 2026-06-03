from dataclasses import dataclass, field
from decimal import Decimal

from futures_mvp.domain.enums import Offset, RiskDecision
from futures_mvp.domain.models import RiskResult, Signal
from futures_mvp.modules.risk.errors import RiskConfigurationError


@dataclass(frozen=True)
class RiskConfig:
    disabled_instruments: set[str] = field(default_factory=set)
    max_order_quantity: Decimal | None = None
    max_notional: Decimal | None = None
    contract_multiplier_by_instrument: dict[str, Decimal] = field(default_factory=dict)
    limit_up_by_instrument: dict[str, Decimal] = field(default_factory=dict)
    limit_down_by_instrument: dict[str, Decimal] = field(default_factory=dict)
    is_trading_session_allowed: bool = True
    allowed_offsets: set[Offset] = field(default_factory=lambda: set(Offset))
    available_margin: Decimal | None = None
    required_margin: Decimal | None = None
    current_position: Decimal | None = None
    projected_position: Decimal | None = None
    max_position: Decimal | None = None

    def __post_init__(self) -> None:
        _require_decimal_or_none("max_order_quantity", self.max_order_quantity)
        _require_decimal_or_none("max_notional", self.max_notional)
        _require_decimal_map(
            "contract_multiplier_by_instrument",
            self.contract_multiplier_by_instrument,
        )
        _require_decimal_map("limit_up_by_instrument", self.limit_up_by_instrument)
        _require_decimal_map("limit_down_by_instrument", self.limit_down_by_instrument)
        _require_decimal_or_none("available_margin", self.available_margin)
        _require_decimal_or_none("required_margin", self.required_margin)
        _require_decimal_or_none("current_position", self.current_position)
        _require_decimal_or_none("projected_position", self.projected_position)
        _require_decimal_or_none("max_position", self.max_position)


class PureFuturesRiskEngine:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()

    def check_order(self, signal: Signal) -> RiskResult:
        _require_signal_decimals(signal)
        self._validate_cross_field_config(signal)

        if signal.instrument_id in self._config.disabled_instruments:
            return _rejected("disabled_instrument", "instrument is disabled")

        if not self._config.is_trading_session_allowed:
            return _rejected("trading_session_closed", "trading session is closed")

        if signal.offset not in self._config.allowed_offsets:
            return _rejected("offset_not_allowed", "offset is not allowed")

        if (
            self._config.max_order_quantity is not None
            and signal.quantity > self._config.max_order_quantity
        ):
            return _rejected("max_order_quantity", "quantity exceeds max_order_quantity")

        limit_up = self._config.limit_up_by_instrument.get(signal.instrument_id)
        if limit_up is not None and signal.limit_price > limit_up:
            return _rejected("price_limit_up", "limit_price is above limit_up")

        limit_down = self._config.limit_down_by_instrument.get(signal.instrument_id)
        if limit_down is not None and signal.limit_price < limit_down:
            return _rejected("price_limit_down", "limit_price is below limit_down")

        if self._config.max_notional is not None:
            multiplier = self._config.contract_multiplier_by_instrument.get(signal.instrument_id)
            if multiplier is None:
                raise RiskConfigurationError("max_notional requires contract multiplier")
            notional = signal.limit_price * signal.quantity * multiplier
            if notional > self._config.max_notional:
                return _rejected("max_notional", "notional exceeds max_notional")

        if (
            self._config.available_margin is not None
            and self._config.required_margin is not None
            and self._config.available_margin < self._config.required_margin
        ):
            return _rejected("margin_insufficient", "available_margin is below required_margin")

        if (
            self._config.projected_position is not None
            and self._config.max_position is not None
            and self._config.projected_position > self._config.max_position
        ):
            return _rejected("max_position", "projected_position exceeds max_position")

        return RiskResult(
            decision=RiskDecision.ACCEPTED,
            rule_name="all_pass",
            reason=None,
        )

    def _validate_cross_field_config(self, signal: Signal) -> None:
        if self._config.max_notional is not None and (
            signal.instrument_id not in self._config.contract_multiplier_by_instrument
        ):
            raise RiskConfigurationError("max_notional requires contract multiplier")

        margin_values = (self._config.available_margin, self._config.required_margin)
        if (margin_values[0] is None) != (margin_values[1] is None):
            raise RiskConfigurationError(
                "available_margin and required_margin must be provided together"
            )

        position_values = (self._config.projected_position, self._config.max_position)
        if (position_values[0] is None) != (position_values[1] is None):
            raise RiskConfigurationError(
                "projected_position and max_position must be provided together"
            )


def _rejected(rule_name: str, reason: str) -> RiskResult:
    return RiskResult(
        decision=RiskDecision.REJECTED,
        rule_name=rule_name,
        reason=reason,
    )


def _require_signal_decimals(signal: Signal) -> None:
    _require_decimal("signal.limit_price", signal.limit_price)
    _require_decimal("signal.quantity", signal.quantity)


def _require_decimal_map(name: str, values: dict[str, Decimal]) -> None:
    for key, value in values.items():
        _require_decimal(f"{name}[{key!r}]", value)


def _require_decimal_or_none(name: str, value: Decimal | None) -> None:
    if value is not None:
        _require_decimal(name, value)


def _require_decimal(name: str, value: object) -> None:
    if not isinstance(value, Decimal):
        raise RiskConfigurationError(f"{name} must be Decimal")
