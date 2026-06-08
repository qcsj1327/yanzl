from __future__ import annotations

from dataclasses import dataclass, field


class SafetyConfigError(ValueError):
    """Raised when operations safety config would not fail closed."""


DEFAULT_KNOWN_ENVIRONMENTS = ("local", "test", "paper", "sim", "production")


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
class SafetyConfig:
    kill_switch: KillSwitchConfig = field(default_factory=KillSwitchConfig)
    live_gate: LiveGateConfig = field(default_factory=LiveGateConfig)
    migration_readiness: MigrationReadinessConfig = field(
        default_factory=MigrationReadinessConfig
    )
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    known_environments: tuple[str, ...] = DEFAULT_KNOWN_ENVIRONMENTS
    production_explicit: bool = False

    def __post_init__(self) -> None:
        _reject_empty_names(self.known_environments, "known_environments")

    def validate_environment(self, environment: str) -> None:
        if environment not in self.known_environments:
            raise SafetyConfigError(f"unknown runtime environment: {environment}")
        if environment == "production" and not self.production_explicit:
            raise SafetyConfigError("production environment requires explicit production flags")


def _reject_empty_names(values: tuple[str, ...], field_name: str) -> None:
    if any(not value for value in values):
        raise SafetyConfigError(f"{field_name} cannot contain empty values")

