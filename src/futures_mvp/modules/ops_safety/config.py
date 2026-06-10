from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class SafetyConfigError(ValueError):
    """Raised when operations safety config would not fail closed."""


DEFAULT_KNOWN_ENVIRONMENTS = ("local", "test", "paper", "sim", "production")


class RolloutMode(StrEnum):
    PAPER = "PAPER"
    SIM = "SIM"
    LIVE = "LIVE"


@dataclass(frozen=True)
class KillSwitchConfig:
    global_kill_switch: bool = False
    per_stage_kill_switches: tuple[str, ...] = ()
    scheduler_paused: bool = False
    replay_paused: bool = False

    def __post_init__(self) -> None:
        _reject_empty_names(self.per_stage_kill_switches, "per_stage_kill_switches")


@dataclass(frozen=True)
class LiveGateConfig:
    broker_enabled: bool = False
    live_submit_enabled: bool = False
    explicit_live_flag: bool = False
    broker_credentials_handle: str | None = None

    def __post_init__(self) -> None:
        if self.broker_credentials_handle is not None and not self.broker_credentials_handle:
            raise SafetyConfigError("broker_credentials_handle cannot be empty")


@dataclass(frozen=True)
class MigrationReadinessConfig:
    enabled: bool = False
    expected_revision: str | None = None
    compatible_revisions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.enabled and not self.expected_revision and not self.compatible_revisions:
            raise SafetyConfigError(
                "enabled migration readiness requires expected_revision or compatible_revisions"
            )
        if self.expected_revision is not None and not self.expected_revision:
            raise SafetyConfigError("expected_revision cannot be empty")
        _reject_empty_names(self.compatible_revisions, "compatible_revisions")


@dataclass(frozen=True)
class ObservabilityConfig:
    enabled: bool = True
    structured_events_enabled: bool = True


@dataclass(frozen=True)
class CapitalControlConfig:
    max_order_size: Decimal | None = None
    max_position_size: Decimal | None = None
    max_daily_loss: Decimal | None = None
    account_whitelist: tuple[str, ...] = ()
    allowed_instruments: tuple[str, ...] = ()
    allow_empty_account_whitelist_in_non_live: bool = True
    allow_empty_instrument_whitelist_in_non_live: bool = True

    def __post_init__(self) -> None:
        _require_decimal_or_none("max_order_size", self.max_order_size)
        _require_decimal_or_none("max_position_size", self.max_position_size)
        _require_decimal_or_none("max_daily_loss", self.max_daily_loss)
        _reject_empty_names(self.account_whitelist, "account_whitelist")
        _reject_empty_names(self.allowed_instruments, "allowed_instruments")


@dataclass(frozen=True)
class RolloutConfig:
    mode: RolloutMode = RolloutMode.PAPER
    previous_mode: RolloutMode | None = None
    requested_mode: RolloutMode | None = None
    capital_controls: CapitalControlConfig = field(default_factory=CapitalControlConfig)

    def __post_init__(self) -> None:
        if self.previous_mode is not None and self.previous_mode == self.mode:
            raise SafetyConfigError("previous_mode must differ from active rollout mode")


@dataclass(frozen=True)
class SafetyConfig:
    kill_switch: KillSwitchConfig = field(default_factory=KillSwitchConfig)
    live_gate: LiveGateConfig = field(default_factory=LiveGateConfig)
    rollout: RolloutConfig = field(default_factory=RolloutConfig)
    migration_readiness: MigrationReadinessConfig = field(
        default_factory=MigrationReadinessConfig
    )
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    known_environments: tuple[str, ...] = DEFAULT_KNOWN_ENVIRONMENTS
    production_explicit: bool = False

    def __post_init__(self) -> None:
        _reject_empty_names(self.known_environments, "known_environments")
        if self.rollout.mode is RolloutMode.LIVE and not self.live_gate.broker_enabled:
            raise SafetyConfigError("LIVE rollout mode requires broker_enabled")

    def validate_environment(self, environment: str) -> None:
        if environment not in self.known_environments:
            raise SafetyConfigError(f"unknown runtime environment: {environment}")
        if environment == "production" and not self.production_explicit:
            raise SafetyConfigError("production environment requires explicit production flags")


def _reject_empty_names(values: tuple[str, ...], field_name: str) -> None:
    if any(not value for value in values):
        raise SafetyConfigError(f"{field_name} cannot contain empty values")


def _require_decimal_or_none(field_name: str, value: Decimal | None) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal):
        raise SafetyConfigError(f"{field_name} must be Decimal")
    if value < 0:
        raise SafetyConfigError(f"{field_name} must be >= 0")
