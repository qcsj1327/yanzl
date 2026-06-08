from futures_mvp.modules.ops_safety import (
    KillSwitchConfig,
    MigrationReadinessConfig,
    MigrationReadinessReport,
    SafetyConfig,
)
from futures_mvp.modules.runtime import (
    ReplayConfig,
    ReplayStage,
    ReplayStatus,
    RuntimeHealthCheck,
    RuntimeHealthReport,
    RuntimeHealthStatus,
    RuntimeJob,
    RuntimeLifecycleManager,
    RuntimeReplayCoordinator,
    RuntimeSchedulerRunResult,
    RuntimeSchedulerRunStatus,
    SchedulerConfig,
    build_scheduler,
)


class FakeScheduler:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True
        self._events.append("scheduler_start")

    def stop(self) -> None:
        self._running = False

    def run_once(self, job_name: str) -> object | None:
        del job_name
        return None


class FakeGraph:
    def validate_required_services(self) -> bool:
        return True


def _ready_report() -> RuntimeHealthReport:
    return RuntimeHealthReport(
        status=RuntimeHealthStatus.READY,
        checks=(RuntimeHealthCheck(name="test", status=RuntimeHealthStatus.READY),),
    )


def _migration(compatible: bool) -> MigrationReadinessReport:
    return MigrationReadinessReport(
        compatible=compatible,
        current_revision="head" if compatible else "old",
        expected_revision="head",
        reason=None if compatible else "db migration revision is incompatible",
    )


def test_kill_switch_blocks_scheduler_startup() -> None:
    events: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(events),
        health_check=_ready_report,
        safety_config=SafetyConfig(
            kill_switch=KillSwitchConfig(global_kill_switch=True),
        ),
        migration_readiness_check=lambda: _migration(True),
    )

    state = manager.startup()

    assert events == []
    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.FAILED
    assert state.ops_health is not None
    assert state.ops_health.incident_state.value == "KILLED"


def test_migration_mismatch_is_failed_and_scheduler_not_started() -> None:
    events: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(events),
        health_check=_ready_report,
        migration_readiness_check=lambda: _migration(False),
    )

    state = manager.startup()

    assert events == []
    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.FAILED
    assert [event.name for event in state.events][-1] == "health_not_ready"


def test_migration_enabled_missing_checker_fails_closed() -> None:
    events: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(events),
        health_check=_ready_report,
        safety_config=SafetyConfig(
            migration_readiness=MigrationReadinessConfig(
                enabled=True,
                expected_revision="head",
            )
        ),
    )

    state = manager.startup()

    assert events == []
    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.FAILED
    assert state.health.checks[0].reason == "migration_readiness_checker_missing"
    assert state.ops_health is not None
    assert state.ops_health.incident_state.value == "FAILED"
    assert state.ops_health.migration_readiness.compatible is False


def test_migration_disabled_missing_checker_can_start_scheduler() -> None:
    events: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(events),
        health_check=_ready_report,
    )

    state = manager.startup()

    assert events == ["scheduler_start"]
    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.READY
    assert state.ops_health is not None
    assert state.ops_health.migration_readiness.compatible is True
    assert state.ops_health.migration_readiness.reason == "migration readiness check disabled"


def test_migration_enabled_checker_compatible_can_start_scheduler() -> None:
    events: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(events),
        health_check=_ready_report,
        safety_config=SafetyConfig(
            migration_readiness=MigrationReadinessConfig(
                enabled=True,
                expected_revision="head",
            )
        ),
        migration_readiness_check=lambda: _migration(True),
    )

    state = manager.startup()

    assert events == ["scheduler_start"]
    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.READY
    assert state.ops_health is not None
    assert state.ops_health.migration_readiness.compatible is True


def test_migration_enabled_checker_incompatible_fails_and_scheduler_not_started() -> None:
    events: list[str] = []
    manager = RuntimeLifecycleManager(
        graph_builder=lambda: FakeGraph(),  # type: ignore[arg-type,return-value]
        scheduler=FakeScheduler(events),
        health_check=_ready_report,
        safety_config=SafetyConfig(
            migration_readiness=MigrationReadinessConfig(
                enabled=True,
                expected_revision="head",
            )
        ),
        migration_readiness_check=lambda: _migration(False),
    )

    state = manager.startup()

    assert events == []
    assert state.health is not None
    assert state.health.status is RuntimeHealthStatus.FAILED
    assert state.ops_health is not None
    assert state.ops_health.incident_state.value == "FAILED"


def test_scheduler_pause_makes_scheduler_noop() -> None:
    calls: list[str] = []
    scheduler = build_scheduler(
        SchedulerConfig(enabled=True, enabled_jobs=("market",)),
        jobs=(RuntimeJob(name="market", callable=lambda: calls.append("called")),),
        safety_config=SafetyConfig(kill_switch=KillSwitchConfig(scheduler_paused=True)),
    )

    scheduler.start()
    result = scheduler.run_once("market")

    assert calls == []
    assert isinstance(result, RuntimeSchedulerRunResult)
    assert result.status is RuntimeSchedulerRunStatus.PAUSED


def test_replay_pause_makes_replay_noop() -> None:
    calls: list[str] = []
    coordinator = RuntimeReplayCoordinator(
        ReplayConfig(enabled=True),
        (ReplayStage(name="market", callable=lambda context: calls.append(context.stage_name)),),
        safety_config=SafetyConfig(kill_switch=KillSwitchConfig(replay_paused=True)),
    )

    result = coordinator.replay()

    assert calls == []
    assert result.status is ReplayStatus.PAUSED


def test_stage_kill_switch_blocks_replay_stage() -> None:
    calls: list[str] = []
    coordinator = RuntimeReplayCoordinator(
        ReplayConfig(enabled=True),
        (
            ReplayStage(name="market", callable=lambda context: calls.append(context.stage_name)),
            ReplayStage(name="feature", callable=lambda context: calls.append(context.stage_name)),
        ),
        safety_config=SafetyConfig(
            kill_switch=KillSwitchConfig(per_stage_kill_switches=("market",)),
        ),
    )

    result = coordinator.replay()

    assert calls == []
    assert result.status is ReplayStatus.PAUSED
    assert result.stage_results[0].stage_name == "market"
    assert result.stage_results[0].reason == "stage kill switch is active"
