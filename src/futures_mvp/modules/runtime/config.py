from __future__ import annotations

from dataclasses import dataclass, field

from futures_mvp.modules.ops_safety.config import SafetyConfig


class RuntimeConfigError(ValueError):
    """Raised when runtime configuration would not fail closed."""


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool = False
    enabled_jobs: tuple[str, ...] = ()
    schedule_policy: str = "manual"
    max_attempts: int = 1
    retry_backoff_seconds: int = 0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise RuntimeConfigError("scheduler max_attempts must be >= 1")
        if self.retry_backoff_seconds < 0:
            raise RuntimeConfigError("scheduler retry_backoff_seconds must be >= 0")
        if self.enabled and not self.enabled_jobs:
            raise RuntimeConfigError("enabled scheduler requires at least one enabled job")


@dataclass(frozen=True)
class ReplayConfig:
    enabled: bool = False
    default_dry_run: bool = True
    allowed_live_apply_stages: tuple[str, ...] = ()
    stop_on_conflict: bool = True
    batch_size: int = 100

    def __post_init__(self) -> None:
        if self.batch_size < 1:
            raise RuntimeConfigError("replay batch_size must be >= 1")
        if not self.default_dry_run and not self.allowed_live_apply_stages:
            raise RuntimeConfigError("live replay requires explicit allowed_live_apply_stages")


@dataclass(frozen=True)
class RuntimeConfig:
    runtime_id: str
    environment: str
    enable_scheduler: bool = False
    enable_replay: bool = False
    startup_check_timeout_seconds: int = 30
    shutdown_drain_timeout_seconds: int = 30
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    replay: ReplayConfig = field(default_factory=ReplayConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)

    def __post_init__(self) -> None:
        if not self.runtime_id:
            raise RuntimeConfigError("runtime_id is required")
        if not self.environment:
            raise RuntimeConfigError("environment is required")
        if self.startup_check_timeout_seconds < 1:
            raise RuntimeConfigError("startup_check_timeout_seconds must be >= 1")
        if self.shutdown_drain_timeout_seconds < 1:
            raise RuntimeConfigError("shutdown_drain_timeout_seconds must be >= 1")
        if self.enable_scheduler != self.scheduler.enabled:
            raise RuntimeConfigError("enable_scheduler must match scheduler.enabled")
        if self.enable_replay != self.replay.enabled:
            raise RuntimeConfigError("enable_replay must match replay.enabled")
        try:
            self.safety.validate_environment(self.environment)
        except ValueError as exc:
            raise RuntimeConfigError(str(exc)) from exc
