from datetime import UTC, datetime

from futures_mvp.modules.ops_safety import (
    MigrationReadinessReport,
    OpsCounters,
    OpsEvent,
    OpsHealthReport,
    OpsIncidentState,
    ReplaySummary,
    SchedulerStatus,
)


def test_structured_event_report_and_counters_build() -> None:
    event = OpsEvent(
        event_type="scheduler_blocked",
        runtime_id="runtime-1",
        stage="market",
        status="PAUSED",
        reason="scheduler is paused",
        correlation_ids=("run-1",),
        timestamp=datetime.now(UTC),
    )
    counters = OpsCounters(conflict_count=1, error_count=2)
    replay = ReplaySummary(dry_run=True, processed_count=3, conflict_count=1)
    scheduler = SchedulerStatus(enabled=True, paused=True, killed=False, running=False)
    health = OpsHealthReport(
        runtime_status="READY",
        incident_state=OpsIncidentState.READY,
        migration_readiness=MigrationReadinessReport(
            compatible=True,
            current_revision="head",
            expected_revision="head",
        ),
        safety_gate_decisions=(),
        counters=counters,
    )

    assert event.event_type == "scheduler_blocked"
    assert counters.conflict_count == 1
    assert replay.dry_run is True
    assert scheduler.paused is True
    assert health.is_ready

