from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from futures_mvp.modules.ops_safety.incident import OpsGateDecision, OpsIncidentState
from futures_mvp.modules.ops_safety.migration import MigrationReadinessReport


@dataclass(frozen=True)
class OpsEvent:
    event_type: str
    runtime_id: str
    status: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    stage: str | None = None
    reason: str | None = None
    correlation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpsCounters:
    conflict_count: int = 0
    error_count: int = 0

    def __post_init__(self) -> None:
        if self.conflict_count < 0:
            raise ValueError("conflict_count must be >= 0")
        if self.error_count < 0:
            raise ValueError("error_count must be >= 0")


@dataclass(frozen=True)
class ReplaySummary:
    dry_run: bool
    live_apply_stages: tuple[str, ...] = ()
    processed_count: int = 0
    duplicate_count: int = 0
    conflict_count: int = 0
    error_count: int = 0
    last_successful_stage: str | None = None
    status: str = "UNKNOWN"
    reason: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("processed_count", self.processed_count),
            ("duplicate_count", self.duplicate_count),
            ("conflict_count", self.conflict_count),
            ("error_count", self.error_count),
        ):
            if value < 0:
                raise ValueError(f"{name} must be >= 0")


@dataclass(frozen=True)
class SchedulerStatus:
    enabled: bool
    paused: bool
    killed: bool
    running: bool
    last_run: datetime | None = None
    last_successful_stage: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class OpsHealthReport:
    runtime_status: str
    incident_state: OpsIncidentState
    migration_readiness: MigrationReadinessReport
    safety_gate_decisions: tuple[OpsGateDecision, ...]
    runtime_health: object | None = None
    counters: OpsCounters = field(default_factory=OpsCounters)

    @property
    def is_ready(self) -> bool:
        return (
            self.runtime_status == "READY"
            and self.incident_state is OpsIncidentState.READY
            and self.migration_readiness.compatible
            and all(decision.allowed for decision in self.safety_gate_decisions)
        )


def incident_state_from_decisions(
    decisions: tuple[OpsGateDecision, ...],
    *,
    migration: MigrationReadinessReport,
    runtime_status: str,
) -> OpsIncidentState:
    if any(decision.incident_state is OpsIncidentState.KILLED for decision in decisions):
        return OpsIncidentState.KILLED
    if any(decision.incident_state is OpsIncidentState.PAUSED for decision in decisions):
        return OpsIncidentState.PAUSED
    if not migration.compatible or runtime_status == "FAILED":
        return OpsIncidentState.FAILED
    if runtime_status == "DEGRADED":
        return OpsIncidentState.DEGRADED
    return OpsIncidentState.READY
